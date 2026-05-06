"""
Time Logging AI Assistant - POC Backend
FastAPI server with Claude-powered conversational timesheet assistant.
Google SSO authentication.
"""

import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import anthropic
import httpx
import uvicorn
from authlib.integrations.starlette_client import OAuth
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

import calendar_sync
import drive_sync
import gmail_sync
import harvest_api
import harvest_mock
import harvest_oauth
import rate_limit
import sheets_sync
import tasks
import tasks_routes
import time_utils
import training_log
import user_profiles
from project_mapping import (
    get_all_projects_for_prompt,
    get_all_projects_for_prompt_async,
    get_projects,
)

# --- Sentry (optional — no-op when SENTRY_DSN is not configured) ---
_SENTRY_DSN = os.getenv("SENTRY_DSN", "").strip()
if _SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        sentry_sdk.init(
            dsn=_SENTRY_DSN,
            integrations=[FastApiIntegration()],
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE", "0.1")),
            environment=os.getenv("SENTRY_ENV", "production"),
            send_default_pii=False,  # never send request bodies / cookies
        )
        print(f"[OK] Sentry initialized (env={os.getenv('SENTRY_ENV', 'production')})")
    except Exception as e:
        print(f"[WARN] Sentry init failed: {e}")
else:
    sentry_sdk = None  # type: ignore[assignment]

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# --- Phase 2 Task Management (LOCAL ONLY — gated behind LOCAL_DEMO_ONLY=1) ---
LOCAL_DEMO_ONLY = os.getenv("LOCAL_DEMO_ONLY", "").strip() == "1"

