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


class HarvestCatalogTests(unittest.TestCase):
    """The harvest_catalog module loads from the master CSV snapshot and
    exposes the leave + internal-project ground truth."""

    def test_leave_constants_match_harvest(self):
        import harvest_catalog as hc
        self.assertEqual(hc.LEAVE_PROJECT_NAME, "Thrive Leave FY26")
        self.assertEqual(hc.LEAVE_PROJECT_CODE, "3-0006")
        self.assertEqual(hc.LEAVE_PROJECT_CLIENT, "Thrive PR")
        # Annual Leave is the canonical task name from the FY26 time report
        self.assertIn("Leave - Annual Leave", hc.LEAVE_TASKS)
        self.assertIn("Leave - Sick / Carer Leave", hc.LEAVE_TASKS)
        # Phrase mapping resolves common AU vocab
        self.assertEqual(hc.leave_task_for_phrase("annual leave"), "Leave - Annual Leave")
        self.assertEqual(hc.leave_task_for_phrase("sick"), "Leave - Sick / Carer Leave")
        self.assertEqual(hc.leave_task_for_phrase("TIL"), "Leave - Time in Lieu Leave")
        self.assertEqual(hc.leave_task_for_phrase("funeral"), "Leave - Compassionate Leave (paid)")
        self.assertIsNone(hc.leave_task_for_phrase("acuity work"))

    def test_all_projects_loads_from_csv_snapshot(self):
        import harvest_catalog as hc
        projects = hc.all_projects()
        # Snapshot has 107 active projects from Thrive Harvest
        self.assertGreater(len(projects), 100)
        names = {p.name for p in projects}
        self.assertIn("Thrive Leave FY26", names)
        self.assertIn("Thrive Operation FY26", names)
        # Codes are populated
        leave = next(p for p in projects if p.name == "Thrive Leave FY26")
        self.assertEqual(leave.code, "3-0006")
        self.assertEqual(leave.client, "Thrive PR")

    def test_find_project_handles_short_form(self):
        import harvest_catalog as hc
        # Exact match
        p = hc.find_project("Thrive Leave FY26")
        self.assertIsNotNone(p)
        self.assertEqual(p.code, "3-0006")
        # Substring fallback — short form should still resolve
        p = hc.find_project("Thrive Leave")
        self.assertIsNotNone(p)
        self.assertEqual(p.name, "Thrive Leave FY26")
        # Client-name fallback
        p = hc.find_project("Acuity")
        self.assertIsNotNone(p)
        self.assertTrue(p.name.startswith("Acuity - "))

    def test_find_project_candidates_returns_close_matches(self):
        import harvest_catalog as hc
        cands = hc.find_project_candidates("Thrive", limit=5)
        self.assertGreater(len(cands), 0)
        # All returned candidates should mention Thrive somewhere
        for p in cands:
            self.assertTrue("Thrive" in p.name or "Thrive" in p.client)


