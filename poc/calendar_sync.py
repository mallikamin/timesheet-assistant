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

    resp = httpx.post(TOKEN_ENDPOINT, data={
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
    })

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
