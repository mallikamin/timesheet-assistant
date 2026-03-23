"""
Harvest API v2 client.
Handles real Harvest time entry creation, retrieval, and deletion.
"""

import os
import time
from typing import Dict, List, Optional

import httpx

HARVEST_BASE = "https://api.harvestapp.com/api/v2"

# Cache for project/task mapping
_project_cache = None
_cache_time = 0
_user_cache = None
_user_cache_time = 0
CACHE_TTL = 300  # 5 minutes


def _headers() -> Dict[str, str]:
    return {
        "Harvest-Account-ID": os.getenv("HARVEST_ACCOUNT_ID", ""),
        "Authorization": f"Bearer {os.getenv('HARVEST_ACCESS_TOKEN', '')}",
        "User-Agent": "ThriveTimesheet",
        "Content-Type": "application/json",
    }


def is_configured() -> bool:
    """Check if Harvest credentials are set."""
    return bool(os.getenv("HARVEST_ACCESS_TOKEN")) and bool(os.getenv("HARVEST_ACCOUNT_ID"))


def get_users() -> List[Dict]:
    """Fetch all active users from Harvest. Cached."""
    global _user_cache, _user_cache_time

    if _user_cache and (time.time() - _user_cache_time) < CACHE_TTL:
        return _user_cache

    try:
        resp = httpx.get(
            f"{HARVEST_BASE}/users",
            headers=_headers(),
            params={"is_active": "true"},
            timeout=10,
        )
        if resp.status_code == 200:
            _user_cache = resp.json().get("users", [])
            _user_cache_time = time.time()
            return _user_cache
        return _user_cache or []
    except Exception as e:
        print(f"Harvest get_users error: {e}")
        return _user_cache or []


def resolve_user_id(email: str) -> Optional[int]:
    """Map a Google login email to a Harvest user ID."""
    if not email:
        return None
    users = get_users()
    for u in users:
        if u.get("email", "").lower() == email.lower():
            return u["id"]
    return None


def get_projects_with_tasks() -> List[Dict]:
    """Fetch all active projects with their task assignments from Harvest.
    Returns list of: {project_id, project_name, client_name, tasks: [{task_id, task_name}]}
    """
    global _project_cache, _cache_time

    if _project_cache and (time.time() - _cache_time) < CACHE_TTL:
        return _project_cache

    try:
        resp = httpx.get(
            f"{HARVEST_BASE}/projects",
            headers=_headers(),
            params={"is_active": "true"},
            timeout=10,
        )
        if resp.status_code != 200:
            print(f"Harvest projects error: {resp.status_code}")
            return _project_cache or []

        projects = resp.json().get("projects", [])
        result = []

        for p in projects:
            # Get task assignments for this project
            ta_resp = httpx.get(
                f"{HARVEST_BASE}/projects/{p['id']}/task_assignments",
                headers=_headers(),
                params={"is_active": "true"},
                timeout=10,
            )
            tasks = []
            if ta_resp.status_code == 200:
                for ta in ta_resp.json().get("task_assignments", []):
                    tasks.append({
                        "task_id": ta["task"]["id"],
                        "task_name": ta["task"]["name"],
                    })

            result.append({
                "project_id": p["id"],
                "project_name": p["name"],
                "client_name": p["client"]["name"] if p.get("client") else p["name"],
                "tasks": tasks,
            })

        _project_cache = result
        _cache_time = time.time()
        return result

    except Exception as e:
        print(f"Harvest get_projects error: {e}")
        return _project_cache or []


def resolve_ids(project_name: str, task_name: str) -> Optional[Dict]:
    """Resolve project/task names to Harvest IDs.
    Returns {project_id, task_id} or None if not found.
    """
    projects = get_projects_with_tasks()

    for p in projects:
        # Match project by name (case-insensitive)
        if p["project_name"].lower() == project_name.lower() or \
           p["client_name"].lower() == project_name.lower():
            # Find matching task
            for t in p["tasks"]:
                if t["task_name"].lower() == task_name.lower():
                    return {
                        "project_id": p["project_id"],
                        "task_id": t["task_id"],
                    }
            # If no exact task match, try partial
            for t in p["tasks"]:
                if task_name.lower() in t["task_name"].lower() or \
                   t["task_name"].lower() in task_name.lower():
                    return {
                        "project_id": p["project_id"],
                        "task_id": t["task_id"],
                    }
    return None


