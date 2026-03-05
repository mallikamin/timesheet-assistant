"""
Mock Harvest API module.
Stores time entries locally in JSON. Same interface as future real Harvest API.
"""

import json
import uuid
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional

DATA_FILE = Path(__file__).parent / "data" / "entries.json"


def _load_entries() -> List[Dict]:
    if not DATA_FILE.exists():
        return []
    with open(DATA_FILE, "r") as f:
        data = f.read().strip()
        return json.loads(data) if data else []


def _save_entries(entries: List[Dict]):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(entries, f, indent=2, default=str)


def create_draft_entry(
    user: str,
    client: str,
    project_code: str,
    project_name: str,
    task: str,
    hours: float,
    notes: str,
    entry_date: str = None,
    status: str = "Draft",
) -> dict:
    """Create a draft time entry. Returns the created entry."""
    entry = {
        "id": str(uuid.uuid4())[:8],
        "user": user,
        "client": client,
        "project_code": project_code,
        "project_name": project_name,
        "task": task,
        "hours": hours,
        "notes": notes,
        "date": entry_date or date.today().isoformat(),
        "status": status,
        "created_at": datetime.now().isoformat(),
    }
    entries = _load_entries()
    entries.append(entry)
    _save_entries(entries)
    return entry


def get_entries(user: str = None, entry_date: str = None) -> List[Dict]:
    """Get entries, optionally filtered by user and/or date."""
    entries = _load_entries()
    if user:
        entries = [e for e in entries if e["user"] == user]
    if entry_date:
        entries = [e for e in entries if e["date"] == entry_date]
    return entries


def update_entry(entry_id: str, **kwargs) -> Optional[Dict]:
    """Update an entry by ID. Returns updated entry or None."""
    entries = _load_entries()
    for entry in entries:
        if entry["id"] == entry_id:
            for key, value in kwargs.items():
                if key in entry:
                    entry[key] = value
            _save_entries(entries)
            return entry
    return None


def delete_entry(entry_id: str) -> bool:
    """Delete an entry by ID. Returns True if deleted."""
    entries = _load_entries()
    original_len = len(entries)
    entries = [e for e in entries if e["id"] != entry_id]
    if len(entries) < original_len:
        _save_entries(entries)
        return True
    return False


def get_user_summary(user: str, entry_date: str = None) -> dict:
    """Get a summary of hours for a user."""
    entries = get_entries(user=user, entry_date=entry_date)
    total_hours = sum(e["hours"] for e in entries)
    by_project = {}
    for e in entries:
        key = e["project_name"]
        by_project[key] = by_project.get(key, 0) + e["hours"]
    return {
        "user": user,
        "total_hours": total_hours,
        "entry_count": len(entries),
        "by_project": by_project,
    }
