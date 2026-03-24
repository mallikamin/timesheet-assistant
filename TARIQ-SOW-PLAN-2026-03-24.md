# Tariq SoW Plan - 2026-03-24

## Why this exists

Tariq's latest voice notes changed the immediate priority from "general roadmap" to a saleable Statement of Work with:

- complete setup + implementation cost
- per-person monthly pricing for 50-60 users
- monthly cost minimized, but still profitable for Sitara Infotech
- Gmail integration where AI reviews email activity and asks the user follow-up questions
- a draft-first approval flow before anything lands in Harvest
- a clear position on whether the POC should be free or priced

## Recommended commercial stance

Treat the current live app as the free demo/POC that has already been delivered.

Do not offer more custom build work for free.

Recommended wording:

- "The current demo is the no-cost proof of concept."
- "The next step is a paid pilot implementation for Thrive's real workflow, users, and credentials."

Why this is the best middle ground:

- avoids debating a small POC fee after a live working demo already exists
- keeps momentum with Tariq
- avoids training the client to expect additional custom work for free
- lets Sitara charge for the real implementation phase

Fallback if Tariq insists on a formal POC line item:

- Charge `USD 500` as a discovery/pilot fee
- Credit 100% of it against implementation if Thrive proceeds

## Recommended scope for the next SoW

This SoW should stay Google-native and approval-first.

## Scope audit: what the original USD 3K-5K quote was for

The original quoted scope was "Google Workspace only" and explicitly excluded browser-extension and non-Google tracking work.

Based on the project notes, the original quoted scope covered:

- AI chat assistant
- voice input
- Google SSO
- Supabase persistence
- Google Sheets sync
- Google Calendar integration
- Google Drive integration
- Harvest integration
- deployment and demo readiness

Important nuance:

- Gmail was already part of the original Google-native roadmap, so a light Gmail integration is directionally inside the original quote
- browser extension and non-Google capture were explicitly separate and were always intended to be charged separately

## What is already built vs what is still enhancement work

Already built in the current app:

- chat-based AI logging
- voice input
- Google SSO
- Supabase
- Google Sheets sync
- Calendar suggestions
- Drive activity suggestions
- Harvest sync
- deployed web app

Still not built, and now part of the new SoW discussion:

- Gmail integration
- explicit draft-sheet approval workflow before Harvest sync
- stronger multi-user/admin handling for 50-60 users
- production hardening for wider rollout
- optional Drive revision-history enrichment

## Will the new asks increase the cost?

Yes, if they are all included together.

The biggest reason is not Gmail by itself.

The main cost driver is the workflow change from:

- "create and sync entries immediately"

to:

- "create drafts, stage them in app + Google Sheet, wait for approval, then sync to Harvest"

That approval-first workflow is a real product change and requires:

- data-model changes
- sync-state logic
- approval UI
- batch or per-entry Harvest sync after approval
- more user-state handling for multi-user rollout

Practical pricing read:

- if the SoW is kept lean: Gmail + approval workflow + current Google integrations + rollout hardening, it can still fit inside the `USD 3K-5K` band
- if Gemini migration, stronger admin tooling, deeper Drive revisions, and broader rollout controls are all pulled into the same SoW, the work moves toward the top end of the band and may justify going above it

Recommendation:

- keep the current SoW inside `USD 3K-5K` by limiting it to Google-native rollout features only
- keep browser extension, advanced admin, and wider non-Google capture as a separate paid Phase 2

### In scope

- Google SSO for pilot and rollout users
- Real Thrive Harvest credentials and project/task sync
- Gmail integration for sent-mail and thread-based activity signals
- Calendar-assisted suggestions
- Google Drive activity signals
- Google Drive revision-history checks where the signal is strong
- Manual voice/text entry
- Draft timesheet layer in app + Google Sheet
- User review and approval before Harvest sync
- Multi-user rollout for 50-60 users
- Basic admin visibility for draft status and sync status
- Deployment hardening, logging, and UAT

### Explicitly out of scope

- browser extension
- desktop tracking
- Slack/Chat bot
- Meet transcript automation
- Workspace Marketplace add-on
- enterprise SSO/SAML/SCIM
- advanced manager analytics

## Product direction

The immediate product should not be "log directly to Harvest."

It should be:

1. AI collects signals from Gmail, Calendar, Drive, and user chat/voice.
2. AI creates structured draft entries.
3. Draft entries are stored in the app and mirrored to a Google Sheet.
4. User reviews, edits, and approves.
5. Only approved entries are pushed to Harvest.

This is the right operating model for rollout because it:

- matches Tariq's stated workflow
- reduces trust risk for 50-60 users
- creates a visible review layer for managers
- works whether the LLM is Claude today or Gemini later

## Important technical change vs current app

Current behavior in the live POC:

- app saves entries to Supabase
- syncs to Google Sheets
- pushes to Harvest immediately

