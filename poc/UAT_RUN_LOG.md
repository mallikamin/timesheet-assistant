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
| 3.1 Future Annual Leave | _pending_ | — | — |

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

## Round-3 PR pending deploy (not yet live)

The leave-path P0 fix (`save_entry` Anthropic tool + picker server-side fallback) is **coded + 51/51 tests pass locally** but **not yet committed/pushed/deployed**. Any UAT test that drafts a LEAVE entry will reproduce 2.3's silent-draft-loss until Render redeploys. Specifically:
- **Test 3.1** (Future Annual Leave) — likely repeats 2.3 failure mode.
- **Test 6.5** (sick leave yesterday) — likely repeats.

Non-leave tests (2.4, 2.5, 3.2, 3.3, 4.x, 5.x, 6.1–6.4, 7.x, 8.x, 11) should behave the same as on the live build.
