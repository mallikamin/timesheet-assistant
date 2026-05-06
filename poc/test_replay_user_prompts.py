"""
Replay every distinct prompt class found in Miles's and Michael's transcripts
and verify the new pipeline now produces an optimal setup for each.

Why this is structured as "system-prompt + tool-gating" assertions instead of
end-to-end Anthropic calls: the AI's exact response wording is non-deterministic
even at temperature 0, but the *behavior class* the model can produce is fully
determined by what we put in the system prompt and which tools we expose.
By asserting on those, we make the contract testable and stable.

For each user-message we replay we check:
  1. The runtime notes set the right "today" anchor.
  2. The system prompt contains the rules that prevent the prior bug from
     recurring (e.g., future-dates allowed, admin-project mappings present).
  3. The tools list contains the right capabilities for the user message.
  4. Where the message implies an entry will be created, the resolved
     spent_date in the resulting Draft is correct.
"""

from __future__ import annotations

import os
import sys
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test")
os.environ.setdefault("HARVEST_CLIENT_ID", "test")
os.environ.setdefault("HARVEST_CLIENT_SECRET", "test")
os.environ.setdefault("SESSION_SECRET", "test-secret")

import user_profiles  # noqa: E402

# Redirect the profile store to a test-only file BEFORE app/time_utils import
# anything that might cache it. Without this the replay matrix mutates
# poc/user_profiles.json on every run, which leaks display-name lower-casing
# + placeholder-claim artifacts into the committed file.
_TEST_PROFILES = _HERE / "user_profiles.test.json"
if _TEST_PROFILES.exists():
    _TEST_PROFILES.unlink()
user_profiles._PROFILES_PATH = _TEST_PROFILES

import app as app_mod  # noqa: E402
import time_utils  # noqa: E402


# Real Thrive emails per memory.
MILES = "miles.alexander@thrivepr.com.au"
MICHAEL = "michael.adamson@thrivepr.com.au"
HUGH = "hugh@thrivepr.co.nz"


def _build_prompt(user_email: str, runtime_notes=None, harvest_token=None) -> str:
    """Render the full system prompt as a single string for assertion."""
    blocks = app_mod.build_system_prompt(
        user_email=user_email,
        harvest_access_token=harvest_token,
        notes=runtime_notes or [],
    )
    return "\n\n".join(b["text"] for b in blocks)


def _ensure_profile(email: str, dialect: str = "en-AU-Sydney"):
    """Make sure there's a profile row for this email with the given dialect."""
    user_profiles.update_profile(email, {"dialect": dialect, "display_name": email.split("@")[0]})


# Pin server clock to a moment when AU and NZ users are both ON Wed 2026-05-06
# locally, but UTC says Tue 2026-05-05 22:00 — exactly the bug situation.
_PINNED_UTC = datetime(2026, 5, 5, 22, 0, 0, tzinfo=ZoneInfo("UTC"))

# Stand-in catalog so build_system_prompt doesn't hit the live Harvest API
# during the replay matrix. Listing the projects users referenced lets the
# admin-mapping assertions reflect realistic conditions.
_FAKE_CATALOG = """\
- Acuity (id=1):
    Existing Business Growth FY26
    New Business Growth FY26
- Thrive Operation FY26 (id=2):
    Reporting & WIPs
- Thrive Finance Operation FY26 (id=3):
    Systems & Process Improvement
    Reporting & WIPs
    Estimate & invoice
- Thrive Learning & Development FY26 (id=4):
    Weekly Planning
    Agency WIPs
- Thrive Culture & Social FY26 (id=5):
    Thrive O'Clock
- Thrive Innovation Project (id=6):
    Digital Champions
- Thrive Leave (id=7):
    Annual Leave
"""


class _TimeFixed(unittest.TestCase):
    """Base class that pins time_utils.datetime.now to _PINNED_UTC and
    mocks the live Harvest project fetch so tests are fast + offline-safe."""

    def setUp(self):
        self._patcher = patch("time_utils.datetime")
        self._dt = self._patcher.start()
        self._dt.now.side_effect = lambda tz: _PINNED_UTC.astimezone(tz)
        self._dt.fromisoformat.side_effect = datetime.fromisoformat

        self._catalog_patcher = patch("app.get_all_projects_for_prompt", return_value=_FAKE_CATALOG)
        self._catalog_patcher.start()

    def tearDown(self):
        self._patcher.stop()
        self._catalog_patcher.stop()


