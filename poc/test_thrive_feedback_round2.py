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
    def test_no_connections_still_offers_save_entry(self):
        # save_entry is always-on so users can draft even without Google or
        # Harvest connected — drafts go to local DB + Sheet, push to Harvest
        # happens at Approve time.
        tools = app_mod._tools_for_user(False, False)
        self.assertIsNotNone(tools)
        self.assertEqual({t["name"] for t in tools}, {"save_entry"})

    def test_only_google_returns_scan_tools_plus_save(self):
        tools = app_mod._tools_for_user(True, False)
        names = {t["name"] for t in tools}
        self.assertEqual(
            names, {"scan_emails", "scan_calendar", "scan_drive", "save_entry"}
        )

    def test_only_harvest_returns_entry_tools_plus_save(self):
        tools = app_mod._tools_for_user(False, True)
        names = {t["name"] for t in tools}
        self.assertEqual(
            names, {"list_entries", "delete_entry", "edit_entry", "save_entry"}
        )

    def test_both_returns_all_seven(self):
        tools = app_mod._tools_for_user(True, True)
        names = {t["name"] for t in tools}
        self.assertEqual(
            names,
            {
                "scan_emails", "scan_calendar", "scan_drive",
                "list_entries", "delete_entry", "edit_entry",
                "save_entry",
            },
        )


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


class ExecuteToolSaveEntryTests(unittest.IsolatedAsyncioTestCase):
    """The save_entry tool is the round-3 fix for Michael's 'logged but not
    appearing as Draft' bug. The model previously had to remember to embed a
    text-only ```ENTRY block — fragile, especially on the leave path. Tool
    calls are structured + always reliable."""

    async def test_save_entry_appends_to_sink_and_persists(self):
        sink = []
        with patch("app.harvest_mock.create_draft_entry") as create, \
             patch("app.sheets_sync.sync_entry_to_sheet"):
            create.return_value = {
                "id": 7001,
                "client": "Thrive Leave",
                "project_name": "Annual Leave",
                "task": "Annual Leave",
                "hours": 7.5,
                "notes": "Funeral",
                "date": "2026-05-12",
                "status": "Draft",
            }
            out = await app_mod.execute_tool(
                "save_entry",
                {
                    "client": "Thrive Leave",
                    "project_code": "",
                    "project_name": "Annual Leave",
                    "task": "Annual Leave",
                    "hours": 7.5,
                    "notes": "Funeral",
                    "date": "2026-05-12",
                    "status": "Draft",
                },
                access_token="g",
                entries_sink=sink,
                user_name="Michael",
                user_email="michael@thrivepr.com.au",
                selected_date="2026-05-12",
            )
        create.assert_called_once()
        self.assertEqual(len(sink), 1)
        self.assertEqual(sink[0]["id"], 7001)
        self.assertIn("Drafted entry id=7001", out)
        self.assertIn("Annual Leave", out)
        # The result text instructs the model to use 'Drafted', not 'Logged'.
        self.assertIn("Drafted", out)
        self.assertIn("'Drafted', not 'Logged'", out)

    async def test_save_entry_without_sink_returns_error(self):
        # Defensive: a save_entry call outside a chat session has no sink and
        # must NOT silently swallow the entry. Old behaviour was the model
        # generating prose with no ENTRY block — that's exactly what we're
        # fixing. Make the failure mode loud.
        out = await app_mod.execute_tool(
            "save_entry",
            {
                "client": "Acuity",
                "project_name": "Existing Growth",
                "task": "Existing Growth",
                "hours": 1.0,
                "date": "2026-05-06",
            },
            access_token="g",
            entries_sink=None,
            user_name="Michael",
        )
        self.assertIn("ERROR", out)
        self.assertIn("entries_sink", out)

    async def test_save_entry_rejects_zero_hours(self):
        sink = []
        out = await app_mod.execute_tool(
            "save_entry",
            {
                "client": "Acuity",
                "project_name": "Existing Growth",
                "task": "Existing Growth",
                "hours": 0,
                "date": "2026-05-06",
            },
            access_token="g",
            entries_sink=sink,
        )
        self.assertIn("ERROR", out)
        self.assertEqual(sink, [])

    async def test_save_entry_rejects_missing_project_name(self):
        sink = []
        out = await app_mod.execute_tool(
            "save_entry",
            {
                "client": "Acuity",
                "project_name": "",
                "task": "Whatever",
                "hours": 1.0,
                "date": "2026-05-06",
            },
            access_token="g",
            entries_sink=sink,
        )
        self.assertIn("ERROR", out)
        self.assertEqual(sink, [])

    async def test_save_entry_passes_picker_as_fallback_date(self):
        # When the model emits date="" but the user picked a date, the picker
        # should land on the entry. This is the second half of the round-3 fix
        # (the first half being: tool always creates the draft).
        sink = []
        with patch("app.harvest_mock.create_draft_entry") as create, \
             patch("app.sheets_sync.sync_entry_to_sheet"):
            create.return_value = {
                "id": 8001, "client": "Thrive Leave", "project_name": "Annual Leave",
                "task": "Annual Leave", "hours": 7.5, "notes": "",
                "date": "2026-05-12", "status": "Draft",
            }
            await app_mod.execute_tool(
                "save_entry",
                {
                    "client": "Thrive Leave",
                    "project_name": "Annual Leave",
                    "task": "Annual Leave",
                    "hours": 7.5,
                    "date": "",  # model omitted; picker should win
                },
                access_token="g",
                entries_sink=sink,
                user_name="Michael",
                user_email="michael@thrivepr.com.au",
                selected_date="2026-05-12",
            )
        kwargs = create.call_args.kwargs
        self.assertEqual(kwargs["entry_date"], "2026-05-12")


