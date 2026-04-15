# Phase 1 Enhanced — Implementation Plan
> $6,850 | 4 Weeks | 3 Features Added to Original Scope

---

## What Changed from Original SoW ($5,450 → $6,850)

### Original Phase 1 Scope (unchanged)
- AI voice/text time logging
- Google SSO for Thrive users
- Google Calendar meeting detection + time suggestions
- Gmail integration (email activity scanning + suggestions)
- Google Drive document activity signals
- Draft timesheet register (app + Google Sheet)
- User review/edit/approval workflow
- Harvest sync only after approval
- Project/task mapping to Thrive's Harvest structure
- Multi-user support (up to 60 users) + admin visibility
- Production hardening + 10 business days hypercare

### 3 Features Added (+$1,400)

#### 1. Gmail Sidebar Add-on
- Native Gmail sidebar panel — shows inside Gmail when reading/composing emails
- Contextual: detects email participants → suggests client/project mapping
- One-click "Add Draft" button → creates draft entry without leaving Gmail
- Pre-fills: client (from email domain), project (from mapping), notes (from subject)
- **API**: Google Workspace Add-ons API (FREE)
- **Approach**: Google Apps Script-based add-on (not Cloud-hosted)
  - Faster to build than Cloud-hosted Workspace Add-on
  - Can deploy to Thrive's Workspace domain directly (no Marketplace review)
  - Calls existing FastAPI backend for suggestions + draft creation
  - Perfect for internal org deployment of 50-60 users

#### 2. Smart Push Reminders
- Browser web push notifications via Firebase Cloud Messaging (FCM)
- 3 automated reminders via Cloud Scheduler:
  - Daily 9am AEST: "You have X draft entries to review"
  - Friday 3pm AEST: "Week closing — X of 40 target hours logged"
  - Monday 9am AEST: "Last week has X unapproved entries"
- User opt-in via browser permission prompt
- **APIs**: FCM (FREE, unlimited) + Cloud Scheduler (3 jobs FREE)
- **Approach**: Service worker in existing web app + Cloud Function triggers

#### 3. Weekly Manager Report (Auto-Generated Google Doc)
- Every Friday, auto-generate a Google Doc per manager/team
- Content: team utilization %, unapproved entries count, missing time gaps, top projects by hours
- Auto-shared to manager's Google Drive
- Formatted with Thrive branding (clean, professional)
- **API**: Google Docs API (FREE) + Cloud Scheduler
- **Approach**: Cloud Function generates Doc from template, shares via Drive API
- **Dependency**: Tariq provides team/manager structure at kickoff

---

## Technical Architecture (Enhanced)

```
User Activity
├── Voice/Text Chat ──────────────────────┐
├── Gmail Sidebar Add-on (NEW) ───────────┤
├── Gmail API scan ───────────────────────┤
├── Google Calendar events ───────────────┤      FastAPI Backend
└── Google Drive activity ────────────────┼────► (Render/Cloud Run)
                                          │          │
                                          │     ┌────┴────┐
                                          │     │ Claude/ │
                                          │     │ Gemini  │
                                          │     └────┬────┘
                                          │          │
                                          │     ┌────▼─────────────┐
                                          │     │ project_mapping  │
                                          │     │ + People API     │
                                          │     │ + Contact enrich │
                                          │     └────┬─────────────┘
                                          │          │
                                          │     ┌────▼────┐
                                          └────►│ Supabase│ ── Draft Entries
                                                └────┬────┘
                                                     │
                                         ┌───────────┼───────────┐
                                         │           │           │
                                    Google Sheet   Harvest    FCM Push
                                    (visibility)   (after     (reminders)
                                                  approval)
                                                               │
                                         Cloud Scheduler ──────┤
                                              │                │
                                         Weekly Report    Daily/Friday
                                         (Google Docs)    Notifications
```

### New Backend Endpoints Required

| Endpoint | Purpose | Used By |
|----------|---------|---------|
| `POST /api/sidebar/suggest` | Return client/project suggestions for an email context | Gmail Sidebar Add-on |
| `POST /api/sidebar/draft` | Create draft entry from sidebar | Gmail Sidebar Add-on |
| `POST /api/notifications/register` | Register FCM device token | Web app (push opt-in) |
| `POST /api/notifications/send` | Trigger notification to user(s) | Cloud Scheduler |
| `GET /api/reports/weekly` | Generate weekly team report data | Cloud Function |
| `POST /api/reports/generate-doc` | Create Google Doc from report data | Cloud Scheduler (Friday) |

