"""
Google Sheets sync module.
Pushes time entries to a shared Google Sheet for visibility.
"""

import json
import os
from typing import Dict, Optional

import gspread
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

_sheet = None


def _get_sheet():
    """Get or create the Google Sheets connection."""
    global _sheet
    if _sheet is not None:
        return _sheet

    sheet_id = os.getenv("GOOGLE_SHEET_ID", "")
    creds_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")

    if not sheet_id or not creds_json:
        return None

    try:
        creds_data = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_data, scopes=SCOPES)
        gc = gspread.authorize(creds)
        _sheet = gc.open_by_key(sheet_id).sheet1
        # Ensure headers exist
        existing = _sheet.row_values(1)
        if not existing:
            _sheet.append_row([
                "Date", "User", "Client", "Project Code", "Project Name",
                "Task", "Hours", "Notes", "Status", "Entry ID", "Created At"
            ])
    except Exception as e:
        print(f"Google Sheets init error: {e}")
        return None

    return _sheet


def sync_entry_to_sheet(entry: Dict) -> bool:
    """Push a time entry to the Google Sheet. Returns True on success."""
    sheet = _get_sheet()
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
    """Remove an entry row from the sheet by entry ID."""
    sheet = _get_sheet()
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
