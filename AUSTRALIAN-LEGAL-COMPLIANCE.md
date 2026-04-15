# Australian Legal Compliance — Timesheet Assistant
> Ensuring compliance with Australian Privacy, Copyright, and Workplace laws

**Date**: 2026-04-01
**Client**: Thrive PR + Communications (AU/NZ)
**Requirement**: "Nothing should be against Australian laws - copyright laws etc"

---

## RELEVANT AUSTRALIAN LAWS

### 1. Copyright Act 1968 (Cth)
**What it covers**:
- Email content is automatically copyrighted to the author
- Documents, presentations, creative work in Drive
- Meeting notes, calendar descriptions
- Any original written content

**Our risk**:
- ❌ Reading and storing full email content without permission
- ❌ Reproducing copyrighted material in time entry notes
- ❌ Training AI models on client confidential/copyrighted content

**Our mitigation**:
- ✅ **Metadata-only approach**: Read subject, sender, recipient, timestamp — NOT full email body
- ✅ **User consent**: Explicit opt-in for Gmail/Calendar/Drive scanning
- ✅ **No storage**: Process in-memory, don't persist copyrighted content
- ✅ **No AI training**: Use API models (Claude/Gemini), never fine-tune on client data

---

### 2. Privacy Act 1988 (Cth) — Australian Privacy Principles (APPs)
**What it covers**:
- Collection, use, disclosure, storage of personal information
- Cross-border data transfers
- Security safeguards
- Individual access and correction rights

**Our obligations**:
- **APP 1**: Privacy policy clearly stating what we collect and why
- **APP 3**: Only collect what's necessary for time logging
- **APP 5**: Tell users how we'll use their data (time entries only)
- **APP 6**: Only use data for time logging, never marketing/other purposes
- **APP 8**: Cross-border disclosure (US-based APIs) requires consent
- **APP 11**: Security safeguards (encryption, access controls)

**Our compliance**:
- ✅ **Privacy Policy**: Clear statement on what we collect (emails metadata, calendar events, Drive activity)
- ✅ **Purpose limitation**: Data used ONLY for generating time entries, nothing else
- ✅ **Minimal collection**: Only subject lines, not full content
- ✅ **Encryption**: HTTPS, encrypted database (Supabase encrypted at rest)
- ✅ **Access controls**: Per-user data isolation, Google SSO authentication
- ✅ **Cross-border consent**: Disclose that AI processing happens in US (Claude/Gemini APIs)
- ✅ **Right to erasure**: User can delete all their data via admin panel

---

### 3. Fair Work Act 2009 (Cth) — Workplace Surveillance
**What it covers**:
- Employer monitoring of employee communications and computer use
- Notice and consent requirements vary by state (e.g., NSW Workplace Surveillance Act 2005)

**Our obligations**:
- Employees must be notified that their Gmail/Calendar/Drive activity is being monitored
- Employer (Thrive) must have a legitimate business purpose (accurate time tracking)
- Cannot be used for performance surveillance beyond time tracking

**Our compliance**:
- ✅ **Employer authorization**: Thrive admin must enable feature for organization
- ✅ **Employee consent**: Each user opts in to Gmail/Calendar/Drive scanning
- ✅ **Purpose notice**: "This tool reads your email metadata to suggest time entries. It does not read full email content or monitor your performance."
- ✅ **Transparency**: Users see what data was used for each suggestion
- ✅ **User control**: Users can disable scanning at any time

---

### 4. Spam Act 2003 (Cth)
**What it covers**:
- Unsolicited commercial electronic messages

