"""
Harvest storage module — backed by Supabase PostgreSQL.
Stores time entries and chat logs persistently.
"""

import os
import uuid
from datetime import date, datetime
from typing import Dict, List, Optional

from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


# --- Time Entries ---

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
) -> Dict:
    """Create a draft time entry in Supabase."""
    entry = {
        "id": str(uuid.uuid4())[:8],
        "user_name": user,
        "client": client,
        "project_code": project_code,
        "project_name": project_name,
        "task": task,
        "hours": hours,
        "notes": notes,
        "entry_date": entry_date or date.today().isoformat(),
        "status": status,
    }
    sb = _get_client()
    result = sb.table("time_entries").insert(entry).execute()
    row = result.data[0] if result.data else entry
    # Remap for frontend compatibility
    row["user"] = row.pop("user_name", user)
    row["date"] = row.pop("entry_date", entry["entry_date"])
    row.setdefault("harvest_id", None)
    return row


def get_entries(user: str = None, entry_date: str = None) -> List[Dict]:
    """Get entries from Supabase, optionally filtered."""
    sb = _get_client()
    query = sb.table("time_entries").select("*")
    if user:
        query = query.eq("user_name", user)
    if entry_date:
        query = query.eq("entry_date", entry_date)
    query = query.order("created_at", desc=False)
    result = query.execute()
    entries = result.data or []
    # Remap fields for frontend
    for e in entries:
        e["user"] = e.pop("user_name", "")
        e["date"] = e.pop("entry_date", "")
        e.setdefault("harvest_id", None)
    return entries


def update_entry(entry_id: str, **kwargs) -> Optional[Dict]:
    """Update an entry by ID."""
    sb = _get_client()
    # Remap frontend field names to DB columns
    if "date" in kwargs:
        kwargs["entry_date"] = kwargs.pop("date")
    if "user" in kwargs:
        kwargs["user_name"] = kwargs.pop("user")
    try:
        result = sb.table("time_entries").update(kwargs).eq("id", entry_id).execute()
        if result.data:
            row = result.data[0]
            row["user"] = row.pop("user_name", "")
            row["date"] = row.pop("entry_date", "")
            return row
    except Exception as e:
        print(f"update_entry error (may need harvest_id column): {e}")
    return None


def delete_entry(entry_id: str) -> bool:
    """Delete an entry by ID."""
    sb = _get_client()
    result = sb.table("time_entries").delete().eq("id", entry_id).execute()
    return bool(result.data)


def get_user_summary(user: str, entry_date: str = None) -> Dict:
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


# --- Chat Logs ---

def save_chat_message(user: str, role: str, content: str, session_id: str = None):
    """Save a chat message to Supabase."""
    sb = _get_client()
    sb.table("chat_logs").insert({
        "user_name": user,
        "role": role,
        "content": content,
        "session_id": session_id or "",
    }).execute()


def get_chat_history(user: str, session_id: str = None, limit: int = 50) -> List[Dict]:
    """Get recent chat history for a user."""
    sb = _get_client()
    query = sb.table("chat_logs").select("*").eq("user_name", user)
    if session_id:
        query = query.eq("session_id", session_id)
    query = query.order("created_at", desc=False).limit(limit)
    result = query.execute()
    return result.data or []
