"""
Time Logging AI Assistant - POC Backend
FastAPI server with Claude-powered conversational timesheet assistant.
Google SSO authentication.
"""

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
from fastapi.responses import HTMLResponse, RedirectResponse
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
import training_log
import user_profiles
from project_mapping import get_all_projects_for_prompt, get_projects

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
    # Saves the first user from waiting 5-10s on the cold N+1 fetch path.
    if harvest_api.is_configured():
        try:
            projects = harvest_api.get_projects_with_tasks()
            users = harvest_api.get_users()
            print(f"[OK] Pre-warmed Harvest cache: {len(projects)} projects, {len(users)} users")
        except Exception as e:
            print(f"[WARN] Harvest pre-warm skipped: {e}")
    else:
        print("[INFO] No Harvest PAT — first user will pay cold-start cost")

    yield
    # No shutdown work yet; uvicorn handles graceful socket close.


app = FastAPI(title="Timesheet Assistant POC", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "timesheet-poc-secret-key-2026"),
)
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


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
client = anthropic.AsyncAnthropic(
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    timeout=30.0,
)

CHAT_MODEL = "claude-haiku-4-5-20251001"

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

REFERENCE — edge cases:
- All-day blocks ("worked on X today"): default 7.5 hours unless the user has logged other entries today; in that case ask "is that the rest of today, or in addition to what you've already logged?"
- Multi-task days ("did emails, then a meeting, then drafted a proposal"): create one entry per task, ask for duration of each.
- Future dates ("for tomorrow's pitch"): refuse politely — only log work that has already happened.
- Past dates ("last Tuesday"): convert to absolute YYYY-MM-DD using today's date as reference, confirm date with the user before logging.
- Negative durations / zero hours: refuse, ask for clarification.
- Hours > 16 in a single entry: confirm before logging — likely a typo or a "this whole week" misphrasing.

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
    cached_text = SYSTEM_PROMPT_TEMPLATE.replace("{{today_display}}", date.today().strftime('%A, %d/%m/%Y')) \
        .replace("{{today_iso}}", date.today().strftime('%Y-%m-%d')) \
        .replace("{{today_day}}", date.today().strftime('%A')) \
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
    if notes:
        uncached_parts.extend(n for n in notes if n)

    if uncached_parts:
        blocks.append({"type": "text", "text": "\n\n".join(uncached_parts)})

    return blocks


def get_current_user(request: Request) -> Optional[Dict]:
    """Get the logged-in user from session."""
    return request.session.get("user")


class ChatRequest(BaseModel):
    user: str
    message: str
    history: List[Dict] = []


class ChatResponse(BaseModel):
    response: str
    entries_created: List[Dict] = []


def save_entry_everywhere(user: str, entry_data: Dict, user_email: str = "") -> Dict:
    """Save an entry as Draft to Supabase and Google Sheets. Harvest push happens on approval."""
    entry = harvest_mock.create_draft_entry(
        user=user,
        client=entry_data.get("client", "Unknown"),
        project_code=entry_data.get("project_code", ""),
        project_name=entry_data.get("project_name", ""),
        task=entry_data.get("task", "General"),
        hours=float(entry_data.get("hours", 0)),
        notes=entry_data.get("notes", ""),
        entry_date=entry_data.get("date", date.today().isoformat()),
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
]

MAX_TOOL_ITERATIONS = 5


async def execute_tool(tool_name: str, tool_input: Dict, access_token: str) -> str:
    """Execute a tool call and return the result string for Claude."""
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