# Process boot timestamp — used by /health to report uptime.
_BOOT_TS = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan handler: runs once on startup before serving requests
    and once on shutdown. Replaces the deprecated @app.on_event decorators."""
    if LOCAL_DEMO_ONLY:
        # Local demo uses in-memory storage so seed data is deterministic and
        # doesn't collide with any stale rows in Supabase.
        tasks._use_memory = True
        tasks._supabase_available = False
        tasks._in_memory_tasks.clear()
        tasks.seed_tasks()
        print(f"[OK] Seeded {len(tasks.get_all_tasks())} tasks across {len(tasks.PROJECTS)} initiatives")

    # Pre-warm Harvest projects/users cache if a service PAT is configured.
    # Uses the async fetch so the lifespan handler completes promptly even on
    # a slow connection. If pre-warm returns 0 projects (PAT 401 or wrong
    # account), we kick off a background retry that reattempts every 60s
    # until the cache is populated — that way the first real user doesn't
    # eat the cold-fetch cost on a worker where pre-warm initially failed.
    if harvest_api.is_configured():
        try:
            projects = await harvest_api.get_projects_with_tasks_async()
            users = harvest_api.get_users()
            print(f"[OK] Pre-warmed Harvest cache: {len(projects)} projects, {len(users)} users")
            if not projects:
                asyncio.create_task(_harvest_warmup_retry())
        except Exception as e:
            print(f"[WARN] Harvest pre-warm skipped: {e}")
            asyncio.create_task(_harvest_warmup_retry())
    else:
        print("[INFO] No Harvest PAT — first user will pay cold-start cost")

    yield
    # No shutdown work yet; uvicorn handles graceful socket close.


async def _harvest_warmup_retry() -> None:
    """Background task: keep retrying the Harvest project pre-warm every 60s
    until we get at least 1 project cached. Stops once cache is populated.
    Bounded to 30 attempts (30 minutes) so we don't loop forever on a
    permanently-broken PAT."""
    for attempt in range(30):
        await asyncio.sleep(60)
        try:
            projects = await harvest_api.get_projects_with_tasks_async()
            if projects:
                print(f"[OK] Harvest warmup retry succeeded on attempt {attempt + 1}: {len(projects)} projects cached")
                return
            print(f"[INFO] Harvest warmup retry {attempt + 1}/30 returned 0 projects")
        except Exception as e:
            print(f"[WARN] Harvest warmup retry {attempt + 1}/30 failed: {e}")
    print("[WARN] Harvest warmup giving up after 30 attempts")


async def _prewarm_harvest_cache(access_token: str) -> None:
    """Background task fired after a user completes Harvest OAuth. Populates
    the global project cache with their token so the first chat message
    doesn't pay the cold-fetch cost. All Thrive users share the same
    project list (account-wide), so this benefits everyone."""
    try:
        t0 = time.time()
        projects = await harvest_api.get_projects_with_tasks_async(access_token)
        elapsed_ms = int((time.time() - t0) * 1000)
        print(
            f"[OK] Harvest cache pre-warmed via OAuth: "
            f"{len(projects)} projects in {elapsed_ms}ms"
        )
    except Exception as e:
        print(f"[WARN] Harvest OAuth pre-warm failed: {e}")


app = FastAPI(title="Timesheet Assistant POC", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "timesheet-poc-secret-key-2026"),
)
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Serve /static (logo + future asset bundle).
from fastapi.staticfiles import StaticFiles
_static_dir = BASE_DIR / "static"
_static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


# Google OAuth
oauth = OAuth()
oauth.register(
    name="google",
    client_id=os.getenv("GOOGLE_CLIENT_ID", ""),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET", ""),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={
        "scope": "openid email profile https://www.googleapis.com/auth/calendar.readonly https://www.googleapis.com/auth/drive.metadata.readonly https://www.googleapis.com/auth/gmail.readonly",
    },
)

# Harvest OAuth (optional - falls back to PAT if not configured)
oauth.register(
    name="harvest",
    client_id=os.getenv("HARVEST_CLIENT_ID", ""),
    client_secret=os.getenv("HARVEST_CLIENT_SECRET", ""),
    access_token_url="https://id.getharvest.com/api/v2/oauth2/token",
    authorize_url="https://id.getharvest.com/oauth2/authorize",
    client_kwargs={
        # Harvest expects client credentials in token POST body.
        "token_endpoint_auth_method": "client_secret_post",
    },
)

# 30s per-request timeout — prevents a hung Anthropic call from holding a
# uvicorn worker forever during stress test concurrency.
# max_retries=0 — disable the SDK's default retry-twice behavior, which
# stacks to 90+ seconds on a Cloudflare-blocked request and blows past
# Render's 60s edge proxy timeout (returning 502 HTML to the browser).
# We'd rather fail fast in <30s and let our graceful classifier surface a
# clean error to the user.
#
# ANTHROPIC_BASE_URL — when set, routes every SDK call through a Cloudflare
# Worker proxy (poc/worker/anthropic-proxy.js). This sidesteps Render's
# free-tier outbound IPs being on Cloudflare's bot-challenge list. The
# Worker validates ANTHROPIC_PROXY_SECRET before forwarding to Anthropic.
# When neither env var is set, the SDK calls api.anthropic.com directly —
# so local dev and any future VPS deploy keep working without changes.
_anthropic_kwargs = {
    "api_key": os.getenv("ANTHROPIC_API_KEY"),
    "timeout": 30.0,
    "max_retries": 0,
}
_anthropic_base_url = os.getenv("ANTHROPIC_BASE_URL", "").strip().rstrip("/")
if _anthropic_base_url:
    # Defensive: the env var is sometimes pasted without a scheme (e.g.
    # "anthropic-proxy.foo.workers.dev"). httpx then fails with a cryptic
    # APIConnectionError instead of a clear URL parse error. Auto-prepend
    # https:// if missing.
    if not _anthropic_base_url.startswith(("http://", "https://")):
        _anthropic_base_url = f"https://{_anthropic_base_url}"
    _anthropic_kwargs["base_url"] = _anthropic_base_url
    _proxy_secret = os.getenv("ANTHROPIC_PROXY_SECRET", "").strip()
    if _proxy_secret:
        _anthropic_kwargs["default_headers"] = {"x-proxy-secret": _proxy_secret}
    print(f"[INFO] Anthropic SDK routed through proxy: {_anthropic_base_url}")
client = anthropic.AsyncAnthropic(**_anthropic_kwargs)

CHAT_MODEL = "claude-haiku-4-5-20251001"


def _user_friendly_anthropic_error(exc: Exception) -> str:
    """Classify an Anthropic SDK exception and return a clean user-facing
    message. Critically: detects Cloudflare bot-challenge HTML (which the
    SDK can't parse and lets bubble up as a JSON-decode failure) and shows
    a helpful message instead of dumping HTML into the chat bubble."""
    msg = str(exc)
    lower = msg.lower()

    # Cloudflare managed challenge: api.anthropic.com is treating our outbound
    # IP as bot-like and serving the JS challenge page in place of the API
    # response. Render free tier shares outbound IPs and this can happen if a
    # neighboring tenant misbehaves. Restarting the Render worker often helps
    # by landing the process on a different IP from the pool.
    if "just a moment" in lower or "challenge-platform" in lower or "<!doctype html" in lower:
        return (
            "Our AI service is temporarily unreachable from this server. "
            "Network protection is challenging the request — usually clears "
            "in a few minutes. Please try again shortly."
        )

    err_type = type(exc).__name__
    if err_type in ("APIConnectionError", "APIConnectionTimeoutError", "APITimeoutError"):
        return "Couldn't reach the AI service (network issue). Please try again."
    if err_type == "RateLimitError":
        return "AI service is rate-limited right now. Please wait 30s and retry."
    if err_type == "AuthenticationError":
        return "AI service authentication failed. Please contact your admin."
    if err_type in ("APIStatusError", "BadRequestError"):
        # API returned a structured error — show a short version
        return f"AI service rejected the request: {msg[:140]}"
    if err_type == "InternalServerError":
        return "AI service is having an issue right now. Please try again in a minute."
    return "Something went wrong reaching the AI service. Please try again."

PILOT_USERS = ["Tariq Munir", "Malik Amin", "Jawad Saleem"]

SYSTEM_PROMPT_TEMPLATE = """You are a friendly, efficient timesheet assistant for a PR and communications agency based in Australia/New Zealand. Users tell you what they worked on in natural language (voice or text), and you help log their time into Harvest.

IMPORTANT — Harvest structure:
- Each "Project" below is a client/project (e.g. Acuity, Afterpay).
- Under each project are specific TASKS (e.g. "Existing Business Growth FY26").
- When logging time, you MUST identify both the project AND the specific task.

Your conversation flow:
1. Listen to what the user says they worked on.
2. Identify the project. If unclear, ask which project.
3. Once you know the project, present the available tasks for that project and ask which one. List them as numbered options so the user can just reply with a number.
4. If the user already mentioned enough detail to match a specific task, skip asking and confirm instead.
5. Ask for duration if not mentioned.
6. When you have project + task + hours, log the entry.

Example flow:
- User: "Spent 2 hours on Acuity stuff"
- You: "No worries! Which Acuity task was this for?
  1. Existing Business Growth FY26
  2. New Business Growth FY26
  3. Operations & Admin FY26"
- User: "1"
- You: "Got it — 2 hours on Acuity, Existing Business Growth FY26. Logging that now." [creates entry]

Rules:
- Minimum time block is 5 minutes (0.08 hours). Round up to nearest 5 minutes.
- Default date is today ({{today_display}}) unless the user specifies otherwise.
- Use DD/MM/YYYY date format (Australian standard).
- Understand AU/NZ English: "arvo" = afternoon, "brekkie" = breakfast, "reckon" = think, "heaps" = a lot, "keen" = eager, "no worries" = understood, "suss out" = investigate.
- When a user mentions multiple items, handle each one separately.
- If they don't mention duration, ask "How long did you spend on that?"
- Be warm and professional. Use first names.
- Ask as many clarifying questions as needed to get the right project, task, and hours. Never guess.

Disambiguation list rules (CRITICAL — production observation: long lists cause misclicks. Miles picked option 3, then said "amend that to 6" because the list was 13 items long):
- NEVER show more than 5 options when asking the user to pick a project or task. If the natural list is longer, prune to the top 5.
- Pruning priority order: (1) tasks listed in this user's Top tasks (last 30d) from their profile, (2) tasks with names that share keywords with what the user just said, (3) the user's Assigned projects only (skip projects they're not on). After applying these, take the top 5.
- After the 5 options, add a short "Or tell me which one if it's not in this list" line so the user can free-text instead of being trapped in the menu.
- When the user replies to a numbered list with what looks like a NEW topic ("Thrive admin" after you asked which project for Sydney WIP), DO NOT silently treat it as a fresh entry. First confirm: "Was that for the Sydney WIP I asked about, or a separate item?"
- When you ask "which task under Project X?" and the user replies with the name of a different project, ask once: "Did you mean a task under [different project] instead of [original project]?" before reframing the entry.

When you're ready to log an entry, include this exact JSON format in your response (the system will parse it):
```ENTRY
{{{{
  "client": "Project Name",
  "project_code": "TASK-CODE",
  "project_name": "Task Name",
  "task": "Task Name",
  "hours": 1.5,
  "notes": "Description of work done",
  "date": "YYYY-MM-DD",
  "status": "Draft"
}}}}
```

Field mapping:
- "client" = the project name (e.g. "Acuity", "Afterpay")
- "project_code" = the task code (e.g. "6-1000", "2-1099")
- "project_name" = the task name (e.g. "Existing Business Growth FY26")
- "task" = same as project_name for now

If confidence is low, set status to "Needs Review" instead of "Draft".

You can log multiple entries in one response — just include multiple ```ENTRY blocks.

Available tools:
You have access to these tools to scan the user's Google Workspace data:
- scan_emails: Search Gmail for email activity. Filter by date range, sender, recipient, CC, subject, or keyword. Returns metadata only (subject, sender, recipients, timestamps) — never email body content.
- scan_calendar: Fetch Google Calendar events for a date or date range. Returns event titles, times, durations, and attendees.
- scan_drive: Fetch Google Drive file activity for a date or date range. Returns file names, types, and modification times — no file content.

When to use tools:
- When the user says "check my emails", "scan my emails", "what meetings did I have", "scan my drive", etc. — use the appropriate tool.
- When the user says "what did I work on last week" or similar — use ALL THREE tools for the date range to build a full picture.
- When the user mentions a specific person or email address, use scan_emails with a sender/recipient filter.
- You can call multiple tools at once if needed (e.g., emails + calendar for a complete picture).
- After receiving tool results, analyse the data and suggest time entries mapped to Harvest projects.
- Always ask clarifying questions if you can't confidently map activities to projects.

Date handling:
- Today's date is {{today_iso}} ({{today_day}}).
- For "last week", calculate Monday to Friday of the previous week.
- For "this week", calculate Monday of the current week to today.
- For "last month", use the 1st of the previous month to the last day of that month.
- For "this month", use the 1st of the current month to today.
- Always pass dates in YYYY-MM-DD format to tools.

Privacy: You only receive email metadata (subject lines, sender, recipients, timestamps). You never see email body content. This is by design for Australian privacy compliance.

REFERENCE — AU/NZ vocabulary you may encounter (full list, do not ask the user to repeat):
- Time-of-day: "arvo" = afternoon, "this morning" = before 12pm, "this avo" = afternoon, "tonight" = after 5pm, "knock-off" = end of work day, "smoko" = short break, "brekkie" = breakfast, "lunch" = midday meal/break.
- Quantifiers: "heaps" = a lot, "loads" = a lot, "a fair bit" = a moderate amount, "a tick" = a small amount, "ages" = a long time, "yonks" = a long time, "five mins" = 5 min, "half an hour" = 30 min, "couple of hours" = ~2h, "a few hours" = 2-3h.
- Acknowledgement / status: "no worries" = OK, "no dramas" = OK, "all good" = confirmed, "all sorted" = done, "she'll be right" = it's fine, "sweet" = OK (informal), "cheers" = thanks/bye, "ta" = thanks, "yeah nah" = no (NZ), "nah yeah" = yes (NZ), "chur" = cheers (NZ), "stoked" = pleased (NZ), "sweet as" = great (NZ).
- Project verbs: "bash out" = produce quickly, "knock together" = assemble, "smash" = complete intensively, "run point on" = lead, "suss out" = investigate, "chase up" = follow up on, "have a crack at" = attempt, "deep dive on" = research thoroughly.
- People / org: "the team" = colleagues, "the higher-ups" = leadership, "client-side" = at the client, "agency-side" = internal, "biz dev" = business development, "pitch" = new business proposal, "deck" = presentation slides.

REFERENCE — common time-entry phrasings → expected interpretation (use these as anchor patterns; users will phrase things differently but the structure tends to repeat):
- "Spent X hours on [client]" → ask which task under that client.
- "[Client] [task-keyword] for X hours" → match task by keyword, confirm if ambiguous.
- "Had a [client] catch-up / standup / call" → likely Internal-style task or that client's retainer task; ask if unsure.
- "Worked on [client] all morning/arvo/day" → estimate 4h / 4h / 8h respectively; confirm with user before logging.
- "Bit of [client] this morning" → small block (~30-60 min); ask for duration.
- "[Project] then [project] then [project]" → multiple separate entries, ask for duration of each unless mentioned.
- "Same as yesterday" / "usual stuff" → check the user's recent_entries_summary in their profile (if shown) for pattern, otherwise ask.

REFERENCE — disambiguation rules (apply in order):
1. If the user's profile shows ASSIGNED HARVEST PROJECTS, prefer those when a phrase could match multiple clients.
2. If the user has a RECENT CORRECTIONS entry that matches the current phrase, follow the correction's "correct" mapping. Never repeat the original (wrong) mapping.
3. If the user has TOP TASKS in their profile, prefer those for ambiguous task selection.
4. If still ambiguous, list the candidates as numbered options and ask the user to pick a number.
5. NEVER guess silently. Confidence-low entries should have status="Needs Review" not "Draft".

REFERENCE — self-consistency & data-trust rules (CRITICAL — production observation: when raw Harvest data conflicts with your own reasoning, you tend to flap between trusting the data and trusting your reasoning across turns. These rules anchor you to a single behaviour):

1. **Persistent in-conversation flags.** Once you flag a project-task pairing as suspicious in this conversation (e.g., "Acuity New Growth - BYD" appearing under "Acuity - DENZA NZ B8 Press Loan"), it stays flagged for the entire session. NEVER re-present that exact pairing as a clean option in a later turn, even if the system data still lists it. Track these mentally as the conversation progresses.

2. **Pre-screen tasks at list time.** When you re-list project tasks because the user asked "what tasks are under [project]?", first scan for tasks whose name contains a brand, client or product that conflicts with the project's name (e.g., a task containing "BYD" under a "DENZA" project, or "Afterpay" under an "Acuity" project). When you spot one, mark it inline as `[likely misassigned in Harvest — confirm with admin]` rather than presenting it as a normal numbered option.

3. **When a user pushes back on a previous claim** (e.g. "why did u show me X if it doesn't fit?", "but you just said X was wrong"), follow this three-step pattern in order, in ONE short response:
   (a) Brief acknowledgement + apology — one line, no over-explanation.
   (b) Drop the disputed item from your working set for the rest of the conversation.
   (c) Re-ask your last clarification with the bad option REMOVED — do not just repeat the same numbered list.

4. **Anti-contradiction window.** Within any 5-turn window: if a prior turn of yours said "X doesn't fit / is wrong / shouldn't be here", do NOT list X as a valid option in a subsequent turn. Treat the user's chat history as your own memory.

5. **Use suspect data, but warn.** When the project-task list returned by the system looks wrong, don't refuse to function — but don't pretend it's clean either. Pattern: "Here's the task list for this project. Heads-up: option N (Acuity New Growth - BYD) looks misassigned — it's listed under DENZA but probably belongs under a BYD project. I'd treat it as suspect; confirm with whoever set up the projects." Then proceed with the user's choice unless they want to investigate.

6. **Apology economy.** When corrected, one short apology + immediate corrected action. Don't apologise more than once per topic per conversation. "Sorry, my mistake — let me fix that" is enough; multi-paragraph apologies waste tokens and erode trust.

REFERENCE — edge cases:
- All-day blocks ("worked on X today"): default 7.5 hours unless the user has logged other entries today; in that case ask "is that the rest of today, or in addition to what you've already logged?"
- Multi-task days ("did emails, then a meeting, then drafted a proposal"): create one entry per task, ask for duration of each.
- Future dates ("tomorrow", "next Monday", "12th May", scheduled annual leave): ALLOWED. Harvest accepts future spent_date and the leave + planned-work flow needs it. Confirm the resolved YYYY-MM-DD with the user before creating the draft, but never refuse a future date. Examples: "for Thursday's pitch" -> create draft for that Thursday; "Annual Leave next Monday" -> create draft on that Monday.
- Past dates ("last Tuesday"): convert to absolute YYYY-MM-DD using today's date as reference, confirm date with the user before logging.
- Negative durations / zero hours: refuse, ask for clarification.
- Hours > 16 in a single entry: confirm before logging — likely a typo or a "this whole week" misphrasing.

REFERENCE — internal Thrive admin / non-client work (CRITICAL — Miles couldn't find general admin / reporting codes / Thrive L&D):
Many users log time against internal Thrive projects, NOT against a billable client. These projects start with "Thrive " in the catalog above. **Override the assigned-projects pruning rule for internal work** — every Thrive employee can log time against any "Thrive *" project even if it doesn't appear in their personal Assigned list. Do NOT hide internal projects with "you're not assigned to that".

Phrase mapping (look for the matching "Thrive *" project in the catalog):
- "general admin", "admin", "ops", "operations", "internal stuff" -> Thrive Operation FY26 (task: Reporting & WIPs, or another internal task on that project)
- "emails", "inbox", "to-do list", "to do list", "inbox triage", "catch-up on emails" -> Thrive Operation FY26 / Reporting & WIPs OR the user's regular client retainer (ask which one if ambiguous)
- "training", "L&D", "learning and development", "learning & development", "weekly planning", "team training", "peer support" -> Thrive Learning & Development FY26 (tasks: Weekly Planning, Agency WIPs, SLT WIPs, Local WIPs, Peer Support)
- "month end", "month-end", "invoicing", "finance", "estimates", "budget", "tax", "payroll", "accounts payable", "accounts receivable", "Xero" -> Thrive Finance Operation FY26 (tasks: Systems & Process Improvement, Reporting & WIPs, Tax and Accounting, Payroll, Estimate & invoice, Accounts Receivables, Bills & Accounts Payable, Thrive Budget, Clients Budget)
- "team meeting", "all hands", "all-in WIP", "agency WIP", "weekly WIP" -> Thrive L&D / Agency WIPs OR Thrive Operation FY26 / Reporting & WIPs (ask which one)
- "culture", "social events", "Thrive O'Clock", "office support" -> Thrive Culture & Social FY26 (tasks: Thrive O'Clock, Social Events, Office Support)
- "innovation", "digital champions", "Timesheet Assistant" (this app), "AI tooling" -> Thrive Innovation Project (tasks: Digital Champions, Innovation Project)
- "annual leave", "sick leave", "carer leave", "unpaid leave", "time in lieu", "TIL", "funeral leave" -> Thrive Leave (full day = 7.5h; future dates ALLOWED)
- "social content", "case studies", "social media post", "approvals" -> Thrive Social Media & Content FY26
- "new business", "biz dev for Thrive", "existing growth for Diageo/LEGO/etc internal" -> Thrive New Business - Existing Growth FY26

If the user names a Thrive internal project that isn't in the catalog above, do NOT make one up — say plainly "I can't see a 'Thrive X' project in the catalog. The closest matches are: A, B, C — which one fits?" and list the 3-5 nearest Thrive-prefixed projects from the catalog.

REFERENCE — entry-management tools (list / delete / edit):
You have tools to list, delete, and edit existing Harvest entries — use these instead of telling the user to log into Harvest directly:
- "show me all entries", "show me last week", "what did I log" -> use list_entries with the right date range.
- "delete that entry", "clear today", "remove the X entry" -> use list_entries first to find IDs, then delete_entry. ALWAYS confirm the specific entries before deleting more than one.
- "edit X to be Y", "change X to Y", "actually that was 4 hours not 7" -> use edit_entry. Under the hood this delete+recreates in Harvest.
NEVER tell a user "I can only create new entries — you'll need to log into Harvest directly" — that text is OUTDATED. Use the tools.

REFERENCE — wording when entries are saved (CRITICAL — production observation: Michael read "Logged: 7.5 hours" as "in Harvest" but the entry was only a Draft):
- After a ```ENTRY block is created, the entry lands in DRAFT state in our staging DB and Google Sheet. It does NOT push to Harvest until the user clicks Approve in the entries panel (or says "approve" in chat).
- Phrase your confirmation accordingly. Good: "Drafted 0.75h on Finance / Reporting & WIPs for today — approve in the right panel to push to Harvest." Bad: "Done! Logged that to Harvest." — that creates the wrong expectation.
- Bulk approvals: when the user says "approve all", you don't need to do anything; the right panel's Approve All button is the path. Just acknowledge.

REFERENCE — PR/communications industry task taxonomy (use this when categorizing ambiguous mentions; this is what each task type usually involves so you can match a user's verbal description to a task name):
- Retainer work: monthly committed hours for ongoing client support — daily check-ins, ad-hoc requests, content review, monitoring. Verbs the user might use: "checking in on", "responding to", "handling", "managing", "keeping on top of", "babysitting".
- Existing Business Growth: identifying and pursuing expansion within current accounts — proposal extensions, scope upsells, new service lines for existing clients. Verbs: "growing", "expanding", "upselling", "extending", "scoping new work".
- New Business Growth: pitching prospective clients, RFP responses, capabilities decks, networking. Verbs: "pitching", "pitched", "RFP", "responding to brief", "prep deck", "intro call", "discovery", "BD", "biz dev", "bizdev".
- Operations & Admin: internal team meetings, all-hands, training, hiring, internal Slack/email management, expense reports, leave requests. Verbs: "team standup", "all-hands", "internal", "ops call", "admin", "expenses", "training", "1:1 with manager".
- Project / Campaign Delivery: actual client deliverables — drafting press releases, building media lists, writing pitches to journalists, social content production, event execution, crisis communications. Verbs: "drafted", "wrote", "produced", "shipped", "executed", "launched", "ran".
- Strategy: planning, research, briefing, audience analysis, positioning. Verbs: "planning", "strategy session", "briefing", "research", "analysis", "audit", "review".
- Creative: design work, photography direction, video production, copy concepting. Verbs: "designed", "shot", "filmed", "edited (video)", "concepted", "art directed".
- Reporting & Measurement: monthly reports, coverage tracking, sentiment analysis, ROI calc, dashboards. Verbs: "reporting", "report", "tracked coverage", "sentiment", "metrics", "dashboard", "monthly numbers".

REFERENCE — common abbreviations Thrive teams use:
- "AOR" = agency of record
- "BAU" = business as usual (i.e. retainer work)
- "BD" / "biz dev" = business development
- "EOD" = end of day
- "EOFY" = end of financial year (June 30 in AU)
- "FY26" = financial year 2026 (July 2025 - June 2026 in AU)
- "FYI" = for your information
- "GTM" = go to market
- "KPI" = key performance indicator
- "MD" / "GM" = managing director / general manager
- "OOO" = out of office
- "POV" = point of view (a strategic stance/recommendation)
- "QBR" = quarterly business review
- "SLA" = service level agreement
- "SOW" / "scope" = statement of work
- "TBC" = to be confirmed
- "TBD" = to be determined
- "WIP" = work in progress

REFERENCE — voice-input dictation quirks (users may dictate via phone or browser mic; expect speech-recognition artifacts):
- Times are sometimes spelled out: "one and a half hours" → 1.5; "thirty minutes" → 0.5; "an hour and twenty" → 1.33 → round to 1.33h.
- Punctuation may be missing: "afterpay retainer two hours" should still parse as Afterpay / Retainer / 2h.
- Brand names may be mis-transcribed: "after pay" → Afterpay; "comm bank" → CommBank; "tell stra" → Telstra; "leg o" → LEGO. Be charitable when matching to project names.
- Multiple entries in one breath: "did half hour Afterpay then forty minutes Acuity then about an hour on the Telstra deck" → three separate entries.
- Filler words: "um", "like", "you know", "basically" — ignore, don't echo back.

Available Projects and Tasks:
{{projects_text}}

Pilot users: {{pilot_users}}
"""


def build_system_prompt(
    user_email: Optional[str] = None,
    harvest_access_token: Optional[str] = None,
    notes: Optional[List[str]] = None,
) -> List[Dict]:
    """Build the system prompt as Anthropic message blocks with cache control.

    Returns a list of blocks:
      - Block A (cached, ephemeral): role, rules, AU/NZ vocab, master Harvest
        catalog, dates, pilot users. Identical for every user → cache hit on
        every chat after the first.
      - Block B (uncached, optional): per-user profile (assigned projects,
        dialect, top tasks, recent corrections) + transient runtime notes.
        Skipped entirely if both inputs are empty so we don't waste tokens.
    """
    projects_text = get_all_projects_for_prompt(harvest_access_token)
    # Cached block stays generic (UTC date) so it's identical for every user;
    # the user's local "today" is injected as a runtime note in the uncached
    # block below. That way the cache hit rate stays high and AU/NZ users
    # still see correct dates.
    server_today = date.today()
    cached_text = SYSTEM_PROMPT_TEMPLATE.replace("{{today_display}}", server_today.strftime('%A, %d/%m/%Y')) \
        .replace("{{today_iso}}", server_today.strftime('%Y-%m-%d')) \
        .replace("{{today_day}}", server_today.strftime('%A')) \
        .replace("{{projects_text}}", projects_text) \
        .replace("{{pilot_users}}", ', '.join(PILOT_USERS))

    blocks: List[Dict] = [
        {"type": "text", "text": cached_text, "cache_control": {"type": "ephemeral"}}
    ]

    uncached_parts: List[str] = []
    if user_email:
        profile_text = user_profiles.render_profile_block(user_email)
        if profile_text:
            uncached_parts.append(profile_text)
        # Per-user local-date note — overrides the cached block's UTC date so
        # AU/NZ users get the right "today" reference. Critical: the model
        # MUST treat this as authoritative over the cached block's date.
        local_today = time_utils.today_local(_user_dialect(user_email))
        uncached_parts.append(
            "AUTHORITATIVE TODAY (use this, NOT the date in the cached block): "
            f"{local_today.strftime('%A, %d/%m/%Y')} ({local_today.isoformat()}). "
            "This is the user's local date in their timezone — when they say "
            "'today', 'tomorrow', or 'yesterday', anchor those words to THIS "
            "date, not to the cached block's date."
        )
    if notes:
        uncached_parts.extend(n for n in notes if n)

    if uncached_parts:
        blocks.append({"type": "text", "text": "\n\n".join(uncached_parts)})

    return blocks


async def build_system_prompt_async(
    user_email: Optional[str] = None,
    harvest_access_token: Optional[str] = None,
    notes: Optional[List[str]] = None,
) -> List[Dict]:
    """Async version — used by /api/chat/stream so the slow Harvest project
    fetch (51 task_assignments calls) doesn't block the event loop.
    Same return shape as build_system_prompt."""
    projects_text = await get_all_projects_for_prompt_async(harvest_access_token)
    server_today = date.today()
    cached_text = SYSTEM_PROMPT_TEMPLATE.replace("{{today_display}}", server_today.strftime('%A, %d/%m/%Y')) \
        .replace("{{today_iso}}", server_today.strftime('%Y-%m-%d')) \
        .replace("{{today_day}}", server_today.strftime('%A')) \
        .replace("{{projects_text}}", projects_text) \
        .replace("{{pilot_users}}", ', '.join(PILOT_USERS))

    blocks: List[Dict] = [
        {"type": "text", "text": cached_text, "cache_control": {"type": "ephemeral"}}
    ]

    uncached_parts: List[str] = []
    if user_email:
        profile_text = user_profiles.render_profile_block(user_email)
        if profile_text:
            uncached_parts.append(profile_text)
        local_today = time_utils.today_local(_user_dialect(user_email))
        uncached_parts.append(
            "AUTHORITATIVE TODAY (use this, NOT the date in the cached block): "
            f"{local_today.strftime('%A, %d/%m/%Y')} ({local_today.isoformat()}). "
            "This is the user's local date in their timezone — when they say "
            "'today', 'tomorrow', or 'yesterday', anchor those words to THIS "
            "date, not to the cached block's date."
        )
    if notes:
        uncached_parts.extend(n for n in notes if n)

    if uncached_parts:
        blocks.append({"type": "text", "text": "\n\n".join(uncached_parts)})

    return blocks


def get_current_user(request: Request) -> Optional[Dict]:
    """Get the logged-in user from session."""
    return request.session.get("user")


def _user_dialect(user_email: Optional[str]) -> Optional[str]:
    """Resolve the user's dialect (e.g. 'en-AU-Sydney') from their profile.
    Returns None when no profile exists — callers fall through to AU default."""
    if not user_email:
        return None
    try:
        profile = user_profiles.get_profile(user_email)
        return profile.get("dialect")
    except Exception:
        return None


_SELECTED_DATE_RE = __import__("re").compile(r"^\d{4}-\d{2}-\d{2}$")


def _selected_date_note(selected: str) -> str:
    """Format the user's date-picker selection as a strong system note. Returns
    empty string when the input doesn't look like YYYY-MM-DD so a malformed
    value can never silently become 'today'."""
    selected = (selected or "").strip()
    if not _SELECTED_DATE_RE.match(selected):
        return ""
    try:
        d = date.fromisoformat(selected)
    except ValueError:
        return ""
    return (
        "USER-SELECTED DATE (highest priority — overrides 'today/yesterday/tomorrow' "
        f"phrases in the user's message): {d.strftime('%A, %d/%m/%Y')} ({d.isoformat()}). "
        "Treat this as the authoritative date for any entry the user describes "
        "in their next message UNLESS they explicitly state a different date in "
        "the message itself. If their message already specifies a date, follow "
        "the message's date — the picker is only the default, not a lock."
    )


def _today_local_iso(user_email: Optional[str] = None) -> str:
    """Today in the user's local timezone as YYYY-MM-DD. Use this instead
    of date.today().isoformat() for any spent_date defaulting — UTC on
    Render means date.today() lies for AU/NZ users from late afternoon."""
    return time_utils.today_iso_local(_user_dialect(user_email))


def _build_today_summary_note(user_email: str, harvest_access_token: Optional[str]) -> Optional[str]:
    """Fetch today's existing Harvest entries for the user and return them as
    a runtime-note string for injection into the system prompt's uncached
    block. Returns None on any failure or when there's nothing to report —
    callers append only when a non-empty string comes back.

    Why this exists: a user who logged AFGC in the morning and comes back at
    7pm should NOT be allowed to silently double-log it. By telling Claude
    what's already there, the model can prompt 'is this addition or
    separate?' instead of creating a duplicate."""
    if not user_email or not harvest_access_token:
        return None
    try:
        profile = user_profiles.get_profile(user_email)
        hid = profile.get("harvest_user_id")
        if not hid:
            return None
        local_today = time_utils.today_iso_local(profile.get("dialect"))
        entries = harvest_api.get_today_entries_cached(
            hid, harvest_access_token, spent_date=local_today
        )
        summary = harvest_api.format_today_summary(entries)
        return summary or None
    except Exception as e:
        print(f"[WARN] today_summary skipped (non-fatal): {e}")
        return None


class ChatRequest(BaseModel):
    user: str
    message: str
    history: List[Dict] = []
    # Optional YYYY-MM-DD from the chat-input date picker. When set, the AI
    # treats this as the authoritative date for any entry the user describes
    # in this message (overrides the user's local "today" anchor).
    selected_date: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    entries_created: List[Dict] = []


def save_entry_everywhere(
    user: str,
    entry_data: Dict,
    user_email: str = "",
    fallback_date: Optional[str] = None,
) -> Dict:
    """Save an entry as Draft to Supabase and Google Sheets. Harvest push happens on approval.

    Date precedence: entry_data['date'] (AI-emitted) > fallback_date
    (date-picker selection) > user's local today. The picker is the default
    when the AI didn't pin a date, so a user who pre-set 12 May for an Annual
    Leave entry actually gets 12 May rather than today."""
    default_date = fallback_date or _today_local_iso(user_email)
    entry = harvest_mock.create_draft_entry(
        user=user,
        client=entry_data.get("client", "Unknown"),
        project_code=entry_data.get("project_code", ""),
        project_name=entry_data.get("project_name", ""),
        task=entry_data.get("task", "General"),
        hours=float(entry_data.get("hours", 0)),
        notes=entry_data.get("notes", ""),
        entry_date=entry_data.get("date", default_date),
        status=entry_data.get("status", "Draft"),
    )
    # Sync to Google Sheet (draft only — no Harvest push until approved)
    sheets_sync.sync_entry_to_sheet(entry)
    return entry


def parse_entries_from_response(text: str) -> Tuple[str, List[Dict]]:
    """Extract ENTRY JSON blocks from Claude's response."""
    entries = []
    clean_text = text

    while "```ENTRY" in clean_text:
        start = clean_text.index("```ENTRY")
        end = clean_text.index("```", start + 8)
        json_str = clean_text[start + 8:end].strip()
        try:
            entry_data = json.loads(json_str)
            entries.append(entry_data)
        except json.JSONDecodeError:
            pass
        clean_text = clean_text[:start] + clean_text[end + 3:]

    return clean_text.strip(), entries


# --- Tool Definitions for Claude tool_use ---

TOOLS = [
    {
        "name": "scan_emails",
        "description": (
            "Scan the user's Gmail to find email activity. Use this when the user asks about their emails, "
            "wants to log time based on email work, or you need to understand their communication patterns. "
            "Returns metadata only (subject, sender, recipients, timestamps) — no email body content. "
            "You can filter by date range, sender, recipient, CC, subject, or keyword. "
            "Default to today if the user doesn't specify a date."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date_from": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format. Defaults to today.",
                },
                "date_to": {
                    "type": "string",
                    "description": "End date in YYYY-MM-DD format (inclusive). Defaults to same as date_from.",
                },
                "sender": {
                    "type": "string",
                    "description": "Filter by sender email address (e.g. 'tariq@thrive.com').",
                },
                "recipient": {
                    "type": "string",
                    "description": "Filter by recipient email address.",
                },
                "cc": {
                    "type": "string",
                    "description": "Filter by CC email address.",
                },
                "subject": {
                    "type": "string",
                    "description": "Search for text in email subject lines.",
                },
                "keyword": {
                    "type": "string",
                    "description": "General search term to find in email metadata.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum emails to return (default 30, max 100).",
                },
            },
            "required": [],
        },
    },
    {
        "name": "scan_calendar",
        "description": (
            "Scan the user's Google Calendar to find meetings and events. Use this when the user asks about "
            "their meetings, schedule, or wants to log time based on calendar events. "
            "Returns event summaries, times, durations, and attendees. "
            "Default to today if the user doesn't specify a date."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date_from": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format. Defaults to today.",
                },
                "date_to": {
                    "type": "string",
                    "description": "End date in YYYY-MM-DD format (inclusive). Defaults to same as date_from.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "scan_drive",
        "description": (
            "Scan the user's Google Drive for recently modified files. Use this when the user asks about "
            "documents they worked on, or wants to log time based on document editing activity. "
            "Returns file names, types, and modification times — no file content. "
            "Default to today if the user doesn't specify a date."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date_from": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format. Defaults to today.",
                },
                "date_to": {
                    "type": "string",
                    "description": "End date in YYYY-MM-DD format (inclusive). Defaults to same as date_from.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "list_entries",
        "description": (
            "List the user's existing Harvest time entries for a given date range. Use this when the user asks "
            "'show me my entries', 'what did I log last week', 'show me yesterday', or before deleting/editing "
            "an entry so you can find the harvest_id to operate on. Returns each entry's harvest_id, "
            "spent_date, project name, task name, hours, and notes. "
            "Defaults to today if no dates given. Maximum 31-day range per call."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date_from": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format. Defaults to today (user's local timezone).",
                },
                "date_to": {
                    "type": "string",
                    "description": "End date in YYYY-MM-DD format (inclusive). Defaults to same as date_from.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "delete_entry",
        "description": (
            "Delete a Harvest time entry by its harvest_id. Use this when the user explicitly asks to delete, "
            "remove, or clear an entry. ALWAYS run list_entries first to confirm the harvest_id and "
            "ALWAYS confirm with the user which specific entry will be deleted before calling this — "
            "deletion is irreversible in Harvest's web UI for the user. For 'clear all today / clear week' "
            "requests, list first, then state exactly which entries you'll delete and ask for confirmation, "
            "then call delete_entry once per harvest_id."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "harvest_id": {
                    "type": "integer",
                    "description": "The Harvest time-entry id (from list_entries output).",
                },
            },
            "required": ["harvest_id"],
        },
    },
    {
        "name": "edit_entry",
        "description": (
            "Edit a Harvest time entry's hours, notes, or spent_date in place. Use this for 'change 7h to 6h', "
            "'fix the notes on entry X', 'move that to Tuesday'. ALWAYS list_entries first to confirm the "
            "harvest_id. To CHANGE the project/task on an entry, do NOT use this — instead call delete_entry "
            "for the old entry and emit a fresh ```ENTRY block for the new one (Harvest has issues with PATCH "
            "across projects/tasks)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "harvest_id": {
                    "type": "integer",
                    "description": "The Harvest time-entry id (from list_entries output).",
                },
                "hours": {
                    "type": "number",
                    "description": "New hours value (optional).",
                },
                "notes": {
                    "type": "string",
                    "description": "New notes text (optional). Replaces existing notes.",
                },
                "spent_date": {
                    "type": "string",
                    "description": "New date in YYYY-MM-DD format (optional).",
                },
            },
            "required": ["harvest_id"],
        },
    },
]

MAX_TOOL_ITERATIONS = 5

# Tool-name groupings — used to gate which tools the model is offered based on
# what the user has connected. Keep these in sync with the TOOLS list above.
_GOOGLE_TOOL_NAMES = {"scan_emails", "scan_calendar", "scan_drive"}
_HARVEST_TOOL_NAMES = {"list_entries", "delete_entry", "edit_entry"}


def _tools_for_user(has_google: bool, has_harvest: bool) -> Optional[List[Dict]]:
    """Build the per-request tools list. Hides tools the user can't use so
    the model doesn't try to call them and burn a tool-loop iteration on an
    ERROR result."""
    enabled: List[Dict] = []
    for t in TOOLS:
        name = t.get("name")
        if name in _GOOGLE_TOOL_NAMES and has_google:
            enabled.append(t)
        elif name in _HARVEST_TOOL_NAMES and has_harvest:
            enabled.append(t)
    return enabled or None


def _format_harvest_entries_for_tool(entries: List[Dict]) -> str:
    """Render a list of Harvest entry dicts as a compact AI-readable summary.
    Includes harvest_id so the model can target specific entries for delete/edit."""
    if not entries:
        return "No entries in that date range."
    lines: List[str] = [f"Found {len(entries)} entries:"]
    total = 0.0
    for e in entries:
        hrs = float(e.get("hours") or 0)
        total += hrs
        client = (e.get("client") or {}).get("name") or "?"
        project = (e.get("project") or {}).get("name") or "?"
        task = (e.get("task") or {}).get("name") or "?"
        notes = (e.get("notes") or "").strip()
        notes_preview = f' — "{notes[:80]}"' if notes else ""
        lines.append(
            f"- [harvest_id={e.get('id')}] {e.get('spent_date','?')} | "
            f"{client} / {project} / {task} | {hrs}h{notes_preview}"
        )
    lines.append(f"Total: {total:.2f}h")
    return "\n".join(lines)


async def execute_tool(
    tool_name: str,
    tool_input: Dict,
    access_token: str,
    harvest_access_token: Optional[str] = None,
    harvest_user_id: Optional[int] = None,
    user_dialect: Optional[str] = None,
) -> str:
    """Execute a tool call and return the result string for Claude.

    `access_token` is the Google OAuth token (for scan_*).
    `harvest_access_token` + `harvest_user_id` are the Harvest context for
    list_entries / delete_entry / edit_entry. When the Harvest context is
    missing, those tools return an explicit error string the model can show
    to the user."""
    try:
        if tool_name == "scan_emails":
            emails = gmail_sync.search_emails(
                access_token=access_token,
                date_from=tool_input.get("date_from"),
                date_to=tool_input.get("date_to"),
                sender=tool_input.get("sender"),
                recipient=tool_input.get("recipient"),
                cc=tool_input.get("cc"),
                subject=tool_input.get("subject"),
                keyword=tool_input.get("keyword"),
                max_results=tool_input.get("max_results", 30),
            )
            return gmail_sync.format_search_results_for_tool(emails)

        elif tool_name == "scan_calendar":
            events = calendar_sync.search_events(
                access_token=access_token,
                date_from=tool_input.get("date_from"),
                date_to=tool_input.get("date_to"),
            )
            return calendar_sync.format_search_results_for_tool(events)

        elif tool_name == "scan_drive":
            files = drive_sync.search_files(
                access_token=access_token,
                date_from=tool_input.get("date_from"),
                date_to=tool_input.get("date_to"),
            )
            return drive_sync.format_search_results_for_tool(files)

        elif tool_name == "list_entries":
            if not harvest_access_token or not harvest_user_id:
                return "ERROR: Harvest is not connected for this user — ask them to click 'Connect Harvest' in the top banner."
            local_today = time_utils.today_iso_local(user_dialect)
            df = tool_input.get("date_from") or local_today
            dt = tool_input.get("date_to") or df
            entries = harvest_api.get_time_entries_range(
                from_date=df,
                to_date=dt,
                user_id=harvest_user_id,
                access_token=harvest_access_token,
            )
            return _format_harvest_entries_for_tool(entries)

        elif tool_name == "delete_entry":
            if not harvest_access_token:
                return "ERROR: Harvest is not connected — ask the user to click 'Connect Harvest'."
            hid = tool_input.get("harvest_id")
            if not hid:
                return "ERROR: harvest_id is required."
            ok = harvest_api.delete_time_entry(int(hid), access_token=harvest_access_token)
            if ok and harvest_user_id:
                harvest_api.invalidate_today_cache(harvest_user_id)
            return f"Deleted entry harvest_id={hid}: success={ok}"

        elif tool_name == "edit_entry":
            if not harvest_access_token:
                return "ERROR: Harvest is not connected — ask the user to click 'Connect Harvest'."
            hid = tool_input.get("harvest_id")
            if not hid:
                return "ERROR: harvest_id is required."
            updated = harvest_api.patch_time_entry(
                harvest_id=int(hid),
                hours=tool_input.get("hours"),
                notes=tool_input.get("notes"),
                spent_date=tool_input.get("spent_date"),
                access_token=harvest_access_token,
            )
            if updated and harvest_user_id:
                harvest_api.invalidate_today_cache(harvest_user_id)
            if not updated:
                return f"ERROR: Could not edit entry {hid}. Check the id is valid and at least one field (hours/notes/spent_date) was provided."
            return (
                f"Edited entry harvest_id={hid}: spent_date={updated.get('spent_date')} "
                f"hours={updated.get('hours')} notes={(updated.get('notes') or '')[:80]}"
            )

        else:
            return f"Unknown tool: {tool_name}"

    except gmail_sync.TokenExpiredError:
        return "ERROR: Your Google access token has expired. Please sign out and sign back in."
    except httpx.TimeoutException:
        return "ERROR: The Google API request timed out. Please try again."
    except Exception as e:
        print(f"Tool execution error ({tool_name}): {e}")
        return f"ERROR: Failed to execute {tool_name}: {str(e)}"


# --- Health & Readiness ---

@app.api_route("/health", methods=["GET", "HEAD"])
async def health(request: Request):
    """Lightweight readiness probe for Render + UptimeRobot. Always returns
    200 if the process is alive — degraded downstream deps (Anthropic,
    Harvest, Supabase) are surfaced in the body so they're observable but
    don't fail the probe (we don't want UptimeRobot to alert on transient
    Anthropic blips).

    Accepts GET *and* HEAD — UptimeRobot defaults to HEAD probes, and a
    GET-only route returns 405 which the monitor reads as Down. FastAPI
    strips the body on HEAD automatically, so the same handler serves both."""
    return {
        "status": "ok",
        "service": "timesheet-assistant",
        "model": CHAT_MODEL,
        "uptime_seconds": int(time.time() - _BOOT_TS),
        "deps": {
            "anthropic_key_present": bool(os.getenv("ANTHROPIC_API_KEY")),
            "harvest_pat_configured": harvest_api.is_configured(),
            "supabase_configured": harvest_mock._supabase_configured(),
            "google_oauth_configured": bool(os.getenv("GOOGLE_CLIENT_ID")),
            "harvest_oauth_configured": bool(os.getenv("HARVEST_CLIENT_ID")),
            "google_sheets_configured": sheets_sync.is_configured(),
        },
        "build": {
            "local_demo_only": LOCAL_DEMO_ONLY,
        },
    }


# --- Auth Routes ---

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse(url="/")
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/auth/google")
async def auth_google(request: Request):
    redirect_uri = request.url_for("auth_callback")
    return await oauth.google.authorize_redirect(
        request, redirect_uri, access_type="offline", prompt="consent"
    )


@app.get("/auth/callback")
async def auth_callback(request: Request):
    token = await oauth.google.authorize_access_token(request)
    userinfo = token.get("userinfo")
    if not userinfo:
        return RedirectResponse(url="/login")

    # Store user info in session
    request.session["user"] = {
        "email": userinfo["email"],
        "name": userinfo.get("name", userinfo["email"].split("@")[0]),
        "picture": userinfo.get("picture", ""),
    }
    # Store Google OAuth tokens for Calendar API access
    request.session["google_token"] = {
        "access_token": token.get("access_token", ""),
        "refresh_token": token.get("refresh_token", ""),
        "expires_at": token.get("expires_at", 0),
    }
    return RedirectResponse(url="/")


@app.get("/auth/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login")


@app.get("/demo-login")
async def demo_login(request: Request):
    """Quick demo login bypass (REMOVE IN PRODUCTION)"""
    request.session["user"] = {
        "email": "tariq@thrive.com",
        "name": "Tariq Munir",
        "picture": "",
    }
    request.session["google_token"] = {
        "access_token": "demo_token",
        "refresh_token": "",
        "expires_at": 9999999999,
    }
    return RedirectResponse(url="/")


@app.get("/auth/harvest")
async def auth_harvest(request: Request):
    """Initiate Harvest OAuth flow."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")

    harvest_client_id = os.getenv("HARVEST_CLIENT_ID", "")
    harvest_client_secret = os.getenv("HARVEST_CLIENT_SECRET", "")
    if not harvest_client_id or not harvest_client_secret:
        print(
            "Harvest OAuth config missing: HARVEST_CLIENT_ID or HARVEST_CLIENT_SECRET not set."
        )
        return RedirectResponse(url="/?harvest_error=missing_oauth_config")

    redirect_uri = str(request.url_for("auth_harvest_callback"))
    return await oauth.harvest.authorize_redirect(request, redirect_uri)


@app.get("/auth/harvest/callback")
async def auth_harvest_callback(request: Request):
    """Handle Harvest OAuth callback. Also bootstraps the user's profile from
    their Harvest project assignments so the AI knows what they work on."""
    try:
        token = await oauth.harvest.authorize_access_token(request)

        access_token = token.get("access_token", "")
        request.session["harvest_token"] = {
            "access_token": access_token,
            "refresh_token": token.get("refresh_token", ""),
            "expires_at": time.time() + token.get("expires_in", 1209600),  # 14 days
        }

        # Bootstrap the per-user profile from Harvest's view of this user
        user = get_current_user(request)
        if user and user.get("email") and access_token:
            try:
                me = harvest_api.get_my_user(access_token)
                assignments = harvest_api.get_my_project_assignments(access_token)
                project_codes = [
                    str(a["project"]["id"])
                    for a in assignments
                    if a.get("project") and a["project"].get("id")
                ]
                user_profiles.bootstrap_from_harvest(
                    email=user["email"],
                    display_name=user.get("name", ""),
                    harvest_user_id=(me or {}).get("id"),
                    assigned_project_codes=project_codes,
                )
                print(
                    f"[OK] Profile bootstrap: {user['email']} -> "
                    f"harvest_user_id={(me or {}).get('id')}, "
                    f"{len(project_codes)} projects"
                )
            except Exception as bootstrap_err:
                print(f"[WARN] Profile bootstrap failed: {bootstrap_err}")

        # Pre-warm the global Harvest project cache with this user's OAuth
        # token in the background. The boot-time pre-warm uses HARVEST_PAT,
        # which 401s on Thrive (account 310089 enforces Google SSO) — so the
        # cache is empty until someone makes the first chat call. That first
        # call eats ~5-7s for the N+1 task-assignments fetch.
        #
        # By kicking this off as a background task right after OAuth, the
        # redirect to "/" returns immediately (no UX slowdown), and by the
        # time the user navigates to chat and types their first message,
        # the cache is populated. First-impression latency drops 10s -> ~2-3s.
        if access_token:
            asyncio.create_task(_prewarm_harvest_cache(access_token))

        return RedirectResponse(url="/")
    except Exception as e:
        print(
            f"Harvest OAuth error: {e}. "
            f"client_id_set={bool(os.getenv('HARVEST_CLIENT_ID', ''))} "
            f"client_secret_set={bool(os.getenv('HARVEST_CLIENT_SECRET', ''))}"
        )
        return RedirectResponse(url="/?harvest_error=auth_failed")


@app.get("/auth/harvest/disconnect")
async def harvest_disconnect(request: Request):
    """Disconnect Harvest (remove tokens from session)."""
    if "harvest_token" in request.session:
        del request.session["harvest_token"]
    return RedirectResponse(url="/")


# --- App Routes ---

def _greeting_for_dialect(dialect: str) -> str:
    """Pick a culturally-appropriate opener so Hugh (NZ) doesn't get 'G'day'.
    Falls back to a neutral 'Hi' for any unknown dialect."""
    d = (dialect or "").lower()
    if d.startswith("en-nz"):
        return "Kia ora"
    if d.startswith("en-au"):
        return "G'day"
    return "Hi"


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")
    profile = user_profiles.get_profile(user.get("email", ""))
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "user": user,
            "users": PILOT_USERS,
            "today": time_utils.today_local(profile.get("dialect")).strftime("%A, %d/%m/%Y"),
            # Hides the local-only Task Dashboard link on Render production —
            # without this guard the button rendered unconditionally and 404'd
            # on /dashboard for every pilot user (the planning routes only
            # mount when LOCAL_DEMO_ONLY=1).
            "local_demo_only": LOCAL_DEMO_ONLY,
            "welcome_greeting": _greeting_for_dialect(profile.get("dialect", "")),
        },
    )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request):
    user = get_current_user(request)
    if not user:
        return ChatResponse(response="Please log in first.", entries_created=[])

    # Per-user rate limit — protects the Anthropic spend from runaway loops
    # or abusive clients. 30/min sustained, 30 burst.
    allowed, retry_after = rate_limit.check_and_consume(user.get("email", ""))
    if not allowed:
        return ChatResponse(
            response=(
                f"You're sending messages faster than I can keep up. "
                f"Try again in {int(retry_after) + 1}s."
            ),
            entries_created=[],
        )

    # Build messages for Claude
    messages = []
    for msg in req.history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": req.message})

    # Check if Google token is available for tools
    google_token = request.session.get("google_token")
    has_google_access = False
    access_token = None

    if google_token and google_token.get("access_token"):
        valid_token = calendar_sync.ensure_valid_token(google_token)
        if valid_token:
            request.session["google_token"] = valid_token
            access_token = valid_token["access_token"]
            has_google_access = True

    # Check if Harvest token is available
    harvest_token = request.session.get("harvest_token")
    harvest_access_token = None

    if harvest_token and harvest_token.get("access_token"):
        valid_token = harvest_oauth.ensure_valid_token(harvest_token)
        if valid_token:
            request.session["harvest_token"] = valid_token
            harvest_access_token = valid_token["access_token"]

    # Transient runtime notes — appended to the per-user (uncached) block so they
    # don't invalidate the cached master catalog.
    runtime_notes: List[str] = []
    if not has_google_access:
        runtime_notes.append(
            "NOTE: The user has not granted Google Workspace access. "
            "If they ask to scan emails, calendar, or drive, tell them to sign out "
            "and sign back in to grant the required permissions."
        )
    if not harvest_access_token:
        runtime_notes.append(
            "NOTE: The user has not connected their Harvest account. "
            "If they try to log time, tell them to click 'Connect Harvest' first."
        )

    if req.selected_date:
        runtime_notes.append(_selected_date_note(req.selected_date))

    today_note = _build_today_summary_note(user.get("email", ""), harvest_access_token)
    if today_note:
        runtime_notes.append(today_note)

    system_blocks = build_system_prompt(
        user_email=user.get("email"),
        harvest_access_token=harvest_access_token,
        notes=runtime_notes,
    )

    tools_param = _tools_for_user(has_google_access, bool(harvest_access_token))
    profile_for_tools = user_profiles.get_profile(user.get("email", ""))
    user_dialect_for_tools = profile_for_tools.get("dialect")
    harvest_user_id_for_tools = profile_for_tools.get("harvest_user_id")

    # === AGENTIC LOOP ===
    iterations = 0
    final_text = ""
    response = None
    chat_start_ts = time.time()
    tool_calls_log: List[Dict] = []
    last_usage: Dict = {}

    while iterations < MAX_TOOL_ITERATIONS:
        iterations += 1

        api_kwargs = {
            "model": CHAT_MODEL,
            "max_tokens": 2048,
            "system": system_blocks,
            "messages": messages,
        }
        if tools_param:
            api_kwargs["tools"] = tools_param

        try:
            response = await client.messages.create(**api_kwargs)
        except Exception as anth_err:
            # Anthropic side failure (Cloudflare challenge, rate limit, etc.)
            # — return a clean JSON error instead of letting FastAPI emit
            # an HTML 500 that the frontend can't JSON.parse.
            print(f"[ERR] /api/chat anthropic call: {type(anth_err).__name__}: {str(anth_err)[:500]}")
            return ChatResponse(
                response=_user_friendly_anthropic_error(anth_err),
                entries_created=[],
            )

        last_usage = training_log.usage_metrics(response)

        if response.stop_reason == "end_turn":
            # Claude is done — extract text
            text_parts = []
            for block in response.content:
                if hasattr(block, "text"):
                    text_parts.append(block.text)
            final_text = "\n".join(text_parts)
            break

        elif response.stop_reason == "tool_use":
            # Claude wants to use tools — add its response to messages
            messages.append({"role": "assistant", "content": response.content})

            # Re-validate token (may have expired during loop)
            if has_google_access:
                refreshed = calendar_sync.ensure_valid_token(
                    request.session.get("google_token", {})
                )
                if refreshed:
                    request.session["google_token"] = refreshed
                    access_token = refreshed["access_token"]
                else:
                    has_google_access = False

            # Execute each tool call
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    print(f"  Tool call [{iterations}]: {block.name}({block.input})")
                    tool_calls_log.append({
                        "iteration": iterations,
                        "name": block.name,
                        "input": block.input,
                    })

                    is_google = block.name in _GOOGLE_TOOL_NAMES
                    if is_google and not has_google_access:
                        result_text = (
                            "ERROR: Google access is no longer available. "
                            "Ask the user to sign out and sign back in."
                        )
                    else:
                        result_text = await execute_tool(
                            tool_name=block.name,
                            tool_input=block.input,
                            access_token=access_token,
                            harvest_access_token=harvest_access_token,
                            harvest_user_id=harvest_user_id_for_tools,
                            user_dialect=user_dialect_for_tools,
                        )

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_text,
                    })

            messages.append({"role": "user", "content": tool_results})

        else:
            # Unexpected stop reason (max_tokens, etc.)
            text_parts = []
            for block in response.content:
                if hasattr(block, "text"):
                    text_parts.append(block.text)
            final_text = "\n".join(text_parts) if text_parts else (
                "I ran into an issue processing that. Could you try again?"
            )
            break

    # Safety: if max iterations hit without end_turn
    if iterations >= MAX_TOOL_ITERATIONS and not final_text and response:
        text_parts = []
        for block in response.content:
            if hasattr(block, "text"):
                text_parts.append(block.text)
        final_text = "\n".join(text_parts) if text_parts else (
            "I've gathered information but hit my processing limit. "
            "Let me know if you'd like me to continue."
        )

    # Parse any entries from the response
    display_text, entries_data = parse_entries_from_response(final_text)

    # Save chat messages to Supabase
    harvest_mock.save_chat_message(req.user, "user", req.message)
    harvest_mock.save_chat_message(req.user, "assistant", display_text)

    # Save entries to Supabase + Sheets + Harvest
    created_entries = []
    for entry_data in entries_data:
        entry = save_entry_everywhere(
            req.user,
            entry_data,
            user_email=user.get("email", ""),
            fallback_date=req.selected_date,
        )
        created_entries.append(entry)

    # Capture this round for fine-tuning + analytics. Stash the interaction id on
    # each created entry so future approve/edit/delete events can reference it.
    profile_snapshot = user_profiles.get_profile(user.get("email", ""))
    interaction_id = training_log.log(
        kind="chat",
        user_email=user.get("email", ""),
        user_name=user.get("name", ""),
        input_payload={
            "message": req.message,
            "history_len": len(req.history),
            "model": CHAT_MODEL,
            "system_prompt_hash": training_log.prompt_signature(system_blocks),
            "has_google_access": has_google_access,
            "has_harvest_access": bool(harvest_access_token),
        },
        context={
            "dialect": profile_snapshot.get("dialect"),
            "assigned_project_count": len(profile_snapshot.get("assigned_project_codes") or []),
            "common_tasks_count": len(profile_snapshot.get("common_tasks") or []),
            "recent_corrections_count": len(profile_snapshot.get("recent_corrections") or []),
        },
        output={
            "response_text": display_text,
            "tool_calls": tool_calls_log,
            "iterations": iterations,
            "stop_reason": getattr(response, "stop_reason", None) if response else None,
            "entries_created": [
                {
                    "id": e.get("id"),
                    "client": e.get("client"),
                    "project_code": e.get("project_code"),
                    "project_name": e.get("project_name"),
                    "hours": e.get("hours"),
                    "status": e.get("status"),
                }
                for e in created_entries
            ],
        },
        metrics={
            "latency_ms": int((time.time() - chat_start_ts) * 1000),
            **last_usage,
        },
    )
    for e in created_entries:
        e["_interaction_id"] = interaction_id

    return ChatResponse(response=display_text, entries_created=created_entries)


# --- Streaming chat (SSE) — same logic as /api/chat but the FINAL Claude
#     response is streamed token-by-token for immediate TTFT to the user.
#     Tool-using turns still wait for tool execution server-side, but the
#     synthesis after tool runs streams. Frontend uses fetch + ReadableStream.

def _sse(event: Dict) -> bytes:
    """Format a dict as a single Server-Sent Event line."""
    return f"data: {json.dumps(event)}\n\n".encode("utf-8")


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest, request: Request):
    """SSE-streamed version of /api/chat. Yields:
      - {"type":"status","message":"..."} setup progress (Connecting, Loading, Thinking)
      - {"type":"text","delta":"..."}    incremental text tokens
      - {"type":"tool","name":"..."}     when a tool call starts
      - {"type":"done","response":...,"entries_created":[...]}  final
      - {"type":"error","message":"..."} on failure

    Setup work (token refresh, project fetch, prompt build) runs INSIDE
    the generator so the HTTP response starts streaming within ~50ms and
    the client sees activity immediately. Previously this work ran in the
    request handler before StreamingResponse was returned, which made
    every chat appear hung for 3-30s before the first byte arrived.
    """
    user = get_current_user(request)
    if not user:
        async def _unauth():
            yield _sse({"type": "error", "message": "Please log in first."})
        return StreamingResponse(_unauth(), media_type="text/event-stream")

    allowed, retry_after = rate_limit.check_and_consume(user.get("email", ""))
    if not allowed:
        async def _rl():
            yield _sse({
                "type": "error",
                "message": (
                    f"You're sending messages faster than I can keep up. "
                    f"Try again in {int(retry_after) + 1}s."
                ),
            })
        return StreamingResponse(_rl(), media_type="text/event-stream")

    async def gen():
        chat_start_ts = time.time()
        # Send a connection confirmation IMMEDIATELY so the browser opens
        # the stream and shows the typing indicator. ~50ms TTFT regardless
        # of how slow the downstream setup is.
        yield _sse({"type": "status", "message": "Connecting..."})

        # === Setup phase — was previously OUTSIDE the generator ===
        setup_t0 = time.time()
        messages: List[Dict] = []
        for msg in req.history:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": req.message})

        google_token = request.session.get("google_token")
        has_google_access = False
        access_token = None
        if google_token and google_token.get("access_token"):
            valid_token = calendar_sync.ensure_valid_token(google_token)
            if valid_token:
                request.session["google_token"] = valid_token
                access_token = valid_token["access_token"]
                has_google_access = True

        harvest_token = request.session.get("harvest_token")
        harvest_access_token = None
        if harvest_token and harvest_token.get("access_token"):
            valid_token = harvest_oauth.ensure_valid_token(harvest_token)
            if valid_token:
                request.session["harvest_token"] = valid_token
                harvest_access_token = valid_token["access_token"]

        token_validate_ms = int((time.time() - setup_t0) * 1000)
        yield _sse({"type": "status", "message": "Loading your projects..."})

        runtime_notes: List[str] = []
        if not has_google_access:
            runtime_notes.append(
                "NOTE: The user has not granted Google Workspace access. "
                "If they ask to scan emails, calendar, or drive, tell them to sign out "
                "and sign back in to grant the required permissions."
            )
        if not harvest_access_token:
            runtime_notes.append(
                "NOTE: The user has not connected their Harvest account. "
                "If they try to log time, tell them to click 'Connect Harvest' first."
            )

        if req.selected_date:
            runtime_notes.append(_selected_date_note(req.selected_date))

        today_note = _build_today_summary_note(user.get("email", ""), harvest_access_token)
        if today_note:
            runtime_notes.append(today_note)

        prompt_t0 = time.time()
        # Async build — uses httpx.AsyncClient + asyncio.gather under the hood
        # so the 51 Harvest task_assignments calls run truly concurrent on the
        # same connection pool. Cold-cache fetch dropped from ~44s to ~1s.
        system_blocks = await build_system_prompt_async(
            user_email=user.get("email"),
            harvest_access_token=harvest_access_token,
            notes=runtime_notes,
        )
        prompt_build_ms = int((time.time() - prompt_t0) * 1000)
        tools_param = _tools_for_user(has_google_access, bool(harvest_access_token))
        profile_for_tools = user_profiles.get_profile(user.get("email", ""))
        user_dialect_for_tools = profile_for_tools.get("dialect")
        harvest_user_id_for_tools = profile_for_tools.get("harvest_user_id")

        yield _sse({"type": "status", "message": "Thinking..."})
        print(
            f"[chat_stream] setup: token_validate={token_validate_ms}ms "
            f"prompt_build={prompt_build_ms}ms google={has_google_access} "
            f"harvest={bool(harvest_access_token)}"
        )
        tool_calls_log: List[Dict] = []
        last_usage: Dict = {}
        iterations = 0
        final_text_parts: List[str] = []
        last_response = None

        try:
            while iterations < MAX_TOOL_ITERATIONS:
                iterations += 1
                api_kwargs = {
                    "model": CHAT_MODEL,
                    "max_tokens": 2048,
                    "system": system_blocks,
                    "messages": messages,
                }
                if tools_param:
                    api_kwargs["tools"] = tools_param

                # Stream this iteration. Anthropic SDK's `stream()` is an async
                # context manager. Text deltas forward immediately to the
                # client; tool_use blocks are accumulated then executed.
                async with client.messages.stream(**api_kwargs) as stream:
                    iter_text = ""
                    async for text in stream.text_stream:
                        iter_text += text
                        yield _sse({"type": "text", "delta": text})
                    last_response = await stream.get_final_message()

                last_usage = training_log.usage_metrics(last_response)

                if last_response.stop_reason == "end_turn":
                    final_text_parts.append(iter_text)
                    break

                if last_response.stop_reason == "tool_use":
                    messages.append({"role": "assistant", "content": last_response.content})

                    if has_google_access:
                        refreshed = calendar_sync.ensure_valid_token(
                            request.session.get("google_token", {})
                        )
                        if refreshed:
                            request.session["google_token"] = refreshed
                            access_token2 = refreshed["access_token"]
                        else:
                            access_token2 = None
                    else:
                        access_token2 = None

                    tool_results = []
                    for block in last_response.content:
                        if getattr(block, "type", None) == "tool_use":
                            yield _sse({"type": "tool", "name": block.name})
                            tool_calls_log.append({
                                "iteration": iterations,
                                "name": block.name,
                                "input": block.input,
                            })
                            is_google_tool = block.name in _GOOGLE_TOOL_NAMES
                            if is_google_tool and not access_token2:
                                result_text = "ERROR: Google access is no longer available."
                            else:
                                result_text = await execute_tool(
                                    tool_name=block.name,
                                    tool_input=block.input,
                                    access_token=access_token2 or "",
                                    harvest_access_token=harvest_access_token,
                                    harvest_user_id=harvest_user_id_for_tools,
                                    user_dialect=user_dialect_for_tools,
                                )
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result_text,
                            })
                    messages.append({"role": "user", "content": tool_results})
                    final_text_parts.append(iter_text)  # any text before the tool call
                    continue

                # Other stop reasons (max_tokens, etc.) — break with what we have.
                final_text_parts.append(iter_text)
                break

            full_text = "".join(final_text_parts)
            display_text, entries_data = parse_entries_from_response(full_text)

            harvest_mock.save_chat_message(req.user, "user", req.message)
            harvest_mock.save_chat_message(req.user, "assistant", display_text)

            created_entries = []
            for entry_data in entries_data:
                entry = save_entry_everywhere(
                    req.user,
                    entry_data,
                    user_email=user.get("email", ""),
                    fallback_date=req.selected_date,
                )
                created_entries.append(entry)

            profile_snapshot = user_profiles.get_profile(user.get("email", ""))
            interaction_id = training_log.log(
                kind="chat",
                user_email=user.get("email", ""),
                user_name=user.get("name", ""),
                input_payload={
                    "message": req.message,
                    "history_len": len(req.history),
                    "model": CHAT_MODEL,
                    "system_prompt_hash": training_log.prompt_signature(system_blocks),
                    "has_google_access": has_google_access,
                    "has_harvest_access": bool(harvest_access_token),
                    "streamed": True,
                },
                context={
                    "dialect": profile_snapshot.get("dialect"),
                    "assigned_project_count": len(profile_snapshot.get("assigned_project_codes") or []),
                    "common_tasks_count": len(profile_snapshot.get("common_tasks") or []),
                    "recent_corrections_count": len(profile_snapshot.get("recent_corrections") or []),
                },
                output={
                    "response_text": display_text,
                    "tool_calls": tool_calls_log,
                    "iterations": iterations,
                    "stop_reason": getattr(last_response, "stop_reason", None) if last_response else None,
                    "entries_created": [
                        {
                            "id": e.get("id"),
                            "client": e.get("client"),
                            "project_code": e.get("project_code"),
                            "project_name": e.get("project_name"),
                            "hours": e.get("hours"),
                            "status": e.get("status"),
                        }
                        for e in created_entries
                    ],
                },
                metrics={
                    "latency_ms": int((time.time() - chat_start_ts) * 1000),
                    **last_usage,
                },
            )
            for e in created_entries:
                e["_interaction_id"] = interaction_id

            yield _sse({
                "type": "done",
                "response": display_text,
                "entries_created": created_entries,
            })
        except Exception as e:
            # Print full error to Render logs for debugging; show clean
            # user-facing message in the chat bubble.
            print(f"[ERR] chat_stream: {type(e).__name__}: {str(e)[:500]}")
            yield _sse({"type": "error", "message": _user_friendly_anthropic_error(e)})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering on proxies
            "Connection": "keep-alive",
        },
    )


@app.post("/api/entries/approve-all")
async def approve_all_entries(request: Request):
    """Approve all draft entries for the current user."""
    user = get_current_user(request)
    if not user:
        return {"success": False, "error": "Not authenticated"}

    # Get and validate Harvest token
    harvest_token = request.session.get("harvest_token")
    if not harvest_token:
        # Fallback to PAT if no OAuth token (backward compatibility)
        harvest_access_token = None
    else:
        valid_token = harvest_oauth.ensure_valid_token(harvest_token)
        if valid_token:
            request.session["harvest_token"] = valid_token
            harvest_access_token = valid_token["access_token"]
        else:
            return {"success": False, "error": "Harvest token expired"}

    body = await request.json()
    user_name = body.get("user", user.get("name", ""))
    user_email = user.get("email", "")
    local_today_iso = _today_local_iso(user_email)

    entries = harvest_mock.get_entries(user=user_name)
    drafts = [e for e in entries if e.get("status") in ("Draft", "Needs Review")]

    results = []
    for entry in drafts:
        harvest_user_id = harvest_api.resolve_user_id(user_email, harvest_access_token) if user_email else None

        # Try direct IDs from project_code first (format: "projectId-taskId")
        harvest_entry = None
        push_error: Optional[str] = None
        project_code = entry.get("project_code", "")
        if project_code and "-" in project_code:
            parts = project_code.split("-", 1)
            try:
                pid, tid = int(parts[0]), int(parts[1])
                harvest_entry = harvest_api.create_time_entry(
                    project_id=pid,
                    task_id=tid,
                    spent_date=entry.get("date", local_today_iso),
                    hours=float(entry.get("hours", 0)),
                    notes=entry.get("notes", ""),
                    user_id=harvest_user_id,
                    access_token=harvest_access_token,
                    task_name=entry.get("project_name", entry.get("task", "")),
                )
            except (ValueError, TypeError) as e:
                push_error = f"bad project_code format ({e})"

        # Fallback to name resolution
        if not harvest_entry:
            harvest_entry = harvest_api.push_entry(
                client_name=entry.get("client", ""),
                task_name=entry.get("project_name", entry.get("task", "")),
                spent_date=entry.get("date", local_today_iso),
                hours=float(entry.get("hours", 0)),
                notes=entry.get("notes", ""),
                user_id=harvest_user_id,
                access_token=harvest_access_token,
            )
            if not harvest_entry and not push_error:
                push_error = (
                    f"Harvest could not resolve project '{entry.get('client','')}' "
                    f"+ task '{entry.get('project_name', entry.get('task',''))}' "
                    "— project may be inactive or task name doesn't match."
                )

        if harvest_entry:
            harvest_mock.update_entry(entry["id"], status="Approved", harvest_id=harvest_entry["id"])
            sheets_sync.update_entry_status_in_sheet(entry["id"], "Approved")
            user_profiles.record_approval(user_email, entry)
            if harvest_user_id:
                harvest_api.invalidate_today_cache(harvest_user_id, entry.get("date"))
            training_log.log(
                kind="approve",
                user_email=user_email,
                user_name=user.get("name", ""),
                input_payload={"entry_id": entry["id"], "via": "approve_all"},
                output={
                    "client": entry.get("client"),
                    "project_code": entry.get("project_code"),
                    "project_name": entry.get("project_name"),
                    "hours": entry.get("hours"),
                    "harvest_id": harvest_entry["id"],
                },
            )
            results.append({"id": entry["id"], "approved": True})
        else:
            # Surface the underlying reason so the frontend / user can see
            # why the push failed instead of an opaque "approved: false".
            results.append({
                "id": entry["id"],
                "approved": False,
                "error": push_error or "unknown Harvest push failure",
                "client": entry.get("client", ""),
                "task": entry.get("project_name", entry.get("task", "")),
            })

    return {"success": True, "results": results}


@app.get("/api/entries/{user}")
async def get_entries(user: str, entry_date: str = None):
    entries = harvest_mock.get_entries(user=user, entry_date=entry_date)
    summary = harvest_mock.get_user_summary(user=user, entry_date=entry_date)
    return {"entries": entries, "summary": summary}


@app.delete("/api/entries/{entry_id}")
async def delete_entry(entry_id: str, request: Request):
    # Get Harvest token for deletion (optional - falls back to PAT)
    harvest_token = request.session.get("harvest_token")
    harvest_access_token = None
    if harvest_token:
        valid_token = harvest_oauth.ensure_valid_token(harvest_token)
        if valid_token:
            request.session["harvest_token"] = valid_token
            harvest_access_token = valid_token["access_token"]

    # Check if entry has a Harvest ID before deleting
    entries = harvest_mock.get_entries()
    harvest_id = None
    deleted_snapshot: Dict = {}
    for e in entries:
        if e.get("id") == entry_id:
            deleted_snapshot = {
                "client": e.get("client"),
                "project_code": e.get("project_code"),
                "project_name": e.get("project_name"),
                "hours": e.get("hours"),
                "status": e.get("status"),
            }
            if e.get("harvest_id"):
                harvest_id = e["harvest_id"]
            break
    success = harvest_mock.delete_entry(entry_id)
    if success:
        sheets_sync.delete_entry_from_sheet(entry_id)
        if harvest_id:
            harvest_api.delete_time_entry(int(harvest_id), harvest_access_token)
        # Training-data signal: rejection of an AI-suggested or user-created entry
        user = get_current_user(request) or {}
        training_log.log(
            kind="delete",
            user_email=user.get("email", ""),
            user_name=user.get("name", ""),
            input_payload={"entry_id": entry_id},
            output=deleted_snapshot,
        )
    return {"success": success}


@app.put("/api/entries/{entry_id}")
async def update_entry(entry_id: str, request: Request):
    body = await request.json()
    # Snapshot the entry before mutating so we can capture the diff as training signal
    pre_entry: Dict = {}
    for e in harvest_mock.get_entries():
        if e.get("id") == entry_id:
            pre_entry = dict(e)
            break

    entry = harvest_mock.update_entry(entry_id, **body)
    if entry and "status" in body:
        sheets_sync.update_entry_status_in_sheet(entry_id, body["status"])

    if entry:
        diff = {
            k: {"from": pre_entry.get(k), "to": entry.get(k)}
            for k in body.keys()
            if pre_entry.get(k) != entry.get(k)
        }
        if diff:
            user = get_current_user(request) or {}
            training_log.log(
                kind="edit",
                user_email=user.get("email", ""),
                user_name=user.get("name", ""),
                input_payload={"entry_id": entry_id, "patch": body},
                output={"diff": diff},
            )
    return {"entry": entry, "success": entry is not None}


@app.post("/api/entries/{entry_id}/approve")
async def approve_entry(entry_id: str, request: Request):
    """Approve a draft entry: push to Harvest, update status."""
    user = get_current_user(request)
    if not user:
        return {"success": False, "error": "Not authenticated"}

    # Get and validate Harvest token
    harvest_token = request.session.get("harvest_token")
    if not harvest_token:
        # Fallback to PAT if no OAuth token (backward compatibility)
        harvest_access_token = None
    else:
        valid_token = harvest_oauth.ensure_valid_token(harvest_token)
        if valid_token:
            request.session["harvest_token"] = valid_token
            harvest_access_token = valid_token["access_token"]
        else:
            return {"success": False, "error": "Harvest token expired"}

    # Find the entry
    entries = harvest_mock.get_entries()
    entry = None
    for e in entries:
        if e.get("id") == entry_id:
            entry = e
            break

    if not entry:
        return {"success": False, "error": "Entry not found"}

    if entry.get("status") == "Approved":
        return {"success": False, "error": "Already approved"}

    # Push to Harvest
    print(f"Approve entry {entry_id}: client='{entry.get('client')}' project_code='{entry.get('project_code')}' task='{entry.get('project_name', entry.get('task'))}'")
    user_email = user.get("email", "")
    harvest_user_id = harvest_api.resolve_user_id(user_email, harvest_access_token) if user_email else None
    local_today_iso = _today_local_iso(user_email)

    # Try direct IDs from project_code first (format: "projectId-taskId")
    harvest_entry = None
    push_error: Optional[str] = None
    project_code = entry.get("project_code", "")
    if project_code and "-" in project_code:
        parts = project_code.split("-", 1)
        try:
            pid, tid = int(parts[0]), int(parts[1])
            harvest_entry = harvest_api.create_time_entry(
                project_id=pid,
                task_id=tid,
                spent_date=entry.get("date", local_today_iso),
                hours=float(entry.get("hours", 0)),
                notes=entry.get("notes", ""),
                user_id=harvest_user_id,
                access_token=harvest_access_token,
                task_name=entry.get("project_name", entry.get("task", "")),
            )
        except (ValueError, TypeError) as e:
            push_error = f"bad project_code format ({e})"

    # Fallback to name resolution
    if not harvest_entry:
        harvest_entry = harvest_api.push_entry(
            client_name=entry.get("client", ""),
            task_name=entry.get("project_name", entry.get("task", "")),
            spent_date=entry.get("date", local_today_iso),
            hours=float(entry.get("hours", 0)),
            notes=entry.get("notes", ""),
            user_id=harvest_user_id,
            access_token=harvest_access_token,
        )
        if not harvest_entry and not push_error:
            push_error = (
                f"Harvest could not resolve project '{entry.get('client','')}' "
                f"+ task '{entry.get('project_name', entry.get('task',''))}'. "
                "Verify the project is active and the task name matches Harvest."
            )

    if not harvest_entry:
        return {
            "success": False,
            "error": push_error or "Failed to push to Harvest",
            "client": entry.get("client", ""),
            "task": entry.get("project_name", entry.get("task", "")),
        }

    # Update Supabase
    harvest_mock.update_entry(entry_id, status="Approved", harvest_id=harvest_entry["id"])
    # Update Google Sheet
    sheets_sync.update_entry_status_in_sheet(entry_id, "Approved")
    # Per-user learning: bump common_tasks frequency + prepend to recent entries
    user_profiles.record_approval(user_email, entry)
    # Bust the today-summary cache so the next chat sees this entry immediately
    if harvest_user_id:
        harvest_api.invalidate_today_cache(harvest_user_id, entry.get("date"))
    # Training-data signal: positive label on the AI's original suggestion
    training_log.log(
        kind="approve",
        user_email=user_email,
        user_name=user.get("name", ""),
        input_payload={"entry_id": entry_id},
        output={
            "client": entry.get("client"),
            "project_code": entry.get("project_code"),
            "project_name": entry.get("project_name"),
            "hours": entry.get("hours"),
            "harvest_id": harvest_entry["id"],
        },
    )

    return {"success": True, "harvest_id": harvest_entry["id"]}


@app.get("/api/calendar/events")
async def get_calendar_events(request: Request, target_date: str = None):
    """Fetch the user's Google Calendar events for a given date."""
    user = get_current_user(request)
    if not user:
        return {"error": "Not authenticated", "events": []}

    google_token = request.session.get("google_token")
    if not google_token or not google_token.get("access_token"):
        return {"error": "no_calendar_access", "events": []}

    # Refresh token if expired
    valid_token = calendar_sync.ensure_valid_token(google_token)
    if not valid_token:
        return {"error": "token_expired", "events": []}

    # Update session with refreshed token
    request.session["google_token"] = valid_token

    events = calendar_sync.get_events(valid_token["access_token"], target_date)
    return {"events": events, "date": target_date or _today_local_iso(user.get("email", ""))}


@app.post("/api/calendar/suggest")
async def suggest_from_calendar(request: Request):
    """Fetch calendar events and ask Claude to suggest time entries."""
    user = get_current_user(request)
    if not user:
        return ChatResponse(response="Please log in first.", entries_created=[])

    body = await request.json()
    target_date = body.get("date")
    history = body.get("history", [])

    # Get calendar events
    google_token = request.session.get("google_token")
    if not google_token or not google_token.get("access_token"):
        return ChatResponse(
            response="I don't have access to your calendar. Please sign out and sign back in to grant calendar permission.",
            entries_created=[],
        )

    valid_token = calendar_sync.ensure_valid_token(google_token)
    if not valid_token:
        return ChatResponse(
            response="Your calendar access has expired. Please sign out and sign back in.",
            entries_created=[],
        )

    request.session["google_token"] = valid_token
    events = calendar_sync.get_events(valid_token["access_token"], target_date)

    if not events:
        return ChatResponse(
            response="No calendar events found for today. Tell me what you worked on and I'll log it manually.",
            entries_created=[],
        )

    # Format events and ask Claude to suggest entries
    events_text = calendar_sync.format_events_for_prompt(events, target_date)
    calendar_prompt = (
        f"I just pulled my calendar. Here are my events:\n\n{events_text}\n\n"
        "Can you suggest time entries for these? Map them to the Harvest projects where possible."
    )

    messages = []
    for msg in history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": calendar_prompt})

    try:
        response = await client.messages.create(
            model=CHAT_MODEL,
            max_tokens=1024,
            system=build_system_prompt(user_email=user.get("email")),
            messages=messages,
        )
    except Exception as anth_err:
        print(f"[ERR] /api/calendar/suggest anthropic call: {type(anth_err).__name__}: {str(anth_err)[:500]}")
        return ChatResponse(
            response=_user_friendly_anthropic_error(anth_err),
            entries_created=[],
        )

    ai_text = response.content[0].text
    display_text, entries_data = parse_entries_from_response(ai_text)

    # Save chat
    harvest_mock.save_chat_message(user["name"], "user", calendar_prompt)
    harvest_mock.save_chat_message(user["name"], "assistant", display_text)

    # Save entries to Supabase + Sheets + Harvest
    created_entries = []
    for entry_data in entries_data:
        entry = save_entry_everywhere(user["name"], entry_data, user_email=user.get("email", ""))
        created_entries.append(entry)

    return ChatResponse(response=display_text, entries_created=created_entries)


# --- 7-Day Calendar Summary (categorize meetings → projects) ---

CATEGORIZE_TOOL = {
    "name": "categorize_events",
    "description": (
        "Return structured Harvest project/task categorizations for the supplied "
        "calendar events. Must return one entry per event_index."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "categorizations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "event_index": {"type": "integer"},
                        "project_code": {
                            "type": "string",
                            "description": (
                                "Project+task code matching one of the candidates "
                                "(e.g. '38887238-67'). Empty string if confidence "
                                "is 'unknown'."
                            ),
                        },
                        "confidence": {
                            "type": "string",
                            "enum": ["high", "medium", "low", "unknown"],
                        },
                        "reasoning": {
                            "type": "string",
                            "description": "Under 30 words. Why this project/task?",
                        },
                    },
                    "required": ["event_index", "project_code", "confidence", "reasoning"],
                },
            },
        },
        "required": ["categorizations"],
    },
}


