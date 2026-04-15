"""
Gmail sync module.
Fetches recent email activity to suggest time entries.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional

import httpx

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


class TokenExpiredError(Exception):
    """Raised when the Google OAuth token has expired."""
    pass


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


def search_emails(
    access_token: str,
    date_from: str = None,
    date_to: str = None,
    sender: str = None,
    recipient: str = None,
    cc: str = None,
    subject: str = None,
    keyword: str = None,
    max_results: int = 30,
) -> List[Dict]:
    """Advanced email search with filtering by date range, sender, recipient, CC, subject, keyword.

    Uses Gmail API metadata-only format (Australian legal compliance — no email body).
    Returns list of dicts with: subject, from, to, cc, time, date, snippet, thread_id.
    """
    # Build Gmail search query
    query_parts = []
    if date_from:
        query_parts.append(f"after:{date_from.replace('-', '/')}")
    if date_to:
        # Gmail 'before' is exclusive, add 1 day to include the end date
        try:
            end = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            query_parts.append(f"before:{end.strftime('%Y/%m/%d')}")
        except ValueError:
            query_parts.append(f"before:{date_to.replace('-', '/')}")
    elif date_from and not date_to:
        # date_from with no date_to: search from that date to now
        pass

    if not date_from and not date_to:
        # Default to today
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)
        query_parts.append(f"after:{today.strftime('%Y/%m/%d')}")
        query_parts.append(f"before:{tomorrow.strftime('%Y/%m/%d')}")

    if sender:
        query_parts.append(f"from:{sender}")
    if recipient:
        query_parts.append(f"to:{recipient}")
    if cc:
        query_parts.append(f"cc:{cc}")
    if subject:
        query_parts.append(f"subject:{subject}")
    if keyword:
        query_parts.append(keyword)

    query = " ".join(query_parts)
    max_results = min(max(max_results, 1), 100)

    # Step 1: List message IDs
    try:
        resp = httpx.get(
            f"{GMAIL_API_BASE}/messages",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"q": query, "maxResults": max_results},
            timeout=15,
        )
    except httpx.TimeoutException:
        print("Gmail API timeout on message list")
        return []

    if resp.status_code == 401:
        raise TokenExpiredError("Gmail access token expired")
    if resp.status_code == 429:
        print("Gmail API rate limit hit")
        return []
    if resp.status_code != 200:
        print(f"Gmail API error: {resp.status_code} {resp.text}")
        return []

    message_refs = resp.json().get("messages", [])
    if not message_refs:
        return []

    # Step 2: Fetch metadata for each message (metadata only — no body content)
    emails = []
    for msg_ref in message_refs:
        try:
            detail_resp = httpx.get(
                f"{GMAIL_API_BASE}/messages/{msg_ref['id']}",
                headers={"Authorization": f"Bearer {access_token}"},
                params={
                    "format": "metadata",
                    "metadataHeaders": ["Subject", "From", "To", "Cc", "Date"],
                },
                timeout=10,
            )
        except httpx.TimeoutException:
            continue

        if detail_resp.status_code == 401:
            raise TokenExpiredError("Gmail access token expired")
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
        date_val = ""
        if date_str:
            try:
                for fmt in [
                    "%a, %d %b %Y %H:%M:%S %z",
                    "%d %b %Y %H:%M:%S %z",
                    "%a, %d %b %Y %H:%M:%S %Z",
                ]:
                    try:
                        dt = datetime.strptime(date_str.strip(), fmt)
                        time_str = dt.strftime("%H:%M")
                        date_val = dt.strftime("%Y-%m-%d")
                        break
                    except ValueError:
                        continue
            except Exception:
                pass

        emails.append({
            "subject": headers.get("Subject", "(no subject)"),
            "from": _clean_email_address(headers.get("From", "")),
            "to": _clean_email_address(headers.get("To", "")),
            "cc": _clean_email_address(headers.get("Cc", "")),
            "time": time_str,
            "date": date_val,
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


def format_search_results_for_tool(emails: List[Dict], query_desc: str = "") -> str:
    """Format email search results for Claude tool_use response.
    Truncates at 8000 chars to prevent token overflow."""
    if not emails:
        return "No emails found matching the search criteria."

    lines = [f"Found {len(emails)} email threads{' for ' + query_desc if query_desc else ''}:"]
    for i, email in enumerate(emails, 1):
        line = f"{i}. "
        if email.get("date"):
            line += f"[{email['date']} "
            if email.get("time"):
                line += f"{email['time']}] "
            else:
                line += "] "
        elif email.get("time"):
            line += f"[{email['time']}] "
        line += f"Subject: {email['subject']}"
        if email.get("from"):
            line += f" | From: {email['from']}"
        if email.get("to"):
            line += f" | To: {email['to']}"
        if email.get("cc"):
            line += f" | CC: {email['cc']}"
        if email.get("snippet"):
            snippet = email["snippet"][:100].replace("\n", " ")
            line += f"\n   Preview: {snippet}"
        lines.append(line)

    result = "\n".join(lines)
    if len(result) > 8000:
        result = result[:8000] + "\n... (results truncated — ask user to narrow the search)"
    return result
