"""
Harvest API v2 client.
Handles real Harvest time entry creation, retrieval, and deletion.
"""

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

import httpx

HARVEST_BASE = "https://api.harvestapp.com/api/v2"

# Cache for project/task mapping
_project_cache = None
_cache_time = 0
_user_cache = None
_user_cache_time = 0
CACHE_TTL = 3600  # 1 hour — projects/users rarely change


def _headers(access_token: str = None) -> Dict[str, str]:
    """Generate Harvest API headers. Uses OAuth token if provided, else falls back to PAT."""
    if access_token:
        # OAuth2 flow (per-user token)
        return {
            "Authorization": f"Bearer {access_token}",
            "Harvest-Account-ID": os.getenv("HARVEST_ACCOUNT_ID", ""),
            "User-Agent": "ThriveTimesheet",
            "Content-Type": "application/json",
        }
    else:
        # Fallback to PAT (backward compatibility)
        return {
            "Harvest-Account-ID": os.getenv("HARVEST_ACCOUNT_ID", ""),
            "Authorization": f"Bearer {os.getenv('HARVEST_ACCESS_TOKEN', '')}",
            "User-Agent": "ThriveTimesheet",
            "Content-Type": "application/json",
        }


def is_configured() -> bool:
    """Check if Harvest credentials are set."""
    return bool(os.getenv("HARVEST_ACCESS_TOKEN")) and bool(os.getenv("HARVEST_ACCOUNT_ID"))