class ResolverSubstringFallbackTests(unittest.TestCase):
    """harvest_api.resolve_ids must handle the AI saying 'Thrive Leave' when
    Harvest has 'Thrive Leave FY26', and 'Annual Leave' when Harvest has
    'Leave - Annual Leave'. This was the root cause of the 2026-05-06 UAT
    'could not resolve' failure on Mon 18 May Annual Leave."""

    def _fake_projects(self):
        # Simulates the live Harvest catalog the resolver fetches
        return [
            {
                "project_id": 7,
                "project_name": "Thrive Leave FY26",
                "client_name": "Thrive PR",
                "tasks": [
                    {"task_id": 101, "task_name": "Leave - Annual Leave"},
                    {"task_id": 102, "task_name": "Leave - Sick / Carer Leave"},
                    {"task_id": 103, "task_name": "Leave - Compassionate Leave (paid)"},
                ],
            },
            {
                "project_id": 11,
                "project_name": "Thrive Operation FY26",
                "client_name": "Thrive PR",
                "tasks": [
                    {"task_id": 201, "task_name": "Thrive Operation - Reporting & WIPs"},
                    {"task_id": 202, "task_name": "Thrive Operation - Office Management"},
                ],
            },
            {
                "project_id": 50,
                "project_name": "Acuity - Existing Business Growth FY26",
                "client_name": "Acuity",
                "tasks": [
                    {"task_id": 301, "task_name": "Acuity - Existing Growth - BYD"},
                ],
            },
        ]

    def test_short_project_name_resolves_via_substring(self):
        import harvest_api
        with patch("harvest_api.get_projects_with_tasks", return_value=self._fake_projects()):
            r = harvest_api.resolve_ids("Thrive Leave", "Annual Leave")
        self.assertIsNotNone(r)
        self.assertEqual(r["project_id"], 7)
        self.assertEqual(r["task_id"], 101)

    def test_client_name_resolves_via_substring(self):
        import harvest_api
        with patch("harvest_api.get_projects_with_tasks", return_value=self._fake_projects()):
            r = harvest_api.resolve_ids("Acuity", "BYD")
        self.assertIsNotNone(r)
        self.assertEqual(r["project_id"], 50)
        self.assertEqual(r["task_id"], 301)

    def test_exact_match_still_wins_over_substring(self):
        """If both 'Thrive Leave FY26' (exact) and another substring-matchable
        project exist, exact must win. Guards against a regression where
        substring tier accidentally short-circuits exact tier."""
        import harvest_api
        with patch("harvest_api.get_projects_with_tasks", return_value=self._fake_projects()):
            r = harvest_api.resolve_ids("Thrive Leave FY26", "Leave - Annual Leave")
        self.assertEqual(r["project_id"], 7)
        self.assertEqual(r["task_id"], 101)

    def test_diagnostics_returns_candidates_on_miss(self):
        import harvest_api
        with patch("harvest_api.get_projects_with_tasks", return_value=self._fake_projects()):
            d = harvest_api.resolve_ids_with_diagnostics(
                "Thrive Leave", "this task does not exist anywhere"
            )
        # Project resolves but task doesn't — we should get None + candidates
        # (the project we considered, with its top tasks)
        self.assertIsNone(d["resolved"])
        self.assertGreater(len(d["candidates"]), 0)
        # First candidate should be the Thrive Leave project we considered
        proj_name, _client, top_tasks = d["candidates"][0]
        self.assertEqual(proj_name, "Thrive Leave FY26")
        self.assertIn("Leave - Annual Leave", top_tasks)

    def test_diagnostics_returns_resolved_with_empty_candidates_on_hit(self):
        import harvest_api
        with patch("harvest_api.get_projects_with_tasks", return_value=self._fake_projects()):
            d = harvest_api.resolve_ids_with_diagnostics("Thrive Leave", "Annual Leave")
        self.assertIsNotNone(d["resolved"])
        self.assertEqual(d["candidates"], [])


class NotesFallbackTests(unittest.TestCase):
    """Some Thrive Harvest projects (e.g. Thrive Operation FY26) require
    non-empty notes at the API level. _derive_notes_fallback supplies a
    sensible default when the user didn't write notes themselves."""

    def test_strips_family_prefix(self):
        import app as app_mod
        cases = [
            ("Leave - Annual Leave", "Annual Leave"),
            ("Thrive Operation - Reporting & WIPs", "Reporting & WIPs"),
            ("Thrive L&D - Weekly Planning", "Weekly Planning"),
            ("Client - Internal WIP", "Internal WIP"),
            ("Thrive Finance - Bank Reconciliation", "Bank Reconciliation"),
        ]
        for inp, expected in cases:
            self.assertEqual(app_mod._derive_notes_fallback(inp), expected,
                             f"input={inp!r}")

    def test_no_prefix_returns_full_name(self):
        import app as app_mod
        self.assertEqual(app_mod._derive_notes_fallback("Reporting & WIPs"),
                         "Reporting & WIPs")

    def test_empty_input_returns_branded_default(self):
        import app as app_mod
        self.assertEqual(app_mod._derive_notes_fallback(""),
                         "Time logged via Timesheet Assistant")
        self.assertEqual(app_mod._derive_notes_fallback("   "),
                         "Time logged via Timesheet Assistant")


class ApproveResolutionErrorMessageTests(unittest.TestCase):
    """_format_resolution_error must surface the candidate list in a way
    the user can act on — no more 'verify the project is active'."""

    def test_no_candidates_falls_back_to_generic_message(self):
        import app as app_mod
        msg = app_mod._format_resolution_error("FooBar", "Baz", [])
        self.assertIn("FooBar", msg)
        self.assertIn("Baz", msg)
        self.assertIn("Verify the project is active", msg)

    def test_with_candidates_includes_actionable_options(self):
        import app as app_mod
        candidates = [
            ("Thrive Leave FY26", "Thrive PR", ["Leave - Annual Leave", "Leave - Sick / Carer Leave"]),
        ]
        msg = app_mod._format_resolution_error("Thrive Leave", "Annual Leave", candidates)
        self.assertIn("Closest matches", msg)
        self.assertIn("Thrive Leave FY26", msg)
        self.assertIn("Leave - Annual Leave", msg)
        self.assertNotIn("Verify the project is active", msg)


