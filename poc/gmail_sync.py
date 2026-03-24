"""
Gmail sync module.
Fetches recent email activity to suggest time entries.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional

import httpx

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


def get_recent_emails(access_token: str, target_date: str = None) -> List[Dict]:
    """Fetch sent and received emails for a given date (default: today).
    Returns list of dicts with: subject, from, to, timestamp, snippet, thread_id.
    """
    if target_date:
        day = datetime.strptime(target_date, "%Y-%m-%d")
    else:
        day = datetime.now()

    day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    # Gmail search syntax: after/before use YYYY/MM/DD
    query = f"after:{day_start.strftime('%Y/%m/%d')} before:{day_end.strftime('%Y/%m/%d')}"

    # Step 1: List message IDs
    resp = httpx.get(
        f"{GMAIL_API_BASE}/messages",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"q": query, "maxResults": 20},
        timeout=15,
    )

    if resp.status_code != 200:
        print(f"Gmail API error: {resp.status_code} {resp.text}")
        return []

    message_refs = resp.json().get("messages", [])
    if not message_refs:
        return []

    # Step 2: Fetch metadata for each message
    emails = []
    for msg_ref in message_refs:
        detail_resp = httpx.get(
            f"{GMAIL_API_BASE}/messages/{msg_ref['id']}",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "format": "metadata",
                "metadataHeaders": ["Subject", "From", "To", "Date"],
            },
            timeout=10,
        )
        if detail_resp.status_code != 200:
            continue

        msg_data = detail_resp.json()
        headers = {
            h["name"]: h["value"]
            for h in msg_data.get("payload", {}).get("headers", [])
        }

        # Parse timestamp
        date_str = headers.get("Date", "")
        time_str = ""
        if date_str:
            try:
                # Gmail Date header can have various formats
                for fmt in [
                    "%a, %d %b %Y %H:%M:%S %z",
                    "%d %b %Y %H:%M:%S %z",
                    "%a, %d %b %Y %H:%M:%S %Z",
                ]:
                    try:
                        dt = datetime.strptime(date_str.strip(), fmt)
                        time_str = dt.strftime("%H:%M")
                        break
                    except ValueError:
                        continue
            except Exception:
                pass

        emails.append({
            "subject": headers.get("Subject", "(no subject)"),
            "from": _clean_email_address(headers.get("From", "")),
            "to": _clean_email_address(headers.get("To", "")),
            "time": time_str,
            "snippet": msg_data.get("snippet", ""),
            "thread_id": msg_data.get("threadId", ""),
        })

    # Deduplicate by thread (keep first message per thread)
    seen_threads = set()
    unique_emails = []
    for email in emails:
        tid = email["thread_id"]
        if tid not in seen_threads:
            seen_threads.add(tid)
            unique_emails.append(email)

    return unique_emails


def _clean_email_address(raw: str) -> str:
    """Extract readable name/email from header like 'John Doe <john@example.com>'."""
    if not raw:
        return ""
    # If multiple recipients, just take first few
    parts = raw.split(",")
    cleaned = []
    for part in parts[:3]:
        part = part.strip()
        if "<" in part:
            name = part.split("<")[0].strip().strip('"')
            if name:
                cleaned.append(name)
            else:
                cleaned.append(part)
        else:
            cleaned.append(part)
    return ", ".join(cleaned)


def format_emails_for_prompt(emails: List[Dict], target_date: str = None) -> str:
    """Format email activity as text for the AI prompt."""
    if not emails:
        return "No email activity found for this date."

    date_label = target_date or datetime.now().strftime("%Y-%m-%d")
    lines = [f"Email activity for {date_label} ({len(emails)} threads):"]

    for i, email in enumerate(emails, 1):
        line = f"{i}. "
        if email["time"]:
            line += f"[{email['time']}] "
        line += f"Subject: {email['subject']}"
        if email["from"]:
            line += f" | From: {email['from']}"
        if email["to"]:
            line += f" | To: {email['to']}"
        if email["snippet"]:
            snippet = email["snippet"][:120].replace("\n", " ")
            line += f"\n   Preview: {snippet}"
        lines.append(line)

    return "\n".join(lines)