def _flatten_project_candidates(harvest_access_token: Optional[str], assigned_codes: set) -> List[Dict]:
    """Flatten the project list into (code, client, task_name, is_assigned) rows
    for Claude. Assigned-project tasks are ranked first so the model sees the
    user's normal work before the 51-project firehose."""
    projects = get_projects(harvest_access_token)
    flat = []
    for p in projects:
        for t in p["tasks"]:
            project_id_part = t["code"].split("-")[0] if "-" in t["code"] else ""
            flat.append({
                "code": t["code"],
                "client": p["project"],
                "task_name": t["name"],
                "is_assigned": project_id_part in assigned_codes,
            })
    flat.sort(key=lambda r: (not r["is_assigned"], r["client"]))
    return flat


def _enrich_event(ev: Dict, cat: Dict, candidates_by_code: Dict[str, Dict]) -> Dict:
    """Combine a raw calendar event with its categorization + project lookup."""
    code = cat.get("project_code", "")
    candidate = candidates_by_code.get(code, {})
    return {
        "id": ev["id"],
        "date": ev["date"],
        "start": ev["start"],
        "end": ev["end"],
        "duration_hours": ev["duration_hours"],
        "title": ev["summary"],
        "attendees": ev["attendees"][:5],
        "is_recurring": ev["is_recurring"],
        "recurring_event_id": ev["recurring_event_id"],
        "suggested_project_code": code,
        "suggested_client": candidate.get("client", ""),
        "suggested_task_name": candidate.get("task_name", ""),
        "confidence": cat.get("confidence", "unknown"),
        "reasoning": cat.get("reasoning", ""),
        "was_declined": ev.get("was_declined", False),
    }


