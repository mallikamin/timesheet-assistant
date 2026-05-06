"""
Timezone-aware date helpers.

Why this module exists: the app runs on Render in UTC, but every user is in
AU (UTC+10/+11) or NZ (UTC+12/+13). `date.today()` therefore lies for the
user from late afternoon onward — when a Sydney user opens the app at 9am
local on Wednesday, UTC is still 22:00 Tuesday, and `date.today()` returns
Tuesday's date. Time entries got tagged with the wrong day.

Confirmed by Michael's 2026-05-06 session: he was on Wed AEST throughout but
the bot kept anchoring to "today is Tuesday 05/05" and writing entries
against the wrong date.

Public API:
    today_local(dialect)            -> datetime.date in the user's local tz
    now_local(dialect)              -> datetime.datetime in the user's local tz
    dialect_to_tz(dialect)          -> ZoneInfo for the dialect
    today_iso_local(dialect)        -> 'YYYY-MM-DD' in local tz

`dialect` is a BCP-47-style code as stored in user_profiles (e.g.
'en-AU-Sydney', 'en-NZ-Auckland'). Falls back to Australia/Sydney when
unrecognized so we never crash on a missing/garbled value.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

try:
    from zoneinfo import ZoneInfo  # py3.9+
except ImportError:  # pragma: no cover — fallback for older Pythons
    from backports.zoneinfo import ZoneInfo  # type: ignore[import-not-found]


_DEFAULT_TZ = "Australia/Sydney"

# Dialect → IANA timezone. Keep this list small and explicit; we'd rather
# fall back to AU than guess wrong for an unknown dialect.
_DIALECT_TZ = {
    "en-AU-Sydney": "Australia/Sydney",
    "en-AU-Melbourne": "Australia/Melbourne",
    "en-AU-Brisbane": "Australia/Brisbane",
    "en-AU-Perth": "Australia/Perth",
    "en-AU-Adelaide": "Australia/Adelaide",
    "en-NZ-Auckland": "Pacific/Auckland",
    "en-NZ-Wellington": "Pacific/Auckland",
}


def dialect_to_tz(dialect: Optional[str]) -> ZoneInfo:
    """Map a dialect string to a ZoneInfo. Falls back to AU/Sydney for any
    unknown value so callers never have to guard for None."""
    if not dialect:
        return ZoneInfo(_DEFAULT_TZ)
    tz_name = _DIALECT_TZ.get(dialect)
    if tz_name:
        return ZoneInfo(tz_name)
    # Try a soft prefix match — 'en-NZ' alone -> NZ tz.
    if dialect.startswith("en-NZ"):
        return ZoneInfo("Pacific/Auckland")
    if dialect.startswith("en-AU"):
        return ZoneInfo(_DEFAULT_TZ)
    return ZoneInfo(_DEFAULT_TZ)


def now_local(dialect: Optional[str] = None) -> datetime:
    """Current wall-clock datetime in the user's local timezone."""
    return datetime.now(dialect_to_tz(dialect))


def today_local(dialect: Optional[str] = None) -> date:
    """Today's calendar date in the user's local timezone.

    Use this everywhere instead of date.today(). On Render (UTC) at e.g.
    22:00 Tuesday UTC, date.today() returns Tuesday but the AU user is
    already on Wednesday morning local time — today_local('en-AU-Sydney')
    correctly returns Wednesday."""
    return now_local(dialect).date()


def today_iso_local(dialect: Optional[str] = None) -> str:
    """Today as YYYY-MM-DD in the user's local timezone."""
    return today_local(dialect).isoformat()
