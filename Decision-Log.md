# Decision Log - Time Logging Automation

## How to Use
After each client call, add one dated entry with decisions, open items, and owner.

---

## Entry Template
Date:
Attendees:

Decisions made:
1.
2.
3.

Open questions:
1.
2.

Action items:
1. [Owner] [Task] [Due]
2. [Owner] [Task] [Due]

Impact on plan:
- Phase 1:
- Phase 2:
- Phase 3:

---

## 2026-03-04 (Internal Prep)
Decisions made:
1. North star is 80-90% automation, but implement one wedge first.
2. First wedge: Google Calendar -> Harvest draft automation.
3. Chrome extension is later phase for non-calendar/focus work enrichment.

Open questions:
1. Daily drafts vs week-end draft generation.
2. Mapping rule ownership and update process.
3. Rollout mode: org-wide vs waves.

Action items:
1. [Team] Present lean 5-question discussion in next client call. [Next call]
2. [Team] Finalize Phase 1 timeline once client confirms decision points. [Post-call]

Impact on plan:
- Phase 1: fixed as calendar-first.
- Phase 2: workflow/review improvements.
- Phase 3: browser context integration.

---

## 2026-03-05 (Client Call - Tariq Munir)
Attendees: Tariq Munir, Malik Amin

Decisions made:
1. POC approach: AI voice/text timesheet assistant — users dictate or type what they did, AI logs it into Harvest.
2. Interface: simple web page with voice + text input.
3. Daily draft generation (not week-end batch).
4. Low-confidence entries go to Needs Review queue.
5. Conversational AI — must push back and ask clarifying questions (e.g. "how many hours?" "which Acuity task?").
6. Everything must live within Harvest — all entries created via Harvest API as drafts.
7. Minimum time block: 5 minutes.
8. Full info capture permitted (no privacy restrictions for POC).
9. Rollout: pilot 5-10 users first, then scale.
10. Preferred AI model: Gemini (Google ecosystem). Use Claude/other for now until Google Cloud access is provided.
11. Harvest already has Google Calendar sidebar — the real gap is auto-mapping Project/Task, not calendar import.

Pilot users:
- Tariq Munir
- Malik Amin
- Jawad Saleem

Known Harvest projects (from screenshots):
- Acuity: [6-1000] Existing Business Growth FY26, [6-1000] New Business Growth FY26, [6-1003] Operations & Admin FY26
- Afterpay Australia Pty Ltd: [2-00049] AUNZ Retainer 2026, [2-1099] Arena Project, [2-1100] Ads Project Mar-Dec 2026, [4-0048] Animates, [4-0049] NZ PR Retainer Mar-Dec 2026
- AGL: Acuity - Existing Growth - AGL

Open questions:
1. Harvest API admin token — when available?
2. Full project/task list export — needed for complete mapping table.
3. Sample filled timesheets from pilot users — needed to validate AI accuracy.
4. Authentication method for web app (Google SSO vs simple login vs none for POC).
5. Hosting preference (Google Cloud vs other).
6. Notes format requirement — what auditors need.

Action items:
1. [Team] Build POC web app: voice/text input + conversational AI + mock Harvest output. [Immediately]
2. [Tariq] Provide Harvest API admin token. [ASAP]
3. [Tariq] Provide full Harvest project/task list export. [ASAP]
4. [Tariq] Provide Google Cloud / Gemini API access. [When ready]
5. [Tariq] Confirm pilot user details and typical projects. [Before pilot]

Impact on plan:
- Phase 1: REVISED — voice/text AI timesheet assistant POC (web page). Mock Harvest output until API available.
- Phase 2: Plug in real Harvest API + add Google Calendar/Workspace auto-capture.
- Phase 3: Desktop app tracking, org-wide scale.

---

## 2026-03-05 (Build Session - Post Call)
Attendees: Malik Amin (dev)

Built and deployed:
1. POC web app: FastAPI + vanilla HTML/JS. Voice + text input. Claude-powered AI.
2. Google SSO login (Authlib OAuth2). Users sign in with Google account.
3. Supabase PostgreSQL persistence — time_entries and chat_logs tables.
4. Google Sheets sync — every entry also pushed to shared Timesheet Log sheet.
5. Deployed to Render free tier: https://timesheet-assistant-jclk.onrender.com
6. Code on GitHub: https://github.com/mallikamin/timesheet-assistant

