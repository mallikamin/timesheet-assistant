"""
Per-user profile store for the Timesheet Assistant.

Backs prompt personalization for the AI: each user has assigned projects, dialect
hints, common-task patterns, name aliases, and a learning trail (recent entries +
corrections). The system prompt stays cache-friendly because the *master catalog*
of all 51 Harvest projects is shared/cached for everyone, and only this small
per-user slice is appended uncached to each chat.

Storage backend: JSON file (`poc/user_profiles.json`) for the POC + 3-user
stress test. Schema is intentionally one-row-per-user with jsonb-friendly fields
so migration to Postgres on the upcoming VPS is a near-direct copy.

Postgres migration target (run on VPS):

    CREATE TABLE user_profiles (
        email                    TEXT PRIMARY KEY,
        display_name             TEXT,
        harvest_user_id          INTEGER,
        assigned_project_codes   JSONB DEFAULT '[]',
        common_tasks             JSONB DEFAULT '[]',
        dialect                  TEXT DEFAULT 'en-AU-Sydney',
        vocabulary_hints         JSONB DEFAULT '[]',
        name_aliases             JSONB DEFAULT '{}',
        preferred_response_style TEXT DEFAULT 'terse',
        recent_entries_summary   JSONB DEFAULT '[]',
        recent_corrections       JSONB DEFAULT '[]',
        updated_at               TIMESTAMPTZ DEFAULT NOW()
    );
    -- RLS: USING (email = auth.jwt() ->> 'email')

To migrate: `python -c "import user_profiles; user_profiles.export_for_postgres()"`
emits a SQL INSERT script, then swap the `_load`/`_save` internals for asyncpg.
The public functions below (get_profile / update_profile / record_*) keep the
same signatures, so callers don't change.
"""

import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

_PROFILES_PATH = Path(__file__).resolve().parent / "user_profiles.json"
_lock = threading.Lock()

# Defaults applied to a new profile. Order matches the Postgres DDL above so a
# row dump and a CREATE TABLE column list line up 1:1.
_DEFAULT_PROFILE: Dict[str, Any] = {
    "email": "",
    "display_name": "",
    "harvest_user_id": None,
    "assigned_project_codes": [],   # ["38887238", "38887240", ...] — Harvest project IDs as strings
    "common_tasks": [],             # [{project_code, task_code, frequency, last_used}]
    "dialect": "en-AU-Sydney",      # BCP-47 + city. en-NZ-Auckland for Kiwi users.
    "vocabulary_hints": [],         # extra slang beyond the global AU/NZ list
    "name_aliases": {},             # {"Mike": "Michael Chen"} — spoken form -> canonical
    "preferred_response_style": "terse",  # "terse" | "verbose"
    "recent_entries_summary": [],   # last 5 approved entries — pattern seed for Claude
    "recent_corrections": [],       # last 10 user corrections — anti-repeat hints
    "updated_at": None,
}

_RECENT_ENTRIES_CAP = 5
_RECENT_CORRECTIONS_CAP = 10
_COMMON_TASKS_CAP = 8


def _load() -> Dict[str, Dict[str, Any]]:
    """Load all profiles from disk. Returns {} if file missing/corrupt."""
    if not _PROFILES_PATH.exists():
        return {}
    try:
        with _PROFILES_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        return data
    except (json.JSONDecodeError, OSError) as e:
        print(f"[WARN] user_profiles.json unreadable, treating as empty: {e}")
        return {}


def _save(profiles: Dict[str, Dict[str, Any]]) -> None:
    """Atomic write: write to .tmp then rename. Avoids torn files on crash."""
    tmp = _PROFILES_PATH.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(profiles, f, indent=2, sort_keys=True)
    os.replace(tmp, _PROFILES_PATH)


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def get_profile(email: str) -> Dict[str, Any]:
    """Return the user's profile, creating an empty one on first call.

    Opportunistically merges a hand-seeded placeholder profile (matching by
    first-name + org) if one exists — covers the case where the placeholder
    `miles@thrivepr.com.au` was seeded but the real email is
    `miles.alexander@thrivepr.com.au`. Once merged the placeholder is removed
    so the merge is one-shot."""
    key = _normalize_email(email)
    if not key:
        return dict(_DEFAULT_PROFILE)

    with _lock:
        profiles = _load()
        created = False
        if key not in profiles:
            new = dict(_DEFAULT_PROFILE)
            new["email"] = key
            new["updated_at"] = datetime.utcnow().isoformat() + "Z"
            profiles[key] = new
            created = True
        # Backfill any missing keys for older saved profiles
        for k, v in _DEFAULT_PROFILE.items():
            profiles[key].setdefault(k, v if not isinstance(v, (list, dict)) else type(v)())
        # Try to merge a placeholder. _claim_placeholder_into is a no-op if
        # there's no matching placeholder, so the cost is one dict scan.
        merged = _claim_placeholder_into(profiles, key)
        if created or merged:
            _save(profiles)
        return dict(profiles[key])