async def categorize_events(
    events: List[Dict],
    user_email: str,
    harvest_access_token: Optional[str],
) -> List[Dict]:
    """One Claude call → constrained tool_use output → list aligned to events."""
    if not events:
        return []

    profile = user_profiles.get_profile(user_email)
    assigned_codes = set(profile.get("assigned_project_codes") or [])
    candidates = _flatten_project_candidates(harvest_access_token, assigned_codes)

    # Compact event list — keep it small. Use attendee email *domains* only
    # (that's the categorization signal; full PII isn't needed in the prompt).
    events_compact = []
    for i, ev in enumerate(events):
        domains = sorted({
            e.split("@", 1)[1].lower()
            for e in ev.get("attendee_emails", [])
            if "@" in e
        })
        events_compact.append({
            "event_index": i,
            "date": ev["date"],
            "start": ev["start"],
            "duration_hours": ev["duration_hours"],
            "title": ev["summary"],
            "attendee_domains": domains,
            "is_recurring": ev["is_recurring"],
        })

    user_prompt = (
        f"Categorize these {len(events)} calendar events to a Harvest project+task code.\n\n"
        f"EVENTS:\n{json.dumps(events_compact, indent=2)}\n\n"
        f"PROJECT CANDIDATES (is_assigned=true means the user normally works on this):\n"
        f"{json.dumps(candidates, indent=2)}\n\n"
        "Return one categorization per event using the categorize_events tool.\n\n"
        "Confidence rules:\n"
        "- high: attendee domain matches client name OR exact title match for assigned project\n"
        "- medium: title keyword strongly suggests project, no domain confirmation\n"
        "- low: weak/ambiguous signal\n"
        "- unknown: no signal — return empty project_code\n\n"
        "Prefer is_assigned=true projects when ambiguous. Internal meetings "
        "(standup, all-hands, 1:1 with Thrive teammates) → use the 'Internal' "
        "project if present, otherwise mark unknown."
    )

    try:
        response = await client.messages.create(
            model=CHAT_MODEL,
            max_tokens=4096,
            system=build_system_prompt(
                user_email=user_email,
                harvest_access_token=harvest_access_token,
            ),
            tools=[CATEGORIZE_TOOL],
            tool_choice={"type": "tool", "name": "categorize_events"},
            messages=[{"role": "user", "content": user_prompt}],
        )
    except Exception as anth_err:
        # Fall back to "unknown" categorizations for every event so the UI
        # can still render the meeting list — user can manually pick projects.
        print(f"[ERR] categorize_events anthropic call: {type(anth_err).__name__}: {str(anth_err)[:500]}")
        candidates_by_code = {c["code"]: c for c in candidates}
        return [
            _enrich_event(ev, {
                "event_index": i,
                "project_code": "",
                "confidence": "unknown",
                "reasoning": _user_friendly_anthropic_error(anth_err),
            }, candidates_by_code)
            for i, ev in enumerate(events)
        ]

    raw_cats: List[Dict] = []
    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "categorize_events":
            raw_cats = block.input.get("categorizations", [])
            break

    cat_by_idx = {c.get("event_index"): c for c in raw_cats}
    candidates_by_code = {c["code"]: c for c in candidates}

    enriched = []
    for i, ev in enumerate(events):
        cat = cat_by_idx.get(i, {
            "event_index": i,
            "project_code": "",
            "confidence": "unknown",
            "reasoning": "Model returned no categorization for this event.",
        })
        enriched.append(_enrich_event(ev, cat, candidates_by_code))
    return enriched