Infrastructure set up:
- Supabase project: vsbhiuozqyxxvqwxwyuh (Time assistant)
- Google Cloud project: pure-feat-380217 (My First Project)
- Service account: timesheet-assistant@pure-feat-380217.iam.gserviceaccount.com
- Google Sheets API enabled
- OAuth consent screen + credentials configured
- Render env vars: ANTHROPIC_API_KEY, SUPABASE_URL, SUPABASE_KEY, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_SHEET_ID, GOOGLE_SERVICE_ACCOUNT_JSON

Open items for next session:
1. Google Calendar API integration — auto-pull meetings to suggest time entries.
2. Enable Calendar API in Google Cloud Console.
3. Add calendar read scope to OAuth + service account.
4. Build calendar-to-entry suggestion flow in the chat assistant.
5. Wire in Harvest API when token is available.

Impact on plan:
- Phase 1: COMPLETE. POC live and deployed with auth, persistence, and sheet sync.
- Phase 2: Starting with Calendar API integration next session.

---

## 2026-03-05 (Build Session 2 - Calendar Integration)
Attendees: Malik Amin (dev)

Built:
1. Google Calendar API integration — OAuth scope extended to calendar.readonly.
2. New calendar_sync.py module — fetches user's calendar events via REST API with httpx.
3. Token management — stores Google OAuth tokens (access + refresh) in session, auto-refreshes on expiry.
4. New endpoints: GET /api/calendar/events, POST /api/calendar/suggest.
5. "Suggest from Calendar" button in chat UI — one click pulls today's meetings and feeds them to Claude for time entry suggestions.
6. Claude maps calendar events to Harvest projects and creates draft entries.

Technical decisions:
- User's OAuth token (not service account) for calendar access — need personal calendar.
- Direct REST calls with httpx — no new dependencies needed.
- Tokens in session for POC — can move to Supabase later.
- User-initiated calendar pull (button click, not auto-load) — privacy-conscious.
- access_type=offline + prompt=consent to get refresh tokens from Google.

Prerequisite:
- Google Calendar API must be enabled in Cloud Console (project: pure-feat-380217).
- Users must re-login after deploy to grant calendar permission.

Open items:
1. Enable Calendar API in Google Cloud Console.
2. Test end-to-end: login → calendar pull → entry suggestion → confirm.
3. Deploy to Render.
4. Next: Gmail API, Drive API, Harvest API.

Impact on plan:
- Phase 2: Calendar API BUILT. Ready to test and deploy.

---

## 2026-03-07 (Tariq — Async Messages)
Attendees: Tariq Munir (voice note + text), Malik Amin (text)

Context:
- Sent Tariq: (1) timesheet demo, (2) another client's digital audit report as a sample of what we could do for Thrive.
- Tariq's response on demo: "Thanks for this Amin. Appreciate this." — positive.
- Tariq's response on audit report: "Thanks but this is not their requirement at this stage. However, will check with them definitely if they need it." — soft pass, door left open.
- Tariq sent 2-min voice note: needs a ballpark figure for timelogging. Scope = Google Workspace functionality only, NOT the browser extension / non-Google activity capture.

Pricing sent to Tariq:
- Development: $3K-5K AUD
- Per-user/month: $12-15 AUD (covers hosting, API, server, updates)

Decisions:
1. Digital audit parked — Tariq is not the buyer for that. Revisit when there's a direct line to Leilani (CEO) or leadership.
2. Pricing scope = Phase 1-2 only (Google Workspace). Phase 3 (browser extension, desktop tracking) priced separately later.
3. Tariq is presenting this to client — he may add his own margin on top.

Open questions:
1. Client's team size — affects monthly revenue projection.
2. Harvest API token — still the #1 blocker for real integration.
3. Does Tariq want a formal proposal or is the ballpark enough for now?

Action items:
1. [Tariq] Present ballpark to Thrive client. [Next few days]
2. [Tariq] Provide Harvest API token. [Still pending]
3. [Malik] Wait for client response on pricing before next build sprint.
4. [Malik] Be ready to send formal proposal if Tariq asks.