class ChatHistoryOrderingTests(unittest.TestCase):
    """Regression: get_chat_history must return the MOST RECENT N rows in
    ascending chronological order. The first version ordered ASC at the DB
    + LIMIT N, which silently returned the N OLDEST rows ever recorded for
    the user — so chat resume on hard refresh always came back empty for any
    user with more than `limit` total historical messages. UAT 2026-05-06."""

    def _fake_supabase_with_rows(self, rows):
        """Build a MagicMock that mimics the supabase-py fluent query chain
        and asserts the order direction we requested. Returns (client, captured)
        so the test can inspect what limit + desc were passed."""
        captured = {}
        result = MagicMock()
        result.data = rows

        query = MagicMock()
        query.eq.return_value = query

        def _order(col, desc=False):
            captured["order_col"] = col
            captured["desc"] = desc
            return query
        query.order.side_effect = _order

        def _limit(n):
            captured["limit"] = n
            # Mimic Supabase: AFTER ordering DESC, take first N rows.
            limited = MagicMock()
            ordered = sorted(
                result.data,
                key=lambda r: r["created_at"],
                reverse=captured.get("desc", False),
            )
            limited.execute.return_value = MagicMock(data=ordered[:n])
            return limited
        query.limit.side_effect = _limit

        table = MagicMock()
        table.select.return_value = query

        client = MagicMock()
        client.table.return_value = table
        return client, captured

    def test_returns_most_recent_when_history_exceeds_limit(self):
        """The exact symptom Malik hit: 100 historical rows, ask for 30,
        expect the 30 NEWEST in ascending order — not the 30 oldest."""
        import harvest_mock
        rows = [
            {
                "user_name": "Malik",
                "role": "user" if i % 2 == 0 else "assistant",
                "content": f"msg-{i:03d}",
                "created_at": f"2026-05-{(i % 28) + 1:02d}T{(i % 24):02d}:00:00Z",
            }
            for i in range(100)
        ]
        # Sort the source rows so insertion order isn't accidentally relied on.
        rows_shuffled = list(reversed(rows))

        client, captured = self._fake_supabase_with_rows(rows_shuffled)
        with patch("harvest_mock._get_client", return_value=client):
            out = harvest_mock.get_chat_history("Malik", limit=30)

        self.assertEqual(captured["desc"], True,
                         "Must order DESC at the DB to slice the most recent N")
        self.assertEqual(captured["limit"], 30)
        self.assertEqual(len(out), 30)
        # Returned in ASCENDING chronological order for replay.
        timestamps = [r["created_at"] for r in out]
        self.assertEqual(timestamps, sorted(timestamps),
                         "Caller expects ascending order for replay")
        # And those 30 must be the most-recent slice — none of the 70 oldest.
        oldest_70_contents = {r["content"] for r in sorted(rows, key=lambda r: r["created_at"])[:70]}
        for r in out:
            self.assertNotIn(r["content"], oldest_70_contents,
                             "Returned rows must come from the newest slice, not the oldest")

    def test_returns_empty_when_supabase_unconfigured(self):
        """Existing fail-safe: no client → empty list, no exception."""
        import harvest_mock
        with patch("harvest_mock._get_client", return_value=None):
            self.assertEqual(harvest_mock.get_chat_history("anyone", limit=10), [])