### New Google APIs to Enable

| API | Purpose | Auth | Cost |
|-----|---------|------|------|
| Google People API | Contact enrichment for client mapping | OAUTH | FREE |
| Firebase Cloud Messaging | Web push notifications | SA | FREE (unlimited) |
| Google Docs API | Weekly manager report generation | SA | FREE |
| Workspace Add-ons API | Gmail sidebar | OAUTH | FREE |
| Cloud Scheduler | Cron jobs for reminders + reports | SA | FREE (3 jobs) |

Total additional API cost: **$0/month**

---

## Gmail Sidebar — Detailed Design

### Apps Script Add-on Architecture

```
Gmail opens email
    ↓
Contextual trigger fires (Apps Script)
    ↓
Script extracts: sender, recipients, subject, thread ID, date
    ↓
Calls FastAPI backend: POST /api/sidebar/suggest
    Body: { from, to, subject, thread_id, user_email }
    ↓
Backend:
    1. Looks up sender/recipient domains in People API contacts
    2. Matches domain → Harvest client via project_mapping.py
    3. Suggests: client, project, estimated hours, notes
    ↓
Returns Card UI to Gmail sidebar:
    ┌─────────────────────────────┐
    │  Log Time                   │
    │                             │
    │  Client:  [Afterpay ▼]     │
    │  Project: [AUNZ Retainer ▼]│
    │  Hours:   [0.5]            │
    │  Notes:   [Email re: Q2    │
    │           brand strategy]  │
    │                             │
    │  [Add Draft]  [Skip]       │
    └─────────────────────────────┘
    ↓
User clicks "Add Draft"
    ↓
Script calls: POST /api/sidebar/draft
    ↓
Entry saved as Draft in Supabase + synced to Google Sheet
```

### Deployment (Internal Only — No Marketplace)
1. Create Apps Script project in Thrive's Google Cloud project
2. Set manifest triggers (contextual, Gmail)
3. Admin deploys to Thrive org domain via Apps Script dashboard
4. All 50-60 users get the sidebar automatically
5. No Google Marketplace review needed for internal deployment

### Files Required
- `appsscript.json` — manifest with Gmail contextual trigger
- `Code.gs` — main Apps Script (contextual trigger handler, Card builder, API calls)
- `Sidebar.gs` — Card UI templates (client picker, project picker, hours input)

---

## Push Notifications — Detailed Design

### Web Push Flow
```
User visits web app
    ↓
Browser asks: "Allow notifications?" (opt-in)
    ↓
Service worker registers with FCM
    ↓
FCM returns device token
    ↓
Token saved to Supabase: user_devices table
    ↓
Cloud Scheduler (3 cron jobs):
    Daily 9am AEST  → Cloud Function → FCM → "4 drafts to review"
    Friday 3pm AEST → Cloud Function → FCM → "28/40 hours logged"
    Monday 9am AEST → Cloud Function → FCM → "3 unapproved from last week"
```

### New Supabase Table
```sql
user_devices (
    id UUID PRIMARY KEY,
    user_email TEXT NOT NULL,
    fcm_token TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    last_active TIMESTAMP
)
```

### Notification Templates
```
DAILY_REVIEW:
  title: "Timesheet Review"
  body: "You have {count} draft entries waiting for approval"
  action_url: /

WEEKLY_CLOSE:
  title: "Week Closing"
  body: "{hours_logged}h of {target}h logged this week. {gap}h unaccounted."
  action_url: /

MONDAY_CATCH:
  title: "Last Week Follow-Up"
  body: "{count} entries from last week still need approval"
  action_url: /
```

---

## Weekly Manager Report — Detailed Design

