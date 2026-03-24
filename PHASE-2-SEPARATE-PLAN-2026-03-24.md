# Phase 2 Separate Build Plan - 2026-03-24

## Purpose

This document isolates the features that should NOT be folded into the current Google-native SoW.

These items represent a separate build and should be priced separately after the Google-native rollout is approved.

## Why this is a separate phase

The current SoW is focused on:

- Gmail
- Calendar
- Drive
- draft-sheet approval workflow
- Harvest sync after approval
- rollout for 50-60 users

The separate Phase 2 is different work.

It expands the product beyond Google signals into universal browser-based activity capture.

That means new client-side software, new ingestion logic, new privacy controls, and different operational risk.

## Recommended Phase 2 scope

### Core deliverables

- Chrome browser extension
- active-tab tracking by domain, page title, and time window
- idle detection and session boundaries
- categorization rules for common tools like Jira, Figma, Asana, Slack web, and Google apps
- extension-to-backend activity ingestion
- AI clustering of captured activity into draft time blocks
- one-click "log this block" or "send to draft sheet"
- privacy controls such as allowlist / denylist / pause tracking
- manager/admin visibility into captured vs approved activity

### Product outcome

Instead of relying only on explicit user input or Google APIs, the system starts building a timeline of what the user was actually working on in the browser.

This is the feature set that unlocks:

- non-Google work capture
- better duration estimates
- cross-tool visibility
- less dependence on Gmail and Drive as the only activity sources

## What Phase 2 should NOT include

Keep these out unless separately approved:

- desktop agent for native apps
- Outlook desktop / Excel desktop tracking
- mobile app
- advanced analytics and BI dashboards
- SSO/SAML enterprise identity work
- Marketplace distribution
- automated timesheet submission without user review

## Suggested implementation breakdown

### Phase 2A - Extension foundation

- extension shell
- auth handshake with backend
- tab and session tracking
- idle detection
- manual pause/resume

### Phase 2B - Activity intelligence

- normalize browser events
- map URLs/titles to clients, projects, and work types
- cluster events into candidate time blocks
- send suggested blocks to the same draft approval layer used in the main app

### Phase 2C - Admin and rollout

- privacy settings
- domain rules
- manager visibility
- rollout testing across 50-60 users
- telemetry and error handling

## Commercial recommendation

This should be quoted as an additional fixed-fee build after the Google-native SoW.

### Recommended price band

- Separate Phase 2 build: `USD 3,000-5,000 additional`

That price assumes:

- Chrome only
- browser tracking only
- reuse of the existing backend and draft approval flow
- basic admin controls, not a full enterprise admin suite

If Tariq later wants:

- desktop app tracking
- richer manager analytics
- more complex workflow controls
- broader enterprise controls

that should become a later phase, not absorbed into this quote.

## Positioning for Tariq

Recommended explanation:

- "Phase 1 is the Google-native rollout and approval workflow."
- "Phase 2 is the universal browser-capture layer for non-Google work like Jira, Figma, Asana, and other web tools."
- "We are separating them so Thrive only pays for the layer it wants right now."

## Why the separation helps commercially

- keeps the current SoW easier to approve
- prevents scope mixing between Google-native automation and browser surveillance-style tracking
- lets Tariq choose rollout order based on client comfort
- preserves pricing leverage for the larger platform build

## Recommended order

1. Approve and deliver the Google-native SoW first
2. Validate adoption and approval workflow with real users
3. Add the browser extension as Phase 2 once Thrive wants broader capture outside Gmail/Calendar/Drive