class PushErrorSurfacingTests(unittest.IsolatedAsyncioTestCase):
    """Verify approve/approve_all return the underlying Harvest error string,
    not just success: false."""

    async def test_approve_returns_resolution_error_on_push_failure(self):
        # Simulate the failure path: resolver returns no match → user gets the
        # candidate-list error. Updated for Path B's signature change
        # (BackgroundTasks param) + new harvest_mock.get_entry_by_id lookup.
        from fastapi import BackgroundTasks
        request = MagicMock()
        request.session = {
            "user": {"email": "u@example.com", "name": "U"},
            "harvest_token": {
                "access_token": "hv",
                "expires_at": (datetime.utcnow() + timedelta(days=1)).timestamp(),
            },
        }
        fake_entry = {
            "id": "e1",
            "client": "Acuity",
            "project_code": "ACU",  # no hyphen -> skip ID fast-path
            "project_name": "Existing Growth FY26",
            "task": "Existing Growth FY26",
            "hours": 2.0,
            "notes": "",
            "date": "2026-05-06",
            "status": "Draft",
        }
        with patch("app.get_current_user", return_value=request.session["user"]), \
             patch("app.harvest_oauth.ensure_valid_token", return_value=request.session["harvest_token"]), \
             patch("app.harvest_mock.get_entry_by_id", return_value=fake_entry), \
             patch("app.harvest_api.get_projects_with_tasks_async", return_value=[]), \
             patch("app.harvest_api.resolve_user_id", return_value=42), \
             patch("app.harvest_api.resolve_ids_with_diagnostics",
                   return_value={"resolved": None, "candidates": []}):
            out = await app_mod.approve_entry("e1", request, BackgroundTasks())
        self.assertFalse(out["success"])
        self.assertIn("could not resolve", out["error"].lower())
        self.assertEqual(out["client"], "Acuity")


class TodayClampTests(unittest.TestCase):
    """Backend safeguard against chat-history date drift.

    Real production observation 2026-05-07: in a 34-message resumed chat
    Malik typed "1h general admin today"; the AI emitted an ENTRY block
    with date=2026-05-08 (Friday) instead of 2026-05-07 (Thursday). The
    clamp fixes that deterministically before the entry is saved.

    Tests pin server_today to 2026-05-07 via patching _today_local_iso so
    the suite is independent of the calendar date when CI runs."""

    SERVER_TODAY = "2026-05-07"

    def setUp(self):
        import app as app_mod
        self.app_mod = app_mod
        # Pin server-today so tests don't depend on the calendar.
        self._patch = patch.object(app_mod, "_today_local_iso", return_value=self.SERVER_TODAY)
        self._patch.start()
        self.clamp = app_mod._clamp_entry_date_to_today

    def tearDown(self):
        self._patch.stop()

    def test_clamps_when_user_says_today_but_model_drifted(self):
        # User said "today" → entry MUST be server today; AI gave 2026-05-08
        clamped, reason = self.clamp(
            tool_date="2026-05-08",
            user_message="1h general admin today",
            user_email=None,
            selected_date=None,
        )
        self.assertEqual(clamped, self.SERVER_TODAY)
        self.assertIsNotNone(reason)
        self.assertIn("today", reason)

    def test_clamp_ignores_picker_drift_when_user_said_today(self):
        # Picker is on a future date but user said 'today' — anchor wins.
        clamped, reason = self.clamp(
            tool_date="2026-05-08",
            user_message="1h general admin today",
            user_email=None,
            selected_date="2026-05-08",
        )
        self.assertEqual(clamped, self.SERVER_TODAY)
        self.assertIsNotNone(reason)

    def test_no_clamp_when_user_explicitly_named_tomorrow(self):
        clamped, reason = self.clamp(
            tool_date="2026-05-08",
            user_message="tomorrow finance month-end work",
            user_email=None,
            selected_date=None,
        )
        self.assertEqual(clamped, "2026-05-08")
        self.assertIsNone(reason)

    def test_no_clamp_when_user_named_specific_date(self):
        clamped, reason = self.clamp(
            tool_date="2026-05-12",
            user_message="annual leave on 12 may",
            user_email=None,
            selected_date=None,
        )
        self.assertEqual(clamped, "2026-05-12")
        self.assertIsNone(reason)

    def test_no_clamp_when_today_aligns(self):
        # Model emitted server today as expected — no override.
        clamped, reason = self.clamp(
            tool_date=self.SERVER_TODAY,
            user_message="1h general admin today",
            user_email=None,
            selected_date=None,
        )
        self.assertEqual(clamped, self.SERVER_TODAY)
        self.assertIsNone(reason)

    def test_no_clamp_when_no_today_keyword(self):
        # User just gave hours — no time anchor at all. Trust the model.
        clamped, reason = self.clamp(
            tool_date="2026-05-08",
            user_message="2h finance",
            user_email=None,
            selected_date=None,
        )
        self.assertEqual(clamped, "2026-05-08")
        self.assertIsNone(reason)

    def test_clamps_on_this_morning_phrasing(self):
        # 'this morning' should anchor to today
        clamped, reason = self.clamp(
            tool_date="2026-05-08",
            user_message="30 min on emails this morning",
            user_email=None,
            selected_date=None,
        )
        self.assertEqual(clamped, self.SERVER_TODAY)
        self.assertIsNotNone(reason)


