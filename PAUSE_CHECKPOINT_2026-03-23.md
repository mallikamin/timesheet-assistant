# Pause Checkpoint — 2026-03-23 (Post Tariq Demo #2)

## Project
- **Name**: Time Logging Automation (Thrive Timesheet)
- **Path**: C:\Users\Malik\desktop\timelogging
- **Branch**: main (clean, pushed to origin)
- **Live URL**: https://timesheet-assistant-jclk.onrender.com
- **Harvest dashboard**: https://mallikamin.harvestapp.com

## What Happened This Session

### Demo with Tariq — SUCCESS
- Gave full live demo on screenshare
- Showed multiple scenarios: single entry, multi-task, voice dictation, bulk tasks
- Tariq **screen recorded** the entire demo
- No crashes, no errors — app performed perfectly
- Tariq impressed with voice feature and Harvest sync
- Showed Google Drive integration: uploaded a doc, assistant detected it was edited today

### Tariq's Questions & Discussion Points
1. **Browser extension** — for tracking non-Google tasks (Jira, Figma, etc.)
   - Decision: browser extension becomes the CORE tracking layer
   - Replaces need for individual API integrations (Drive, Gmail, etc.)
   - Tracks any web-based tool via active tab monitoring
2. **Google Antigravity** — Tariq asked how it plays into this
   - It's Google's AI IDE (dev tool, not productivity tool)
   - Tariq likely meant broader Google AI ecosystem integration (see below)
3. **Google Drive time calculation** — how to know total time spent on a file
   - Browser extension solves this: tracks time on docs.google.com/d/xxx tabs
   - No need for Revisions API if extension is the core approach
4. **Beyond Google** — extending to non-Google tools
   - Browser extension covers everything web-based in one shot
   - Only gap: native desktop apps (Outlook desktop, Excel desktop)
5. **60-user pricing** — how to minimize per-user cost at scale

### Google Ecosystem Integration Opportunities (for Tariq)

#### Tier 1 — High Value, Direct Fit
- **Gemini API (replace Claude)**: If Thrive has Google Workspace, Gemini included in license. Swap Claude for Gemini = AI cost drops from ~$1.50/user/month to near $0. Per-user cost at 60 users drops to $1-2 USD.
- **Google Workspace Add-on (sidebar app)**: Build assistant as sidebar inside Gmail/Docs/Sheets instead of separate website. User works in a Doc → opens sidebar → "log this". Marketplace distribution = easy rollout.
- **Workspace Studio (agentic automation)**: New Google feature — multi-step AI workflows in plain English. E.g. "Every Friday at 4pm, draft timesheet from this week's calendar and email, send for review." No code, Tariq's team could customize.

#### Tier 2 — Nice to Have
- **Google Meet transcripts**: Meet auto-transcribes → AI identifies project discussed → auto-log meeting time.
- **NotebookLM**: Team dumps project docs → AI understands project context better for ambiguous entries.
- **Gemini in Sheets**: Manager asks "Show me who's under-logging this week" → Gemini answers from timesheet sheet.

#### Tier 3 — Not Relevant
- Nano Banana: image generation model, not useful for timesheets
- Google Vids: video creation, not relevant
- Antigravity: developer IDE, for building software not end-user tool

### Key Questions to Ask Tariq Next Time
1. "Does Thrive have Google Workspace Business/Enterprise?" — if yes, Gemini is free
2. "Would your team prefer a sidebar inside Gmail/Docs or a standalone app?" — determines build direction
3. "Are you using Google Meet for client calls?" — unlocks auto-logging from transcripts
4. What did he actually mean by Antigravity? Broader Google AI play?

## Pricing — Final Numbers

### Development Costs
| Item | Amount | Status |
|------|--------|--------|
| POC demo (1-2 pilot users) | **$500 USD** | Quoted to Tariq |
| Original Phase 1-2 build | $3K-5K AUD | Mostly DONE |
| Browser extension + scale to 60 users | $3K-5K AUD additional | NEW scope |
| **Total build cost** | **$6K-9K AUD all-in** | |

### What $3K-5K AUD (original) included:
- AI chat assistant (Claude) — DONE
- Voice input (Web Speech API) — DONE
- Google SSO authentication — DONE
- Supabase database — DONE
- Google Sheets sync — DONE
- Google Calendar integration — DONE
- Google Drive integration — DONE
- Harvest API integration — DONE
- Deployment on Render — DONE