**Our risk**: Low (we're not sending marketing emails)

**Our compliance**:
- ✅ Notifications are transactional (time entry reminders), not commercial
- ✅ Users opt-in to push notifications
- ✅ Clear unsubscribe mechanism

---

### 5. Data Sovereignty (Australian Government Contracts)
**What it covers**:
- Some Australian government/regulated entities require data stored in Australia

**Thrive's status**: Private company (not government) — less strict requirements

**Our compliance**:
- ✅ **Current**: Data in US (Supabase US-East, Render US-East, Claude/Gemini US APIs)
- ✅ **Option**: Can deploy to Australian region if required (Supabase AU, Render Sydney, Gemini AU endpoint)
- ✅ **Disclosure**: POC will clearly state data residency (US), offer AU upgrade if needed

---

## COMPLIANCE-FIRST ARCHITECTURE

### What We Collect (POC Approach)

| Data Source | What We Read | What We DON'T Read | Storage |
|-------------|--------------|-------------------|---------|
| **Gmail** | Subject, sender, recipient, timestamp, thread ID | ❌ Email body, attachments, quoted replies | Metadata only (discarded after processing) |
| **Calendar** | Event title, attendees, start/end time, location | ❌ Event description, notes, attachments | Metadata only (discarded after processing) |
| **Drive** | File name, modified date, owner, shared with | ❌ File content, comments, version history | Metadata only (discarded after processing) |
| **Time Entries** | Date, project, task, hours, notes (user-written) | ❌ Source emails/docs are NOT stored | Persistent (Supabase + Google Sheets + Harvest) |
| **User Profile** | Email, name, Google ID, Harvest user ID | ❌ Contacts, browsing history, passwords | Persistent (Supabase, encrypted) |

---

### Data Flow (Copyright-Safe)

```
1. USER INITIATES SCAN
   ↓ (explicit user action, not automatic)

2. FETCH METADATA ONLY
   Gmail API: GET /messages?q=from:client@example.com → subject, sender, timestamp
   Calendar API: GET /events → summary, attendees, start/end
   Drive API: GET /files → name, modifiedTime, owners
   ↓ (no full content fetched)

3. AI PROCESSING (IN-MEMORY ONLY)
   Send to Claude/Gemini: "Subject: Q2 Strategy Call, Attendees: afterpay.com.au, Time: 2h"
   AI suggests: "Client: Afterpay, Project: AUNZ Retainer, Hours: 2, Notes: Q2 Strategy Call"
   ↓ (original metadata discarded after AI response)

4. USER REVIEWS & EDITS
   Draft entry shown in UI → user approves, edits, or rejects
   ↓ (user control, not automatic)

5. STORE APPROVED ENTRY ONLY
   Supabase: {date, project, task, hours, notes}
   Google Sheets: Same
   Harvest: Same (after approval)
   ↓ (NO email content, NO document content stored)
```

**Key principle**: We never store copyrighted content, only user-generated time entry metadata.

---

## POC LEGAL SAFEGUARDS

### 1. User Consent Flow (First Login)

```
┌─────────────────────────────────────────────────────┐
│  Welcome to Thrive Timesheet Assistant              │
│                                                      │
│  This tool helps you log time by reading metadata   │
│  from your Google Workspace account.                │
│                                                      │
│  What we collect:                                   │
│  ✓ Email subject lines (not full content)          │
│  ✓ Calendar event titles and attendees             │
│  ✓ Drive file names and activity                   │
│                                                      │
│  What we DON'T collect:                            │
│  ✗ Full email content or attachments               │
│  ✗ Document contents or comments                   │
│  ✗ Passwords or personal contacts                  │
│                                                      │
│  Your data is:                                      │
│  • Processed in-memory only (not stored)           │
│  • Used only for time entry suggestions            │
│  • Sent to US-based AI APIs (Claude/Gemini)        │
│  • Encrypted in transit and at rest                │
│                                                      │
│  You can disable scanning at any time.             │
│                                                      │
│  [ ] I consent to metadata collection              │
│  [ ] I acknowledge cross-border AI processing      │
│                                                      │
│  [Continue]  [Learn More]  [Contact Admin]         │
└─────────────────────────────────────────────────────┘
```

### 2. Privacy Policy (Required for POC)

**Must include**:
- What data we collect and why
- How we use it (time logging only)
- Where it's stored (US cloud providers)
- Who has access (user + Thrive admins only)
- How long we keep it (time entries: indefinitely; metadata: not stored)
- User rights (access, correction, deletion)
- How to contact us (Sitara Infotech + Thrive admin)
- Cross-border disclosure (AI APIs in US)

**Action**: Create `PRIVACY-POLICY.md` and link from POC login page.

### 3. Employer Authorization (Thrive Admin)

**Before POC launch**:
- Thrive admin (Tariq or delegate) must authorize the tool for organization
- Admin confirms: "I authorize metadata collection from employee Google Workspace accounts for time tracking purposes"
- Admin acknowledges employee notification requirement

### 4. Australian Hosting Option (If Required)

**Current**: US-based (Supabase Oregon, Render US-East, Claude US, Gemini US)

**Australian option** (if Thrive requires data sovereignty):
- Supabase: Sydney region (ap-southeast-2)
- Render: Sydney region
- Gemini: Australia endpoint (europe-west1 or us-central1 with data residency agreement)
- Claude: No AU endpoint (must disclose cross-border processing)

**Cost impact**: +$50-100/month for AU hosting (smaller free tiers in AU regions)

---

## TECHNICAL COMPLIANCE MEASURES

### 1. Metadata-Only Gmail Integration

**Current approach** (NEEDS UPDATING for compliance):
```python
# ❌ DON'T DO THIS (reads full email body)
message = gmail.users().messages().get(userId='me', id=msg_id, format='full').execute()
body = message['payload']['body']['data']  # COPYRIGHTED CONTENT
```

**Compliant approach** (metadata only):
```python
# ✅ DO THIS (metadata only)
message = gmail.users().messages().get(userId='me', id=msg_id, format='metadata').execute()
headers = {h['name']: h['value'] for h in message['payload']['headers']}
subject = headers.get('Subject', '')
from_email = headers.get('From', '')
to_email = headers.get('To', '')
date = headers.get('Date', '')

# Send to AI: only subject + participants
ai_context = f"Email: {subject}, From: {from_email}, To: {to_email}"
# ✅ No body content, no attachments
```

### 2. Minimal AI Prompt (No Copyright Violation)

**Current approach** (MAY violate copyright):
```python
# ❌ If we're sending full email content
prompt = f"Email content: {full_email_body}\n\nExtract time entry."
```

**Compliant approach**:
```python
# ✅ Metadata only
prompt = f"""
User had email activity:
- Subject: "Q2 Brand Strategy Discussion"
- Participants: user@thrive.com.au, client@afterpay.com.au
- Duration: 2 hours (calendar event linked)

Suggest a Harvest time entry with appropriate client and project.
"""
# ✅ No copyrighted email content reproduced
```

### 3. No Training on Client Data

**Compliance rule**: NEVER use client emails/docs to fine-tune or train AI models.

**Current approach**: ✅ Using API-only models (Claude, Gemini) — no training on user data
**Prohibited**: ❌ Fine-tuning, ❌ Model training, ❌ Data retention for model improvement

**API provider guarantees**:
- Anthropic: "We do not train on API data" (confirmed in ToS)
- Google Gemini: "API data not used for model training unless explicitly opted in"

---

## AUSTRALIAN-SPECIFIC RECOMMENDATIONS

### 1. Add "AU Mode" Toggle

**Feature**: Admin can enable "Australia Compliance Mode"

**Changes in AU mode**:
- ✅ All data stored in Australian region (Supabase Sydney, Render Sydney)
- ✅ Enhanced consent flow with Fair Work Act notice
- ✅ Stricter data retention (auto-delete metadata after 7 days)
- ✅ Audit log for admin (who accessed what, when)
- ✅ Annual privacy compliance report

**Cost**: +$50-100/month for AU hosting

### 2. Thrive-Specific Privacy Policy

**Customization**:
- Replace "Sitara Infotech" with "Thrive PR + Communications (data controller)" and "Sitara Infotech (data processor)"
- Add Thrive's privacy officer contact
- Reference Thrive's existing employee privacy policy
- Add clause: "This tool is authorized by Thrive management for business time tracking purposes"

### 3. Employee Notification (Thrive's Responsibility)

**Recommended notice from Thrive to employees**:
```
Subject: New Time Tracking Tool — Privacy Notice

Dear Team,

Thrive is introducing an AI-powered timesheet assistant to streamline time entry.

What it does:
- Reads your email subject lines, calendar events, and file activity (metadata only)
- Suggests time entries based on your work activity
- You review and approve before anything is logged to Harvest

What it doesn't do:
- Read full email content or attachments
- Monitor your performance or productivity
- Share your data with third parties

Your consent:
- Participation is voluntary
- You can opt out of automated scanning and use manual entry
- You can disable the tool at any time

Privacy:
- Data is processed securely and used only for time tracking
- AI processing occurs via US-based APIs (Anthropic, Google)
- See full privacy policy: [link]

Questions? Contact [Thrive Privacy Officer]

Thanks,
Thrive Management
```

---

## POC COMPLIANCE CHECKLIST

**Before launching 1-2 user POC**:

- [ ] **Update Gmail integration**: Switch to `format='metadata'` (no full email body)
- [ ] **Update Calendar integration**: Fetch summary/attendees only (no description content)
- [ ] **Update Drive integration**: Fetch file names/activity only (no file content)
- [ ] **Create Privacy Policy**: `PRIVACY-POLICY.md` + display on login page
- [ ] **Add consent flow**: User must explicitly opt-in to metadata collection
- [ ] **Add cross-border notice**: "AI processing occurs in the United States"
- [ ] **Get Thrive admin authorization**: Tariq confirms employer authorization
- [ ] **Provide employee notice template**: For Thrive to send to pilot users
- [ ] **Document data residency**: Confirm current US hosting, offer AU option
- [ ] **Add data deletion**: User can delete all their data via settings
- [ ] **Verify API providers**: Anthropic + Google don't train on API data
- [ ] **Test metadata-only approach**: Ensure time entry suggestions still work without full content

---

## RISK ASSESSMENT

| Risk | Likelihood | Impact | Mitigation | Status |
|------|------------|--------|------------|--------|
| Copyright violation (email content) | Medium | High | Metadata-only approach | ✅ Addressable |
| Privacy Act breach (insufficient consent) | Medium | High | Explicit consent flow + privacy policy | ✅ Addressable |
| Workplace surveillance concerns | Low | Medium | Employee notice + opt-in | ✅ Addressable |
| Cross-border data transfer issues | Low | Low | Disclose + offer AU hosting | ✅ Addressable |
| Data breach (unauthorized access) | Low | High | Encryption + access controls + audit logs | ✅ Current measures sufficient |
| Client confidential data exposure | Medium | High | No storage of source content, only entries | ✅ Addressable |

**Overall compliance risk**: LOW (after implementing checklist above)

---

## NEXT STEPS (Pre-POC)

1. **Immediate** (today):
   - Update code to metadata-only approach
   - Create basic privacy policy
   - Add consent checkbox to login

2. **Before POC** (this week):
   - Test metadata-only approach with dummy data
   - Get Thrive admin (Tariq) authorization in writing
   - Send employee notice to 1-2 pilot users

3. **During POC** (next week):
   - Monitor for any privacy/copyright issues
   - Gather user feedback on consent flow clarity
   - Document compliance approach for Phase 1 SoW

4. **Post-POC** (if proceeding):
   - Formal privacy impact assessment
   - Legal review by Australian lawyer (optional, recommended)
   - Offer Australian hosting option in Phase 1 pricing

---

## SUMMARY

**Tariq's concern**: "Nothing should be against Australian laws - copyright laws etc"

**Our response**:
✅ **Copyright compliance**: Metadata-only approach, no storage of email/document content
✅ **Privacy compliance**: Explicit consent, privacy policy, minimal collection, encryption
✅ **Workplace compliance**: Employer authorization, employee notice, opt-in, transparency
✅ **Data sovereignty**: Disclose US hosting, offer Australian region option if required

**Confidence level**: HIGH — we can launch POC in full compliance with Australian law.

**Recommendation**: Implement POC compliance checklist (4-6 hours work) before launch.
