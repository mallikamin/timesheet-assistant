"""
Tests for the Thrive feedback round 2 fixes.

Covers:
  - timezone helper (today_local picks up dialect, not UTC)
  - selected-date system note formatting + injection
  - chat tools list/delete/edit gating + execution
  - multi-day chat resume endpoint
  - push-error surfacing on /approve and /approve-all

These tests run with no external network — Anthropic + Harvest + Supabase
are all stubbed so the suite is hermetic and CI-safe.
"""

from __future__ import annotations

import importlib
import os
import sys
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

# Ensure poc/ is importable when this test runs from the repo root.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

# Pre-set env vars so module imports don't try to hit external services.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test")
os.environ.setdefault("HARVEST_CLIENT_ID", "test")
os.environ.setdefault("HARVEST_CLIENT_SECRET", "test")
os.environ.setdefault("SESSION_SECRET", "test-secret")

import time_utils  # noqa: E402
import app as app_mod  # noqa: E402


class TimeUtilsTests(unittest.TestCase):
    def test_au_dialect_resolves_to_sydney(self):
        tz = time_utils.dialect_to_tz("en-AU-Sydney")
        self.assertEqual(str(tz), "Australia/Sydney")

    def test_nz_dialect_resolves_to_auckland(self):
        tz = time_utils.dialect_to_tz("en-NZ-Auckland")
        self.assertEqual(str(tz), "Pacific/Auckland")

    def test_unknown_dialect_falls_back_to_au(self):
        tz = time_utils.dialect_to_tz("en-US-Boston")
        self.assertEqual(str(tz), "Australia/Sydney")

    def test_none_dialect_does_not_crash(self):
        tz = time_utils.dialect_to_tz(None)
        self.assertEqual(str(tz), "Australia/Sydney")

    def test_today_local_is_ahead_of_utc_in_au_evening(self):
        """The bug at the heart of Miles + Michael's feedback: when UTC is
        still on Tuesday 22:00, AU local is already Wednesday 09:00 — so
        today_local should return Wednesday."""
        # Pin server clock to a moment when AU is +1 day from UTC.
        utc_moment = datetime(2026, 5, 5, 22, 0, 0, tzinfo=ZoneInfo("UTC"))
        with patch("time_utils.datetime") as dt_mock:
            dt_mock.now.side_effect = lambda tz: utc_moment.astimezone(tz)
            self.assertEqual(time_utils.today_local("en-AU-Sydney"), date(2026, 5, 6))
            self.assertEqual(time_utils.today_local("en-NZ-Auckland"), date(2026, 5, 6))
            # NZ at this moment is even further ahead — Wed 10:00.

    def test_today_iso_local_format(self):
        out = time_utils.today_iso_local("en-AU-Sydney")
        self.assertRegex(out, r"^\d{4}-\d{2}-\d{2}$")


class SelectedDateNoteTests(unittest.TestCase):
    def test_well_formed_date_produces_strong_anchor(self):
        note = app_mod._selected_date_note("2026-05-12")
        self.assertIn("USER-SELECTED DATE", note)
        self.assertIn("2026-05-12", note)
        self.assertIn("Tuesday", note)

    def test_malformed_date_returns_empty(self):
        self.assertEqual(app_mod._selected_date_note("not-a-date"), "")
        self.assertEqual(app_mod._selected_date_note("2026/05/12"), "")
        self.assertEqual(app_mod._selected_date_note(""), "")

    def test_invalid_calendar_date_returns_empty(self):
        # 2026-02-30 matches the regex but is not a real date.
        self.assertEqual(app_mod._selected_date_note("2026-02-30"), "")


class ToolGatingTests(unittest.TestCase):
    def test_no_connections_returns_none(self):
        self.assertIsNone(app_mod._tools_for_user(False, False))

    def test_only_google_returns_scan_tools(self):
        tools = app_mod._tools_for_user(True, False)
        names = {t["name"] for t in tools}
        self.assertEqual(names, {"scan_emails", "scan_calendar", "scan_drive"})

    def test_only_harvest_returns_entry_tools(self):
        tools = app_mod._tools_for_user(False, True)
        names = {t["name"] for t in tools}
        self.assertEqual(names, {"list_entries", "delete_entry", "edit_entry"})

    def test_both_returns_all_six(self):
        tools = app_mod._tools_for_user(True, True)
        self.assertEqual(len(tools), 6)


class ExecuteToolHarvestTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_entries_no_harvest_returns_error(self):
        out = await app_mod.execute_tool(
            "list_entries", {}, access_token="g",
            harvest_access_token=None, harvest_user_id=None,
        )
        self.assertIn("ERROR", out)
        self.assertIn("Connect Harvest", out)

    async def test_list_entries_calls_harvest_with_user_filter(self):
        with patch("harvest_api.get_time_entries_range") as fetch:
            fetch.return_value = [
                {
                    "id": 12345,
                    "spent_date": "2026-05-06",
                    "client": {"name": "Acuity"},
                    "project": {"name": "Acuity Retainer"},
                    "task": {"name": "Existing Growth"},
                    "hours": 1.5,
                    "notes": "deck review",
                },
            ]
            out = await app_mod.execute_tool(
                "list_entries", {"date_from": "2026-05-06"},
                access_token="g",
                harvest_access_token="hv",
                harvest_user_id=42,
                user_dialect="en-AU-Sydney",
            )
        fetch.assert_called_once()
        kwargs = fetch.call_args.kwargs
        self.assertEqual(kwargs["user_id"], 42)
        self.assertEqual(kwargs["from_date"], "2026-05-06")
        self.assertIn("harvest_id=12345", out)
        self.assertIn("Acuity Retainer", out)

    async def test_delete_entry_invokes_harvest_and_invalidates_cache(self):
        with patch("harvest_api.delete_time_entry", return_value=True) as deleter, \
             patch("harvest_api.invalidate_today_cache") as inv:
            out = await app_mod.execute_tool(
                "delete_entry", {"harvest_id": 999},
                access_token="g",
                harvest_access_token="hv",
                harvest_user_id=42,
            )
        deleter.assert_called_once_with(999, access_token="hv")
        inv.assert_called_once_with(42)
        self.assertIn("success=True", out)

    async def test_edit_entry_passes_through_fields(self):
        with patch("harvest_api.patch_time_entry") as patcher, \
             patch("harvest_api.invalidate_today_cache"):
            patcher.return_value = {
                "id": 999, "spent_date": "2026-05-06", "hours": 6.0, "notes": "fixed"
            }
            out = await app_mod.execute_tool(
                "edit_entry",
                {"harvest_id": 999, "hours": 6.0, "notes": "fixed"},
                access_token="g",
                harvest_access_token="hv",
                harvest_user_id=42,
            )
        patcher.assert_called_once()
        kwargs = patcher.call_args.kwargs
        self.assertEqual(kwargs["harvest_id"], 999)
        self.assertEqual(kwargs["hours"], 6.0)
        self.assertEqual(kwargs["notes"], "fixed")
        self.assertIn("Edited entry harvest_id=999", out)

    async def test_edit_entry_with_no_fields_returns_error(self):
        with patch("harvest_api.patch_time_entry", return_value=None):
            out = await app_mod.execute_tool(
                "edit_entry", {"harvest_id": 999},
                access_token="g",
                harvest_access_token="hv",
                harvest_user_id=42,
            )
        self.assertIn("ERROR", out)


class HarvestPatchTests(unittest.TestCase):
    """Direct unit tests for harvest_api.patch_time_entry. We mock httpx so
    no network call escapes."""

    def setUp(self):
        os.environ["HARVEST_ACCESS_TOKEN"] = "pat"
        os.environ["HARVEST_ACCOUNT_ID"] = "1"

    def test_patch_returns_none_when_no_fields(self):
        import harvest_api
        out = harvest_api.patch_time_entry(harvest_id=1, access_token="t")
        self.assertIsNone(out)

    def test_patch_sends_only_provided_fields(self):
        import harvest_api
        with patch("harvest_api.httpx.patch") as p:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"id": 5}
            p.return_value = mock_resp
            out = harvest_api.patch_time_entry(
                harvest_id=5, hours=2.5, access_token="t"
            )
        self.assertEqual(out["id"], 5)
        kwargs = p.call_args.kwargs
        self.assertEqual(kwargs["json"], {"hours": 2.5})


class ChatRecentEndpointTests(unittest.TestCase):
    """The /api/chat/recent endpoint signature now accepts ?days=N."""

    def test_signature_accepts_days_param(self):
        import inspect
        sig = inspect.signature(app_mod.chat_recent)
        self.assertIn("days", sig.parameters)
        self.assertEqual(sig.parameters["days"].default, 1)


class PushErrorSurfacingTests(unittest.IsolatedAsyncioTestCase):
    """Verify approve/approve_all return the underlying Harvest error string,
    not just success: false."""

    async def test_approve_returns_resolution_error_on_push_failure(self):
        # Simulate the failure path: push_entry returns None.
        request = MagicMock()
        request.session = {
            "user": {"email": "u@example.com", "name": "U"},
            "harvest_token": {
                "access_token": "hv",
                "expires_at": (datetime.utcnow() + timedelta(days=1)).timestamp(),
            },
        }
        with patch("app.get_current_user", return_value=request.session["user"]), \
             patch("app.harvest_oauth.ensure_valid_token", return_value=request.session["harvest_token"]), \
             patch("app.harvest_mock.get_entries", return_value=[
                 {
                     "id": "e1",
                     "client": "Acuity",
                     "project_code": "ACU",  # no hyphen -> skip ID branch, go straight to name resolution
                     "project_name": "Existing Growth FY26",
                     "task": "Existing Growth FY26",
                     "hours": 2.0,
                     "notes": "",
                     "date": "2026-05-06",
                     "status": "Draft",
                 }
             ]), \
             patch("app.harvest_api.resolve_user_id", return_value=42), \
             patch("app.harvest_api.create_time_entry", return_value=None), \
             patch("app.harvest_api.push_entry", return_value=None):
            out = await app_mod.approve_entry("e1", request)
        self.assertFalse(out["success"])
        self.assertIn("could not resolve", out["error"].lower())
        self.assertEqual(out["client"], "Acuity")


if __name__ == "__main__":
    unittest.main(verbosity=2)