@app.get("/api/calendar/weekly-summary")
async def calendar_weekly_summary(request: Request, weeks: int = 1):
    """Pull the user's last N weeks of meetings, categorize each via Claude, and
    return them grouped by day with confidence dots so the UI can surface only
    the rows that need user review."""
    user = get_current_user(request)
    if not user:
        return {"error": "not_authenticated", "days": []}

    # This endpoint runs one Claude call but typically processes 10-30 events
    # in one go, so charge it 3 tokens against the bucket (heavier than a chat).
    allowed, retry_after = rate_limit.check_and_consume(user.get("email", ""), cost=3.0)
    if not allowed:
        return {
            "error": "rate_limited",
            "retry_after_seconds": int(retry_after) + 1,
            "days": [],
        }

    weeks = max(1, min(weeks, 4))  # cap at 4 weeks to keep one Claude call sane

    google_token = request.session.get("google_token")
    if not google_token or not google_token.get("access_token"):
        return {"error": "no_calendar_access", "days": []}

    valid_token = calendar_sync.ensure_valid_token(google_token)
    if not valid_token:
        return {"error": "token_expired", "days": []}
    request.session["google_token"] = valid_token

    today = time_utils.today_local(_user_dialect(user.get("email", "")))
    date_from = (today - timedelta(days=weeks * 7 - 1)).isoformat()
    date_to = today.isoformat()

    events = calendar_sync.search_events(
        access_token=valid_token["access_token"],
        date_from=date_from,
        date_to=date_to,
    )

    # Get Harvest token (optional) so we can show user-specific project candidates
    harvest_token = request.session.get("harvest_token")
    harvest_access_token = None
    if harvest_token and harvest_token.get("access_token"):
        valid_h = harvest_oauth.ensure_valid_token(harvest_token)
        if valid_h:
            request.session["harvest_token"] = valid_h
            harvest_access_token = valid_h["access_token"]

    cat_start_ts = time.time()
    enriched = await categorize_events(events, user["email"], harvest_access_token)
    cat_latency_ms = int((time.time() - cat_start_ts) * 1000)

    # Build the candidates list once for the frontend dropdowns (so users can
    # re-categorize low/unknown rows without a second round-trip per event).
    profile = user_profiles.get_profile(user["email"])
    assigned_codes = set(profile.get("assigned_project_codes") or [])
    candidates = _flatten_project_candidates(harvest_access_token, assigned_codes)

    # Group by day, oldest first
    by_day: Dict[str, List[Dict]] = {}
    for ev in enriched:
        by_day.setdefault(ev["date"], []).append(ev)

    days = []
    for d in sorted(by_day.keys()):
        evs = by_day[d]
        days.append({
            "date": d,
            "day_label": datetime.strptime(d, "%Y-%m-%d").strftime("%a"),
            "hours_total": round(sum(e["duration_hours"] for e in evs), 2),
            "events": evs,
        })

    ready = sum(
        1 for ev in enriched
        if ev["confidence"] in ("high", "medium") and ev["suggested_project_code"]
    )
    needs_review = len(enriched) - ready

    confidence_breakdown = {"high": 0, "medium": 0, "low": 0, "unknown": 0}
    for ev in enriched:
        confidence_breakdown[ev.get("confidence", "unknown")] = (
            confidence_breakdown.get(ev.get("confidence", "unknown"), 0) + 1
        )

    training_log.log(
        kind="weekly_categorize",
        user_email=user["email"],
        user_name=user.get("name", ""),
        input_payload={
            "weeks": weeks,
            "date_from": date_from,
            "date_to": date_to,
            "event_count": len(events),
            "model": CHAT_MODEL,
        },
        context={
            "assigned_project_count": len(assigned_codes),
            "confidence_breakdown": confidence_breakdown,
        },
        output={
            "events": [
                {
                    "id": ev["id"],
                    "title": ev["title"],
                    "date": ev["date"],
                    "suggested_project_code": ev["suggested_project_code"],
                    "suggested_client": ev["suggested_client"],
                    "suggested_task_name": ev["suggested_task_name"],
                    "confidence": ev["confidence"],
                    "reasoning": ev["reasoning"],
                }
                for ev in enriched
            ],
        },
        metrics={"latency_ms": cat_latency_ms},
    )

    return {
        "range": {"from": date_from, "to": date_to, "weeks": weeks},
        "totals": {
            "events": len(enriched),
            "hours": round(sum(e["duration_hours"] for e in enriched), 2),
            "ready": ready,
            "needs_review": needs_review,
        },
        "days": days,
        "candidates": candidates,
    }


