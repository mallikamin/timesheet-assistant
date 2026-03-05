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
