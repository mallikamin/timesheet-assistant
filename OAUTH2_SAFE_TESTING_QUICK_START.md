# OAuth2 Safe Testing — Quick Start Guide

**When Tariq sends OAuth2 credentials, follow this checklist.**

---

## ✅ STEP 1: Receive Credentials (5 minutes)

Tariq emails you:
```
HARVEST_CLIENT_ID=...
HARVEST_CLIENT_SECRET=...
```

✅ **Ask Tariq**: Which testing environment path?
- [ ] Path A: Separate test Harvest account (BEST)
- [ ] Path B: Test projects in production account (OK)

---

## ✅ STEP 2: Choose Testing Path

### Path A: Separate Test Account (Recommended)
**Setup**: Thrive admin provides test account credentials
```
You will have:
- Test HARVEST_ACCOUNT_ID
- Test HARVEST_CLIENT_ID
- Test HARVEST_CLIENT_SECRET
- Zero risk to production
```

### Path B: Test Projects in Production
**Setup**: Create these projects in Harvest directly
```
You will create:
- ZZ_TEST_TIMESHEET_A
- ZZ_TEST_TIMESHEET_B
- Must follow cleanup discipline
```

---

## ✅ STEP 3: Configure Environment (5 minutes)

```bash
cd C:\Users\Malik\desktop\timelogging\poc

# Edit .env file
# Add from Tariq:
HARVEST_CLIENT_ID=<from_tariq>
HARVEST_CLIENT_SECRET=<from_tariq>

# If Path A (test account), use test account ID instead
HARVEST_ACCOUNT_ID=<test_account_id>  # Only if Path A
```

---

## ✅ STEP 4: Take Baseline Snapshot (5 minutes)

**Path A (Test Account)**:
```bash
cd C:\Users\Malik\desktop\timelogging

# No snapshot needed - test account is isolated
# Skip to Step 5
```

**Path B (Production Account)**:
```bash
cd C:\Users\Malik\desktop\timelogging

python harvest_snapshot.py --before --token <HARVEST_TOKEN>
# Creates: harvest_snapshot_before_YYYYMMDD_HHMMSS.json
```

---

## ✅ STEP 5: Start App and Test (30 minutes)

```bash
cd C:\Users\Malik\desktop\timelogging\poc

# Start app
python app.py

# Open browser
# http://localhost:8080
```

**Follow**: `HARVEST_OAUTH2_TEST_PLAN.md`

Run tests 1-10 in order:
- [ ] Test 1: OAuth Flow
- [ ] Test 2: Create Entry
- [ ] Test 3: Approve (Single)
- [ ] Test 4: Approve (Bulk)
- [ ] Test 5: Delete Entry
- [ ] Test 6: Disconnect/Reconnect
- [ ] Test 7: Token Refresh
- [ ] Test 8: Multi-User
- [ ] Test 9: Error Handling
- [ ] Test 10: PAT Fallback

---

## ✅ STEP 6: Verify & Cleanup (20 minutes)

**Path A (Test Account)**:
```bash
# No cleanup needed
# Just verify all tests passed
# You can keep test account for regression testing
```

**Path B (Production Account)**:
```bash
# Take post-test snapshot
python harvest_snapshot.py --after --token <HARVEST_TOKEN>

# Compare results
python harvest_snapshot.py --compare \
  harvest_snapshot_before_*.json \
  harvest_snapshot_after_*.json

# Expected output: Only test entries in "created" section
# Delete test entries from Harvest UI
# Delete test projects: ZZ_TEST_TIMESHEET_A, ZZ_TEST_TIMESHEET_B

# Verify cleanup
python harvest_snapshot.py --after --token <HARVEST_TOKEN>
python harvest_snapshot.py --compare \
  harvest_snapshot_before_*.json \
  harvest_snapshot_after_*.json

# Expected: 0 changes detected
```

---

## ✅ STEP 7: Go/No-Go Decision (5 minutes)

### ✅ GO FOR PILOT if:
- All 10 tests passed
- Snapshot clean (Path B only)
- No confusing error messages
- Everything felt smooth

### ❌ PAUSE if:
- Any test failed
- Snapshot has unexpected changes (Path B)
- Error messages were confusing
- Feel uncertain about anything

---

## ✅ STEP 8: Deploy to Render (5 minutes)

```bash
cd C:\Users\Malik\desktop\timelogging

# Make sure .env is NOT committed (should be in .gitignore)
git status  # Verify no .env in staged changes

# Commit test notes (optional)
git add HARVEST_OAUTH2_TEST_RESULTS.md
git commit -m "OAuth2 testing complete - ready for pilot"

# Push to Render
git push origin main

# In Render Dashboard:
# 1. Navigate to timesheet-assistant service
# 2. Environment tab
# 3. Add:
#    HARVEST_CLIENT_ID=<from_tariq>
#    HARVEST_CLIENT_SECRET=<from_tariq>
# 4. Save (auto-deploys)
```

---

## ✅ STEP 9: Notify Pilot Users (5 minutes)

Email to Tariq, pilot users:

```
Subject: Harvest Connection Now Available

Hi team,

OAuth2 authentication is now live. When you next log in, you'll see:

1. Orange banner: "Connect your Harvest account"
2. Click "Connect Harvest"
3. Login with your Thrive Google account
4. Approve access
5. Done! Banner disappears, you can start logging time

This takes 30 seconds and only happens once per user.

Let me know if you have any questions!

Cheers,
Malik
```

---

## Troubleshooting Quick Links

| Issue | Solution |
|-------|----------|
| 401 Unauthorized | Click "Connect Harvest" again to re-authenticate |
| Token Expired | System auto-refreshes (no action needed) |
| Banner keeps showing | Clear browser cookies, log back in |
| Can't find test project | Go to Harvest UI to verify project exists |
| Test entries in Harvest | They should be there - see Step 6 for cleanup |

---

## File Reference

| File | Purpose | When to Use |
|------|---------|-----------|
| `PAUSE_CHECKPOINT_2026-04-10.md` | Full context & architecture | Before starting |
| `HARVEST_OAUTH2_TEST_PLAN.md` | Detailed test scenarios | During testing |
| `harvest_snapshot.py` | Before/after comparison | Path B only |
| `OAUTH2_SAFE_TESTING_QUICK_START.md` | This guide | Right now! |

---

## Total Time Estimate

- Step 1 (Credentials): 5 min
- Step 2 (Choose Path): 2 min
- Step 3 (Configure): 5 min
- Step 4 (Snapshot): 5 min
- Step 5 (Testing): 30 min
- Step 6 (Verify): 20 min
- Step 7 (Decision): 5 min
- Step 8 (Deploy): 5 min
- Step 9 (Notify): 5 min

**Total: ~82 minutes (~1.5 hours)**

---

## Success Criteria

✅ You can confidently say to Tariq:
- "OAuth2 is working perfectly"
- "I tested it thoroughly with 10 different scenarios"
- "No production data was touched"
- "Ready to launch pilot Monday"

---

**Keep this file handy when Tariq sends credentials!** 🚀

When you're done, update `PAUSE_CHECKPOINT_2026-04-10.md` with test results.
