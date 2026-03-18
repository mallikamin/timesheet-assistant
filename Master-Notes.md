# Time Logging Automation - Master Notes

Last updated: 2026-03-07

## North Star
Reach 80-90% automated time logging with high audit quality while keeping Harvest/team lead approval flow unchanged.

## Pitch Line
Dictate to your timesheet assistant — it logs it in Harvest for you.

## Build Strategy (Revised after Tariq call 2026-03-05)

### Phase 1 — POC [BUILT + DEPLOYED]
AI voice/text timesheet assistant as a simple web page.
- Input: user speaks or types what they worked on in plain language.
- AI engine: Claude (swap to Gemini when access provided). Conversational — pushes back with clarifying questions.
- Mapping: keyword matching against Harvest project/task list.
- Output: Draft entries stored in Supabase + synced to Google Sheet.
- Safety: low-confidence entries routed to Needs Review queue.
- Auth: Google SSO login.
- Min time block: 5 minutes.
- Pilot users: Tariq Munir, Malik Amin, Jawad Saleem.
- Live URL: https://timesheet-assistant-jclk.onrender.com
- Repo: https://github.com/mallikamin/timesheet-assistant

### Phase 2 — Auto-Capture [IN PROGRESS]
- Google Calendar API: auto-pull meetings, suggest time entries. [BUILT]
- Gmail API: detect client email activity, suggest entries.
- Google Drive API: track doc/sheet/slide editing time. [BUILT]
- Harvest API: create real draft entries (when token provided).
- Google Chat bot: log time from team chat.
- Daily draft generation + Friday review reminder (Cloud Scheduler).
- Gemini API: replace Claude when access provided.

### Phase 3 — Scale + Intelligence
- Desktop app/browser activity tracking for non-Google work.
- Org-wide rollout to 100 users.
- Vertex AI: learn from user correction patterns.
- Looker Studio dashboards for utilisation reporting.
- AppSheet mobile app for on-the-go logging.
- Cloud Run hosting (replace Render free tier).

## Current Architecture

```
[User] --voice/text--> [Web App (Render)]
                          |
                    [Google SSO Auth]
                          |
                    [AI Engine - Claude API]
                          |
                    [Mapping Engine]
                          |
              +-----------+-----------+
              |                       |
        [Supabase DB]         [Google Sheet]
        (entries + chat)      (visible log)
```

## Tech Stack
- Backend: Python FastAPI
- Frontend: Vanilla HTML/JS (single page)
- AI: Claude API (Anthropic) → Gemini later
- Auth: Google SSO (Authlib + OAuth2)
- DB: Supabase PostgreSQL (time_entries + chat_logs tables)
- Sync: Google Sheets API (gspread)
- Voice: Web Speech API (browser, en-AU)
- Hosting: Render free tier
- Repo: GitHub (mallikamin/timesheet-assistant)

## Infrastructure Credentials

### Render
- Service: timesheet-assistant (srv-d6knrv7tskes73cueam0)
- URL: https://timesheet-assistant-jclk.onrender.com
- Env vars: ANTHROPIC_API_KEY, SUPABASE_URL, SUPABASE_KEY, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_SHEET_ID, GOOGLE_SERVICE_ACCOUNT_JSON

### Supabase
- Project: Time assistant (vsbhiuozqyxxvqwxwyuh)
- URL: https://vsbhiuozqyxxvqwxwyuh.supabase.co
- Tables: time_entries, chat_logs

### Google Cloud
- Project: My First Project (pure-feat-380217)
- Service account: timesheet-assistant@pure-feat-380217.iam.gserviceaccount.com
- OAuth Client ID: 199782164823-j910h9m9sroes50if0tcbq00sfgu30d6.apps.googleusercontent.com
- APIs enabled: Google Sheets API, Google Calendar API, Google Drive API
- APIs to enable next: Gmail API

### Google Sheet
- Timesheet Log: https://docs.google.com/spreadsheets/d/1PcDZ-5xPQr2mTyhujHLHmwIHp0INmOAITkGFbFwDwzw
- Shared with service account as Editor

### Harvest (Thrive PR)
- Workspace: thrivers.harvestaapp.com
- API token: PENDING from Tariq

## Known Harvest Projects (from screenshots)

| Client | Code | Project |
|--------|------|---------|
| Acuity | [6-1000] | Existing Business Growth FY26 |
| Acuity | [6-1000] | New Business Growth FY26 |
| Acuity | [6-1003] | Operations & Admin FY26 |
| Afterpay | [2-00049] | AUNZ Retainer 2026 |
| Afterpay | [2-1099] | Arena Project |
| Afterpay | [2-1100] | Ads Project Mar-Dec 2026 |
| Afterpay | [4-0048] | Animates |
| Afterpay | [4-0049] | NZ PR Retainer Mar-Dec 2026 |
| AGL | — | Existing Growth - AGL |
| CommBank | CB-001 | Brand Campaign 2026 (dummy) |
| Telstra | TEL-001 | Digital Transformation (dummy) |
| Internal | INT-001 | Operations & Admin (dummy) |
| Internal | INT-002 | Business Development (dummy) |

## Key Decisions (from Tariq call)
- Daily drafts, not week-end batch.
- Conversational AI — must ask clarifying questions.
- Everything within Harvest — no separate UI for approvals.
- Pilot first (5-10 users), then scale.
- Gemini preferred (Google ecosystem), Claude for now.
- Full info capture ok — no privacy restrictions for POC.
- 5-minute minimum time blocks.
- Google SSO for authentication.
- Supabase for persistence + Google Sheet for visibility.

## Commercial (2026-03-07)
- **Scope quoted**: Phase 1-2 (Google Workspace only, no browser extension)
- **Development**: $3K-5K AUD
- **Per-user/month**: $12-15 AUD (hosting, API, server, updates)
- **Quoted to**: Tariq Munir (he's presenting to Thrive client, may add his margin)
- **Status**: Ballpark sent, awaiting client response

## Sent to Tariq
- Timesheet demo (live URL)
- Architecture diagram + process flow screenshots (poc/diagrams/architecture-for-tariq.html)
- Ballpark pricing: $3K-5K dev + $12-15/user/month
- Scope: Phase 1-2 (Google Workspace only). Phase 3 (browser ext, desktop) priced separately.

## Current Status (2026-03-18)
- **Demo link sent to Tariq**: https://timesheet-assistant-jclk.onrender.com/
- **System status**: ✅ All green — live, stable, fully functional
- **Waiting for**: Tariq's feedback after team testing
- **Next step**: Follow-up call in ~1 day to discuss feedback

## Waiting On (from client)
- Client response on pricing ballpark.
- Tariq's feedback on demo testing.
- Harvest API admin token.
- Full project/task list export.
- Google Cloud / Gemini API access.
- Sample filled timesheets from pilot users.
- Pilot user details and typical projects.

## Google APIs Roadmap (all free tier)
1. Calendar API — auto-pull meetings → suggest time entries [BUILT]
2. Gmail API — detect client email activity
3. Drive API — track document editing time [BUILT]
4. Gemini API — replace Claude
5. Cloud Speech-to-Text — better voice than browser API
6. Chat API — bot for logging via Google Chat
7. Cloud Scheduler — automated reminders
8. Looker Studio — utilisation dashboards
9. AppSheet — mobile app from Sheet data
10. Admin SDK — org user management for scale
