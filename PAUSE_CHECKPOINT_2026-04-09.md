# Pause Checkpoint — 2026-04-09

## Status
- **Phase 1**: Approved ($5,850), NDA signed, CFO locked in
- **Current Blocker**: Waiting for Harvest API token from Thrive
- **Action**: Tariq request sent for token + pilot user details

---

## Harvest API Deep Dive — Key Learnings

### Email from Harvest Support (Apr 8, 2026)
**Summary**: All accounts include API access. Permissions mirror user roles.

**Key Points:**
- ✅ **API Access**: Included in all plans (no separate tier needed)
- ✅ **Python Code Samples**: Available in Harvest docs
- ✅ **Rate Limiting**: Documented (check before scaling)
- ✅ **Permissions Model**: Admin/Manager/Member hierarchy enforced per API call

**Links:**
- API v2 docs: https://help.getharvest.com/api-v2
- Code samples: https://help.getharvest.com/api-v2/introduction/overview/code-samples
- Rate limiting: https://help.getharvest.com/api-v2/introduction/overview/general/#rate-limiting
- Permissions article: https://support.getharvest.com/hc/en-us/articles/360048687451

---

## Token vs API — Clarification

| Concept | What It Is | For Thrive |
|---------|-----------|-----------|
| **API** | The service/endpoints (POST /time_entries, GET /projects, etc.) | ✅ Already have it |
| **Token** | The secret key to authenticate calls (Bearer credential) | ❌ WAITING FOR IT |

**How It Works:**
- 1 token authenticates the entire app
- Each user logs in via Google OAuth (separate from token)
- Token used for all API calls regardless of who's logged in
- Harvest checks user permissions automatically based on their role

---

## Token Generation Process — Simple Explanation

**For Thrive (Non-Technical PR Firm):**

1. Go to: https://id.getharvest.com/oauth2/access_tokens/new
2. Click "Create Token"
3. Name it: `Timesheet Assistant`
4. Check all permissions (Harvest + Forecast)
5. Click "Create"
6. Copy the long code (appears once only)
7. Send to Malik

**How Many Tokens?**
- ✅ Just 1 token needed
- ✅ Works for 5+ users simultaneously
- ❌ Not one token per user

---

## What Thrive Needs to Send

**Request sent to Tariq (2026-04-09):**

```
We need 3 things:

1. **Harvest API Token**
   - Generated from: https://id.getharvest.com/oauth2/access_tokens/new
   - Name it: "Timesheet Assistant"
   - Copy and send

2. **Pilot User Details (1-2 minimum, suggest 5)**
   - Example: Tariq Munir, tariq@thrive.com.au (Manager role)
   - Example: Jane Smith, jane@thrive.com.au (Member role)
   - Must be assigned to at least 1 project in Harvest

3. **Confirm Harvest Account Number**
   - We believe it's: 2175490
   - Need confirmation
```

---

## Current Implementation Status

**What We Have:**
- ✅ Dummy Harvest account (2175490) — working
- ✅ Agentic tool-use (scan emails/calendar/drive) — deployed
- ✅ Draft-approval workflow — implemented
- ✅ Australian legal compliance (metadata-only) — documented
- ✅ harvest_api.py with push_entry(), resolve_user_id(), reassign_time_entry() — tested

**What We're Waiting For:**
- ❌ Real Thrive Harvest API token
- ❌ Pilot user names/emails (5 users for initial test)
- ❌ Confirmation pilot users are assigned to projects
- ❌ Verification of permission levels (Admin/Manager/Member)

**What's Not Needed Yet:**
- Forecast API token (Phase 2, but check availability now)
- IP whitelist rules (unless Thrive has security requirements)
- Custom reporting endpoints (Phase 2)

---

## Next Steps (When Token Arrives)

1. **Add real token to .env**
   ```
   HARVEST_API_TOKEN=<thrive-token-here>
   HARVEST_ACCOUNT_ID=2175490
   ```

2. **Test with pilot users**
   - Create 5 accounts in Thrive's Harvest
   - Assign each to projects
   - Add Google OAuth emails to GCP
   - Test login flow

3. **Run smoke tests**
   - agentic tool-use (scan emails → create entries)
   - Draft-approval workflow (AI suggests → user approves → Harvest push)
   - Permission checks (Member sees only own entries)

4. **Verify Australian compliance**
   - Privacy policy deployed
   - Consent flow triggered
   - No full email/document content collected (metadata-only)

5. **Deploy to Render**
   - Real token live
   - Monitor rate limits
   - Keep-alive check running

---

## Files Modified (Latest Commit: fdd7fe6)

- `poc/app.py` — Agentic tool-use endpoints, draft-approval UI
- `poc/gmail_sync.py` — Advanced email filtering, metadata-only
- `poc/calendar_sync.py` — Calendar metadata scanning
- `poc/drive_sync.py` — Drive file metadata scanning
- `.claude/settings.local.json` — Local settings

**Untracked (documentation + deliverables):**
- AUSTRALIAN-LEGAL-COMPLIANCE.md
- CFO-Brief-1-Pager.pdf
- SOW-Thrive-v3.pdf
- PHASE1-ENHANCED-PLAN.md
- IMPLEMENTATION_LOG_2026-04-04.md

---

## Decision Log

**Harviest Token Strategy:**
- ❌ NOT one token per user (unnecessary)
- ✅ One token + 5 users in Google OAuth (simple, scalable)
- ✅ Harvest enforces permissions automatically (no manual role management)

**Pilot Size:**
- Suggest 5 users initially (enough to test roles + permissions)
- Fall back to 1-2 if Thrive prefers slower rollout

---

## Contact & Timeline

- **Tariq (Thrive)**: Sent token request 2026-04-09
- **Expected Response**: EOW 2026-04-11 (if expedited)
- **Testing Phase**: Following week (2026-04-14+)
- **Phase 1 Delivery**: TBD (depends on kickoff)

---

## Lessons from This Session

1. **Harvest Support is non-technical**: Email was bot-generated, directed us to docs, no deep API discussion
2. **Token = App Credential, not User Credential**: One key for the app, users stay separate (OAuth)
3. **Permissions are Automatic**: Harvest checks user role on each API call, we don't need to enforce it
4. **Rate Limiting is Real**: Need to test agentic tool-use under load (multiple scan calls)
5. **Simple Explanation Works**: "Token is a key, API is the house" resonates with non-technical teams

---

## Ready to Resume When

- ✅ Harvest API token received from Thrive
- ✅ Pilot user list (5 names + emails)
- ✅ Confirmation users are in Harvest + assigned to projects