@app.get("/health")
async def health(request: Request):
    """Lightweight readiness probe for Render + UptimeRobot. Always returns
    200 if the process is alive — degraded downstream deps (Anthropic,
    Harvest, Supabase) are surfaced in the body so they're observable but
    don't fail the probe (we don't want UptimeRobot to alert on transient
    Anthropic blips)."""
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

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "user": user,
            "users": PILOT_USERS,
            "today": date.today().strftime("%A, %d/%m/%Y"),
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

    system_blocks = build_system_prompt(
        user_email=user.get("email"),
        harvest_access_token=harvest_access_token,
        notes=runtime_notes,
    )

    # Only offer tools if Google access is available
    tools_param = TOOLS if has_google_access else None

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

        response = await client.messages.create(**api_kwargs)
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

                    if not has_google_access:
                        result_text = (
                            "ERROR: Google access is no longer available. "
                            "Ask the user to sign out and sign back in."
                        )
                    else:
                        result_text = await execute_tool(
                            tool_name=block.name,
                            tool_input=block.input,
                            access_token=access_token,
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
        entry = save_entry_everywhere(req.user, entry_data, user_email=user.get("email", ""))
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

    entries = harvest_mock.get_entries(user=user_name)
    drafts = [e for e in entries if e.get("status") in ("Draft", "Needs Review")]

    results = []
    for entry in drafts:
        harvest_user_id = harvest_api.resolve_user_id(user_email, harvest_access_token) if user_email else None

        # Try direct IDs from project_code first (format: "projectId-taskId")
        harvest_entry = None
        project_code = entry.get("project_code", "")
        if project_code and "-" in project_code:
            parts = project_code.split("-", 1)
            try:
                pid, tid = int(parts[0]), int(parts[1])
                harvest_entry = harvest_api.create_time_entry(
                    project_id=pid,
                    task_id=tid,
                    spent_date=entry.get("date", date.today().isoformat()),
                    hours=float(entry.get("hours", 0)),
                    notes=entry.get("notes", ""),
                    user_id=harvest_user_id,
                    access_token=harvest_access_token,
                    task_name=entry.get("project_name", entry.get("task", "")),
                )
            except (ValueError, TypeError):
                pass

        # Fallback to name resolution
        if not harvest_entry:
            harvest_entry = harvest_api.push_entry(
                client_name=entry.get("client", ""),
                task_name=entry.get("project_name", entry.get("task", "")),
                spent_date=entry.get("date", date.today().isoformat()),
                hours=float(entry.get("hours", 0)),
                notes=entry.get("notes", ""),
                user_id=harvest_user_id,
                access_token=harvest_access_token,
            )

        if harvest_entry:
            harvest_mock.update_entry(entry["id"], status="Approved", harvest_id=harvest_entry["id"])
            sheets_sync.update_entry_status_in_sheet(entry["id"], "Approved")
            user_profiles.record_approval(user_email, entry)
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
            results.append({"id": entry["id"], "approved": False})

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

    # Try direct IDs from project_code first (format: "projectId-taskId")
    harvest_entry = None
    project_code = entry.get("project_code", "")
    if project_code and "-" in project_code:
        parts = project_code.split("-", 1)
        try:
            pid, tid = int(parts[0]), int(parts[1])
            harvest_entry = harvest_api.create_time_entry(
                project_id=pid,
                task_id=tid,
                spent_date=entry.get("date", date.today().isoformat()),
                hours=float(entry.get("hours", 0)),
                notes=entry.get("notes", ""),
                user_id=harvest_user_id,
                access_token=harvest_access_token,
                task_name=entry.get("project_name", entry.get("task", "")),
            )
        except (ValueError, TypeError):
            pass  # Not numeric IDs, fall through to name resolution

    # Fallback to name resolution
    if not harvest_entry:
        harvest_entry = harvest_api.push_entry(
            client_name=entry.get("client", ""),
            task_name=entry.get("project_name", entry.get("task", "")),
            spent_date=entry.get("date", date.today().isoformat()),
            hours=float(entry.get("hours", 0)),
            notes=entry.get("notes", ""),
            user_id=harvest_user_id,
            access_token=harvest_access_token,
        )

    if not harvest_entry:
        return {"success": False, "error": "Failed to push to Harvest"}

    # Update Supabase
    harvest_mock.update_entry(entry_id, status="Approved", harvest_id=harvest_entry["id"])
    # Update Google Sheet
    sheets_sync.update_entry_status_in_sheet(entry_id, "Approved")
    # Per-user learning: bump common_tasks frequency + prepend to recent entries
    user_profiles.record_approval(user_email, entry)
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
    return {"events": events, "date": target_date or date.today().isoformat()}


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

    response = await client.messages.create(
        model=CHAT_MODEL,
        max_tokens=1024,
        system=build_system_prompt(user_email=user.get("email")),
        messages=messages,
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

    today = date.today()
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

    response = await client.messages.create(
        model=CHAT_MODEL,
        max_tokens=1024,
        system=build_system_prompt(user_email=user.get("email")),
        messages=messages,
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

    response = await client.messages.create(
        model=CHAT_MODEL,
        max_tokens=1024,
        system=build_system_prompt(user_email=user.get("email")),
        messages=messages,
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
    return {"authenticated": True, "has_calendar": has_calendar, "has_harvest": has_harvest, **user}


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
