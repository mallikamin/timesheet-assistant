# Harvest OAuth2 Testing Plan

**Purpose**: Verify Harvest OAuth2 implementation works correctly before pilot launch

**Scope**: Single user, multi-user, error handling, token lifecycle

**Risk Level**: LOW (snapshot + rollback strategy)

**Timeline**: 2-3 hours total (includes setup, testing, cleanup)

---

## Pre-Testing Checklist

- [ ] OAuth2 credentials received from Tariq
- [ ] Added to `poc/.env`:
  ```
  HARVEST_CLIENT_ID=<value>
  HARVEST_CLIENT_SECRET=<value>
  ```
- [ ] Decided on test environment (Path A or B below)
- [ ] Path A: Test Harvest account created and credentials obtained
- [ ] Path B: Test projects created in same account (e.g., ZZ_TEST_1, ZZ_TEST_2)

---

## Path A: Separate Test Harvest Account (RECOMMENDED)

**Safety Level**: ⭐⭐⭐ (Maximum - completely isolated)

### Setup
1. Thrive admin creates: `Timesheet Assistant - Test` account
2. Thrive provides: Account ID + OAuth app credentials
3. Setup OAuth app in test account with redirect URIs

### Benefits
- Zero risk to production data
- Can test destructively (create/delete aggressively)
- Mirrors real-world scenario
- No cleanup needed (can delete test account)

### Testing Workflow
```bash
# Use test account OAuth credentials for all tests
# All data goes to test account only
# No production data is touched
```

---

## Path B: Test Projects in Production Account

**Safety Level**: ⭐⭐ (Acceptable - but with precautions)

### Setup
1. Create test projects in production Harvest:
   - `ZZ_TEST_TIMESHEET_A` (for single-user tests)
   - `ZZ_TEST_TIMESHEET_B` (for multi-user tests)
   - With tasks: `Test Task 1`, `Test Task 2`, `Test Task 3`

2. Take baseline snapshot BEFORE testing:
   ```bash
   python harvest_snapshot.py --before --token <HARVEST_TOKEN>
   ```

### Benefits
- No extra setup needed
- Tests real production account scenario
- Faster to start

### Risks
- Test data in production account (mitigated by distinct naming)
- Cleanup required after testing
- Must follow strict discipline

### Testing Workflow
```bash
# 1. Baseline snapshot
python harvest_snapshot.py --before --token <HARVEST_TOKEN>

# 2. Run all test scenarios (below)

# 3. After snapshot
python harvest_snapshot.py --after --token <HARVEST_TOKEN>

# 4. Compare and verify
python harvest_snapshot.py --compare harvest_snapshot_before_*.json harvest_snapshot_after_*.json

# 5. Cleanup: Delete test entries and projects
```

---

## Test Scenarios

### Test 1: Single User OAuth Flow
**Goal**: Verify user can authenticate with Harvest via OAuth

```
Steps:
1. Visit http://localhost:8080/login
2. Login with Google (should use same account)
3. See banner: "Connect your Harvest account"
4. Click "Connect Harvest"
5. Redirected to Harvest login
6. See: "Timesheet Assistant wants to access your Harvest account"
7. Click "Allow"
8. Redirected back to app
9. Banner disappears
10. Status in top-right shows "Harvest Connected"

Expected Result: ✅ OAuth flow completes, user connected
```

### Test 2: Create Time Entry with OAuth Token
**Goal**: Verify time entry creation uses OAuth token

```
Steps:
1. (After Test 1 - user is connected)
2. Say: "2 hours on ZZ_TEST_TIMESHEET_A - Test Task 1"
3. Claude creates draft entry
4. Verify entry appears in UI with status "Draft"

Expected Result: ✅ Draft entry created
```

### Test 3: Approve Entry (Single) with OAuth Token
**Goal**: Verify single entry approval uses OAuth token to push to Harvest

```
Steps:
1. (Continue from Test 2 - draft entry exists)
2. Click approve button on draft entry
3. Watch for "Approved" status change
4. Check Harvest UI: https://timesheet-assistant-jclk.onrender.com (or test account)
5. Verify entry appears in Harvest with 2 hours

Expected Result: ✅ Entry pushed to Harvest, status is "Approved"
```

