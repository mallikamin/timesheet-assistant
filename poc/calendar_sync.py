"""
Google Calendar sync module.
Fetches calendar events using the user's OAuth token.
"""

import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import httpx

CALENDAR_API_BASE = "https://www.googleapis.com/calendar/v3"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"


def _get_day_bounds(target_date: str = None) -> Tuple[str, str]:
    """Get ISO format start/end of a given date (or today) in UTC."""
    if target_date:
        day = datetime.strptime(target_date, "%Y-%m-%d")
    else:
        day = datetime.now()
    start = day.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start.isoformat() + "Z", end.isoformat() + "Z"


def refresh_access_token(refresh_token: str) -> Optional[Dict]:
    """Use a refresh token to get a new access token from Google."""
    client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")

    if not refresh_token or not client_id:
        return None

    try:
        resp = httpx.post(
            TOKEN_ENDPOINT,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            timeout=10,
        )
    except httpx.HTTPError as e:
        print(f"Google token refresh network error: {e}")
        return None

    if resp.status_code != 200:
        print(f"Token refresh failed: {resp.status_code} {resp.text}")
        return None

    data = resp.json()
    return {
        "access_token": data["access_token"],
        "expires_at": time.time() + data.get("expires_in", 3600),
    }


def is_token_expired(google_token: Dict) -> bool:
    """Check if the access token is expired (with 60s buffer)."""
    expires_at = google_token.get("expires_at", 0)
    return time.time() > (expires_at - 60)


def ensure_valid_token(google_token: Dict) -> Optional[Dict]:
    """Return a valid token dict, refreshing if needed. Returns None if can't refresh."""
    if not is_token_expired(google_token):
        return google_token

    refresh_token = google_token.get("refresh_token", "")
    if not refresh_token:
        return None

    refreshed = refresh_access_token(refresh_token)
    if not refreshed:
        return None

    # Merge — keep the refresh_token, update access_token and expires_at
    return {
        "access_token": refreshed["access_token"],
        "refresh_token": refresh_token,
        "expires_at": refreshed["expires_at"],
    }


def get_events(access_token: str, target_date: str = None) -> List[Dict]:
    """Fetch calendar events for a given date (default: today)."""
    time_min, time_max = _get_day_bounds(target_date)

    resp = httpx.get(
        f"{CALENDAR_API_BASE}/calendars/primary/events",
        headers={"Authorization": f"Bearer {access_token}"},
        params={
            "timeMin": time_min,
            "timeMax": time_max,
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": 50,
        },
    )

    if resp.status_code != 200:
        print(f"Calendar API error: {resp.status_code} {resp.text}")
        return []

    raw_events = resp.json().get("items", [])
    events = []

    for ev in raw_events:
        # Skip all-day events (they have "date" instead of "dateTime")
        start_raw = ev.get("start", {})
        end_raw = ev.get("end", {})
        if "dateTime" not in start_raw:
            continue

        start_dt = datetime.fromisoformat(start_raw["dateTime"])
        end_dt = datetime.fromisoformat(end_raw["dateTime"])
        duration = (end_dt - start_dt).total_seconds() / 3600

        # Round to nearest 5 minutes (0.08 hours minimum)
        duration = max(round(duration * 12) / 12, 0.08)

        attendees = ev.get("attendees", [])
        attendee_names = [
            a.get("displayName", a.get("email", ""))
            for a in attendees
            if not a.get("self", False)
        ]

        events.append({
            "summary": ev.get("summary", "No title"),
            "start": start_dt.strftime("%H:%M"),
            "end": end_dt.strftime("%H:%M"),
            "duration_hours": round(duration, 2),
            "attendees": attendee_names,
            "location": ev.get("location", ""),
            "description": ev.get("description", ""),
        })

    return events


def format_events_for_prompt(events: List[Dict], target_date: str = None) -> str:
    """Format calendar events as text for the AI prompt."""
    if not events:
        return "No calendar events found for this date."

    date_label = target_date or datetime.now().strftime("%Y-%m-%d")
    lines = [f"Calendar events for {date_label}:"]

    for i, ev in enumerate(events, 1):
        line = f"{i}. {ev['start']}-{ev['end']} ({ev['duration_hours']}h): {ev['summary']}"
        if ev["attendees"]:
            line += f" [with: {', '.join(ev['attendees'][:5])}]"
        if ev["location"]:
            line += f" @ {ev['location']}"
        lines.append(line)

    return "\n".join(lines)


