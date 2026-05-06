"""
Harvest API v2 client.
Handles real Harvest time entry creation, retrieval, and deletion.
"""

import asyncio
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

# Per-user "today's entries" cache. Short TTL because the user is actively
# logging entries and we want the AI to see them within seconds. Keyed by
# (user_id, spent_date). Invalidated explicitly after an approve push.
_today_cache: Dict[str, Dict] = {}
_TODAY_CACHE_TTL = 30  # seconds


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


async def get_projects_with_tasks_async(access_token: str = None) -> List[Dict]:
    """Async version of get_projects_with_tasks.

    Fast path (when access_token present): single GET to
    /users/me/project_assignments. Returns the user's assigned projects
    WITH their tasks in one response. ~500ms cold-cache cost for 100+
    projects. This is the recommended path for OAuth-authenticated calls.

    Legacy fallback: GET /projects + N parallel
    /projects/{id}/task_assignments. Used when no access_token is
    available (server-side admin paths) or when the assignments endpoint
    fails. Concurrency capped at SEMAPHORE_LIMIT (15) to stay inside
    Harvest's 100-req/15s budget and avoid Cloudflare 429s — UAT
    2026-05-06 proved unbounded gather() trips the limit and silently
    empties the project list.

    Cache trade-off: cache is keyed globally, not per-user. For the
    Thrive PoC (small team, mostly overlapping project sets) this is
    fine; first user populates cache, subsequent users read it. For
    larger-scale production, key by access_token hash to avoid leaking
    user A's assignment list to user B."""
    global _project_cache, _cache_time

    if _project_cache and (time.time() - _cache_time) < CACHE_TTL:
        return _project_cache

    fetch_t0 = time.time()
    headers = _headers(access_token)
    SEMAPHORE_LIMIT = 15

    # Fast path: /users/me/project_assignments returns projects + tasks
    # in one shot. Only available when we have an OAuth token (the PAT
    # path also works but maps to whoever owns the PAT, which is usually
    # not what we want for Approve resolution).
    if access_token:
        try:
            async with httpx.AsyncClient(timeout=15, headers=headers) as client:
                resp = await client.get(
                    f"{HARVEST_BASE}/users/me/project_assignments",
                    params={"is_active": "true", "per_page": 200},
                )
            if resp.status_code == 200:
                assignments = resp.json().get("project_assignments", [])
                result = []
                for a in assignments:
                    proj = a.get("project") or {}
                    if not proj.get("id") or not proj.get("name"):
                        continue
                    result.append({
                        "project_id": proj["id"],
                        "project_name": proj["name"],
                        "client_name": (a.get("client") or {}).get("name") or proj["name"],
                        "tasks": [
                            {
                                "task_id": (ta.get("task") or {}).get("id"),
                                "task_name": (ta.get("task") or {}).get("name", ""),
                            }
                            for ta in (a.get("task_assignments") or [])
                            if (ta.get("task") or {}).get("id")
                        ],
                    })
                _project_cache = result
                _cache_time = time.time()
                total_ms = int((time.time() - fetch_t0) * 1000)
                print(
                    f"[harvest_api] fetched via /users/me/project_assignments: "
                    f"{len(result)} projects in {total_ms}ms (1 round-trip)"
                )
                return result
            print(
                f"[harvest_api] /users/me/project_assignments returned "
                f"{resp.status_code}, falling back to /projects + task_assignments"
            )
        except Exception as e:
            print(
                f"[harvest_api] /users/me/project_assignments error: {e}, "
                "falling back to /projects + task_assignments"
            )

    try:
        async with httpx.AsyncClient(timeout=15, headers=headers) as client:
            resp = await client.get(
                f"{HARVEST_BASE}/projects",
                params={"is_active": "true"},
            )
            if resp.status_code != 200:
                print(f"[harvest_api] projects list error {resp.status_code}")
                return _project_cache or []

            projects = resp.json().get("projects", [])
            list_ms = int((time.time() - fetch_t0) * 1000)

            sem = asyncio.Semaphore(SEMAPHORE_LIMIT)

            async def _fetch_one(pid: int) -> List[Dict]:
                async with sem:
                    try:
                        r = await client.get(
                            f"{HARVEST_BASE}/projects/{pid}/task_assignments",
                            params={"is_active": "true"},
                        )
                        if r.status_code == 429:
                            # Throttled — back off and retry once. The
                            # semaphore should normally prevent this, but
                            # Cloudflare's burst window is short.
                            await asyncio.sleep(2.0)
                            r = await client.get(
                                f"{HARVEST_BASE}/projects/{pid}/task_assignments",
                                params={"is_active": "true"},
                            )
                        if r.status_code != 200:
                            return []
                        return [
                            {"task_id": ta["task"]["id"], "task_name": ta["task"]["name"]}
                            for ta in r.json().get("task_assignments", [])
                        ]
                    except Exception:
                        return []

            ta_t0 = time.time()
            ta_lists = await asyncio.gather(
                *(_fetch_one(p["id"]) for p in projects),
                return_exceptions=False,
            )
            ta_ms = int((time.time() - ta_t0) * 1000)

        result = [
            {
                "project_id": p["id"],
                "project_name": p["name"],
                "client_name": p["client"]["name"] if p.get("client") else p["name"],
                "tasks": ta_lists[i],
            }
            for i, p in enumerate(projects)
        ]

        _project_cache = result
        _cache_time = time.time()
        total_ms = int((time.time() - fetch_t0) * 1000)
        print(
            f"[harvest_api] async fetch done: {len(result)} projects in "
            f"{total_ms}ms (list={list_ms}ms, task_assignments={ta_ms}ms "
            f"parallel, sem={SEMAPHORE_LIMIT})"
        )
        return result

    except Exception as e:
        print(f"[harvest_api] async fetch error: {e}")
        return _project_cache or []


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

    Fast path (with OAuth token): single GET /users/me/project_assignments.
    Legacy fallback: /projects + N parallel /projects/{id}/task_assignments
    via 10-thread pool. The async sibling get_projects_with_tasks_async
    has the same fast/legacy split — see its docstring for details."""
    global _project_cache, _cache_time

    if _project_cache and (time.time() - _cache_time) < CACHE_TTL:
        return _project_cache

    # Fast bail-out when no creds — without this, every caller eats a Harvest
    # 401 round-trip (~300-700ms) since the failure path doesn't update
    # _cache_time. Matters for /planning where 4+ reconciliation calls land
    # before the first one can populate the cache.
    if not is_configured() and not access_token:
        _project_cache = []
        _cache_time = time.time()
        return []

    # Fast path: /users/me/project_assignments returns projects + tasks in 1 call
    if access_token:
        try:
            resp = httpx.get(
                f"{HARVEST_BASE}/users/me/project_assignments",
                headers=_headers(access_token),
                params={"is_active": "true", "per_page": 200},
                timeout=15,
            )
            if resp.status_code == 200:
                assignments = resp.json().get("project_assignments", [])
                result = []
                for a in assignments:
                    proj = a.get("project") or {}
                    if not proj.get("id") or not proj.get("name"):
                        continue
                    result.append({
                        "project_id": proj["id"],
                        "project_name": proj["name"],
                        "client_name": (a.get("client") or {}).get("name") or proj["name"],
                        "tasks": [
                            {
                                "task_id": (ta.get("task") or {}).get("id"),
                                "task_name": (ta.get("task") or {}).get("name", ""),
                            }
                            for ta in (a.get("task_assignments") or [])
                            if (ta.get("task") or {}).get("id")
                        ],
                    })
                _project_cache = result
                _cache_time = time.time()
                return result
            print(
                f"[harvest_api] sync /users/me/project_assignments returned "
                f"{resp.status_code}, falling back to /projects"
            )
        except Exception as e:
            print(
                f"[harvest_api] sync /users/me/project_assignments error: {e}, "
                "falling back to /projects"
            )

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

    Match tiers (try in order, return first match):
      1. Exact project_name OR client_name match → exact task_name match
      2. Exact project_name OR client_name match → substring task_name match
      3. Substring project_name OR client_name match → exact task_name match
      4. Substring project_name OR client_name match → substring task_name match

    The substring tiers exist because the AI may generate canonical short
    names ("Thrive Leave") that map to FY-suffixed Harvest projects
    ("Thrive Leave FY26"), and similarly task names ("Annual Leave" vs the
    actual "Leave - Annual Leave"). Case-insensitive throughout.
    """
    out, _candidates = _resolve_with_candidates(project_name, task_name, access_token)
    return out


