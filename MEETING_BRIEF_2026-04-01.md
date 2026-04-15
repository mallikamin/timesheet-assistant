# TARIQ MEETING BRIEF — 2026-04-01
> 5-Minute Briefing for Malik Amin

---

## WHERE WE ARE

### Documents Created (2026-03-25)
1. **SOW-Thrive-v3.pdf** (8 pages) — Main SoW, sent to Jawad for approval
2. **Reporting-Enhancement-Thrive.pdf** (3 pages) — Separate reporting automation proposal
3. **PHASE1-ENHANCED-PLAN.md** — Internal plan to add 3 features (+$1,400)

### Approval Status
- ❌ **Not yet sent to Tariq** — waiting on Jawad's internal approval first
- Decision: Do we present **v3.0 ($5,850)** or **Enhanced ($6,850)**?

---

## TWO PRICING OPTIONS

### Option A: SoW v3.0 (Current Document)
| Phase | Price (USD) | What's Included |
|-------|-------------|-----------------|
| Demo | Delivered | Current live demo |
| **POC** | **$500** | 1-2 Thrive users, real Harvest data |
| **Phase 1** | **$5,850** | Gmail integration, Calendar, Drive, draft approval workflow, 60 users, 10-day hypercare |
| **Monthly** | **$5/user** (annual) or **$7.50/user** (M2M) | 50-user minimum |

**At 60 users annual**: $300/month = $3,600/year
**Year 1 total**: $500 (POC) + $5,850 (Phase 1) + $3,600 (12 months) = **$9,950**
*(POC credited if proceed within 7 days → $9,450)*

---

### Option B: Enhanced Plan (+$1,400)
**Same as Option A, PLUS 3 features:**

1. **Gmail Sidebar Add-on**
   - Native Gmail sidebar panel (appears inside Gmail)
   - Contextual client/project suggestions from email
   - One-click "Add Draft" button without leaving Gmail
   - Uses Google Apps Script (free API, no Marketplace review needed)

2. **Smart Push Reminders**
   - Browser web push notifications (Firebase Cloud Messaging - free)
   - 3 automated reminders:
     - Daily 9am AEST: "4 draft entries to review"
     - Friday 3pm AEST: "28/40 hours logged this week"
     - Monday 9am AEST: "3 unapproved entries from last week"

3. **Weekly Manager Report**
   - Auto-generated Google Doc every Friday 4pm AEST
   - Team utilization %, unapproved entries, missing time gaps, top projects
   - Auto-shared to manager's Google Drive
   - Formatted with Thrive branding

**Enhanced Phase 1**: **$6,850** (everything else unchanged)
**Year 1 total**: $500 + $6,850 + $3,600 = **$10,950** *(or $10,450 with POC credit)*

---

## OPEN QUESTIONS FOR TARIQ (from SoW Section 8)

1. ⏱️ **Approval cadence**: daily, weekly, or both?
2. 📧 **Gmail depth**: sent mail only or full client threads?
3. ✅ **Harvest entry status**: drafts or ready-to-submit after approval?
4. 👥 **Rollout**: pilot 5-10 users first or direct 50-60?
5. 🔑 **Admin owner**: who manages rollout at Thrive?
6. 📊 **Forecast API access**: does Thrive have Harvest Forecast API key?
7. ☁️ **Google Workspace tier**: Business or Enterprise?

---

## KICKOFF REQUIREMENTS (for $500 POC)

To start 1-2 user pilot immediately after approval:

