# Time Logging Automation - Tomorrow Call Plan

## Objective for Tomorrow
Align the client on a concrete Phase 1 automation approach that reduces end-of-week timesheet effort while preserving Harvest/team lead approval workflow.

## Proposed Meeting Flow (45-60 min)

### 1) Context and Goal Lock (5 min)
- Confirm current flow: Google Calendar/manual input -> Harvest draft/entry -> team lead approval.
- Confirm target state: system auto-prepares entries; user only reviews/submits.

### 2) Demo-level Solution Walkthrough (10 min)
- Input sources: Google Calendar + Chrome extension activity context + optional Excel/Sheet mapping.
- Automation engine: rule-based project/activity mapping + confidence scoring.
- Output: Harvest draft entries with audit-friendly notes.
- Approval: unchanged team lead approval.

### 3) Phase 1 Scope Confirmation (10 min)
- Org-wide rollout up to 100 users.
- Single Harvest workspace.
- Works for both calendar and non-calendar users.
- Standard naming assumed unless exceptions are provided.

### 4) Decision Questions (15-20 min)
Ask these to drive implementation decisions only (not general discovery):

1. Data source priority
- If Calendar and browser context conflict, which should win by default?

2. Auto-post policy
- Should high-confidence entries be auto-created as drafts daily, or only generated at week end?

3. Confidence threshold
- What confidence level should trigger "Needs Review" instead of direct draft creation?

4. Mapping ownership
- Who owns the mapping file/rules (PMO, Ops, Team leads), and who can change it?

5. Minimum granularity
- Smallest allowed entry block (for example 15 vs 30 minutes)?

6. Notes standard
- What note format is required for audit readiness (event title, app/domain tags, manual reason)?

7. Non-calendar users
- For users with no useful Calendar data, should we rely on browser context + manual quick-review queue?

8. Privacy boundary
- Is domain-level capture enough, or do they need full URL/page titles? (Recommend domain-level only.)

9. Exception handling
- How should uncategorized time be routed: user review queue, team lead queue, or shared ops queue?

10. Reminder policy
- When should nudges be sent (daily EOD, Thursday, Friday), and via what channel (email only or Teams/Slack too)?

11. Submission behavior
- Should system auto-submit after user review, or keep explicit submit click mandatory?

12. Rollout strategy
- Start all 100 users at once, or staged by department over 2-3 waves?

### 5) Close with Deliverables (5 min)
- Confirm Phase 1 architecture.
- Confirm rule/mapping owner.
- Confirm rollout mode (big bang vs waves).
- Confirm timeline and sign-off checkpoint.

## Recommended Decisions to Push Tomorrow
- Draft-first model (never direct final submission).
- Domain-level browser capture (privacy-safe default).
- Daily draft generation + Friday review reminder.
- Low-confidence items routed to "Needs Review" queue.

## What We Will Send After Call
1. Finalized Phase 1 scope note.
2. Rule/mapping template (Excel/Sheet format).
3. Implementation timeline with milestones (Week 1-4).
4. Pilot acceptance criteria for go-live.
