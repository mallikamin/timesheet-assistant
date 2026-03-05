# Time Logging Automation - Master Notes

Last updated: 2026-03-05

## North Star
Reach 80-90% automated time logging with high audit quality while keeping Harvest/team lead approval flow unchanged.

## Pitch Line
Dictate to your timesheet assistant — it logs it in Harvest for you.

## Build Strategy (Revised after Tariq call 2026-03-05)

### Phase 1 — POC (Build Now)
AI voice/text timesheet assistant as a simple web page.
- Input: user speaks or types what they worked on in plain language.
- AI engine: parses natural language into Project, Task, Duration, Notes. Conversational — pushes back with clarifying questions when input is ambiguous.
- Mapping: keyword matching against Harvest project/task list.
- Output: Harvest draft entries via API (mock output until API token provided).
- Safety: low-confidence entries routed to Needs Review queue.
- Min time block: 5 minutes.
- Pilot users: Tariq Munir, Malik Amin, Jawad Saleem.

Target outcome:
- Zero dropdown hunting — user just talks.
- Better notes and audit trails from natural language context.
- Immediate reduction in manual timesheet effort.

### Phase 2 — Harvest API Live + Auto-Capture
- Plug in real Harvest API (create draft entries programmatically).
- Add Google Calendar auto-import (Harvest already has sidebar — we add smart Project/Task mapping).
- Add Google Workspace activity capture (Docs, Sheets, Slides, Gmail).
- Daily draft generation + Friday review reminder.

### Phase 3 — Scale + Desktop Tracking
- Desktop app/browser activity tracking for non-Google work (Excel, PowerPoint, etc.).
- Org-wide rollout to 100 users.
- Advanced mapping rules and learning from user corrections.

## POC Architecture

```
[User] --voice/text--> [Web App]
                          |
                    [AI Engine - Claude now / Gemini later]
                          |
                    [Mapping Engine]
                    (project/task matcher)
                          |
                    [Harvest API] --> Draft entries in Harvest
```

Components:
1. Web page — voice input (Web Speech API) + text chat.
2. AI engine — LLM parses input, asks clarifying questions, extracts structured data.
3. Mapping engine — matches extracted project/client names to Harvest project codes.
4. Harvest connector — creates draft time entries via API (mocked until token available).

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

## Key Decisions (from Tariq call)
- Daily drafts, not week-end batch.
- Conversational AI — must ask clarifying questions.
- Everything within Harvest — no separate UI for approvals.
- Pilot first (5-10 users), then scale.
- Gemini preferred (Google ecosystem), Claude for now.
- Full info capture ok — no privacy restrictions for POC.
- 5-minute minimum time blocks.

## Waiting On (from client)
- Harvest API admin token.
- Full project/task list export.
- Google Cloud / Gemini API access.
- Sample filled timesheets from pilot users.
- Pilot user details and typical projects.