def _resolve_with_candidates(
    project_name: str, task_name: str, access_token: str = None
) -> tuple:
    """Internal: returns (resolution_or_None, candidates).

    `candidates` is a list of up to 5 (project_name, client_name, top_task_names)
    tuples for the closest projects we considered, used to build
    actionable error messages.

    Special sentinel: if the live Harvest project list comes back empty
    (API error / token issue / rate limit), we tag the candidate list with
    a __HARVEST_FETCH_EMPTY__ marker so the caller can show a different
    error than 'no name match'. Empty == we couldn't even check."""
    projects = get_projects_with_tasks(access_token)
    if not projects:
        print(
            "[harvest_api] resolve_ids: project list is EMPTY — "
            "live fetch failed or token has no project visibility. "
            f"Tried to resolve project={project_name!r} task={task_name!r}"
        )
        return None, [("__HARVEST_FETCH_EMPTY__", "", [])]
    pn = (project_name or "").strip().lower()
    tn = (task_name or "").strip().lower()
    if not pn:
        return None, []

    # Tier 1 + 2: exact project match
    exact_proj = [
        p for p in projects
        if p["project_name"].lower() == pn or p["client_name"].lower() == pn
    ]
    for p in exact_proj:
        for t in p["tasks"]:
            if t["task_name"].lower() == tn:
                return {"project_id": p["project_id"], "task_id": t["task_id"]}, []
    for p in exact_proj:
        for t in p["tasks"]:
            tname = t["task_name"].lower()
            if tn and (tn in tname or tname in tn):
                return {"project_id": p["project_id"], "task_id": t["task_id"]}, []

    # Tier 3 + 4: substring project match
    substr_proj = [
        p for p in projects
        if p not in exact_proj
        and (pn in p["project_name"].lower() or pn in p["client_name"].lower())
    ]
    for p in substr_proj:
        for t in p["tasks"]:
            if t["task_name"].lower() == tn:
                return {"project_id": p["project_id"], "task_id": t["task_id"]}, []
    for p in substr_proj:
        for t in p["tasks"]:
            tname = t["task_name"].lower()
            if tn and (tn in tname or tname in tn):
                return {"project_id": p["project_id"], "task_id": t["task_id"]}, []

    # No match — build candidate list for actionable error message
    candidate_pool = exact_proj + substr_proj
    if not candidate_pool:
        # Last resort: substring on project_name only, looser
        candidate_pool = [
            p for p in projects
            if any(word in p["project_name"].lower() for word in pn.split() if len(word) > 2)
        ][:5]
    candidates = [
        (
            p["project_name"],
            p["client_name"],
            [t["task_name"] for t in p["tasks"][:5]],
        )
        for p in candidate_pool[:5]
    ]
    return None, candidates