Sent to Tariq (2026-03-07):
- Screenshots of architecture diagram + process flow (from poc/diagrams/architecture-for-tariq.html).
- Shows: system architecture (5 layers), 8-step user journey, and Phase 1-2-3 roadmap.
- Clearly scoped to Phase 1-2 (Google Workspace). Phase 3 shown as separate/future.

Impact on plan:
- Phase 1: COMPLETE and demo'd.
- Phase 2: Paused on Harvest integration until token received. Calendar + Drive built.
- Digital audit: PARKED. Ready to deploy when path to Leilani opens.

---

## 2026-03-18 (Demo Link Sent)
Attendees: Malik Amin (dev)

Action taken:
1. Full system health check completed — all APIs functional, deployment live and stable.
2. Demo link sent to Tariq: https://timesheet-assistant-jclk.onrender.com/
3. User flow: Google sign-in → immediate access to AI assistant, Calendar sync, Drive sync.
4. No setup required — zero-config demo ready for Thrive team testing.

Current status:
- Phase 1: COMPLETE and production-ready.
- Phase 2: Calendar API ✓, Drive API ✓, Gmail pending, Harvest blocked on token.
- System health: All green — 17 endpoints, 1,032 lines of code, zero errors.
- Infrastructure: Render (live), Supabase (connected), Google Cloud (3 APIs active).

Waiting on:
1. Tariq's feedback on demo after team testing.
2. Harvest API admin token (still blocking real integration).
3. Client pricing approval ($3K-5K + $12-15/user/month).

Next steps:
1. [Tariq] Test demo with team, provide feedback. [Next 1-2 days]
2. [Malik] Schedule follow-up call to discuss feedback. [~1 day from now]
3. [Tariq] Provide Harvest API token if client approves. [Post-approval]

Impact on plan:
- Phase 1: Demo in client hands for validation.
- Phase 2: Ready to implement Harvest integration once token provided.
- Timeline: Waiting on client feedback to proceed.

---

## 2026-03-24 (Tariq Voice Notes - SoW Direction)
Attendees: Tariq Munir (voice notes), Malik Amin

Context:
- Tariq asked for a proper Statement of Work with full setup, implementation, and per-user monthly pricing for 50-60 users.
- Recurring monthly cost must be minimized while staying profitable for Sitara Infotech.
- Tariq explicitly asked for Gmail integration and a draft approval workflow before anything is pushed into Harvest.
- Tariq suggested the POC could be treated as free if needed.
- Pricing direction now needs to be in USD rather than AUD.

Decisions:
1. Treat the current live demo as the free POC already delivered; the next step is a paid implementation SoW.
2. Keep the current SoW focused on Google-native rollout: Gmail, Calendar, Drive/low-hanging Google signals, draft approval workflow, Harvest sync after approval, and 50-60 user rollout.
3. Keep pricing for the Google-native SoW within the original quoted `USD 3K-5K` band by avoiding scope creep.
4. Browser extension / non-Google capture remains a separate Phase 2 build and should be quoted separately.
5. Monthly pricing target for 50+ users should land around `USD 5-6/user/month`, with a minimum-user floor.

Open questions:
1. Should Gmail analysis start with sent mail only, or include deeper client-thread reads?
2. Should approved entries land in Harvest as drafts or directly as ready-to-submit entries?
3. Does Thrive want daily approvals, weekly approvals, or both?
4. Does Tariq want the SoW as a formal PDF proposal, a Word-style document, or both?

Action items:
1. [Malik] Draft internal SoW plan aligned to USD pricing and 50-60 user rollout. [Done]
2. [Malik] Split scope into Google-native SoW vs separate browser-extension Phase 2 plan. [Done]
3. [Malik] Prepare professional client-facing SoW/proposal draft. [Next]
4. [Tariq] Confirm preferred approval workflow and Gmail privacy boundary. [Next call]

Impact on plan:
- Phase 1: Existing live demo can be treated as the free POC.
- Phase 2: Reframed as Google-native rollout with Gmail + approval-first workflow.
- Phase 3: Browser extension / non-Google capture remains a separate paid build after the Google-native rollout.