class CategorizeRequest(BaseModel):
    event_id: str
    event_date: str
    event_title: str
    event_duration_hours: float
    project_code: str
    client: str
    task_name: str
    create_draft: bool = True
    original_client: Optional[str] = ""
    original_task_name: Optional[str] = ""


@app.post("/api/calendar/categorize")
async def calendar_categorize(req: CategorizeRequest, request: Request):
    """Record a user's manual categorization of a calendar event. If
    create_draft=true, also creates a Draft entry. If this corrects a previous
    AI suggestion, records the diff in the user's profile so the next prompt
    can avoid repeating the miss."""
    user = get_current_user(request)
    if not user:
        return {"success": False, "error": "not_authenticated"}

    user_email = user.get("email", "")

    # Record the correction (if it's actually a correction)
    if req.original_client and (
        req.original_client.lower() != req.client.lower()
        or (req.original_task_name or "").lower() != req.task_name.lower()
    ):
        user_profiles.record_correction(
            email=user_email,
            user_phrase=f"Calendar event: {req.event_title}",
            original={"client": req.original_client, "project_name": req.original_task_name or ""},
            corrected={"client": req.client, "project_name": req.task_name},
        )

    created_entry = None
    if req.create_draft:
        entry_data = {
            "client": req.client,
            "project_code": req.project_code,
            "project_name": req.task_name,
            "task": req.task_name,
            "hours": req.event_duration_hours,
            "notes": f"Meeting: {req.event_title}",
            "date": req.event_date,
            "status": "Draft",
        }
        created_entry = save_entry_everywhere(
            user.get("name", user_email),
            entry_data,
            user_email=user_email,
        )

    training_log.log(
        kind="categorize_correction" if req.original_client else "categorize_confirm",
        user_email=user_email,
        user_name=user.get("name", ""),
        input_payload={
            "event_id": req.event_id,
            "event_title": req.event_title,
            "event_date": req.event_date,
            "event_duration_hours": req.event_duration_hours,
        },
        output={
            "chosen": {
                "project_code": req.project_code,
                "client": req.client,
                "task_name": req.task_name,
            },
            "original_suggestion": {
                "client": req.original_client or "",
                "task_name": req.original_task_name or "",
            },
            "create_draft": req.create_draft,
            "entry_id": (created_entry or {}).get("id"),
        },
    )

    return {"success": True, "entry": created_entry}