class HistoryTrimAndCacheTests(unittest.TestCase):
    """Round-3 token-optimization helpers. Long conversations otherwise grow
    unbounded and pay the full input cost on every turn."""

    def test_trim_returns_unchanged_when_under_cap(self):
        h = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "ok"}]
        self.assertEqual(app_mod._trim_history(h), h)

    def test_trim_drops_oldest_when_over_cap(self):
        h = [{"role": "user", "content": str(i)} for i in range(50)]
        out = app_mod._trim_history(h)
        self.assertEqual(len(out), app_mod._MAX_HISTORY_MSGS)
        # Newest 30 retained, oldest dropped.
        self.assertEqual(out[0]["content"], "20")
        self.assertEqual(out[-1]["content"], "49")

    def test_trim_handles_empty_history(self):
        self.assertEqual(app_mod._trim_history([]), [])

    def test_cache_breakpoint_no_op_when_too_few_messages(self):
        msgs = [{"role": "user", "content": "first turn"}]
        app_mod._attach_messages_cache_breakpoint(msgs)
        # Single message — nothing to cache, untouched.
        self.assertEqual(msgs, [{"role": "user", "content": "first turn"}])

    def test_cache_breakpoint_marks_second_to_last_string_message(self):
        msgs = [
            {"role": "user", "content": "older"},
            {"role": "assistant", "content": "previous reply"},
            {"role": "user", "content": "new turn"},
        ]
        app_mod._attach_messages_cache_breakpoint(msgs)
        target = msgs[-2]
        self.assertIsInstance(target["content"], list)
        self.assertEqual(target["content"][0]["type"], "text")
        self.assertEqual(target["content"][0]["text"], "previous reply")
        self.assertEqual(target["content"][0]["cache_control"], {"type": "ephemeral"})
        # The new user message stays uncached.
        self.assertEqual(msgs[-1]["content"], "new turn")
        # The older message is also untouched.
        self.assertEqual(msgs[0]["content"], "older")

    def test_cache_breakpoint_skips_list_content(self):
        # Mid-tool-loop the assistant message is already a list of blocks
        # (tool_use). Caching that is wasted work — the loop changes it
        # between iterations.
        msgs = [
            {"role": "user", "content": "older"},
            {"role": "assistant", "content": [{"type": "text", "text": "x"}]},
            {"role": "user", "content": "new"},
        ]
        before = msgs[-2]["content"]
        app_mod._attach_messages_cache_breakpoint(msgs)
        # Untouched — no cache_control added because it was already a list.
        self.assertEqual(msgs[-2]["content"], before)