### What additional $3K-5K AUD covers (new scope):
- Chrome browser extension (core tracking layer)
- Extension backend (activity ingestion, session clustering)
- Multi-user support (proper user management)
- Admin/manager dashboard
- Production hardening (auth, rate limits, error handling)
- 60-user load testing

### Per-User Monthly Costs (Infrastructure Breakdown)

| Cost Component | Per user (5 users) | Per user (60 users) |
|----------------|--------------------|--------------------|
| Claude API (~100 msgs/user/month) | ~$1.50 | ~$1.50 |
| Render hosting (Pro) | ~$5.00 | ~$0.40 |
| Supabase (Pro) | ~$5.00 | ~$0.40 |
| Google Cloud APIs | ~$0 | ~$0 |
| Harvest API | $0 | $0 |
| **Raw infrastructure** | **~$11.50** | **~$2.30** |

### With Gemini (if Thrive has Workspace)

| Cost Component | Per user (60 users) |
|----------------|---------------------|
| Gemini API (Workspace included) | ~$0 |
| Render hosting (Pro) | ~$0.40 |
| Supabase (Pro) | ~$0.40 |
| **Raw infrastructure** | **~$0.80** |

### Tiered Pricing for Tariq

| Users | Per user/month | Monthly total |
|-------|---------------|---------------|
| 1-5 (pilot) | $15 USD | $75 |
| 6-20 | $10 USD | $200 |
| 21-60 | $7 USD | $420 |
| 60 flat deal | **$5-6 USD** | **$300-360/month** |

At 60 users @ $5-6/user: ~$300-360 revenue, ~$140 infra cost, ~$160-220/month margin.
With Gemini swap: infra drops to ~$48/month, margin increases to ~$250-310/month.

## Architecture Decision: Browser Extension as Core

### Old plan (5 separate API integrations):
- Google Calendar API (keep for meetings)
- Google Drive API (can deprecate — extension covers it)
- Google Drive Revisions API (planned → SKIP)
- Gmail API (planned → SKIP)
- Per-tool integrations (planned → SKIP)

### New plan (single extension):
- Chrome extension = universal tracking layer
- Tracks ANY web app via tab URL + page title + time
- Google Calendar API kept (catches meetings without browser tab)
- Everything else covered by extension
- Simpler architecture, broader coverage

### Future: Full Google-native architecture
- Gemini replaces Claude (free with Workspace)
- Workspace Add-on replaces standalone web app
- Workspace Studio for automated workflows
- Meet transcripts for auto-logging meetings
- Extension for non-Google web tools

## What We Asked Tariq For
1. **Harvest API Token** — https://id.getharvest.com/oauth2/access_tokens/new
2. **Pilot user Gmail addresses** — for GCP OAuth test users
3. **Go-ahead on $500 USD POC**
4. **Clarify: 60-user timeline** — when does he want to scale?
5. **Does Thrive have Google Workspace Business/Enterprise?**

## Pending / Next Steps
- [ ] **WAIT**: Tariq to send Harvest API token + Account ID
- [ ] **WAIT**: Tariq to confirm pilot user emails
- [ ] **WAIT**: Tariq formal go-ahead on $500 USD
- [ ] **ON TOKEN**: Swap dummy Harvest creds for real Thrive creds on Render
- [ ] **ON EMAILS**: Add pilot users to GCP OAuth test users
- [ ] Keep-alive ping for Render + Supabase (prevent sleep)
- [ ] Google OAuth verification (for org-wide rollout later)
- [ ] Browser extension design + build (Phase 2 core)
- [ ] Admin dashboard for managers
- [ ] Explore Gemini API swap (if Thrive confirms Workspace license)
- [ ] Explore Workspace Add-on as delivery format
- [ ] Clarify Antigravity / Google ecosystem question with Tariq

## Resume Prompt
"Resuming Timesheet Assistant. Last: successful demo with Tariq 2026-03-23. Quoted $500 USD POC. Pricing: $5-6/user/month at 60 users, $3-5K AUD for browser extension build. Waiting on Tariq for: (1) Harvest API token, (2) pilot emails, (3) go-ahead, (4) confirm Google Workspace tier. Key decisions: browser extension is core tracking layer, exploring Gemini swap + Workspace Add-on for deeper Google integration. Check services, then pick up next task."