def search_events(
    access_token: str,
    date_from: str = None,
    date_to: str = None,
    include_declined: bool = False,
    drop_future: bool = True,
) -> List[Dict]:
    """Fetch calendar events for a date range (default: today only).
    Returns list of dicts with: id, summary, date, start, end, duration_hours,
    attendees (display names), attendee_emails, location, is_recurring,
    recurring_event_id, response_status, was_declined.

    Filters:
      - all-day events (no dateTime) are skipped
      - declined events are skipped unless include_declined=True
      - future events (after now) are skipped if drop_future=True
    """
    if date_from:
        start = datetime.strptime(date_from, "%Y-%m-%d")
    else:
        start = datetime.now()
    start = start.replace(hour=0, minute=0, second=0, microsecond=0)

    if date_to:
        # Include the end date by going to start of next day
        end = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
    else:
        end = start + timedelta(days=1)

    if drop_future:
        now = datetime.now()
        if end > now:
            end = now

    time_min = start.isoformat() + "Z"
    time_max = end.isoformat() + "Z"

    try:
        resp = httpx.get(
            f"{CALENDAR_API_BASE}/calendars/primary/events",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "timeMin": time_min,
                "timeMax": time_max,
                "singleEvents": "true",
                "orderBy": "startTime",
                "maxResults": 250,
            },
            timeout=15,
        )
    except httpx.TimeoutException:
        print("Calendar API timeout")
        return []

    if resp.status_code != 200:
        print(f"Calendar API error: {resp.status_code} {resp.text}")
        return []

    raw_events = resp.json().get("items", [])
    events = []

    for ev in raw_events:
        start_raw = ev.get("start", {})
        end_raw = ev.get("end", {})
        if "dateTime" not in start_raw:
            continue

        attendees_raw = ev.get("attendees", [])
        # Find self response status — declined events should usually be skipped
        self_status = None
        for a in attendees_raw:
            if a.get("self"):
                self_status = a.get("responseStatus")
                break
        was_declined = self_status == "declined"
        if was_declined and not include_declined:
            continue

        start_dt = datetime.fromisoformat(start_raw["dateTime"])
        end_dt = datetime.fromisoformat(end_raw["dateTime"])
        duration = (end_dt - start_dt).total_seconds() / 3600
        duration = max(round(duration * 12) / 12, 0.08)

        attendee_names = [
            a.get("displayName", a.get("email", ""))
            for a in attendees_raw
            if not a.get("self", False)
        ]
        attendee_emails = [
            a.get("email", "")
            for a in attendees_raw
            if not a.get("self", False) and a.get("email")
        ]

        events.append({
            "id": ev.get("id", ""),
            "summary": ev.get("summary", "No title"),
            "date": start_dt.strftime("%Y-%m-%d"),
            "start": start_dt.strftime("%H:%M"),
            "end": end_dt.strftime("%H:%M"),
            "duration_hours": round(duration, 2),
            "attendees": attendee_names,
            "attendee_emails": attendee_emails,
            "location": ev.get("location", ""),
            "is_recurring": bool(ev.get("recurringEventId")),
            "recurring_event_id": ev.get("recurringEventId", ""),
            "response_status": self_status or "unknown",
            "was_declined": was_declined,
        })

    return events


def format_search_results_for_tool(events: List[Dict]) -> str:
    """Format calendar search results for Claude tool_use response.
    Groups events by date. Truncates at 8000 chars."""
    if not events:
        return "No calendar events found for the specified date range."

    lines = [f"Found {len(events)} calendar events:"]
    current_date = None
    for ev in events:
        if ev.get("date") != current_date:
            current_date = ev.get("date")
            lines.append(f"\n--- {current_date} ---")
        line = f"  {ev['start']}-{ev['end']} ({ev['duration_hours']}h): {ev['summary']}"
        if ev["attendees"]:
            line += f" [with: {', '.join(ev['attendees'][:5])}]"
        if ev.get("location"):
            line += f" @ {ev['location']}"
        lines.append(line)

    result = "\n".join(lines)
    if len(result) > 8000:
        result = result[:8000] + "\n... (results truncated)"
    return result