### Report Content
```
┌──────────────────────────────────────────────┐
│  THRIVE PR — Weekly Timesheet Report         │
│  Week of 24 March 2026                       │
│  Generated: Friday 28 March, 4:00pm AEST     │
│                                              │
│  TEAM SUMMARY                                │
│  ─────────────────────────────────────       │
│  Total Hours Logged:     312.5h              │
│  Target Hours:           400h (60 users)     │
│  Utilization:            78.1%               │
│  Approved Entries:       245                 │
│  Pending Approval:       38                  │
│  Rejected:               4                   │
│                                              │
│  TOP PROJECTS                                │
│  ─────────────────────────────────────       │
│  1. Afterpay AUNZ Retainer    —  87.5h       │
│  2. Acuity Business Growth    —  62.0h       │
│  3. AGL Existing Growth       —  45.0h       │
│  4. Internal Ops & Admin      —  38.5h       │
│  5. Afterpay Arena Project    —  32.0h       │
│                                              │
│  ATTENTION NEEDED                            │
│  ─────────────────────────────────────       │
│  Users with < 30h logged:                    │
│    - Sarah Chen (22.5h)                      │
│    - James Wilson (18.0h)                    │
│    - Priya Patel (25.5h)                     │
│                                              │
│  Users with pending approvals > 5:           │
│    - Michael Brown (8 pending)               │
│    - Emily Davis (6 pending)                 │
│                                              │
└──────────────────────────────────────────────┘
```

### Generation Flow
```
Cloud Scheduler (Friday 4pm AEST)
    ↓
Cloud Function: generate_weekly_report()
    ↓
Query Supabase:
    - All entries this week (Mon-Fri), grouped by user
    - Status counts (Draft, Approved, Submitted, Rejected)
    - Hours per project
    - Users below threshold
    ↓
Google Docs API:
    - Create new Doc from template
    - Insert formatted data (tables, headers, highlights)
    - Set title: "Thrive Timesheet Report — Week of {date}"
    ↓
Google Drive API:
    - Share Doc with manager(s) — viewer or editor access
    - Place in designated "Reports" folder
    ↓
Optional: Send FCM push to manager(s): "Weekly report ready"
```

### Dependency
- Tariq provides team/manager structure at kickoff
- If not available by Week 3: report starts as org-wide (single report for all users)
- Team breakdown added when structure is provided (can be a post-launch tweak within hypercare)

---

## 4-Week Timeline

### Week 1: Core Workflow + Harvest
> **Goal**: Draft-first approval workflow working with real Harvest

| Day | Task | Deliverable |
|-----|------|-------------|
| 1 | Kickoff call with Tariq. Receive: Harvest token, Account ID, user emails, team structure | Credentials + user list |
| 1-2 | Decouple draft creation from Harvest sync. Add `status` state machine (Draft → Approved → Submitted → Rejected) | Draft workflow backend |
| 3 | Review queue UI — approve, reject, edit actions. Batch approve. | Review UI in web app |
| 4 | Google Sheet draft register (per-user tab or per-user sheet). Auto-sync drafts. | Sheet visibility layer |
| 5 | Real Harvest workspace config. Map all Thrive projects/tasks. Test sync. | Harvest integration live |

### Week 2: Intelligence Layer + Push
> **Goal**: Gmail, Calendar, Drive signals feeding smart drafts. Push notifications working.

| Day | Task | Deliverable |
|-----|------|-------------|
| 1 | Gmail API scopes + OAuth flow update. Sent-mail scanning. Thread clustering by client/domain. | Gmail signal ingestion |
| 2 | Google People API integration. Contact enrichment for client mapping. Calendar attendee domain mapping. | Smarter project matching |
| 3 | Merge all signals: Gmail + Calendar + Drive + People → unified draft suggestions. Confidence scoring. | Unified suggestion engine |
| 4 | FCM setup. Service worker. Device token registration. Push opt-in flow. | Push infrastructure |
| 5 | Cloud Scheduler: 3 cron jobs (daily review, Friday close, Monday catch-up). Cloud Function triggers. | Automated reminders live |

### Week 3: Gmail Sidebar + Manager Report
> **Goal**: Sidebar working in Gmail. Weekly report generating.