class TodayIsoMetaTagTests(unittest.TestCase):
    """The frontend reads today from a <meta> tag so the date picker
    matches the AU profile timezone, not the browser timezone. The route
    handler must populate today_iso for the template."""

    def test_template_has_meta_tag(self):
        path = _HERE / "templates" / "index.html"
        src = path.read_text(encoding="utf-8")
        self.assertIn('name="server-today-iso"', src)
        self.assertIn('{{ today_iso }}', src)

    def test_localTodayIso_prefers_meta_tag(self):
        path = _HERE / "templates" / "index.html"
        src = path.read_text(encoding="utf-8")
        # JS reads the meta tag before falling back to browser-local time.
        self.assertIn('server-today-iso', src)
        self.assertIn('isoFromMeta', src)


class AuthoritativeTodayClampPromptTests(unittest.TestCase):
    """The strengthened AUTHORITATIVE TODAY block must spell out
    today/yesterday/tomorrow ISO dates and explicitly tell the model to
    ignore conversation drift."""

    def test_prompt_lists_explicit_iso_dates(self):
        import app as app_mod
        with patch.object(
            app_mod, "get_all_projects_for_prompt", return_value="(no projects)"
        ):
            blocks = app_mod.build_system_prompt(user_email="hugh.preston@thrivepr.com.au")
        joined = "\n".join(b["text"] for b in blocks)
        # Hard rules section is present
        self.assertIn("AUTHORITATIVE TODAY", joined)
        self.assertIn("Hard rules", joined)
        # Today + yesterday + tomorrow are spelled out as ISO
        au_today = app_mod.time_utils.today_iso_local("en-AU-Sydney")
        self.assertIn(au_today, joined)
        # Drift defense
        self.assertIn("dead", joined.lower())


