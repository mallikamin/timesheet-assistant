# Statement of Work Draft

## AI-Assisted Time Logging for Thrive PR

Prepared for: Thrive PR / Tariq Munir  
Prepared by: Sitara Infotech  
Date: 2026-03-24

## 1. Objective

Build and roll out a Google-native, AI-assisted time logging workflow for Thrive PR that:

- captures work signals from Google tools and direct user input
- creates draft timesheet entries
- allows users to review and approve entries
- pushes approved entries into Harvest
- minimizes recurring monthly cost for a 50-60 user rollout

## 2. Current Position

A live proof of concept already exists and can be treated as the initial no-cost demo.

The next step is a production-focused implementation aligned to Thrive's real workflow, users, and credentials.

## 3. Scope of Work - Phase 1

Phase 1 is the Google-native rollout.

### Included features

- AI-powered voice and text time logging
- Google SSO login
- Google Calendar-assisted time suggestions
- Gmail-assisted time suggestions
- Google Drive activity signals
- draft timesheet register in app and Google Sheet
- user review, edit, and approval workflow
- Harvest sync only after approval
- project/task mapping to Thrive's Harvest structure
- deployment, configuration, and rollout support for 50-60 users

### Target workflow

1. User dictates, types, or works across Gmail / Calendar / Drive.
2. AI creates structured draft entries.
3. Draft entries appear in the app and Google Sheet.
4. User reviews, edits, and approves.
5. Approved entries are pushed into Harvest.

## 4. Deliverables

- configured production environment
- Google OAuth configuration for Thrive users
- Harvest workspace integration using Thrive credentials
- Gmail, Calendar, and Drive signal ingestion for draft creation
- draft approval workflow
- Google Sheet visibility layer
- rollout support for initial 50-60 user deployment
- basic training / handover

## 5. Commercials - Phase 1

### One-time implementation

- `USD 3,000-5,000`

This covers setup, configuration, workflow implementation, integration work, testing, and launch support.

### Monthly software fee

- `USD 5/user/month` on fixed-term or annual commitment
- `USD 6/user/month` month-to-month
- minimum billing floor: `50 users`

### Monthly examples

| Users | Price/user | Monthly total |
|---|---:|---:|
| 50 | $5 | $250 |
| 50 | $6 | $300 |
| 60 | $5 | $300 |
| 60 | $6 | $360 |

## 6. Assumptions

- Thrive provides the required Harvest credentials and Google access
- rollout remains within the Google-native scope described above
- approval workflow is user-first and Harvest sync happens after approval
- monthly fee covers normal hosting, maintenance, and minor bug fixes
- major new features are quoted separately

## 7. Explicit Exclusions

The following are not included in Phase 1 and would be quoted separately:

- browser extension for non-Google activity capture
- desktop app tracking
- mobile app
- enterprise SSO / SAML / SCIM
- advanced analytics dashboards
- Marketplace distribution
- broader non-Google integrations

## 8. Optional Phase 2 - Separate Build

If Thrive wants broader coverage beyond Gmail / Calendar / Drive, Sitara can deliver a separate browser-based activity capture phase.

### Phase 2 features

- Chrome browser extension
- active tab tracking across browser tools
- idle detection and session grouping
- non-Google work capture for tools such as Jira, Figma, Asana, and Slack web
- activity clustering into draft time blocks
- privacy controls and admin visibility

### Phase 2 commercial range

- additional build fee: `USD 3,000-5,000`

This phase is intentionally separate so Thrive can approve the Google-native rollout first and add broader capture later only if needed.

## 9. Indicative Timeline

### Phase 1

- implementation and rollout: `4-6 weeks`

### Optional Phase 2

- browser-extension build: `4-6 weeks additional`

## 10. Next Steps

To finalize this SoW, Thrive should confirm:

- Gmail privacy boundary and desired depth of email analysis
- approval cadence: daily, weekly, or both
- whether approved entries should enter Harvest as drafts or ready-to-submit entries
- pilot vs direct 50-60 user rollout
- preferred final document format: PDF, DOC, or both