### Test 4: Approve Multiple Entries
**Goal**: Verify bulk approval works with OAuth token

```
Steps:
1. Create 3 more draft entries:
   - "1 hour on ZZ_TEST - Task 1"
   - "1.5 hours on ZZ_TEST - Task 2"
   - "0.5 hours on ZZ_TEST - Task 3"
2. Click "Approve All Drafts"
3. Watch all 3 turn to "Approved"
4. Check Harvest: verify all 3 entries exist with correct hours

Expected Result: ✅ All 3 entries pushed to Harvest
```

### Test 5: Delete Entry (with Harvest ID)
**Goal**: Verify deletion removes entry from both app and Harvest

```
Steps:
1. (Continue from Test 4 - 3 approved entries in Harvest)
2. Click delete (×) on one of the approved entries
3. Confirm it's removed from UI
4. Check Harvest: verify entry no longer exists there

Expected Result: ✅ Entry deleted from both app and Harvest
```

### Test 6: Disconnect and Reconnect
**Goal**: Verify disconnect/reconnect cycle works

```
Steps:
1. Click "Disconnect Harvest" (if visible) OR manually clear session
2. Refresh page (or navigate away and back)
3. Banner reappears: "Connect Harvest"
4. Click "Connect Harvest" again
5. Complete OAuth flow
6. Banner disappears again

Expected Result: ✅ Disconnect and reconnect work smoothly
```

### Test 7: Token Expiry (Simulated)
**Goal**: Verify token refresh when expired

```
Steps:
1. (User is connected with valid token)
2. Open browser DevTools → Application → Cookies
3. Find `session` cookie
4. In browser console, manually expire the Harvest token:
   ```javascript
   // This simulates token expiry (60+ seconds old)
   // In production, this happens automatically every 14 days
   ```
5. Try to approve an entry
6. Should see token refresh happen silently
7. Approval succeeds

Expected Result: ✅ Token refresh handles expiry transparently
```

### Test 8: Multi-User Isolation (if 2 accounts available)
**Goal**: Verify two users' tokens don't contaminate each other

```
Prerequisites: Two browser windows or incognito windows

Steps:
1. Window A: User 1 logs in, connects Harvest (gets User 1 token)
2. Window B: User 2 logs in, connects Harvest (gets User 2 token)
3. Window A: Create entry for User 1
4. Window A: Approve entry
5. Window B: Create entry for User 2
6. Window B: Approve entry
7. Check Harvest: User 1's entry shows user_id=User1, User 2's shows user_id=User2

Expected Result: ✅ Each user's token is isolated, entries attributed correctly
```

### Test 9: Error Handling - 401 Unauthorized
**Goal**: Verify handling of invalid/expired tokens

```
Steps:
1. (User is connected)
2. In browser console:
   ```javascript
   // Manually invalidate the token
   let cookie = document.cookie;
   document.cookie = "session=corrupted; path=/";
   ```
3. Try to approve an entry
4. Should see error: "Harvest token expired" or similar
5. Banner reappears
6. User must reconnect

Expected Result: ✅ Graceful error handling, user prompted to reconnect
```

### Test 10: Fallback to PAT (if OAuth not configured)
**Goal**: Verify system still works without OAuth credentials

```
Prerequisites: Remove OAuth env vars from .env temporarily

Steps:
1. Restart app (no HARVEST_CLIENT_ID/SECRET)
2. Login and try to approve entry
3. Should use fallback PAT
4. Entry created successfully
5. No error messages

Expected Result: ✅ Fallback works, system is backward compatible
```

---

## Verification Checklist

After all tests complete:

- [ ] All 10 test scenarios passed
- [ ] No 401 errors in logs
- [ ] No "Harvest connection lost" messages
- [ ] Banner displays correctly (hidden when connected)
- [ ] Token refresh happened silently (no user intervention)
- [ ] Multi-user tokens were isolated
- [ ] All test entries visible in Harvest
- [ ] Snapshot comparison shows only test entries created
- [ ] No production data was modified