def update_profile(email: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    """Shallow-merge `patch` into the user's profile. Returns the updated profile."""
    key = _normalize_email(email)
    if not key:
        return dict(_DEFAULT_PROFILE)

    with _lock:
        profiles = _load()
        existing = profiles.get(key) or dict(_DEFAULT_PROFILE)
        existing["email"] = key
        for k, v in patch.items():
            if k in _DEFAULT_PROFILE:
                existing[k] = v
        existing["updated_at"] = datetime.utcnow().isoformat() + "Z"
        profiles[key] = existing
        _save(profiles)
        return dict(existing)


def _org_prefix(email: str) -> str:
    """Pull the 'org' part of an email domain so cross-tld Thrive emails match.
    'miles@thrivepr.com.au'    -> 'thrivepr'
    'hugh@thrivepr.co.nz'      -> 'thrivepr'
    'tariq@thrive.com'         -> 'thrive'
    """
    if "@" not in email:
        return ""
    domain = email.split("@", 1)[1].lower()
    return domain.split(".", 1)[0]


def _first_name(email: str) -> str:
    """Extract the first-name segment of an email local-part.
    'miles.alexander@x' -> 'miles'; 'miles@x' -> 'miles'."""
    if "@" not in email:
        return ""
    local = email.split("@", 1)[0].lower()
    return local.split(".", 1)[0]


# Fields the placeholder profile owns that the real profile should inherit on
# merge. assigned_project_codes / common_tasks / harvest_user_id are NOT on
# this list — those come from Harvest, not from a hand-seeded placeholder.
_PLACEHOLDER_INHERIT_FIELDS = (
    "dialect",
    "vocabulary_hints",
    "name_aliases",
    "preferred_response_style",
    "display_name",
)


def _claim_placeholder_into(profiles: Dict[str, Dict[str, Any]], real_email: str) -> bool:
    """If a hand-seeded placeholder profile exists for the same first-name +
    org as `real_email`, copy its dialect/vocab/aliases into the real profile
    and remove the placeholder.

    This is the fix for the "Miles ran on default vocab" bug — the JSON had
    `miles@thrivepr.com.au` but the real OAuth email is
    `miles.alexander@thrivepr.com.au`, so the lookup silently fell through.

    Idempotent: once the placeholder is gone, calling this again is a no-op.
    Returns True if a merge happened (caller should persist), False otherwise.
    """
    real_key = _normalize_email(real_email)
    if real_key not in profiles:
        return False
    fname = _first_name(real_key)
    org = _org_prefix(real_key)
    if not fname or not org:
        return False

    candidates: List[str] = []
    for k in list(profiles.keys()):
        if k == real_key:
            continue
        if _first_name(k) == fname and _org_prefix(k) == org:
            candidates.append(k)
    # If multiple candidates (ambiguous), don't merge — safer to leave defaults
    # than to inherit the wrong dialect.
    if len(candidates) != 1:
        return False

    placeholder = profiles[candidates[0]]
    real = profiles[real_key]
    merged = False
    for field in _PLACEHOLDER_INHERIT_FIELDS:
        ph_val = placeholder.get(field)
        real_val = real.get(field)
        empty_real = (
            real_val in (None, "", [], {})
            or (field == "dialect" and real_val == _DEFAULT_PROFILE["dialect"])
            or (field == "preferred_response_style" and real_val == _DEFAULT_PROFILE["preferred_response_style"])
        )
        if ph_val and empty_real:
            real[field] = ph_val
            merged = True

    if merged:
        # Mark provenance — useful for analytics + lets us see which profiles
        # were seeded vs. fully Harvest-bootstrapped.
        real["claimed_from_placeholder"] = candidates[0]
        real["updated_at"] = datetime.utcnow().isoformat() + "Z"

    # Always remove the placeholder once a real profile exists for the user —
    # leaving it around means the next user who happens to share a first-name
    # would also try to claim it.
    profiles.pop(candidates[0], None)
    return True


def bootstrap_from_harvest(
    email: str,
    display_name: str,
    harvest_user_id: Optional[int],
    assigned_project_codes: List[str],
) -> Dict[str, Any]:
    """Called from the Harvest OAuth callback after we know who the user is and
    which projects they're assigned. Idempotent — only fills empty fields so we
    don't clobber Malik's hand-tuned dialect overrides.

    Also merges any hand-seeded placeholder profile for this user (e.g. the
    `miles@thrivepr.com.au` placeholder when the real email is
    `miles.alexander@thrivepr.com.au`) so the dialect / vocab / aliases that
    were seeded for the stress test actually reach the user."""
    # Make sure a row exists, then run the placeholder-merge before applying
    # the Harvest-derived patch — that way the patch wins over placeholder
    # values for fields it sets (assigned_project_codes, harvest_user_id),
    # but the placeholder's dialect/vocab survive.
    get_profile(email)  # ensures row exists
    with _lock:
        profiles = _load()
        if _claim_placeholder_into(profiles, email):
            _save(profiles)

    profile = get_profile(email)
    patch: Dict[str, Any] = {}
    if not profile.get("display_name"):
        patch["display_name"] = display_name
    if not profile.get("harvest_user_id") and harvest_user_id:
        patch["harvest_user_id"] = harvest_user_id
    # Always refresh project assignments — they can change in Harvest
    if assigned_project_codes:
        patch["assigned_project_codes"] = assigned_project_codes
    if patch:
        return update_profile(email, patch)
    return profile


def record_approval(email: str, entry: Dict[str, Any]) -> None:
    """A draft was approved → bump task frequency + remember it as a recent entry.
    `entry` is the harvest_mock entry dict (has client, project_code, project_name,
    hours, notes, date)."""
    key = _normalize_email(email)
    if not key:
        return

    with _lock:
        profiles = _load()
        if key not in profiles:
            return  # don't create a profile just from an approval; bootstrap path owns creation
        prof = profiles[key]

        project_code = entry.get("project_code", "")
        task_name = entry.get("project_name") or entry.get("task", "")

        # 1. Update common_tasks frequency
        common = prof.get("common_tasks", [])
        found = False
        for ct in common:
            if ct.get("project_code") == project_code and ct.get("task_name") == task_name:
                ct["frequency"] = ct.get("frequency", 0) + 1
                ct["last_used"] = datetime.utcnow().isoformat() + "Z"
                found = True
                break
        if not found and project_code and task_name:
            common.append({
                "project_code": project_code,
                "task_name": task_name,
                "client": entry.get("client", ""),
                "frequency": 1,
                "last_used": datetime.utcnow().isoformat() + "Z",
            })
        common.sort(key=lambda c: c.get("frequency", 0), reverse=True)
        prof["common_tasks"] = common[:_COMMON_TASKS_CAP]

        # 2. Prepend to recent_entries_summary (cap N)
        recent = prof.get("recent_entries_summary", [])
        recent.insert(0, {
            "date": entry.get("date", ""),
            "client": entry.get("client", ""),
            "task_name": task_name,
            "hours": entry.get("hours", 0),
            "notes_excerpt": (entry.get("notes", "") or "")[:80],
        })
        prof["recent_entries_summary"] = recent[:_RECENT_ENTRIES_CAP]

        prof["updated_at"] = datetime.utcnow().isoformat() + "Z"
        profiles[key] = prof
        _save(profiles)


def record_correction(
    email: str,
    user_phrase: str,
    original: Dict[str, Any],
    corrected: Dict[str, Any],
) -> None:
    """A user fixed the AI's categorization (e.g. changed client from 'Reddit' to
    'OpenAI' before approving). Append to recent_corrections so the next prompt
    can warn Claude not to repeat this miss."""
    key = _normalize_email(email)
    if not key:
        return

    with _lock:
        profiles = _load()
        if key not in profiles:
            return
        prof = profiles[key]
        corrections = prof.get("recent_corrections", [])
        corrections.insert(0, {
            "ts": datetime.utcnow().isoformat() + "Z",
            "user_phrase": (user_phrase or "")[:200],
            "original": {
                "client": original.get("client", ""),
                "task_name": original.get("project_name") or original.get("task", ""),
            },
            "corrected": {
                "client": corrected.get("client", ""),
                "task_name": corrected.get("project_name") or corrected.get("task", ""),
            },
        })
        prof["recent_corrections"] = corrections[:_RECENT_CORRECTIONS_CAP]
        prof["updated_at"] = datetime.utcnow().isoformat() + "Z"
        profiles[key] = prof
        _save(profiles)


def render_profile_block(email: str) -> str:
    """Format the profile as a compact text block to append to the system prompt
    (uncached portion). Returns empty string if no useful data — caller can skip
    the block entirely so we don't waste tokens on empty profiles."""
    profile = get_profile(email)
    if not profile.get("email"):
        return ""

    lines = ["--- USER PROFILE ---"]
    name = profile.get("display_name") or profile.get("email")
    dialect = profile.get("dialect") or "en-AU-Sydney"
    style = profile.get("preferred_response_style") or "terse"
    lines.append(f"User: {name} ({profile['email']})")
    lines.append(f"Dialect: {dialect}  |  Response style: {style}")

    assigned = profile.get("assigned_project_codes") or []
    if assigned:
        lines.append(
            f"Assigned Harvest projects (prefer these when ambiguous, "
            f"{len(assigned)} codes): {', '.join(assigned)}"
        )

    common = profile.get("common_tasks") or []
    if common:
        lines.append("Top tasks (last 30d):")
        for ct in common[:5]:
            lines.append(
                f"  - [{ct.get('project_code','')}] "
                f"{ct.get('client','')} / {ct.get('task_name','')} "
                f"(x{ct.get('frequency',0)})"
            )

    vocab = profile.get("vocabulary_hints") or []
    if vocab:
        lines.append(f"Extra vocab/slang for this user: {', '.join(vocab)}")

    aliases = profile.get("name_aliases") or {}
    if aliases:
        alias_str = ", ".join(f'"{k}"->"{v}"' for k, v in aliases.items())
        lines.append(f"Name aliases this user uses: {alias_str}")

    recent_entries = profile.get("recent_entries_summary") or []
    if recent_entries:
        lines.append("Recent entries (pattern seed):")
        for e in recent_entries[:3]:
            lines.append(
                f"  - {e.get('date','')}: {e.get('client','')} / "
                f"{e.get('task_name','')} ({e.get('hours',0)}h) — "
                f"{e.get('notes_excerpt','')}"
            )

    corrections = profile.get("recent_corrections") or []
    if corrections:
        lines.append("RECENT CORRECTIONS — DO NOT REPEAT THESE MISCLASSIFICATIONS:")
        for c in corrections[:5]:
            lines.append(
                f"  - When user said \"{c.get('user_phrase','')}\": "
                f"do NOT pick {c.get('original',{}).get('client','?')} / "
                f"{c.get('original',{}).get('task_name','?')}; "
                f"correct = {c.get('corrected',{}).get('client','?')} / "
                f"{c.get('corrected',{}).get('task_name','?')}"
            )

    return "\n".join(lines)


def export_for_postgres(out_path: Optional[str] = None) -> str:
    """Generate a SQL INSERT script for migrating the JSON store to Postgres on
    the upcoming VPS. Returns the SQL as a string and (if out_path given) writes
    it to disk."""
    profiles = _load()
    sql_parts = [
        "-- Generated by user_profiles.export_for_postgres()",
        "-- Run after CREATE TABLE user_profiles (see file docstring).",
        "BEGIN;",
    ]
    for email, p in profiles.items():
        cols = [
            "email", "display_name", "harvest_user_id", "assigned_project_codes",
            "common_tasks", "dialect", "vocabulary_hints", "name_aliases",
            "preferred_response_style", "recent_entries_summary",
            "recent_corrections", "updated_at",
        ]
        vals = [
            _sql_str(email),
            _sql_str(p.get("display_name", "")),
            "NULL" if p.get("harvest_user_id") is None else str(p["harvest_user_id"]),
            _sql_jsonb(p.get("assigned_project_codes", [])),
            _sql_jsonb(p.get("common_tasks", [])),
            _sql_str(p.get("dialect", "en-AU-Sydney")),
            _sql_jsonb(p.get("vocabulary_hints", [])),
            _sql_jsonb(p.get("name_aliases", {})),
            _sql_str(p.get("preferred_response_style", "terse")),
            _sql_jsonb(p.get("recent_entries_summary", [])),
            _sql_jsonb(p.get("recent_corrections", [])),
            _sql_str(p.get("updated_at") or datetime.utcnow().isoformat() + "Z"),
        ]
        sql_parts.append(
            f"INSERT INTO user_profiles ({', '.join(cols)}) VALUES "
            f"({', '.join(vals)}) ON CONFLICT (email) DO NOTHING;"
        )
    sql_parts.append("COMMIT;")
    sql = "\n".join(sql_parts)
    if out_path:
        Path(out_path).write_text(sql, encoding="utf-8")
    return sql


def _sql_str(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def _sql_jsonb(obj: Any) -> str:
    return _sql_str(json.dumps(obj)) + "::jsonb"