def resolve_ids_with_diagnostics(
    project_name: str, task_name: str, access_token: str = None
) -> Dict:
    """Like resolve_ids but always returns a dict with diagnostics.

    On success: {"resolved": {project_id, task_id}, "candidates": []}
    On failure: {"resolved": None, "candidates": [...]} where candidates
    is up to 5 (project_name, client_name, top_task_names) tuples for the
    closest projects we considered."""
    resolved, candidates = _resolve_with_candidates(project_name, task_name, access_token)
    return {"resolved": resolved, "candidates": candidates}


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

    Returns the Harvest entry dict with id, or None on failure. Existing
    callers expect Optional[Dict] — for callers that need the actual
    Harvest error reason (status code + body), use
    create_time_entry_with_diag() instead.

    If task_name is provided and the initial task_id fails with 422
    ('Task isn't assigned'), retries by looking up the correct task."""
    entry, _err = create_time_entry_with_diag(
        project_id=project_id,
        task_id=task_id,
        spent_date=spent_date,
        hours=hours,
        notes=notes,
        user_id=user_id,
        access_token=access_token,
        task_name=task_name,
    )
    return entry


def create_time_entry_with_diag(
    project_id: int,
    task_id: int,
    spent_date: str,
    hours: float,
    notes: str = "",
    user_id: int = None,
    access_token: str = None,
    task_name: str = None,
) -> tuple:
    """Like create_time_entry but returns (entry, error) where error is
    None on success or a dict with {status, body, hint} on failure.

    `hint` translates Harvest's status codes into actionable advice for
    the user (e.g. 422 + 'task' in body → 'task not assigned to this
    project for your user — ask an admin to add you to the project team
    in Harvest'). Used by the Approve flow to surface the real reason
    instead of the misleading 'could not resolve project' fallback."""
    if not is_configured() and not access_token:
        return None, {"status": None, "body": "no Harvest credentials available", "hint": "session not authenticated with Harvest"}

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
            return entry, None

        # 429 — Cloudflare/Harvest rate limit. Sleep + retry once. The
        # semaphore in the project-list fetcher mitigates burst load, but
        # an Approve right after a cold prewarm can still trip the budget.
        if resp.status_code == 429:
            print(f"Harvest 429 on create_time_entry — sleeping 3s and retrying once")
            time.sleep(3.0)
            resp = httpx.post(
                f"{HARVEST_BASE}/time_entries",
                headers=_headers(access_token),
                json=payload,
                timeout=10,
            )
            if resp.status_code in (200, 201):
                entry = resp.json()
                print(f"Harvest entry created (after 429 backoff): ID {entry['id']}")
                return entry, None

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
                    return entry, None
                resp = resp2  # surface the retry error if it still failed

        body_text = (resp.text or "")[:500]
        print(f"Harvest create error: {resp.status_code} {body_text}")
        return None, {
            "status": resp.status_code,
            "body": body_text,
            "hint": _harvest_create_error_hint(resp.status_code, body_text),
        }
    except httpx.TimeoutException:
        print("Harvest create_time_entry timeout")
        return None, {"status": None, "body": "timeout after 10s", "hint": "Harvest API didn't respond in 10s — try again, or check Harvest status page"}
    except Exception as e:
        print(f"Harvest create_time_entry error: {e}")
        return None, {"status": None, "body": repr(e), "hint": "unexpected error reaching Harvest API"}


def _harvest_create_error_hint(status: int, body: str) -> str:
    """Translate a Harvest API rejection into actionable user-facing text."""
    body_lower = (body or "").lower()
    if status == 401:
        return "Harvest token is not authorised — Sign Out → Sign In with Harvest"
    if status == 403:
        return "Harvest says you don't have permission for this project — ask the Harvest admin to add you to the project team"
    if status == 404:
        return "project or task ID doesn't exist in Harvest (catalog may be stale — refresh data/harvest_master/ exports)"
    if status == 422:
        if "task" in body_lower and ("assign" in body_lower or "not been assigned" in body_lower):
            return "the task isn't assigned to this project for your Harvest user — ask the Harvest admin to add you to the project team"
        if "project" in body_lower and "archived" in body_lower:
            return "this project is archived in Harvest — pick an active project"
        return "Harvest validation rejected the entry — check the response body for the field name"
    if status == 429:
        return "Harvest rate limit hit — wait a minute and retry"
    if status and 500 <= status < 600:
        return "Harvest API is having issues right now — retry in a minute"
    return "unexpected Harvest response — check Render logs for the full body"


def patch_time_entry(
    harvest_id: int,
    hours: Optional[float] = None,
    notes: Optional[str] = None,
    spent_date: Optional[str] = None,
    access_token: str = None,
) -> Optional[Dict]:
    """PATCH a time entry's hours, notes, or spent_date in place.

    Project/task changes are NOT supported here (use delete_time_entry + a
    fresh create_time_entry for that — Harvest's PATCH semantics around
    project_id/task_id can silently no-op when the new task isn't assigned
    to the user, which we already handle in create_time_entry's retry).

    Returns the updated entry dict or None on failure.
    """
    if not is_configured() and not access_token:
        return None

    payload: Dict = {}
    if hours is not None:
        payload["hours"] = hours
    if notes is not None:
        payload["notes"] = notes
    if spent_date is not None:
        payload["spent_date"] = spent_date
    if not payload:
        return None  # no-op; treat as failure so caller can show "nothing changed"

    try:
        resp = httpx.patch(
            f"{HARVEST_BASE}/time_entries/{harvest_id}",
            headers=_headers(access_token),
            json=payload,
            timeout=10,
        )
        if resp.status_code in (200, 201):
            return resp.json()
        print(f"Harvest patch error: {resp.status_code} {resp.text[:200]}")
        return None
    except Exception as e:
        print(f"Harvest patch_time_entry error: {e}")
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


def _today_iso() -> str:
    """UTC today fallback. Callers SHOULD pass an explicit spent_date in the
    user's local timezone — this is only a last-ditch default. Sweep for any
    leftover callsites: the helper exists for backward compatibility but is
    timezone-naive (anchored on the server's UTC) and will be off by one day
    for AU/NZ users in their evening."""
    from datetime import date as _date
    return _date.today().isoformat()


def get_today_entries_cached(user_id: int, access_token: str, spent_date: Optional[str] = None) -> List[Dict]:
    """Return today's Harvest time entries for one user, cached for ~30s.

    Short TTL because the user is actively logging — we want the next chat
    message to see the entry they just approved. invalidate_today_cache()
    is called by the approve handler so the AI never gives stale 'already
    logged' advice."""
    if not user_id:
        return []
    spent_date = spent_date or _today_iso()
    key = f"{user_id}:{spent_date}"
    entry = _today_cache.get(key)
    if entry and (time.time() - entry["ts"]) < _TODAY_CACHE_TTL:
        return entry["entries"]

    fetched = get_time_entries(spent_date=spent_date, user_id=user_id, access_token=access_token)
    _today_cache[key] = {"ts": time.time(), "entries": fetched}
    return fetched


def invalidate_today_cache(user_id: int, spent_date: Optional[str] = None) -> None:
    """Bust the today-entries cache after a write so the next chat sees fresh
    state. Called from /api/entries/{id}/approve and approve-all."""
    if not user_id:
        return
    spent_date = spent_date or _today_iso()
    _today_cache.pop(f"{user_id}:{spent_date}", None)


def format_today_summary(entries: List[Dict]) -> str:
    """Render today's entries as a compact, AI-readable summary. Empty string
    when there are no entries — caller can skip injection so we don't waste
    tokens on 'you haven't logged anything yet' (the AI already knows that)."""
    if not entries:
        return ""
    lines: List[str] = []
    total_hours = 0.0
    for e in entries:
        hrs = float(e.get("hours") or 0)
        total_hours += hrs
        client = (e.get("client") or {}).get("name") or e.get("client_name") or "?"
        project = (e.get("project") or {}).get("name") or e.get("project_name") or "?"
        task = (e.get("task") or {}).get("name") or e.get("task_name") or "?"
        notes = (e.get("notes") or "").strip()
        notes_preview = f' — "{notes[:60]}"' if notes else ""
        lines.append(f"- {project} / {task} — {hrs}h{notes_preview}")
    summary = (
        "ALREADY LOGGED IN HARVEST FOR TODAY (do NOT re-suggest these as new entries; "
        "if the user describes work that matches one of these, ask if it's an addition "
        f"to the existing entry or a separate block):\n" + "\n".join(lines) +
        f"\nTotal so far today: {total_hours:.2f}h"
    )
    return summary


def get_time_entries_range(
    from_date: str,
    to_date: str,
    project_id: Optional[int] = None,
    user_id: Optional[int] = None,
    access_token: str = None,
) -> List[Dict]:
    """Get all time entries in a [from_date, to_date] range, paginating through
    Harvest's 100/page limit. Used by the Planning module's reconciliation view.
    """
    if not is_configured() and not access_token:
        return []
    out: List[Dict] = []
    page = 1
    try:
        while True:
            params = {"from": from_date, "to": to_date, "per_page": 100, "page": page}
            if project_id:
                params["project_id"] = project_id
            if user_id:
                params["user_id"] = user_id
            resp = httpx.get(
                f"{HARVEST_BASE}/time_entries",
                headers=_headers(access_token),
                params=params,
                timeout=15,
            )
            if resp.status_code != 200:
                break
            payload = resp.json()
            out.extend(payload.get("time_entries", []))
            if not payload.get("next_page"):
                break
            page = payload["next_page"]
        return out
    except Exception as e:
        print(f"Harvest get_time_entries_range error: {e}")
        return out


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
