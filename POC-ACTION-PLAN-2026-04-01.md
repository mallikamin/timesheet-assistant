# POC Action Plan — Compliance-First Approach
> **Target**: Launch 1-2 user POC by end of this week | **Next decision**: ~1 week after launch

**Date**: 2026-04-01
**Client**: Thrive PR + Communications
**Requirement**: Australian legal compliance (copyright, privacy, workplace laws)

---

## POC SCOPE

### What's Included
✅ 1-2 Thrive pilot users (Tariq to confirm)
✅ Real Harvest credentials (Thrive's account)
✅ Voice + text time logging (existing feature)
✅ Google Calendar integration (existing, compliance-ready)
✅ Gmail metadata scanning (NEEDS UPDATE: metadata-only)
✅ Google Drive activity (existing, compliance-ready)
✅ Draft approval workflow (existing feature)
✅ Google Sheets visibility (existing feature)
✅ Privacy policy + consent flow (NEW)
✅ Employee notification template (NEW)
✅ Australian legal compliance (NEW)

### What's Excluded
❌ Multi-user rollout (50-60 users) — Phase 1 only
❌ Gmail sidebar add-on — Phase 1 only
❌ Push reminders — Phase 1 only
❌ Weekly manager reports — Phase 1 only
❌ Australian hosting (US hosting for POC, AU optional for Phase 1)

---

## COMPLIANCE REQUIREMENTS (MUST COMPLETE BEFORE POC LAUNCH)

### Priority 1: Code Updates (4-6 hours)

#### 1.1 Gmail Integration — Metadata-Only
**File**: `gmail_integration.py` (or wherever Gmail code lives)

**Current approach** (if reading full email):
```python
# ❌ REMOVE THIS if present
message = gmail.users().messages().get(userId='me', id=msg_id, format='full').execute()
body = base64.urlsafe_b64decode(message['payload']['body']['data'])
```

**Required approach** (metadata only):
```python
# ✅ USE THIS
message = gmail.users().messages().get(userId='me', id=msg_id, format='metadata').execute()
headers = {h['name']: h['value'] for h in message['payload']['headers']}

# Extract metadata only
email_metadata = {
    'subject': headers.get('Subject', ''),
    'from': headers.get('From', ''),
    'to': headers.get('To', ''),
    'date': headers.get('Date', ''),
    'message_id': headers.get('Message-ID', '')
}
# ✅ NO body content, NO attachments
```

**AI prompt update**:
```python
# Only send metadata to Claude/Gemini
context = f"""
User email activity:
- Subject: {email_metadata['subject']}
- From: {email_metadata['from']}
- To: {email_metadata['to']}
- Date: {email_metadata['date']}

Suggest a Harvest time entry.
"""
# ✅ No copyrighted email content reproduced
```

#### 1.2 Calendar Integration — Title/Attendees Only
**File**: `calendar_sync.py`

**Check current implementation**:
```python
# ✅ KEEP THIS (already compliant if fetching summary/attendees)
events = calendar.events().list(
    calendarId='primary',
    timeMin=start_time,
    timeMax=end_time,
    fields='items(summary,start,end,attendees)'  # ✅ No description field
).execute()

# Extract metadata
for event in events.get('items', []):
    metadata = {
        'title': event.get('summary', ''),
        'start': event['start'].get('dateTime', ''),
        'end': event['end'].get('dateTime', ''),
        'attendees': [a['email'] for a in event.get('attendees', [])]
        # ✅ NO event description, NO notes, NO attachments
    }
```

#### 1.3 Drive Integration — File Names/Activity Only
**File**: `drive_integration.py` (if exists)

**Required approach**:
```python
# ✅ Fetch file metadata only
files = drive.files().list(
    pageSize=50,
    fields='files(id,name,modifiedTime,owners,mimeType)',
    orderBy='modifiedTime desc'
).execute()

# ✅ NO file content retrieval via files().get(fileId, alt='media')
```

---

### Priority 2: Privacy & Consent (2-3 hours)

#### 2.1 Create Privacy Policy
**File**: `PRIVACY-POLICY.md` (markdown) + `templates/privacy.html` (web page)

**Required sections**:
1. **What we collect**: Email subjects, calendar titles, Drive file names, time entry data
2. **What we DON'T collect**: Full email content, attachments, document contents
3. **Why we collect**: To suggest time entries and sync to Harvest
4. **How we use it**: Time logging only, never marketing or other purposes
5. **Where it's stored**: US-based cloud (Supabase Oregon, Render US, Claude/Gemini US APIs)
6. **Who has access**: User + Thrive administrators only
7. **How long we keep it**: Metadata processed in-memory (not stored), time entries indefinitely
8. **Your rights**: Access, correction, deletion (contact Thrive admin or Sitara support)
9. **Cross-border disclosure**: AI processing in US (Anthropic, Google)
10. **Employer authorization**: Thrive has authorized this tool for business time tracking
11. **Contact**: [Thrive privacy officer] and support@sitarainfotech.com

**Action**:
- [ ] Write `PRIVACY-POLICY.md` (1 hour)
- [ ] Create `/privacy` web page route (30 min)
- [ ] Link from login page footer (5 min)

#### 2.2 Add Consent Flow
**File**: `templates/login.html` or `/consent` route

**Required flow**:
1. After Google SSO login (first time only), show consent screen
2. User must check boxes:
   - [ ] I consent to metadata collection from my Google Workspace account
   - [ ] I acknowledge that AI processing occurs in the United States
   - [ ] I have read the Privacy Policy
3. Only after consent can user access the app
4. Store consent in database: `user_consents` table

**Database schema**:
```sql
CREATE TABLE user_consents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_email TEXT NOT NULL UNIQUE,
    metadata_collection BOOLEAN DEFAULT FALSE,
    cross_border_processing BOOLEAN DEFAULT FALSE,
    privacy_policy_read BOOLEAN DEFAULT FALSE,
    consent_date TIMESTAMP DEFAULT NOW(),
    ip_address TEXT,
    user_agent TEXT
);
```

**Action**:
- [ ] Create `user_consents` table in Supabase (5 min)
- [ ] Build consent screen UI (1 hour)
- [ ] Add consent check middleware (30 min)
- [ ] Allow user to revoke consent in settings (30 min)

#### 2.3 Employee Notification Template
**File**: `EMPLOYEE-NOTICE-TEMPLATE.md`

**For Thrive to send to pilot users BEFORE POC launch**:

```markdown
Subject: New Time Tracking Tool — Privacy Notice & Pilot Invitation

Dear [Pilot User Name],

Thrive is piloting an AI-powered timesheet assistant to streamline time entry for our team.

**What it does:**
- Reads your email subject lines, calendar events, and file activity (metadata only)
- Suggests time entries based on your work activity
- You review and approve before anything is logged to Harvest

**What it doesn't do:**
- Read full email content or attachments
- Access document contents or comments
- Monitor your performance or productivity beyond time tracking
- Share your data with third parties

**Your participation:**
- You've been selected for the 1-2 user pilot (this week)
- Participation is voluntary
- You can opt out at any time and use manual time entry instead

**Privacy:**
- Data is processed securely via US-based AI providers (Anthropic, Google)
- See full privacy policy: [link to be provided]
- You'll be asked to consent on first login

**Questions?**
Contact: [Tariq Munir / Thrive Admin Email]

Thanks for helping us test this new tool!

Thrive Management
```

**Action**:
- [ ] Create `EMPLOYEE-NOTICE-TEMPLATE.md` (done above, copy to file)
- [ ] Send to Tariq to customize and send to pilot users

---

### Priority 3: Thrive Authorization (10 minutes)

#### 3.1 Get Written Authorization from Thrive
**Required before POC launch**:

Email from Tariq (or Thrive admin):
```
Subject: Authorization for Timesheet Assistant Pilot

Sitara Infotech,

Thrive PR + Communications authorizes the deployment of the AI-powered
timesheet assistant pilot for 1-2 employees.

I confirm:
- Thrive has a legitimate business purpose for this tool (accurate time tracking)
- Employees will be notified before the pilot begins
- The tool will collect only metadata (email subjects, calendar titles, file names)
- Employees will provide explicit consent before their data is accessed
- Data will be used only for time logging purposes

Authorized by: [Tariq Munir / Title]
Date: [Date]
```

**Action**:
- [ ] Request authorization email from Tariq (send template above)

---

## TECHNICAL CHECKLIST

### Code Changes
- [ ] **Gmail**: Update to `format='metadata'` (no full email body)
- [ ] **Calendar**: Verify no `description` field fetched
- [ ] **Drive**: Verify no file content retrieval
- [ ] **AI prompts**: Update to use metadata only (no copyrighted content)
- [ ] **Test**: Verify time entry suggestions still work with metadata-only approach

### Database
- [ ] Create `user_consents` table in Supabase
- [ ] Test consent storage and retrieval
- [ ] Add user data deletion endpoint (GDPR compliance)

### UI/UX
- [ ] Create `/privacy` page with privacy policy
- [ ] Create `/consent` page with consent checkboxes
- [ ] Add consent check on login (redirect if not consented)
- [ ] Add "Revoke Consent" button in user settings
- [ ] Add "Delete My Data" button in user settings
- [ ] Link privacy policy in footer of all pages

### Documentation
- [ ] Write `PRIVACY-POLICY.md`
- [ ] Write `EMPLOYEE-NOTICE-TEMPLATE.md`
- [ ] Update `README.md` with compliance notes

### Testing
- [ ] Test metadata-only Gmail fetching with dummy account
- [ ] Test consent flow (first login → consent → app access)
- [ ] Test consent revocation (user opts out → app access blocked)
- [ ] Test data deletion (user deletes → all data purged)
- [ ] Test AI suggestions with metadata-only input (still accurate?)

---

## POC TIMELINE

### This Week (2026-04-01 to 2026-04-04)

| Day | Task | Owner | Hours |
|-----|------|-------|-------|
| **Mon** (today) | Update Gmail to metadata-only | Malik | 2h |
| **Mon** | Verify Calendar/Drive compliance | Malik | 1h |
| **Mon** | Create `user_consents` table | Malik | 0.5h |
| **Mon** | Write Privacy Policy | Malik | 1h |
| **Mon** | Request Thrive authorization email | Malik | 0.5h |
| **Tue** | Build consent screen UI | Malik | 1.5h |
| **Tue** | Add consent middleware | Malik | 1h |
| **Tue** | Create `/privacy` page | Malik | 0.5h |
| **Tue** | Test metadata-only approach | Malik | 1h |
| **Wed** | Request Harvest token from Tariq | Malik | 0.5h |
| **Wed** | Swap dummy Harvest creds on Render | Malik | 0.5h |
| **Wed** | Get pilot user emails from Tariq | Malik | 0.5h |
| **Wed** | Add pilot users to GCP OAuth | Malik | 0.5h |
| **Wed** | Send employee notice template to Tariq | Malik | 0.5h |
| **Thu** | Tariq sends employee notice to pilots | Tariq | 0.5h |
| **Thu** | Test end-to-end POC flow | Malik | 2h |
| **Thu** | Deploy to Render with compliance updates | Malik | 1h |
| **Fri** | POC launch with 1-2 pilot users | Tariq + pilots | - |
| **Fri** | Monitor for issues, provide support | Malik | 2h |

**Total effort**: ~16 hours (2 days of focused work)

---

### Next Week (2026-04-07 to 2026-04-11)

| Day | Task | Owner |
|-----|------|-------|
| **Mon** | Gather pilot user feedback | Tariq |
| **Mon-Wed** | Fix any POC issues | Malik |
| **Thu** | Review POC results with Tariq | Tariq + Malik |
| **Fri** | Decision: Proceed to Phase 1 or iterate? | Tariq |

---

## SUCCESS CRITERIA (POC)

### Functional Success
✅ Pilot users can log time via voice/text
✅ Gmail metadata scanning suggests relevant entries
✅ Calendar events auto-suggest time entries
✅ Draft approval workflow works (review → edit → approve → Harvest)
✅ Harvest sync works with real Thrive credentials
✅ Google Sheets visibility works

### Compliance Success
✅ No full email/document content accessed or stored
✅ Users complete consent flow on first login
✅ Privacy policy displayed and acknowledged
✅ Employee notification sent before pilot launch
✅ Thrive admin authorization received
✅ Metadata-only approach still produces accurate suggestions

### User Success
✅ Pilot users find the tool helpful (saves time)
✅ Suggestions are accurate (80%+ correct client/project mapping)
✅ No privacy concerns raised by pilot users
✅ Tariq approves to proceed with Phase 1

---

## RISKS & MITIGATION

| Risk | Mitigation |
|------|------------|
| Metadata-only approach less accurate | Test with dummy data first; can add optional "paste email snippet" feature with explicit consent |
| Pilot users concerned about privacy | Clear consent flow, privacy policy, employee notice addresses this upfront |
| Harvest API token delayed | Use dummy creds for initial testing, swap when real token available |
| Thrive admin authorization delayed | Follow up with Tariq daily, provide simple email template |
| POC reveals compliance gaps | 1-week pilot gives time to iterate before Phase 1 commitment |
| Australian law changes during pilot | Low likelihood; monitor for any updates |

---

## REQUIRED FROM TARIQ (THIS WEEK)

1. ✅ **Thrive authorization email** (use template in Priority 3.1 above)
2. ✅ **Harvest API token + Account ID** (Thrive's real account)
3. ✅ **1-2 pilot user emails** (who will test the POC?)
4. ✅ **Send employee notice** (use template in Priority 2.3 above)
5. ✅ **Confirm Google Workspace admin** (to mark app as Internal, if needed)

---

## DELIVERABLES (END OF POC)

1. **Working POC**: 1-2 Thrive users actively using the tool
2. **Compliance report**: Document confirming all legal requirements met
3. **User feedback**: Summary of pilot user experience and suggestions
4. **Recommendation**: Proceed to Phase 1 / Iterate POC / Pause project
5. **Updated SoW** (if needed): Adjust Phase 1 scope based on POC learnings

---

## NEXT DECISION POINT

**When**: ~1 week after POC launch (approx. 2026-04-08 to 2026-04-11)

**Questions to answer**:
1. Does the metadata-only approach produce accurate suggestions?
2. Are pilot users satisfied with the tool?
3. Did we encounter any compliance issues?
4. Is Thrive ready to proceed with Phase 1 ($5,850 or $6,850)?
5. Does Thrive require Australian hosting for Phase 1?

**Outcome**:
- ✅ **Proceed to Phase 1**: Sign SoW, collect 50% deposit, start 4-week implementation
- 🔄 **Iterate POC**: Address feedback, extend pilot to 5-10 users
- ⏸️ **Pause**: Thrive needs more time or budget approval

---

## SUMMARY

**What's happening**: 1-2 user POC with Australian legal compliance as priority #1
**When**: Launch by end of this week (Fri 2026-04-04)
**What's needed from Tariq**: Authorization email, Harvest token, pilot user emails, send employee notice
**What we're delivering**: Compliance-first POC with privacy policy, consent flow, metadata-only approach
**Next step**: Review POC results in ~1 week, decide on Phase 1 implementation

**Confidence level**: HIGH — POC scope is achievable in 1 week with compliance measures in place.