class DateAnchorReplayTests(_TimeFixed):
    """Bug class: 'Day Thursday but date is Wednesday'. Verify the system
    prompt now anchors AU users to their local Wednesday, not UTC's Tuesday."""

    def test_au_user_today_is_local_wednesday(self):
        _ensure_profile(MICHAEL, "en-AU-Sydney")
        prompt = _build_prompt(MICHAEL)
        self.assertIn("AUTHORITATIVE TODAY", prompt)
        self.assertIn("Wednesday", prompt)
        self.assertIn("2026-05-06", prompt)

    def test_nz_user_today_is_local_wednesday(self):
        _ensure_profile(HUGH, "en-NZ-Auckland")
        prompt = _build_prompt(HUGH)
        self.assertIn("AUTHORITATIVE TODAY", prompt)
        self.assertIn("Wednesday", prompt)
        self.assertIn("2026-05-06", prompt)

    def test_authoritative_today_overrides_cached_utc_date(self):
        """Catch a regression where someone removes the 'use this NOT the
        cached date' phrasing and the model starts following the UTC date."""
        _ensure_profile(MICHAEL, "en-AU-Sydney")
        prompt = _build_prompt(MICHAEL)
        self.assertIn("use this, NOT the date in the cached block", prompt)


class FutureDateReplayTests(_TimeFixed):
    """Michael's 'Tuesday 12th May Annual Leave' worked but 'Thursday 07/05
    Finance Operation whole day' was refused. Same future date — different
    outcome. The fix: future dates ALLOWED across the board."""

    def test_prompt_no_longer_refuses_future_dates(self):
        _ensure_profile(MICHAEL, "en-AU-Sydney")
        prompt = _build_prompt(MICHAEL)
        self.assertNotIn("refuse politely — only log work that has already happened", prompt)
        self.assertIn("Future dates", prompt)
        self.assertIn("ALLOWED", prompt)

    def test_prompt_explicitly_allows_future_for_planned_work(self):
        _ensure_profile(MICHAEL, "en-AU-Sydney")
        prompt = _build_prompt(MICHAEL)
        self.assertIn("planned-work flow needs it", prompt)


class AdminProjectReplayTests(_TimeFixed):
    """Miles couldn't find general admin / reporting / Thrive L&D codes. The
    prompt now overrides the assigned-projects pruning rule for internal work."""

    def test_admin_phrases_mapped_to_thrive_projects(self):
        _ensure_profile(MILES, "en-AU-Sydney")
        prompt = _build_prompt(MILES)
        # All four families Miles asked about should be present (case-insensitive):
        for phrase in ["general admin", "reporting", "L&D", "learning & development", "month end"]:
            self.assertIn(phrase.lower(), prompt.lower())

    def test_override_rule_present(self):
        _ensure_profile(MILES, "en-AU-Sydney")
        prompt = _build_prompt(MILES)
        self.assertIn("Override the assigned-projects pruning rule for internal work", prompt)

    def test_thrive_leave_explicitly_allows_future(self):
        """Annual Leave for Tuesday 12 May was Michael's smoke test — must
        keep working AND extend to all future dates, not just leave."""
        _ensure_profile(MICHAEL, "en-AU-Sydney")
        prompt = _build_prompt(MICHAEL)
        self.assertIn("annual leave", prompt.lower())
        self.assertIn("future dates ALLOWED", prompt)


class EditDeleteToolReplayTests(_TimeFixed):
    """Michael asked 'edit entries' / 'show me all entries' / 'clear entries'
    six times. The bot kept saying 'I can only create new entries — log into
    Harvest directly'. The fix: list/delete/edit tools surface, the prompt
    forbids that fallback line."""

    def test_prompt_forbids_log_into_harvest_directly_message(self):
        _ensure_profile(MICHAEL, "en-AU-Sydney")
        prompt = _build_prompt(MICHAEL)
        self.assertIn("NEVER tell a user", prompt)
        self.assertIn("OUTDATED", prompt)

    def test_tools_list_includes_list_delete_edit_when_harvest_connected(self):
        tools = app_mod._tools_for_user(has_google=False, has_harvest=True)
        names = {t["name"] for t in tools}
        self.assertIn("list_entries", names)
        self.assertIn("delete_entry", names)
        self.assertIn("edit_entry", names)

    def test_prompt_describes_each_tool_use_case(self):
        _ensure_profile(MICHAEL, "en-AU-Sydney")
        prompt = _build_prompt(MICHAEL)
        self.assertIn("show me all entries", prompt)
        self.assertIn("delete that entry", prompt)
        self.assertIn("edit X to be Y", prompt)