Requested behavior for Thrive rollout:

- app saves draft entries first
- syncs drafts to Google Sheet first
- Harvest push happens only after explicit user approval

This means the first engineering task in the SoW is to decouple "draft creation" from "Harvest sync".

## Gmail integration plan

Recommended Gmail v1:

- read sent-mail activity and selected client threads
- cluster emails by client/domain, thread, and time window
- generate draft time suggestions
- ask clarifying questions when confidence is low
- do not auto-log email-derived time straight into Harvest

Recommended privacy boundary for v1:

- default to metadata + subject + snippet + selected thread summary
- only inspect full thread content when required by the workflow and clearly approved

This gives Tariq the Gmail value without creating an unnecessarily invasive first release.

## Implementation plan

### Phase A - Pilot hardening

- add approval state and sync state to entries
- stop auto-pushing every entry into Harvest
- add review queue UI
- generate Google Sheet draft register
- support approve, reject, and edit actions

### Phase B - Gmail intelligence + low-hanging Google signals

- add Gmail scopes and OAuth flow updates
- pull sent-mail activity for target date range
- cluster by contact, domain, subject, and thread
- ask the user follow-up questions when mapping is weak
- merge Gmail suggestions with manual and calendar suggestions
- enrich suggestions with recent Drive file activity
- add revision-history checks for key Docs/Sheets where useful

### Phase C - 50-60 user rollout

- real Harvest workspace configuration
- user onboarding
- production env hardening
- usage monitoring
- light admin visibility
- UAT and go-live

## Commercial model

### Recommended pricing

- One-time setup + implementation: `USD 3,000-5,000`
- Monthly software fee:
  - `USD 5/user/month` on annual or fixed-term commitment
  - `USD 6/user/month` month-to-month
- Minimum monthly commitment: `50 users`

### What that means at rollout size

| Users | Price/user | Monthly total |
|------|-----------:|--------------:|
| 50 | $5 | $250 |
| 50 | $6 | $300 |
| 60 | $5 | $300 |
| 60 | $6 | $360 |

### Optional support policy

Base monthly pricing should include:

- hosting
- normal maintenance
- small bug fixes

It should not silently include ongoing custom feature work.

If Tariq expects hands-on support, reporting tweaks, or change requests every month, add a separate support retainer instead of lowering margin on the core subscription.

Suggested support retainer if needed:

- `USD 250-500/month` depending on responsiveness and scope

## Lean unit economics for Sitara

Assumptions:

- one production app service
- one production database
- one Sitara Render seat
- Gemini used for production LLM workload
- moderate daily usage across 50-60 users

Estimated monthly cost base:

| Cost item | Estimated monthly | Per user at 60 |
|---|---:|---:|
| Render app hosting | $44-63 | $0.73-1.05 |
| Supabase | $25 | $0.42 |
| Gemini AI usage reserve | $15-60 | $0.25-1.00 |
| Ops / monitoring reserve | $15-30 | $0.25-0.50 |
| **Total estimated cost** | **$99-178** | **$1.65-2.97** |

Interpretation:

- at `60 users x $5`, revenue is `$300/month`
- at `60 users x $6`, revenue is `$360/month`
- this keeps the monthly price low enough for Tariq's ask
- it still leaves room for margin if support is controlled

## Recommended negotiation position

Lead with this:

1. Current app = free proof of concept already delivered
2. Next step = paid implementation for Gmail + approval workflow + 50-60 user rollout
3. Keep monthly price low with a 50-user minimum
4. Keep browser extension as a later phase, not in this SoW

If price pressure increases:

- keep monthly at `$5/user`
- reduce month-to-month flexibility
- require a minimum user floor
- keep support outside the base monthly fee

Do not solve price pressure by expanding scope for free.

## Gemini answer

Yes, Gemini can support this workflow.

The draft -> review -> approve -> Harvest pattern is application logic, not Claude-specific logic.

Gemini can:

- return structured JSON for draft entries
- use function calling/tool use for actions like:
  - create draft entries
  - update Google Sheet rows
  - push approved entries to Harvest

The main work is prompt tuning and orchestration, not model limitation.

## Open questions for Tariq

- Does Thrive want daily approvals, weekly approvals, or both?
- Should Gmail analysis look only at sent mail first, or full client threads?
- Does Thrive want approved entries pushed to Harvest as drafts or as ready-to-submit entries?
- Who will act as the admin owner for the 50-60 user rollout?
- Is the 50-60 user rollout immediate, or does Tariq want a smaller pilot first?

## Recommended next message to Tariq

"The live demo can be treated as the free POC already completed. The next step is a paid implementation focused on Thrive's real workflow: Gmail-assisted time capture, draft timesheet review in app/Google Sheet, and push to Harvest only after user approval. For 50-60 users, we can keep the monthly fee lean at around $5-6 per user with a 50-user minimum, and keep browser extension tracking as a separate future phase."
