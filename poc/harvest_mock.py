"""
Harvest storage module — backed by Supabase PostgreSQL.
Stores time entries and chat logs persistently.

Fail-safe behavior: if SUPABASE_URL/SUPABASE_KEY are missing, every call here
becomes a no-op rather than raising. Means the chat endpoint keeps working
during a Supabase outage or in local dev without creds — entries just won't
persist to Supabase. Sheets + Harvest pushes still happen.
"""

import os
import uuid
from datetime import date, datetime
from typing import Dict, List, Optional

from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

_client = None
_in_memory_entries: List[Dict] = []  # Local fallback when Supabase is unavailable


def _supabase_configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


def _get_client():
    global _client
    if not _supabase_configured():
        return None
    if _client is None:
        try:
            _client = create_client(SUPABASE_URL, SUPABASE_KEY)
        except Exception as e:
            print(f"[WARN] Supabase client init failed (storage degraded to in-memory): {e}")
            return None
    return _client


# --- Time Entries ---

def _frontend_remap(row: Dict, default_user: str = "", default_date: str = "") -> Dict:
    row["user"] = row.pop("user_name", default_user)
    row["date"] = row.pop("entry_date", default_date)
    row.setdefault("harvest_id", None)
    return row


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
    """Create a draft time entry. Persists to Supabase when configured,
    otherwise to an in-memory list so the chat flow keeps working."""
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
    row: Dict = dict(entry)
    if sb is not None:
        try:
            result = sb.table("time_entries").insert(entry).execute()
            row = result.data[0] if result.data else entry
        except Exception as e:
            print(f"[WARN] Supabase insert failed, falling back to in-memory: {e}")
            _in_memory_entries.append(dict(entry))
    else:
        _in_memory_entries.append(dict(entry))
    return _frontend_remap(row, default_user=user, default_date=entry["entry_date"])


def get_entries(user: str = None, entry_date: str = None) -> List[Dict]:
    """Get entries from Supabase (or in-memory fallback), optionally filtered."""
    sb = _get_client()
    if sb is None:
        rows = [dict(e) for e in _in_memory_entries]
    else:
        try:
            query = sb.table("time_entries").select("*")
            if user:
                query = query.eq("user_name", user)
            if entry_date:
                query = query.eq("entry_date", entry_date)
            query = query.order("created_at", desc=False)
            result = query.execute()
            rows = result.data or []
        except Exception as e:
            print(f"[WARN] Supabase select failed, returning in-memory entries: {e}")
            rows = [dict(e) for e in _in_memory_entries]

    # Apply filters when reading from in-memory
    if sb is None:
        if user:
            rows = [r for r in rows if r.get("user_name") == user]
        if entry_date:
            rows = [r for r in rows if r.get("entry_date") == entry_date]

    return [_frontend_remap(r) for r in rows]


def update_entry(entry_id: str, **kwargs) -> Optional[Dict]:
    """Update an entry by ID."""
    if "date" in kwargs:
        kwargs["entry_date"] = kwargs.pop("date")
    if "user" in kwargs:
        kwargs["user_name"] = kwargs.pop("user")

    sb = _get_client()
    if sb is not None:
        try:
            result = sb.table("time_entries").update(kwargs).eq("id", entry_id).execute()
            if result.data:
                return _frontend_remap(result.data[0])
        except Exception as e:
            print(f"[WARN] Supabase update failed, trying in-memory: {e}")

    # In-memory fallback
    for e in _in_memory_entries:
        if e.get("id") == entry_id:
            e.update(kwargs)
            return _frontend_remap(dict(e))
    return None


def delete_entry(entry_id: str) -> bool:
    """Delete an entry by ID."""
    sb = _get_client()
    if sb is not None:
        try:
            result = sb.table("time_entries").delete().eq("id", entry_id).execute()
            if result.data:
                return True
        except Exception as e:
            print(f"[WARN] Supabase delete failed, trying in-memory: {e}")

    before = len(_in_memory_entries)
    _in_memory_entries[:] = [e for e in _in_memory_entries if e.get("id") != entry_id]
    return len(_in_memory_entries) < before


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

def save_chat_message(user: str, role: str, content: str, session_id: str = None) -> None:
    """Persist a chat message. No-op when Supabase isn't configured or fails —
    the training_log JSONL captures the same data with richer context, so we
    don't lose the signal if Supabase is down."""
    sb = _get_client()
    if sb is None:
        return
    try:
        sb.table("chat_logs").insert({
            "user_name": user,
            "role": role,
            "content": content,
            "session_id": session_id or "",
        }).execute()
    except Exception as e:
        print(f"[WARN] save_chat_message failed (non-fatal): {e}")


def get_chat_history(user: str, session_id: str = None, limit: int = 50) -> List[Dict]:
    """Get recent chat history for a user.

    Returns up to `limit` messages in ascending chronological order
    (oldest → newest) so callers can replay them as-is. We must order
    DESC at the DB to slice off the *most recent* N rows — ordering
    ASC + LIMIT N returns the N oldest rows ever recorded for the
    user, which is never what the chat-resume path wants. Reverse
    in Python to hand the caller the natural replay order."""
    sb = _get_client()
    if sb is None:
        return []
    try:
        query = sb.table("chat_logs").select("*").eq("user_name", user)
        if session_id:
            query = query.eq("session_id", session_id)
        query = query.order("created_at", desc=True).limit(limit)
        result = query.execute()
        rows = list(result.data or [])
        rows.reverse()
        return rows
    except Exception as e:
        print(f"[WARN] get_chat_history failed: {e}")
        return []
