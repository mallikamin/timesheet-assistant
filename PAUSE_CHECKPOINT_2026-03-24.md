# Pause Checkpoint — 2026-03-24 (SoW + Phase 2 Planning)

## Project
- **Name**: Time Logging Automation (Thrive Timesheet Assistant)
- **Path**: C:\Users\Malik\desktop\timelogging
- **Branch**: main (clean, pushed to origin — new files untracked)
- **Live URL**: https://timesheet-assistant-jclk.onrender.com

## Goal
Create a professional Statement of Work and Phase 2 plan based on Tariq's voice note feedback. Tariq wants: full cost breakdown for 50-60 users, minimized monthly cost, Gmail integration, draft-first approval workflow before Harvest, and a clear separation between Google-native rollout and browser extension.

## Completed
- [x] Decoded Tariq's 5 voice note requests into actionable items
- [x] Reconciled analysis between Claude (Opus) and Codex (OpenAI)
- [x] Created SoW v2.0 — `SOW-Thrive-Timesheet-Assistant.html` (print-to-PDF ready)
- [x] Created Phase 2 standalone plan — `Phase-2-Browser-Extension-Plan.html`
- [x] Codex created internal analysis docs (TARIQ-SOW-PLAN, THRIVE-SOW-DRAFT, PHASE-2-SEPARATE-PLAN)
- [x] Decision-Log.md updated with 2026-03-24 entry
- [x] Memory updated with current pricing, decisions, and lessons learned
- [x] SoW refined through multiple iterations:
  - POC = already delivered (no more free work)
  - Phase 2 removed from main SoW (separate document)
  - Implementation: $5,450 (not round $5K — looks more considered)
  - Annual: $5/user/month, M2M: $7.50/user/month (50% gap to discourage M2M)
  - 50-user minimum billing floor
  - 10 business days hypercare included in implementation
  - Extended support NOT priced in SoW (quote separately if asked: $500/mo retainer or $75-125/hr)
  - Source code transfer explicitly excluded (SaaS/licence model, not handover)
  - Delivery timeline: 4 weeks (not 6 — most is already built)

## In Progress
- [ ] Tariq has not yet responded to the SoW — waiting for his feedback
- [ ] Open questions for Tariq still pending (approval cadence, Gmail depth, Harvest entry status, rollout plan, admin owner)

## Pending
- [ ] Tariq to send Harvest API token + Account ID (real Thrive account)
- [ ] Tariq to confirm pilot user emails
- [ ] Tariq to answer 5 open questions in SoW section 8
- [ ] Tariq to confirm whether Thrive has Google Workspace Business/Enterprise (Gemini swap opportunity)
- [ ] Swap dummy Harvest creds for real Thrive creds on Render
- [ ] Add pilot users to GCP OAuth test users
- [ ] Keep-alive ping for Render + Supabase (prevent sleep)
- [ ] Build Gmail integration (when approved)
- [ ] Build draft approval workflow (when approved)
- [ ] Build multi-user support + admin visibility (when approved)
- [ ] Production hardening for 60 users

## Key Decisions
- **POC = free, already delivered.** No more free work. Codex and Claude both agreed.
- **SoW covers Phase 1 only.** Phase 2 (browser extension) is a separate document and separate charge.
- **$5,450 implementation** — slightly above $5K, looks more deliberate than a round number.
- **$5/user annual vs $7.50/user M2M** — 50% gap strongly encourages annual commitment.
- **50-user minimum billing floor** — guarantees $250/month minimum revenue.
- **10 business days hypercare** in implementation — protects against open-ended onboarding.
- **Extended support quoted separately** — not in SoW. Back-pocket rates: $500/mo retainer or $75-125/hr.
- **SaaS/licence model, NOT code handover** — source code transfer excluded unless separately agreed.
- **Draft-first approval workflow** — biggest architecture change. AI drafts → Google Sheet → user approves → Harvest.
- **Gmail integration** fits inside Google-native scope (not a Phase 2 feature).
- **Gemini confirmed compatible** — function calling + structured output. Swap option preserved for future.
- **All prices in USD** (not AUD as originally quoted).
- **Delivery: 4 weeks** from receiving Harvest credentials.

## Files Created/Modified This Session
- `SOW-Thrive-Timesheet-Assistant.html` — **THE main deliverable.** Professional SoW, print to PDF. Phase 1 only.
- `Phase-2-Browser-Extension-Plan.html` — Standalone Phase 2 plan with full technical spec and pricing ($3,500).
- `TARIQ-SOW-PLAN-2026-03-24.md` — Codex internal analysis (scope audit, pricing logic, negotiation position).
- `THRIVE-SOW-DRAFT-2026-03-24.md` — Codex client-facing SoW draft (markdown format).
- `PHASE-2-SEPARATE-PLAN-2026-03-24.md` — Codex Phase 2 separation plan.
- `Decision-Log.md` — Updated with 2026-03-24 entry (Tariq voice notes, pricing decisions).
- `MEMORY.md` — Updated with final pricing, SoW decisions, open questions.

## Uncommitted Changes
- Modified: `.claude/settings.local.json`, `Decision-Log.md`
- Untracked: `PAUSE_CHECKPOINT_2026-03-23.md`, `PHASE-2-SEPARATE-PLAN-2026-03-24.md`, `Phase-2-Browser-Extension-Plan.html`, `SOW-Thrive-Timesheet-Assistant.html`, `TARIQ-SOW-PLAN-2026-03-24.md`, `THRIVE-SOW-DRAFT-2026-03-24.md`
- Nothing committed this session — all new files are on disk but not in git.

## Errors & Resolutions
- No errors this session. Pure planning/documentation work.

## Critical Context
- **Two AI agents collaborated**: Claude (Opus) for HTML SoW + strategy, Codex (OpenAI) for internal analysis + commercial positioning. Both edited the same SoW file — final version incorporates best of both.
- **Codex's key contribution**: "hypercare" framing, source-code exclusion clause, keeping support rates OUT of SoW, lean scope to stay in $3-5K band.
- **Claude's key contribution**: Professional HTML with print CSS, market comparison table, workflow visualization, Phase 2 standalone document.
- **SoW is ready to send** — Malik should open in browser, print to PDF, review once, then send to Tariq.
- **Tariq may run our SoW through Codex/AI for review** — document is technically sound and competitively priced.
- **Back-pocket negotiation**: If Tariq pushes on implementation price, can drop to $4,500 by deferring admin dashboard. If pushes on monthly, Gemini swap drops infra cost and preserves margin at $5/user.
- **Margin at 60 users annual**: $300/month revenue - ~$140 infra = ~$160/month (Claude) or ~$250/month (Gemini).

## Resume Prompt
"Resuming Timesheet Assistant. Last session: Created SoW v2.0 and Phase 2 plan based on Tariq's voice note feedback. SoW: $5,450 implementation + $5/user/month annual (50-user min) + 10-day hypercare. Phase 2 browser extension: $3,500 separate. Waiting on Tariq for: (1) feedback on SoW, (2) Harvest API token, (3) answers to 5 open questions, (4) Google Workspace tier confirmation. SoW file ready to print-to-PDF. Check if Tariq has responded, then pick up next action."