---

## Post-Testing Cleanup

### Path A (Test Account)
```bash
# Nothing to clean - test account can be deleted
# Or left for future regression testing
```

### Path B (Test Projects in Production)
```bash
# 1. Delete test time entries (manual via Harvest UI or API)
# 2. Delete test projects: ZZ_TEST_TIMESHEET_A, ZZ_TEST_TIMESHEET_B
# 3. Run final snapshot comparison to confirm clean

python harvest_snapshot.py --after --token <HARVEST_TOKEN>
python harvest_snapshot.py --compare harvest_snapshot_before_*.json harvest_snapshot_after_*.json
```

**Expected**: Comparison shows 0 changes after cleanup

---

## Troubleshooting

### Scenario: 401 Unauthorized Error
**Cause**: Token invalid or expired
**Solution**:
- Click "Connect Harvest" again
- Re-authenticate with Harvest
- Token refreshes

### Scenario: "Harvest not configured" Error
**Cause**: Missing HARVEST_ACCOUNT_ID in .env
**Solution**:
- Check `poc/.env` has `HARVEST_ACCOUNT_ID=<value>`
- Restart app
- Try again

### Scenario: OAuth Redirect Loop
**Cause**: Redirect URI mismatch or OAuth app misconfigured
**Solution**:
- Verify OAuth app has correct redirect URIs:
  - http://localhost:8080/auth/harvest/callback (local)
  - https://timesheet-assistant-jclk.onrender.com/auth/harvest/callback (prod)
- Check HARVEST_CLIENT_ID and CLIENT_SECRET are correct
- Restart app
- Try again

### Scenario: Cannot Delete Entry from Harvest
**Cause**: User doesn't have permission, or entry is protected
**Solution**:
- Check Harvest user role (Member/Manager/Admin)
- Try deleting via Harvest UI directly to confirm permission
- If Harvest UI delete fails, that's not our code issue

---

## Test Results Documentation

After testing, create `HARVEST_OAUTH2_TEST_RESULTS.md`:

```markdown
# OAuth2 Testing Results — [DATE]

## Environment
- Account: [Test/Production]
- OAuth Credentials: Obtained from [Date]
- Branch: main
- Commit: [hash]

## Test Scenarios
- [x] Test 1: OAuth Flow — PASSED
- [x] Test 2: Create Entry — PASSED
- [x] Test 3: Approve (Single) — PASSED
- [x] Test 4: Approve (Bulk) — PASSED
- [x] Test 5: Delete Entry — PASSED
- [x] Test 6: Disconnect/Reconnect — PASSED
- [x] Test 7: Token Refresh — PASSED
- [x] Test 8: Multi-User — PASSED
- [x] Test 9: Error Handling — PASSED
- [x] Test 10: PAT Fallback — PASSED

## Issues Found
(None if all pass)

## Sign-Off
✅ Ready for pilot launch: YES
✅ Snapshot clean (no unwanted changes): YES
✅ All team notified: YES
```

---

## Go/No-Go Decision Criteria

### ✅ GO FOR PILOT if:
- All 10 test scenarios passed
- Snapshot clean (only test entries created)
- No 401 errors in logs
- Error messages clear and actionable
- Token refresh worked transparently
- Multi-user isolation verified

### ❌ NO-GO (pause for fixes) if:
- Any test scenario failed
- Snapshot has unexpected changes
- 401 errors not handled gracefully
- Token refresh required user intervention
- Multi-user tokens contaminated each other
- Error messages are unclear

---

## Success!

Once all tests pass and cleanup is complete:

```bash
# Commit your findings
git add HARVEST_OAUTH2_TEST_RESULTS.md
git commit -m "OAuth2 testing complete - ready for pilot"

# Deploy to Render
git push origin main

# Notify pilot users
Email: "OAuth2 is live. When you next login, you'll see a Connect Harvest banner."
```

---

**Estimated Time**: 2-3 hours total
**Expected Success Rate**: 95%+ (architecture is solid)
**Go-Live Target**: Pilot week starts Monday

Good luck! 🚀