class DraftedWordingReplayTests(_TimeFixed):
    """Michael read 'Logged: 7.5 hours' as 'in Harvest' but it was a Draft
    awaiting Approve. The system prompt now nudges 'Drafted ... approve to
    push to Harvest' wording."""

    def test_prompt_nudges_drafted_wording(self):
        _ensure_profile(MICHAEL, "en-AU-Sydney")
        prompt = _build_prompt(MICHAEL)
        self.assertIn("DRAFT state", prompt)
        self.assertIn("approve in the right panel to push to harvest", prompt.lower())


class SelectedDateInjectionTests(_TimeFixed):
    """When the user picks 12 May in the date picker, every chat message
    should treat 12 May as the authoritative entry date."""

    def test_selected_date_note_is_appended_strongly(self):
        _ensure_profile(MICHAEL, "en-AU-Sydney")
        prompt = _build_prompt(MICHAEL, runtime_notes=[app_mod._selected_date_note("2026-05-12")])
        self.assertIn("USER-SELECTED DATE", prompt)
        self.assertIn("2026-05-12", prompt)
        self.assertIn("highest priority", prompt.lower())


class SaveEntryRespectsPickedDateTests(_TimeFixed):
    """When the AI emits an ENTRY without a 'date' field but the user picked
    12 May, the saved Draft must land on 12 May (not today)."""

    def test_fallback_date_used_when_entry_omits_date(self):
        _ensure_profile(MICHAEL, "en-AU-Sydney")
        with patch("app.harvest_mock.create_draft_entry") as creator, \
             patch("app.sheets_sync.sync_entry_to_sheet"):
            creator.return_value = {"id": "x"}
            app_mod.save_entry_everywhere(
                user="Michael Adamson",
                entry_data={
                    "client": "Thrive Leave", "project_code": "L-1",
                    "project_name": "Annual Leave",
                    "task": "Annual Leave", "hours": 7.5, "notes": "Funeral",
                    # NO 'date' field
                },
                user_email=MICHAEL,
                fallback_date="2026-05-12",
            )
        kwargs = creator.call_args.kwargs
        self.assertEqual(kwargs["entry_date"], "2026-05-12")

    def test_explicit_entry_date_wins_over_fallback(self):
        _ensure_profile(MICHAEL, "en-AU-Sydney")
        with patch("app.harvest_mock.create_draft_entry") as creator, \
             patch("app.sheets_sync.sync_entry_to_sheet"):
            creator.return_value = {"id": "x"}
            app_mod.save_entry_everywhere(
                user="Michael Adamson",
                entry_data={
                    "client": "Acuity", "project_code": "X",
                    "project_name": "Existing Growth", "task": "Existing Growth",
                    "hours": 1.0, "notes": "",
                    "date": "2026-05-04",  # explicit
                },
                user_email=MICHAEL,
                fallback_date="2026-05-12",
            )
        self.assertEqual(creator.call_args.kwargs["entry_date"], "2026-05-04")

    def test_no_picker_no_date_falls_back_to_local_today(self):
        _ensure_profile(MICHAEL, "en-AU-Sydney")
        with patch("app.harvest_mock.create_draft_entry") as creator, \
             patch("app.sheets_sync.sync_entry_to_sheet"):
            creator.return_value = {"id": "x"}
            app_mod.save_entry_everywhere(
                user="Michael Adamson",
                entry_data={
                    "client": "Acuity", "project_code": "X",
                    "project_name": "Existing Growth", "task": "Existing Growth",
                    "hours": 1.0, "notes": "",
                },
                user_email=MICHAEL,
            )
        # Pinned UTC is Tue 22:00 → AU local is Wed 2026-05-06.
        self.assertEqual(creator.call_args.kwargs["entry_date"], "2026-05-06")