def get_my_user(access_token: str) -> Optional[Dict]:
    """Fetch the current OAuth-authenticated user's Harvest profile.
    Returns dict with id, email, first_name, last_name — or None on failure."""
    if not access_token:
        return None
    try:
        resp = httpx.get(
            f"{HARVEST_BASE}/users/me",
            headers=_headers(access_token),
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
        print(f"Harvest get_my_user error: {resp.status_code}")
        return None
    except Exception as e:
        print(f"Harvest get_my_user error: {e}")
        return None


def get_my_project_assignments(access_token: str) -> List[Dict]:
    """Fetch the current OAuth user's active project assignments.
    Returns list of project_assignment dicts (each has 'project' and
    'task_assignments' subkeys)."""
    if not access_token:
        return []
    try:
        resp = httpx.get(
            f"{HARVEST_BASE}/users/me/project_assignments",
            headers=_headers(access_token),
            params={"is_active": "true"},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json().get("project_assignments", [])
        print(f"Harvest get_my_project_assignments error: {resp.status_code}")
        return []
    except Exception as e:
        print(f"Harvest get_my_project_assignments error: {e}")
        return []


def get_users(access_token: str = None) -> List[Dict]:
    """Fetch all active users from Harvest. Cached."""
    global _user_cache, _user_cache_time

    if _user_cache and (time.time() - _user_cache_time) < CACHE_TTL:
        return _user_cache

    try:
        resp = httpx.get(
            f"{HARVEST_BASE}/users",
            headers=_headers(access_token),
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


def resolve_user_id(email: str, access_token: str = None) -> Optional[int]:
    """Map a Google login email to a Harvest user ID."""
    if not email:
        return None
    users = get_users(access_token)
    for u in users:
        if u.get("email", "").lower() == email.lower():
            return u["id"]
    return None


def _fetch_task_assignments(project_id: int, access_token: Optional[str]) -> List[Dict]:
    """Fetch the task_assignments for a single project. Returns the parsed
    [{task_id, task_name}, ...] list (empty on any failure)."""
    try:
        ta_resp = httpx.get(
            f"{HARVEST_BASE}/projects/{project_id}/task_assignments",
            headers=_headers(access_token),
            params={"is_active": "true"},
            timeout=10,
        )
        if ta_resp.status_code != 200:
            return []
        return [
            {"task_id": ta["task"]["id"], "task_name": ta["task"]["name"]}
            for ta in ta_resp.json().get("task_assignments", [])
        ]
    except Exception:
        return []


def get_projects_with_tasks(access_token: str = None) -> List[Dict]:
    """Fetch all active projects with their task assignments from Harvest.
    Returns list of: {project_id, project_name, client_name, tasks: [{task_id, task_name}]}.

    Performance: the per-project task_assignments calls are run in parallel
    via a 10-thread pool. Drops cold-cache cost from ~7-10s (51 sequential
    requests) to ~0.5-1s. Capped at 10 workers to stay polite to Harvest's
    rate limit (100 req/15s per account)."""
    global _project_cache, _cache_time

    if _project_cache and (time.time() - _cache_time) < CACHE_TTL:
        return _project_cache

    try:
        resp = httpx.get(
            f"{HARVEST_BASE}/projects",
            headers=_headers(access_token),
            params={"is_active": "true"},
            timeout=10,
        )
        if resp.status_code != 200:
            print(f"Harvest projects error: {resp.status_code}")
            return _project_cache or []

        projects = resp.json().get("projects", [])

        # Parallel task_assignments fetch — preserves project ordering by
        # mapping futures back to the original project list.
        tasks_by_project: Dict[int, List[Dict]] = {}
        if projects:
            with ThreadPoolExecutor(max_workers=10) as pool:
                future_to_pid = {
                    pool.submit(_fetch_task_assignments, p["id"], access_token): p["id"]
                    for p in projects
                }
                for future in as_completed(future_to_pid):
                    pid = future_to_pid[future]
                    tasks_by_project[pid] = future.result()

        result = [
            {
                "project_id": p["id"],
                "project_name": p["name"],
                "client_name": p["client"]["name"] if p.get("client") else p["name"],
                "tasks": tasks_by_project.get(p["id"], []),
            }
            for p in projects
        ]

        _project_cache = result
        _cache_time = time.time()
        return result

    except Exception as e:
        print(f"Harvest get_projects error: {e}")
        return _project_cache or []


def resolve_ids(project_name: str, task_name: str, access_token: str = None) -> Optional[Dict]:
    """Resolve project/task names to Harvest IDs.
    Returns {project_id, task_id} or None if not found.
    """
    projects = get_projects_with_tasks(access_token)

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


def get_task_assignments(project_id: int, access_token: str = None) -> List[Dict]:
    """Fetch active task assignments for a specific project."""
    try:
        resp = httpx.get(
            f"{HARVEST_BASE}/projects/{project_id}/task_assignments",
            headers=_headers(access_token),
            params={"is_active": "true"},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json().get("task_assignments", [])
        return []
    except Exception as e:
        print(f"Harvest get_task_assignments error: {e}")
        return []


def find_task_in_project(project_id: int, task_name: str, access_token: str = None) -> Optional[int]:
    """Find a task ID by name within a project's task assignments."""
    assignments = get_task_assignments(project_id, access_token)
    task_name_lower = task_name.lower()

    # Exact match first
    for ta in assignments:
        if ta["task"]["name"].lower() == task_name_lower:
            return ta["task"]["id"]

    # Partial match: task name contained in search or vice versa
    for ta in assignments:
        harvest_name = ta["task"]["name"].lower()
        if harvest_name in task_name_lower or task_name_lower in harvest_name:
            return ta["task"]["id"]

    # Log available tasks for debugging
    available = [ta["task"]["name"] for ta in assignments]
    print(f"Harvest: task '{task_name}' not found in project {project_id}. Available: {available}")
    return None


def create_time_entry(
    project_id: int,
    task_id: int,
    spent_date: str,
    hours: float,
    notes: str = "",
    user_id: int = None,
    access_token: str = None,
    task_name: str = None,
) -> Optional[Dict]:
    """Create a time entry in Harvest.
    Returns the Harvest entry dict with id, or None on failure.
    If task_name is provided and the initial task_id fails, retries by looking up the correct task.
    """
    if not is_configured() and not access_token:
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
            headers=_headers(access_token),
            json=payload,
            timeout=10,
        )
        if resp.status_code in (200, 201):
            entry = resp.json()
            print(f"Harvest entry created: ID {entry['id']}")
            return entry

        # If 422 "Task isn't assigned" and we have a task name, try to find the correct task
        if resp.status_code == 422 and task_name:
            print(f"Harvest 422 for task_id={task_id}, searching by name '{task_name}'...")
            correct_task_id = find_task_in_project(project_id, task_name, access_token)
            if correct_task_id and correct_task_id != task_id:
                print(f"Harvest: retrying with correct task_id={correct_task_id}")
                payload["task_id"] = correct_task_id
                resp2 = httpx.post(
                    f"{HARVEST_BASE}/time_entries",
                    headers=_headers(access_token),
                    json=payload,
                    timeout=10,
                )
                if resp2.status_code in (200, 201):
                    entry = resp2.json()
                    print(f"Harvest entry created (retry): ID {entry['id']}")
                    return entry
                else:
                    print(f"Harvest retry error: {resp2.status_code} {resp2.text[:200]}")

        print(f"Harvest create error: {resp.status_code} {resp.text[:200]}")
        return None
    except Exception as e:
        print(f"Harvest create_time_entry error: {e}")
        return None


def delete_time_entry(harvest_id: int, access_token: str = None) -> bool:
    """Delete a time entry from Harvest."""
    if not is_configured() and not access_token:
        return False

    try:
        resp = httpx.delete(
            f"{HARVEST_BASE}/time_entries/{harvest_id}",
            headers=_headers(access_token),
            timeout=10,
        )
        return resp.status_code == 200
    except Exception as e:
        print(f"Harvest delete error: {e}")
        return False


def get_time_entries(spent_date: str = None, user_id: int = None, access_token: str = None) -> List[Dict]:
    """Get time entries from Harvest, optionally filtered."""
    if not is_configured() and not access_token:
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
            headers=_headers(access_token),
            params=params,
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json().get("time_entries", [])
        return []
    except Exception as e:
        print(f"Harvest get_time_entries error: {e}")
        return []


def reassign_time_entry(harvest_id: int, new_user_id: int, access_token: str = None) -> Optional[Dict]:
    """Reassign a time entry to a different user.
    Harvest doesn't allow PATCH on user_id, so we delete + recreate.
    Returns the new entry dict or None on failure.
    """
    if not is_configured() and not access_token:
        return None

    try:
        # Get the existing entry
        resp = httpx.get(
            f"{HARVEST_BASE}/time_entries/{harvest_id}",
            headers=_headers(access_token),
            timeout=10,
        )
        if resp.status_code != 200:
            print(f"Harvest: could not fetch entry {harvest_id}")
            return None

        old = resp.json()

        # Delete the old entry
        if not delete_time_entry(harvest_id, access_token):
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
            access_token=access_token,
        )
        if new_entry:
            print(f"Harvest: reassigned entry {harvest_id} -> {new_entry['id']} for user {new_user_id}")
        return new_entry
    except Exception as e:
        print(f"Harvest reassign error: {e}")
        return None


def push_entry(client_name: str, task_name: str, spent_date: str, hours: float, notes: str = "", user_id: int = None, access_token: str = None) -> Optional[Dict]:
    """High-level: resolve names to IDs and create a Harvest time entry.
    This is the main function called by the app.
    """
    if not is_configured() and not access_token:
        return None

    ids = resolve_ids(client_name, task_name, access_token)
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
        access_token=access_token,
    )