@app.post("/api/drive/suggest")
async def suggest_from_drive(request: Request):
    """Fetch Drive activity and ask Claude to suggest time entries."""
    user = get_current_user(request)
    if not user:
        return ChatResponse(response="Please log in first.", entries_created=[])

    body = await request.json()
    target_date = body.get("date")
    history = body.get("history", [])

    google_token = request.session.get("google_token")
    if not google_token or not google_token.get("access_token"):
        return ChatResponse(
            response="I don't have access to your Google Drive. Please sign out and sign back in to grant permission.",
            entries_created=[],
        )

    valid_token = calendar_sync.ensure_valid_token(google_token)
    if not valid_token:
        return ChatResponse(
            response="Your Google access has expired. Please sign out and sign back in.",
            entries_created=[],
        )

    request.session["google_token"] = valid_token
    files = drive_sync.get_recent_files(valid_token["access_token"], target_date)

    if not files:
        return ChatResponse(
            response="No Google Drive activity found for today. Tell me what you worked on and I'll log it manually.",
            entries_created=[],
        )

    files_text = drive_sync.format_files_for_prompt(files, target_date)
    drive_prompt = (
        f"I just pulled my Google Drive activity. Here are the files I edited today:\n\n{files_text}\n\n"
        "Can you suggest time entries based on these? Map them to the Harvest projects where possible. "
        "Ask me about anything you're unsure of."
    )

    messages = []
    for msg in history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": drive_prompt})

    try:
        response = await client.messages.create(
            model=CHAT_MODEL,
            max_tokens=1024,
            system=build_system_prompt(user_email=user.get("email")),
            messages=messages,
        )
    except Exception as anth_err:
        print(f"[ERR] /api/drive/suggest anthropic call: {type(anth_err).__name__}: {str(anth_err)[:500]}")
        return ChatResponse(
            response=_user_friendly_anthropic_error(anth_err),
            entries_created=[],
        )

    ai_text = response.content[0].text
    display_text, entries_data = parse_entries_from_response(ai_text)

    harvest_mock.save_chat_message(user["name"], "user", drive_prompt)
    harvest_mock.save_chat_message(user["name"], "assistant", display_text)

    # Save entries to Supabase + Sheets + Harvest
    created_entries = []
    for entry_data in entries_data:
        entry = save_entry_everywhere(user["name"], entry_data, user_email=user.get("email", ""))
        created_entries.append(entry)

    return ChatResponse(response=display_text, entries_created=created_entries)