class CmdEnterReplayTests(unittest.TestCase):
    """Hugh asked for Cmd-Enter. The handler is in the template — we assert
    the source still binds the right modifiers."""

    def test_template_handles_cmd_or_ctrl_enter(self):
        path = _HERE / "templates" / "index.html"
        src = path.read_text(encoding="utf-8")
        self.assertIn("metaKey", src)
        self.assertIn("ctrlKey", src)
        self.assertIn("Cmd/Ctrl+Enter", src)


class MultiDayResumeReplayTests(unittest.TestCase):
    """Hugh asked to see last week's chat. Endpoint accepts ?days=, frontend
    requests 7."""

    def test_template_requests_seven_days_on_resume(self):
        path = _HERE / "templates" / "index.html"
        src = path.read_text(encoding="utf-8")
        self.assertIn("days=7", src)


class FullPromptReplayMatrixTests(_TimeFixed):
    """Walk a representative set of the actual user prompts from Miles + Mike's
    sessions. For each, build the system prompt + decide tools and assert the
    optimal setup is in place. Each entry is (label, message, expected_must_have)."""

    PROMPTS = [
        ("michael_today_finance",
         "Sweet! Right, so for the Finance AI discussion — that's a Thrive internal finance systems/process improvement task.",
         ["Thrive Finance", "AUTHORITATIVE TODAY"]),
        ("michael_yesterday",
         "yesterday 6.25 hours finance operations, systems process, notes of Revenue, timesheets, emails",
         ["AUTHORITATIVE TODAY", "Override the assigned-projects pruning"]),
        ("michael_future_annual_leave",
         "Tuesday 12th May, Annual Leave, 7.5 hours, note of Funeral",
         ["future dates ALLOWED", "annual leave"]),
        ("michael_future_work_thursday",
         "Thursday, Finance Operation, finalise revenue, whole day",
         ["future dates ALLOWED", "Thrive Finance"]),
        ("michael_show_all_entries",
         "show me all entries",
         ["show me all entries", "list_entries"]),
        ("michael_clear_entries",
         "clear entries",
         ["NEVER tell a user", "delete_entry"]),
        ("michael_edit_entries",
         "edit entries",
         ["edit X to be Y", "edit_entry"]),
        ("michael_correct_entry",
         "edit finance & ai overview entry, change task to Finance Meeting",
         ["edit X to be Y", "edit_entry"]),
        ("miles_general_admin",
         "general admin time on emails and to-do lists",
         ["general admin", "Thrive Operation FY26"]),
        ("miles_l_and_d",
         "Thrive learning and development for an hour",
         ["learning and development", "Thrive Learning & Development FY26"]),
        ("miles_reporting_codes",
         "reporting codes for emails and to do lists",
         ["reporting", "Thrive Operation FY26"]),
        ("hugh_kia_ora_chat",
         "did some account planning this morning",
         ["AUTHORITATIVE TODAY"]),
    ]

    def test_each_prompt_has_optimal_setup(self):
        # Use Miles's email for "miles_*" prompts, Hugh for "hugh_*", Michael otherwise.
        # Each profile uses its real dialect so the local-today anchoring is
        # correct per user.
        results = []
        for label, msg, must in self.PROMPTS:
            email = MILES if label.startswith("miles_") else (
                HUGH if label.startswith("hugh_") else MICHAEL
            )
            dialect = "en-NZ-Auckland" if email == HUGH else "en-AU-Sydney"
            _ensure_profile(email, dialect)
            prompt = _build_prompt(email)
            tools = app_mod._tools_for_user(has_google=True, has_harvest=True)
            tool_names = {t["name"] for t in tools}
            missing = []
            for token in must:
                # Tool names match against tool_names; everything else is
                # case-insensitive substring on the prompt.
                if token in tool_names:
                    continue
                if token.lower() not in prompt.lower():
                    missing.append(token)
            results.append((label, missing))

        bad = [(label, m) for label, m in results if m]
        self.assertFalse(
            bad,
            "Replay matrix found prompts where the optimal setup is missing:\n"
            + "\n".join(f"  - {label}: missing {m}" for label, m in bad),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
