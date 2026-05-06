# UAT Run Log — Thrive Feedback Round 2

- **Date started**: 2026-05-06
- **Build commit**: `1a480a0` (PR #21) + `e4d7615` (PR #23 — real thrive-logo.png)
- **Live URL**: https://timesheet-assistant-jclk.onrender.com
- **Tester**: Malik Amin
- **Facilitator**: Claude (one-test-at-a-time mode)
- **Source script**: `poc/UAT_THRIVE_FEEDBACK_ROUND2.md`

---

## Results

| Test | Status | Severity (if fail) | Notes |
| --- | --- | --- | --- |
| 0. Pre-flight | ✅ pass | — | Signed in, Harvest connected, DevTools open |
| 1.1 Today resolves to local date | ✅ pass | — | — |
| 1.2 Yesterday anchors to local yesterday | ⏭️ skip | — | Skipped by tester |
| 1.3 No double-day drift over evening | ✅ pass | — | Drafted: 1h on Reporting & WIPs (2026-05-06), draft card shows Wed 6 May. Side-signal: Drafted wording (9.1) + AI didn't say "Logged" (9.2). Disambiguation surfaced 3 internal Thrive admin projects → admin override (Section 6) firing |
| 2.1 Date picker default state | ✅ pass | — | Entry date / today / Reset all visible |
| 2.2 Picking a date changes hint colour + label | ✅ pass | — | — |
| 2.3 Picked date drives entries | ❌ FAIL | **P0** | **Silent draft loss on leave path.** Bot text said "Drafted 7.5h on Thrive Leave / Compassionate Leave (paid) for today" but NO green system bubble fired and NO draft card appeared in the right panel. Pre-existing cards untouched. This is exactly Michael's original "logged but not appearing as Draft" bug — round 2 fix didn't cover the leave path. Adjacent: **P1** picker override ignored — picker showed 01/05/2026, bot booked for today (06/05/2026); `selected_date` runtime note not honoured. **P2** leave subtype mismatch — "Annual Leave for funeral" booked as "Compassionate Leave (paid)". Fix coded locally (round-3 PR pending deploy). |
| 2.4 Explicit date in message overrides picker | ✅ pass | — | Picker = 01/05, message = "Friday 9 May" → entry booked on 2026-05-09 (Sat, 9 May). Green bubble + draft card both fired. Side-observations: (a) **P3** bot called "9 May" Friday in its chat text but the date itself is Sat — user typo passed through. (b) frontend showed `Scanning your list_entries...` (legacy copy; round-3 fix replaces with `Looking up your entries...`). |
| 2.5 Reset returns to today | ✅ pass | — | — |
| 3.1 Future Annual Leave | ❓ INCONCLUSIVE — split out | — | Leave-path draft creation **works** (two Mon 18 May Annual Leave cards in right panel; entries 17→19, +15h — save_entry tool is firing). BUT Malik's broader acceptance criterion includes the new chat-history restore feature working post-refresh, which it did not. Splitting the chat-history-restore investigation into a parallel Claude Code session (continuation prompt below). UAT continues from 3.2 in this session. **Side note (P2)**: recursion-bug retries during the broken-build window double-drafted Mon 18 May — Malik to delete one card before Approve. |
| 3.2 Future regular work | _pending_ | — | — |

---

## Section tallies

| Section | Pass | Fail | Skip | Blocked |
| --- | --- | --- | --- | --- |
| 0. Pre-flight | 1 | 0 | 0 | 0 |
| 1. Date handling | 2 | 0 | 1 | 0 |
| 2. Date picker | 4 | 1 | 0 | 0 |
| 3. Future-date entries | 0 | 0 | 0 | 0 |
| 4. List/Edit/Delete | 0 | 0 | 0 | 0 |
| 5. Push-error surfacing | 0 | 0 | 0 | 0 |
| 6. Internal Thrive projects | 0 | 0 | 0 | 0 |
| 7. Multi-day chat resume | 0 | 0 | 0 | 0 |
| 8. Cmd/Ctrl-Enter | 0 | 0 | 0 | 0 |
| 9. Drafted wording | 0 | 0 | 0 | 0 |
| 10. Welcome dialect | 0 | 0 | 0 | 0 |
| 11. Today-so-far | 0 | 0 | 0 | 0 |
| 12. Calendar weekly review | 0 | 0 | 0 | 0 |
| 13. Regression matrix | 0 | 0 | 0 | 0 |
| **TOTAL** | **0** | **0** | **0** | **0** |

---

## Failures (to triage at end)

### P0

- **Test 2.3 — Silent draft loss on leave path.** Bot reports "Drafted 7.5h on Thrive Leave / Compassionate Leave (paid) for today" but no green Drafted bubble fires and no draft card appears in the right panel. Pre-existing entries untouched. This is Michael's original "Entries say logged but not appearing in Timesheet or as a Draft Entry" complaint — leave path was not actually fixed in round 2. Reproducer: with date picker set to any value, type `7.5 hours Annual Leave for funeral`. Compare to a regular-work prompt (e.g. `1h on internal admin today`) which does create a draft + bubble.

### P1

- **Test 2.3 — `selected_date` runtime note not honoured.** Picker showed `01/05/2026 (Fri 1 May)`, bot booked entry for today `(06/05/2026)`. The "USER-SELECTED DATE (highest priority)" rule isn't winning over the model's default-to-today behaviour. Possibly leave-path-specific (untested for non-leave prompts in this run).

### P2

- **Test 2.3 — Leave subtype mismatch.** Prompt said "Annual Leave for funeral", AI booked "Compassionate Leave (paid)". The AI inferred from "funeral" — defensible interpretation, but ignored the explicit "Annual Leave" wording. Edge case, not blocking.
  - **Catalog audit done**: Compassionate Leave (paid) is a real task under Thrive Leave in Thrive's Harvest account (catalog comes live from Harvest API; no hardcoded leave list in our code). Nothing missing.
  - **Post-UAT email to Thrive (TODO)**: ask Tariq's ops team to confirm the Thrive Leave task list is complete (Annual / Sick / Carer / Compassionate / Bereavement / Unpaid / TIL — any others?). If a user types a leave type that isn't a task in Harvest, the bot will hallucinate or pick the nearest match. Knowing the canonical list lets us harden the prompt's leave-phrase mapping.

## Round-3 deploy live (commit 7a1a04a)

Deployed mid-UAT after 2.3 caught the P0 leave-path silent-draft-loss bug.
- `save_entry` Anthropic tool replaces the fragile text-block ENTRY parser. Tool calls are structured, never silently miss.
- Picker note rewritten with explicit precedence (message date > picker > AUTHORITATIVE TODAY) and server-side fallback.
- localStorage chat persistence — survives Render redeploy / Supabase pause / cold start; renders restored bubbles visibly.
- Anthropic prompt-cache breakpoint on messages prefix — ~80-95% input token reduction on multi-turn conversations.
- History capped at 30 messages (drop-oldest).
- 41 → 57 tests; new `ChatEndpointSaveEntryE2ETests` does the full round-trip mock that would have caught 2.3.

Tests 3.1, 6.5 (leave paths that previously silent-failed) should now pass.

## Round-4 followups (not blocking UAT)

- **Privacy: localStorage cleanup on sign-out.** `chat_history_v1_<name>` is not wiped when a user signs out — next user on a shared browser could read it via DevTools. Acceptable for Thrive's single-user-laptop pilot, but should be closed under the AU privacy compliance memo before broader rollout.
- **Console error hygiene.** Browser console currently shows stack traces with internal function names (`pushHistory`, `resumeConversation`, etc.). Not a security exploit — DevTools is each user's own browser — but it's free reconnaissance for an attacker. Round-4 fix: route `console.warn`/`console.error` to Sentry only when `SENTRY_DSN` is set (env slot already wired); strip user-facing console output to clean messages. Verify no API responses include Render service IDs / Supabase URLs / tokens.
- **Server-side `/api/chat/recent` not restoring on first new-build refresh.** Malik hard-refreshed after the round-3 deploy, localStorage was empty (first run with the new code path), and server fallback fired but visibly restored nothing. Either Supabase chat_logs is empty for this user (write-side may have been failing silently) or the day-cutoff filter is excluding messages. Needs a quick `/api/chat/recent` payload inspection in DevTools next time. localStorage-backed resume now primes itself from any new message Malik sends, so the user-visible problem self-heals from the next send onward — but the server path should still work as a backstop for new devices.
  - **FIXED 2026-05-06.** Root cause: `harvest_mock.get_chat_history` ordered `created_at` ASC + LIMIT N, so it returned the N OLDEST chat_logs rows ever recorded for the user — never the recent ones. The `/api/chat/recent` cutoff filter then dropped them all. Fix: order DESC, slice N, reverse in Python so callers still get ascending replay order. Added `ChatHistoryOrderingTests` round-trip regression coverage (now 59 tests pass). Single-line behaviour change in `harvest_mock.py:204`; no other callsites affected.