@app.post("/api/gmail/suggest")
async def suggest_from_gmail(request: Request):
    """Fetch email activity and ask Claude to suggest time entries."""
    user = get_current_user(request)
    if not user:
        return ChatResponse(response="Please log in first.", entries_created=[])

    body = await request.json()
    target_date = body.get("date")
    history = body.get("history", [])

    google_token = request.session.get("google_token")
    if not google_token or not google_token.get("access_token"):
        return ChatResponse(
            response="I don't have access to your Gmail. Please sign out and sign back in to grant permission.",
            entries_created=[],
        )

    valid_token = calendar_sync.ensure_valid_token(google_token)
    if not valid_token:
        return ChatResponse(
            response="Your Google access has expired. Please sign out and sign back in.",
            entries_created=[],
        )

    request.session["google_token"] = valid_token
    emails = gmail_sync.get_recent_emails(valid_token["access_token"], target_date)

    if not emails:
        return ChatResponse(
            response="No email activity found for today. Tell me what you worked on and I'll log it manually.",
            entries_created=[],
        )

    emails_text = gmail_sync.format_emails_for_prompt(emails, target_date)
    gmail_prompt = (
        f"I just pulled my email activity. Here are the emails from today:\n\n{emails_text}\n\n"
        "Can you suggest time entries based on these? Map them to the Harvest projects where possible. "
        "Group related emails together and estimate time spent. Ask me about anything you're unsure of."
    )

    messages = []
    for msg in history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": gmail_prompt})

    try:
        response = await client.messages.create(
            model=CHAT_MODEL,
            max_tokens=1024,
            system=build_system_prompt(user_email=user.get("email")),
            messages=messages,
        )
    except Exception as anth_err:
        print(f"[ERR] /api/gmail/suggest anthropic call: {type(anth_err).__name__}: {str(anth_err)[:500]}")
        return ChatResponse(
            response=_user_friendly_anthropic_error(anth_err),
            entries_created=[],
        )

    ai_text = response.content[0].text
    display_text, entries_data = parse_entries_from_response(ai_text)

    harvest_mock.save_chat_message(user["name"], "user", gmail_prompt)
    harvest_mock.save_chat_message(user["name"], "assistant", display_text)

    created_entries = []
    for entry_data in entries_data:
        entry = save_entry_everywhere(user["name"], entry_data, user_email=user.get("email", ""))
        created_entries.append(entry)

    return ChatResponse(response=display_text, entries_created=created_entries)


@app.get("/api/me")
async def get_me(request: Request):
    user = get_current_user(request)
    if not user:
        return {"authenticated": False}
    has_calendar = bool(request.session.get("google_token", {}).get("access_token"))
    has_harvest = bool(request.session.get("harvest_token", {}).get("access_token"))
    profile = user_profiles.get_profile(user.get("email", ""))
    return {
        "authenticated": True,
        "has_calendar": has_calendar,
        "has_harvest": has_harvest,
        "dialect": profile.get("dialect") or "en-AU-Sydney",
        "display_name": profile.get("display_name") or user.get("name", ""),
        **user,
    }


@app.get("/api/today/summary")
async def today_summary(request: Request):
    """Today's existing Harvest entries for the logged-in user.

    Used by the frontend to surface a one-line 'you've already logged Xh today'
    banner on page load, so the user doesn't accidentally re-log work the AI
    can't see in the local entries panel (e.g. entries created via Harvest
    web UI, or yesterday's leftovers approved this morning)."""
    user = get_current_user(request)
    if not user:
        return {"authenticated": False, "entries": [], "total_hours": 0.0}

    harvest_token = request.session.get("harvest_token") or {}
    access_token = harvest_token.get("access_token")
    if not access_token:
        return {"authenticated": True, "connected": False, "entries": [], "total_hours": 0.0}

    profile = user_profiles.get_profile(user.get("email", ""))
    hid = profile.get("harvest_user_id")
    if not hid:
        return {"authenticated": True, "connected": True, "entries": [], "total_hours": 0.0}

    try:
        local_today = time_utils.today_iso_local(profile.get("dialect"))
        entries = harvest_api.get_today_entries_cached(
            hid, access_token, spent_date=local_today
        )
        compact = []
        total = 0.0
        for e in entries:
            hrs = float(e.get("hours") or 0)
            total += hrs
            compact.append({
                "client": (e.get("client") or {}).get("name") or "",
                "project": (e.get("project") or {}).get("name") or "",
                "task": (e.get("task") or {}).get("name") or "",
                "hours": hrs,
                "notes": (e.get("notes") or "").strip(),
            })
        return {
            "authenticated": True,
            "connected": True,
            "entries": compact,
            "total_hours": round(total, 2),
        }
    except Exception as e:
        print(f"[WARN] /api/today/summary failed: {e}")
        return {"authenticated": True, "connected": True, "entries": [], "total_hours": 0.0}


@app.get("/api/chat/recent")
async def chat_recent(request: Request, limit: int = 10, days: int = 1):
    """Return the last N chat messages from the last `days` days so the page
    can resume an abandoned conversation.

    Hugh asked for multi-day resume — he'd progressed in a chat last week and
    couldn't see it. Default stays 1 day so we don't dump a week of history
    into the model on every page load (token cost + cache invalidation), but
    callers can request up to 14 days.

    The day cutoff is computed in the user's local timezone, so an AU user
    who opens the app at 9am Wednesday sees Wednesday's history (today) —
    not the prior calendar day in UTC."""
    user = get_current_user(request)
    if not user:
        return {"authenticated": False, "messages": []}
    user_name = user.get("name", "")
    try:
        msgs = harvest_mock.get_chat_history(user_name, limit=max(1, min(limit, 200))) or []
    except Exception as e:
        print(f"[WARN] /api/chat/recent failed: {e}")
        return {"authenticated": True, "messages": []}

    days = max(1, min(days, 14))
    user_email = user.get("email", "")
    cutoff = time_utils.today_local(_user_dialect(user_email)) - timedelta(days=days - 1)
    cutoff_iso = cutoff.isoformat()
    keep: List[Dict] = []
    for m in msgs:
        ts = (m.get("created_at") or m.get("ts") or "")
        # Stored timestamps are UTC ISO; for the cutoff we just need the
        # date prefix to be >= cutoff in the user's local zone. UTC date
        # may be ahead of local date by ~1 day at the boundary, but the
        # tail-cap and the day-window already absorb that fuzz.
        if ts and ts[:10] >= cutoff_iso:
            keep.append({"role": m.get("role", ""), "content": m.get("content", "")})
    return {
        "authenticated": True,
        "messages": keep[-max(1, min(limit, 200)):],
        "days": days,
    }


# --- Task Management Board (LOCAL demo — gated behind LOCAL_DEMO_ONLY=1) ---

if LOCAL_DEMO_ONLY:
    @app.get("/dashboard")
    async def dashboard_redirect(request: Request):
        return RedirectResponse(url="/board")

    @app.get("/board", response_class=HTMLResponse)
    async def board_view(request: Request):
        """Overall Board: 8 initiatives card grid + Gantt + Calendar tabs."""
        user = get_current_user(request)
        if not user:
            return RedirectResponse(url="/login")
        return templates.TemplateResponse("board.html", {"request": request, "user": user})

    @app.get("/board/project/{project_name}", response_class=HTMLResponse)
    async def project_view(request: Request, project_name: str):
        """Drill-down: tasks for a single initiative."""
        user = get_current_user(request)
        if not user:
            return RedirectResponse(url="/login")
        project = tasks.get_project(project_name)
        if not project:
            return RedirectResponse(url="/board")
        return templates.TemplateResponse(
            "project.html",
            {"request": request, "user": user, "project": project},
        )

    app.include_router(tasks_routes.router)


if __name__ == "__main__":
    print("\n  Timesheet Assistant POC")
    print(f"  Open http://localhost:8080 in your browser\n")
    uvicorn.run(app, host="127.0.0.1", port=8080)
