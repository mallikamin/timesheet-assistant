"""
Google Sheets sync module.

Two worksheets in a single workbook (GOOGLE_SHEET_ID):

  Tab 1 — "Entries"  (legacy default sheet1)
    Approved/draft time entries that flow through the assistant.
    Columns: Date | User | Client | Project Code | Project Name | Task |
             Hours | Notes | Status | Entry ID | Created At

  Tab 2 — "ChatLog"  (added 2026-05-04 for full PoC observability)
    Every interaction recorded by training_log.log() — chat turns, weekly
    categorize runs, approvals, edits, deletes — mirrored row-by-row so we
    have a durable record that survives Render free-tier filesystem wipes.
    Columns: Timestamp (UTC) | User Email | User Name | Kind | Message |
             Response | Tool Calls | Entries Created | Latency ms |
             Input Tokens | Output Tokens | Cache Read | Cache Creation |
             Model | Stop Reason | Streamed | System Prompt Hash |
             Interaction ID | Related ID

Why both tabs share one workbook: keeps the service-account scope and the
auth handshake to a single round trip, lets reviewers cross-reference an
entry with the chat turn that produced it (Entry ID ↔ Interaction ID via
related_id), and means there's exactly one URL to share with Tariq.

All public functions silently no-op when GOOGLE_SHEET_ID or
GOOGLE_SERVICE_ACCOUNT_JSON are unset, or when the Sheets API call fails —
logging must never break the request path.
"""

import json
import os
from typing import Any, Dict, Optional

import gspread
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

_ENTRIES_TAB = "Entries"
_CHATLOG_TAB = "ChatLog"

_ENTRIES_HEADER = [
    "Date", "User", "Client", "Project Code", "Project Name",
    "Task", "Hours", "Notes", "Status", "Entry ID", "Created At",
]

_CHATLOG_HEADER = [
    "Timestamp (UTC)", "User Email", "User Name", "Kind",
    "Message", "Response", "Tool Calls", "Entries Created",
    "Latency ms", "Input Tokens", "Output Tokens",
    "Cache Read", "Cache Creation", "Model", "Stop Reason",
    "Streamed", "System Prompt Hash", "Interaction ID", "Related ID",
]

# Sheets cell content limit is 50,000 chars; truncate well below that so a
# single huge tool result can't blow up the row.
_CELL_TRUNCATE = 8000

_workbook = None
_entries_sheet = None
_chatlog_sheet = None