class _FakeRequest:
    """Minimal stand-in for a Starlette Request — chat() only touches .session."""
    def __init__(self, session):
        self.session = dict(session)


def _stop_block(text):
    """Build a minimal Anthropic content block for end_turn."""
    b = MagicMock()
    b.type = "text"
    b.text = text
    return b


def _tool_use_block(name, input_dict, block_id="toolu_test_1"):
    b = MagicMock()
    b.type = "tool_use"
    b.name = name
    b.input = input_dict
    b.id = block_id
    return b


def _fake_response(stop_reason, content_blocks):
    """Mimic the bits of an Anthropic Message that chat() reads."""
    r = MagicMock()
    r.stop_reason = stop_reason
    r.content = content_blocks
    r.usage = MagicMock(input_tokens=10, output_tokens=5,
                        cache_creation_input_tokens=0, cache_read_input_tokens=0)
    return r


class ChatEndpointSaveEntryE2ETests(unittest.IsolatedAsyncioTestCase):
    """End-to-end test that covers the round-trip: chat() invokes the agentic
    loop, the loop receives a save_entry tool_use from a (mocked) Claude, the
    server creates a draft via save_entry_everywhere, the response surfaces
    entries_created. The leave-path P0 bug from UAT 2.3 (silent draft loss)
    fails this test in the OLD code path because the prose-only response
    produced no draft."""

    async def test_save_entry_tool_use_returns_entry_in_response(self):
        # First Anthropic call → model emits a tool_use for save_entry.
        # Second call (after tool_result) → model wraps with end_turn text.
        first = _fake_response(
            "tool_use",
            [_tool_use_block(
                "save_entry",
                {
                    "client": "Thrive Leave",
                    "project_code": "",
                    "project_name": "Annual Leave",
                    "task": "Annual Leave",
                    "hours": 7.5,
                    "notes": "Funeral",
                    "date": "2026-05-12",
                    "status": "Draft",
                },
            )],
        )
        second = _fake_response(
            "end_turn",
            [_stop_block(
                "Drafted 7.5h on Thrive Leave / Annual Leave for 12 May "
                "— approve in the right panel to push to Harvest."
            )],
        )

        # AsyncMock-style sequenced responses
        async def _create(**_kwargs):
            return _create.responses.pop(0)
        _create.responses = [first, second]

        fake_req = _FakeRequest({
            "user": {"email": "michael@thrivepr.com.au", "name": "Michael"},
            "google_token": None,
            "harvest_token": None,
        })

        chat_req = app_mod.ChatRequest(
            user="Michael",
            message="7.5 hours Annual Leave for funeral",
            history=[],
            selected_date="2026-05-12",
        )

        with patch.object(app_mod.client.messages, "create", side_effect=_create), \
             patch("app.harvest_mock.create_draft_entry") as create, \
             patch("app.sheets_sync.sync_entry_to_sheet"), \
             patch("app.harvest_mock.save_chat_message"), \
             patch("app.training_log.log", return_value="iid-1"):
            create.return_value = {
                "id": 9001,
                "client": "Thrive Leave",
                "project_code": "",
                "project_name": "Annual Leave",
                "task": "Annual Leave",
                "hours": 7.5,
                "notes": "Funeral",
                "date": "2026-05-12",
                "status": "Draft",
            }
            resp = await app_mod.chat(chat_req, fake_req)

        # The headline assertion: an entry was created and surfaces back to
        # the frontend via entries_created. In the OLD code path (no tool,
        # prose-only model output), this list was empty — exactly the bug.
        self.assertEqual(len(resp.entries_created), 1)
        self.assertEqual(resp.entries_created[0]["id"], 9001)
        self.assertEqual(resp.entries_created[0]["project_name"], "Annual Leave")
        self.assertIn("Drafted", resp.response)


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