1. ✅ **Harvest API token** + Account ID (Thrive's real account)
2. ✅ **1-2 pilot user emails** (e.g., Tariq + 1 team member)
3. ✅ **Pilot users assigned** to at least one Harvest project
4. ✅ **Google Workspace admin** to mark app as Internal (org-wide access)
5. ⚠️ **Forecast API key** (optional, only needed for reporting enhancement)

---

## WHAT TARIQ ASKED FOR (from Voice Notes 2026-03-24)

✅ **Full cost breakdown for 50-60 users** → SoW Section 5
✅ **Minimize monthly cost** → $5/user annual (lowest viable)
✅ **Gmail integration** → Included in Phase 1
✅ **Draft approval workflow** → Core feature in Phase 1
✅ **Separate browser extension** → Excluded from Phase 1 (separate Phase 2, TBC)

---

## TARIQ'S REPORTING PAIN POINT (from Screenshots 2026-03-25)

**Current manual workflow**:
- Export Harvest time entries to CSV → Excel
- Export Forecast schedules → manual cross-reference
- Build utilization reports in Excel (billable %, scheduled vs actual, capacity)
- Team roster maintained separately

**Opportunity**: Automate with Harvest + Forecast APIs (both available)
- Covered in **Reporting-Enhancement-Thrive.pdf** (companion doc, pricing TBC)
- Can be Phase 1.5 or Phase 2, separate from core timesheet assistant

---

## DECISION MATRIX FOR THIS MEETING

| Question | Answer | Next Action |
|----------|--------|-------------|
| Has Jawad approved SoW v3.0? | ☐ Yes ☐ No | If No: get approval before sending to Tariq |
| Present Enhanced Plan (+$1,400)? | ☐ Yes ☐ No | If Yes: update SoW pricing to $6,850 |
| Is Tariq ready to proceed with POC? | ☐ Yes ☐ No | If Yes: collect kickoff requirements |
| Can Tariq answer 7 confirmation questions? | ☐ Yes ☐ No | If Yes: capture answers in Decision-Log.md |
| Can Tariq provide Harvest credentials now? | ☐ Yes ☐ No | If Yes: swap dummy creds on Render immediately |

---

## CONVERSATION FLOW (Suggested)

1. **Status check** (1 min)
   - "Have you had a chance to review the pricing direction we discussed last week?"
   - Gauge Tariq's urgency and internal approval status

2. **SoW walkthrough** (2 min)
   - Present Option A ($5,850) as baseline
   - If Tariq asks for "more features": present Option B ($6,850)
   - Highlight: POC $500 credited if proceed within 7 days

3. **Answer open questions** (1 min)
   - Walk through 7 confirmation questions (SoW Section 8)
   - Capture answers for implementation planning

4. **Next steps** (1 min)
   - If approved: collect kickoff requirements immediately
   - If needs time: set follow-up date (max 3 days)
   - If stalled: ask what's blocking (budget? approval? scope?)

---

## PRICING NEGOTIATION (Back-Pocket)

**If Tariq pushes on implementation price:**
- Option 1: Drop to $5,450 (original v2.0 price, remove admin dashboard)
- Option 2: Bundle POC into Phase 1 (remove POC line item, keep $5,850)
- Option 3: Offer payment plan (3 installments instead of 50/50)

**If Tariq pushes on monthly price:**
- Option 1: Gemini swap (reduce AI infra cost, stay at $5/user)
- Option 2: Annual-only (remove M2M option, simplify)
- Option 3: Tiered pricing (51-60 users at $5, 61+ at $4.50)

**DO NOT go below**:
- Implementation: $5,000 minimum
- Monthly: $4.50/user minimum (covers infra + margin)

---

## FILES TO SHARE (if approved)

1. **SOW-Thrive-v3.pdf** (or updated with $6,850 if Enhanced)
2. **Reporting-Enhancement-Thrive.pdf** (position as "optional future add-on")
3. **Demo link**: https://timesheet-assistant-jclk.onrender.com

---

## POST-MEETING ACTIONS

If approved:
1. Update Decision-Log.md with meeting notes
2. Update MEMORY.md with final pricing and Tariq's answers
3. Commit SoW + checkpoint files to git
4. Email formal SoW PDF to Tariq with signature block
5. Collect Harvest API token + pilot user details
6. Swap dummy Harvest creds on Render
7. Add pilot users to GCP OAuth test users
8. Start POC (1-2 days delivery)

If not approved:
1. Capture blockers in Decision-Log.md
2. Set follow-up date
3. Prepare revised SoW if scope/pricing changes requested

---

## KEY TALKING POINTS

✅ **"Demo was free, POC is $500 to validate with real Harvest data"**
✅ **"Phase 1 is $5,850 for 60 users — includes Gmail, Calendar, Drive, approval workflow, 10-day hypercare"**
✅ **"Monthly is $5/user annual or $7.50/user M2M, 50-user minimum protects both sides"**
✅ **"POC credited in full if you proceed within 7 days"**
✅ **"Browser extension is separate Phase 2, we keep Phase 1 Google-native as you requested"**
✅ **"Reporting automation is optional enhancement, separate pricing, we can tackle after Phase 1 is live"**
✅ **"Year 1 total is $9,450 at 60 users (with POC credit)"**

---

## RISKS TO WATCH

⚠️ **Tariq may need internal approval from Thrive leadership** → offer to present to CEO Leilani if needed
⚠️ **Harvest API token may take time** → can start Gmail/Calendar work while waiting
⚠️ **Budget may be tight** → emphasize ROI (saves 2-3 hours/week per user = $120-180/week/user at AU rates)
⚠️ **Scope creep risk** → keep browser extension and reporting as separate phases, don't bundle

---

**GOAL**: Leave meeting with either (1) approval + kickoff date, or (2) clear timeline for decision + follow-up booked.