| Day | Task | Deliverable |
|-----|------|-------------|
| 1 | Gmail Sidebar: Apps Script project setup. Manifest with contextual triggers. Backend endpoints (`/sidebar/suggest`, `/sidebar/draft`). | Sidebar backend |
| 2 | Gmail Sidebar: Card UI (client picker, project picker, hours, notes, Add Draft button). | Sidebar frontend |
| 3 | Gmail Sidebar: Testing with real Gmail data. Edge cases (unknown senders, no mapping, group emails). Deploy to Thrive org. | Sidebar deployed |
| 4 | Weekly Manager Report: Docs API template. Report generation Cloud Function. Data aggregation queries. | Report generation |
| 5 | Weekly Manager Report: Auto-sharing to manager Drive. Cloud Scheduler (Friday 4pm AEST). Push notification to managers. | Report automated |

### Week 4: Multi-User + Hardening + Launch
> **Goal**: Production-ready for 60 users. Go-live.

| Day | Task | Deliverable |
|-----|------|-------------|
| 1 | Multi-user support: individual profiles, data isolation, per-user Sheets. Admin visibility (draft status, sync status, team overview). | Multi-user ready |
| 2 | Production hardening: rate limiting, error handling, logging, monitoring. Security review. | Production grade |
| 3 | Deployment to production (Render or Cloud Run). Domain/SSL. Environment configs. | Deployed |
| 4 | UAT with Tariq + pilot group (5-10 users). Fix blockers. | UAT passed |
| 5 | Full rollout to 50-60 users. Onboarding docs. Go-live. Hypercare begins (10 business days). | LIVE |

---

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Thrive doesn't have Google Workspace (paid) | Sidebar can't deploy as org add-on | Confirm in kickoff call. Fallback: deploy as editor add-on (per-user install) |
| Harvest API token delayed | Blocks Week 1 Day 5 | Start with mock Harvest (already built). Swap creds when received. Non-blocking for other work. |
| Gmail sidebar takes longer than 3 days | Pushes Week 3-4 | Simplified v1: show suggestion card only, no project picker dropdown. Full picker in post-launch iteration. |
| Manager team structure not provided | Report can't group by team | Start with org-wide report (single doc). Add team grouping when structure provided. |
| FCM push opt-in rate is low | Reminders don't reach users | Add email fallback reminders via Gmail API (send summary email). |
| 4-week timeline is too tight | Quality suffers | Sidebar and report can iterate during 10-day hypercare if needed. Core workflow is priority. |

---

## Hidden Value (Don't Pitch, Just Build)

These cost $0 and make the product smarter. Include silently:

1. **Calendar attendee domain → client mapping** — parse @afterpay.com.au → Afterpay. Already pulling Calendar data.
2. **People API contact enrichment** — resolve email addresses to company names from user's contacts.
3. **Gemini API for dev/testing** — free tier, aligns with Tariq's preference. Reduces LLM cost pressure.
4. **Cloud Natural Language API** — pre-classify email subjects for better project mapping (5K/month free).

---

## Updated SoW Changes

### Price
- Implementation fee: **USD $6,850** (single line item)
- Monthly: unchanged ($5/user annual, $7.50/user M2M, 50 user minimum)

### New Inclusions (add to Section 4 "Included")
- Gmail sidebar add-on — contextual time logging from within Gmail
- Smart push reminders — automated daily, weekly, and follow-up notifications
- Weekly manager report — auto-generated Google Doc with team utilization and attention items

### Timeline
- Keep 4 weeks. The additional features fit because:
  - Core app is 80% built already (chat, voice, Calendar, Drive, Sheets, SSO, Harvest)
  - Gmail sidebar uses Apps Script (3 days, not 8)
  - Push reminders are 1-2 days (FCM + service worker + 3 cron jobs)
  - Manager report is 2 days (Docs API template + scheduler)

### What NOT to Change
- Exclusions stay the same (browser extension, desktop, mobile, SAML, Marketplace)
- Monthly pricing stays the same
- Payment terms stay the same (50/50)
- Hypercare stays 10 business days
- Phase 2 browser extension stays separate ($3,000-5,000)

---

## For the SoW Document

Add these 3 bullets to Section 4 "Included":
```
- Gmail sidebar add-on — contextual time logging directly inside Gmail
  with one-click draft creation
- Smart push reminders — automated daily review, weekly close, and
  follow-up notifications via browser push
- Weekly manager report — auto-generated Google Doc with team utilization,
  pending approvals, and attention items, delivered to managers every Friday
```

Update Section 5 pricing: $5,450 → $6,850

Keep everything else identical.