def is_configured() -> bool:
    """True iff both env vars are present. Surfaced in /health."""
    return bool(os.getenv("GOOGLE_SHEET_ID")) and bool(os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON"))


def _parse_service_account_json(raw: str) -> dict:
    """Robustly parse a Google service-account JSON string from an env var.

    Handles three real-world variants we've seen in production:
      1. Single-line JSON with `\\n` escapes inside the private_key — parses
         directly via json.loads.
      2. Pretty-printed multi-line JSON, copy-pasted from the GCP key download
         (private_key as a quoted multi-line string with escaped \\n inside).
         Naive parsing fails because real newlines BETWEEN fields are valid
         JSON whitespace, but real newlines INSIDE the private_key string are
         not — they have to be escaped.
      3. Mixed: some fields with \\n escapes, private_key with real newlines,
         some both. We escape only the newlines inside string values, leave
         whitespace between tokens alone, and let json.loads do the rest.

    Why we hand-roll this instead of pulling in json5 / PyYAML: this is the
    only place we deal with messy-JSON env vars, the parser is ~20 lines, and
    a new dependency for a one-off would be overkill.
    """
    # Fast path: well-formed JSON with no real newlines in strings
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Repair path: walk the string, escape real newlines/CR only when inside
    # a string literal. Track an `escaped` flag so we don't mis-toggle the
    # in_string state on `\\"` inside a value.
    fixed_chars = []
    in_string = False
    escaped = False
    for ch in raw:
        if escaped:
            fixed_chars.append(ch)
            escaped = False
            continue
        if ch == "\\":
            fixed_chars.append(ch)
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            fixed_chars.append(ch)
            continue
        if in_string and ch == "\n":
            fixed_chars.append("\\n")
            continue
        if in_string and ch == "\r":
            fixed_chars.append("\\r")
            continue
        if in_string and ch == "\t":
            fixed_chars.append("\\t")
            continue
        fixed_chars.append(ch)
    return json.loads("".join(fixed_chars))


def _normalize_private_key_pem(pk: str) -> str:
    """Repair a PEM private key whose BEGIN/END markers got broken by
    multi-line env-var encoding.

    The PEM standard requires `-----BEGIN ... KEY-----` and the matching
    END line each on a single physical line. When a service-account JSON
    is pasted into a UI that soft-wraps at column ~80 (Render's env var
    textarea among others), real newlines can land inside the marker
    strings, e.g. `-----BEGIN PRIVATE\\n  KEY-----`. After json.loads
    those become real newlines in the parsed value, and the cryptography
    library reports `Valid PEM but no BEGIN/END delimiters`.

    Repair: collapse internal whitespace in any `-----BEGIN ... KEY-----`
    or `-----END ... KEY-----` marker so each marker sits on one line.
    Also ensure exactly one newline between the BEGIN marker and the
    base64 body, and between the body and the END marker.
    """
    import re
    if not isinstance(pk, str) or "BEGIN" not in pk or "END" not in pk:
        return pk

    def _collapse(match: "re.Match[str]") -> str:
        return re.sub(r"\s+", " ", match.group(0))

    # `[\w\s]+?` matches word characters and any whitespace (incl. newlines)
    # non-greedily up to the next `KEY` token. Anchored on the literal
    # five-dash framing so we don't accidentally rewrite anything in the
    # base64 body.
    pk = re.sub(r"-----\s*BEGIN[\w\s]+?KEY\s*-----", _collapse, pk)
    pk = re.sub(r"-----\s*END[\w\s]+?KEY\s*-----", _collapse, pk)

    # Ensure newline separation around markers — without it the cryptography
    # library's PEM tokenizer can still misread the body.
    pk = re.sub(r"(-----BEGIN [^-]+ KEY-----)\s*", r"\1\n", pk)
    pk = re.sub(r"\s*(-----END [^-]+ KEY-----)", r"\n\1", pk)
    if not pk.endswith("\n"):
        pk = pk + "\n"
    return pk


def _get_workbook():
    """Open the workbook once and cache it. Returns None when unconfigured
    or when init fails (errors are printed once, then we no-op)."""
    global _workbook
    if _workbook is not None:
        return _workbook

    sheet_id = os.getenv("GOOGLE_SHEET_ID", "")
    creds_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not sheet_id or not creds_json:
        return None

    try:
        creds_data = _parse_service_account_json(creds_json)
        if "private_key" in creds_data:
            creds_data["private_key"] = _normalize_private_key_pem(creds_data["private_key"])
        creds = Credentials.from_service_account_info(creds_data, scopes=SCOPES)
        gc = gspread.authorize(creds)
        _workbook = gc.open_by_key(sheet_id)
    except Exception as e:
        print(f"Google Sheets init error: {e}")
        return None
    return _workbook


def _ensure_tab(title: str, header: list):
    """Get or create a worksheet by title; ensure the header row exists."""
    wb = _get_workbook()
    if wb is None:
        return None
    try:
        try:
            ws = wb.worksheet(title)
        except gspread.WorksheetNotFound:
            ws = wb.add_worksheet(title=title, rows=1000, cols=max(len(header), 20))
        existing = ws.row_values(1)
        if not existing:
            ws.append_row(header)
        return ws
    except Exception as e:
        print(f"Google Sheets tab init error ({title}): {e}")
        return None


def _get_entries_sheet():
    """Entries tab. Falls back to legacy sheet1 if the workbook was created
    before this module knew about named tabs (single-sheet workbooks)."""
    global _entries_sheet
    if _entries_sheet is not None:
        return _entries_sheet
    wb = _get_workbook()
    if wb is None:
        return None
    try:
        try:
            ws = wb.worksheet(_ENTRIES_TAB)
        except gspread.WorksheetNotFound:
            # Legacy: pre-existing workbooks just had sheet1; reuse it and rename.
            ws = wb.sheet1
            try:
                ws.update_title(_ENTRIES_TAB)
            except Exception:
                # Renaming requires more permissions than we may have; carry on.
                pass
        existing = ws.row_values(1)
        if not existing:
            ws.append_row(_ENTRIES_HEADER)
        _entries_sheet = ws
        return ws
    except Exception as e:
        print(f"Google Sheets entries tab error: {e}")
        return None


def _get_chatlog_sheet():
    global _chatlog_sheet
    if _chatlog_sheet is not None:
        return _chatlog_sheet
    _chatlog_sheet = _ensure_tab(_CHATLOG_TAB, _CHATLOG_HEADER)
    return _chatlog_sheet


# ---------------- Entries (existing API, unchanged contract) ----------------


def sync_entry_to_sheet(entry: Dict) -> bool:
    """Push a time entry to the Entries tab. Returns True on success."""
    sheet = _get_entries_sheet()
    if sheet is None:
        return False
    try:
        row = [
            entry.get("date", entry.get("entry_date", "")),
            entry.get("user", entry.get("user_name", "")),
            entry.get("client", ""),
            entry.get("project_code", ""),
            entry.get("project_name", ""),
            entry.get("task", ""),
            entry.get("hours", 0),
            entry.get("notes", ""),
            entry.get("status", "Draft"),
            entry.get("id", ""),
            entry.get("created_at", ""),
        ]
        sheet.append_row(row, value_input_option="USER_ENTERED")
        return True
    except Exception as e:
        print(f"Google Sheets sync error: {e}")
        return False


def delete_entry_from_sheet(entry_id: str) -> bool:
    sheet = _get_entries_sheet()
    if sheet is None:
        return False
    try:
        cell = sheet.find(entry_id)
        if cell:
            sheet.delete_rows(cell.row)
            return True
    except Exception as e:
        print(f"Google Sheets delete error: {e}")
    return False


def update_entry_status_in_sheet(entry_id: str, new_status: str) -> bool:
    sheet = _get_entries_sheet()
    if sheet is None:
        return False
    try:
        cell = sheet.find(entry_id)
        if cell:
            # Status is column 9 (header layout: Date(1)..Created At(11))
            sheet.update_cell(cell.row, 9, new_status)
            return True
    except Exception as e:
        print(f"Google Sheets status update error: {e}")
    return False


# ---------------- Chat log (new) ----------------


def _truncate(value: Any, limit: int = _CELL_TRUNCATE) -> str:
    """Coerce to string and cap length so a giant tool payload can't poison
    the cell or trip Sheets' 50k-char hard limit."""
    if value is None:
        return ""
    if not isinstance(value, str):
        try:
            value = json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            value = repr(value)
    if len(value) > limit:
        return value[: limit - 14] + "...[truncated]"
    return value


def _summarize_tool_calls(tool_calls: Any) -> str:
    """Tool calls in training_log.output are a list of {name, input, ...} dicts.
    For the Sheet we want a compact human-readable summary, not the raw blob."""
    if not tool_calls:
        return ""
    if not isinstance(tool_calls, list):
        return _truncate(tool_calls, 500)
    names = []
    for tc in tool_calls:
        if isinstance(tc, dict):
            n = tc.get("name") or tc.get("type") or "unknown"
        else:
            n = str(tc)[:40]
        names.append(n)
    return ", ".join(names)


def log_chat_to_sheet(record: Dict[str, Any]) -> bool:
    """Mirror one training_log record to the ChatLog tab. The record shape is
    exactly what training_log.log() persists to JSONL — see that module's
    docstring for the schema."""
    sheet = _get_chatlog_sheet()
    if sheet is None:
        return False
    try:
        inp = record.get("input") or {}
        out = record.get("output") or {}
        metrics = record.get("metrics") or {}

        row = [
            record.get("ts", ""),
            record.get("user_email", ""),
            record.get("user_name", ""),
            record.get("kind", ""),
            _truncate(inp.get("message", "")),
            _truncate(out.get("response_text", "")),
            _summarize_tool_calls(out.get("tool_calls")),
            len(out.get("entries_created", []) or []),
            metrics.get("latency_ms", ""),
            metrics.get("input_tokens", ""),
            metrics.get("output_tokens", ""),
            metrics.get("cache_read_input_tokens", ""),
            metrics.get("cache_creation_input_tokens", ""),
            inp.get("model", ""),
            out.get("stop_reason", ""),
            inp.get("streamed", ""),
            inp.get("system_prompt_hash", ""),
            record.get("id", ""),
            record.get("related_id", "") or "",
        ]
        sheet.append_row(row, value_input_option="USER_ENTERED")
        return True
    except Exception as e:
        print(f"Google Sheets chat log error: {e}")
        return False