def create_time_entry(
    project_id: int,
    task_id: int,
    spent_date: str,
    hours: float,
    notes: str = "",
    user_id: int = None,
) -> Optional[Dict]:
    """Create a time entry in Harvest.
    Returns the Harvest entry dict with id, or None on failure.
    """
    if not is_configured():
        return None

    try:
        payload = {
            "project_id": project_id,
            "task_id": task_id,
            "spent_date": spent_date,
            "hours": hours,
            "notes": notes,
        }
        if user_id:
            payload["user_id"] = user_id
        resp = httpx.post(
            f"{HARVEST_BASE}/time_entries",
            headers=_headers(),
            json=payload,
            timeout=10,
        )
        if resp.status_code in (200, 201):
            entry = resp.json()
            print(f"Harvest entry created: ID {entry['id']}")
            return entry
        else:
            print(f"Harvest create error: {resp.status_code} {resp.text[:200]}")
            return None
    except Exception as e:
        print(f"Harvest create_time_entry error: {e}")
        return None


def delete_time_entry(harvest_id: int) -> bool:
    """Delete a time entry from Harvest."""
    if not is_configured():
        return False

    try:
        resp = httpx.delete(
            f"{HARVEST_BASE}/time_entries/{harvest_id}",
            headers=_headers(),
            timeout=10,
        )
        return resp.status_code == 200
    except Exception as e:
        print(f"Harvest delete error: {e}")
        return False


def get_time_entries(spent_date: str = None, user_id: int = None) -> List[Dict]:
    """Get time entries from Harvest, optionally filtered."""
    if not is_configured():
        return []

    try:
        params = {}
        if spent_date:
            params["from"] = spent_date
            params["to"] = spent_date
        if user_id:
            params["user_id"] = user_id

        resp = httpx.get(
            f"{HARVEST_BASE}/time_entries",
            headers=_headers(),
            params=params,
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json().get("time_entries", [])
        return []
    except Exception as e:
        print(f"Harvest get_time_entries error: {e}")
        return []


def reassign_time_entry(harvest_id: int, new_user_id: int) -> Optional[Dict]:
    """Reassign a time entry to a different user.
    Harvest doesn't allow PATCH on user_id, so we delete + recreate.
    Returns the new entry dict or None on failure.
    """
    if not is_configured():
        return None

    try:
        # Get the existing entry
        resp = httpx.get(
            f"{HARVEST_BASE}/time_entries/{harvest_id}",
            headers=_headers(),
            timeout=10,
        )
        if resp.status_code != 200:
            print(f"Harvest: could not fetch entry {harvest_id}")
            return None

        old = resp.json()

        # Delete the old entry
        if not delete_time_entry(harvest_id):
            print(f"Harvest: could not delete entry {harvest_id}")
            return None

        # Recreate with correct user
        new_entry = create_time_entry(
            project_id=old["project"]["id"],
            task_id=old["task"]["id"],
            spent_date=old["spent_date"],
            hours=old["hours"],
            notes=old.get("notes", ""),
            user_id=new_user_id,
        )
        if new_entry:
            print(f"Harvest: reassigned entry {harvest_id} -> {new_entry['id']} for user {new_user_id}")
        return new_entry
    except Exception as e:
        print(f"Harvest reassign error: {e}")
        return None


def push_entry(client_name: str, task_name: str, spent_date: str, hours: float, notes: str = "", user_id: int = None) -> Optional[Dict]:
    """High-level: resolve names to IDs and create a Harvest time entry.
    This is the main function called by the app.
    """
    if not is_configured():
        return None

    ids = resolve_ids(client_name, task_name)
    if not ids:
        print(f"Harvest: could not resolve '{client_name}' / '{task_name}'")
        return None

    return create_time_entry(
        project_id=ids["project_id"],
        task_id=ids["task_id"],
        spent_date=spent_date,
        hours=hours,
        notes=notes,
        user_id=user_id,
    )