class DraftHallucinationGuardTests(unittest.IsolatedAsyncioTestCase):
    """Guard against the 2026-05-07 production observation: in a 42-message
    resumed chat, the model wrote 'Drafted 4h on Thrive Operation / Reporting
    & WIPs for today...' as plain text without calling save_entry. The right
    panel stayed empty and the user thought the entry was lost.

    The regex must:
      - match 'Drafted 4h on ...' / 'Drafted 1h on ...' / 'Drafted 7.5 hours on ...'
      - NOT match 'I drafted a press release for Acuity yesterday' (no number)
      - NOT match 'Logged 4h' (different verb — that path doesn't claim a draft)

    The recovery helper must, given a forced save_entry tool_use, populate
    entries_sink and return a synthesized 'Drafted Nh on Client / Project for
    YYYY-MM-DD ...' confirmation."""

    def test_regex_matches_production_hallucination(self):
        import app as app_mod
        pat = app_mod._DRAFT_HALLUCINATION_RE
        self.assertIsNotNone(pat.search(
            "Drafted 4h on Thrive Operation / Reporting & WIPs for today — "
            "approve in the right panel to push to Harvest."
        ))
        self.assertIsNotNone(pat.search("Drafted 1h on Project X for today."))
        self.assertIsNotNone(pat.search("Drafted 7.5 hours on Annual Leave"))
        self.assertIsNotNone(pat.search("drafting 0.75h on emails"))

    def test_regex_rejects_non_hallucinations(self):
        import app as app_mod
        pat = app_mod._DRAFT_HALLUCINATION_RE
        # Real "draft" usage that has nothing to do with time entries.
        self.assertIsNone(pat.search("I drafted a press release for Acuity yesterday"))
        # Different verb — not the hallucination pattern.
        self.assertIsNone(pat.search("Logged 4h on Acuity"))
        # Too far between draft and the number.
        self.assertIsNone(pat.search(
            "Drafted the press release. We covered a lot of ground today, including the 4h "
            "mark of the brand campaign."
        ))

    async def test_recovery_forces_save_entry_and_synthesizes_confirmation(self):
        """End-to-end: when the model hallucinates a draft, the recovery
        helper runs a forced tool_choice=save_entry call, executes the
        returned tool_use via execute_tool, and returns a 'Drafted Nh on
        Client / Project for YYYY-MM-DD ...' confirmation. The entries_sink
        is populated as a side-effect."""
        import app as app_mod

        # Hallucinated assistant turn — text only, no tool_use.
        hallucinated = MagicMock()
        hallucinated_block = MagicMock()
        hallucinated_block.type = "text"
        hallucinated_block.text = "Drafted 4h on Thrive Operation / Reporting & WIPs for today."
        hallucinated.content = [hallucinated_block]

        # Forced response — model emits a save_entry tool_use because
        # tool_choice forces it.
        forced = MagicMock()
        tool_use_block = MagicMock()
        tool_use_block.type = "tool_use"
        tool_use_block.name = "save_entry"
        tool_use_block.id = "toolu_recovery_1"
        tool_use_block.input = {
            "client": "Thrive Operation FY26",
            "project_code": "",
            "project_name": "Thrive Operation - Reporting & WIPs",
            "task": "Thrive Operation - Reporting & WIPs",
            "hours": 4.0,
            "notes": "",
            "date": "2026-05-07",
            "status": "Draft",
        }
        forced.content = [tool_use_block]

        async def fake_create(**kwargs):
            # Recovery is called with tool_choice forcing save_entry.
            self.assertEqual(
                kwargs.get("tool_choice"),
                {"type": "tool", "name": "save_entry"},
            )
            return forced

        sink: list = []
        with patch.object(app_mod.client.messages, "create", side_effect=fake_create), \
             patch.object(app_mod, "_today_local_iso", return_value="2026-05-07"), \
             patch.object(app_mod.harvest_mock, "create_draft_entry", return_value={
                 "id": "draft-recover-1",
                 "client": "Thrive Operation FY26",
                 "project_code": "",
                 "project_name": "Thrive Operation - Reporting & WIPs",
                 "task": "Thrive Operation - Reporting & WIPs",
                 "hours": 4.0,
                 "notes": "",
                 "date": "2026-05-07",
                 "status": "Draft",
             }), \
             patch.object(app_mod.sheets_sync, "sync_entry_to_sheet", return_value=None):
            recovered = await app_mod._recover_from_draft_hallucination(
                last_response=hallucinated,
                messages=[{"role": "user", "content": "4h general admin today"}],
                system_blocks=[{"type": "text", "text": "system"}],
                tools_param=[{"name": "save_entry"}],
                access_token="",
                harvest_access_token=None,
                harvest_user_id=None,
                user_dialect="en-AU-Sydney",
                entries_sink=sink,
                user_name="Malik Amin",
                user_email="mallikamiin@gmail.com",
                selected_date=None,
                user_message="4h general admin today",
            )

        self.assertIsNotNone(recovered)
        self.assertEqual(len(sink), 1)
        self.assertEqual(sink[0]["hours"], 4.0)
        self.assertIn("Drafted 4", recovered)
        self.assertIn("Thrive Operation FY26", recovered)
        self.assertIn("Thrive Operation - Reporting & WIPs", recovered)
        self.assertIn("2026-05-07", recovered)
        self.assertIn("right panel", recovered)

    async def test_recovery_returns_none_when_forced_call_emits_no_tool_use(self):
        """If the forced call somehow returns text-only despite tool_choice
        (rare — would be an API regression), the recovery returns None so the
        caller can surface a retry hint instead of leaking a wrong reply."""
        import app as app_mod

        hallucinated = MagicMock()
        hallucinated_block = MagicMock()
        hallucinated_block.type = "text"
        hallucinated_block.text = "Drafted 4h on X for today."
        hallucinated.content = [hallucinated_block]

        # Forced response — but text-only, no tool_use (pathological).
        forced = MagicMock()
        text_only = MagicMock()
        text_only.type = "text"
        text_only.text = "I refuse"
        forced.content = [text_only]

        async def fake_create(**kwargs):
            return forced

        sink: list = []
        with patch.object(app_mod.client.messages, "create", side_effect=fake_create):
            recovered = await app_mod._recover_from_draft_hallucination(
                last_response=hallucinated,
                messages=[],
                system_blocks=[{"type": "text", "text": "system"}],
                tools_param=[{"name": "save_entry"}],
                access_token="",
                harvest_access_token=None,
                harvest_user_id=None,
                user_dialect=None,
                entries_sink=sink,
                user_name="Malik",
                user_email="malik@example.com",
                selected_date=None,
                user_message="4h general admin today",
            )

        self.assertIsNone(recovered)
        self.assertEqual(len(sink), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
