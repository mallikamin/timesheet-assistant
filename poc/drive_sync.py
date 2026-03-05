"""
Google Drive activity module.
Fetches recently modified files to suggest time entries.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional

import httpx

DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"

# Google Workspace MIME types we care about
MIME_LABELS = {
    "application/vnd.google-apps.document": "Google Doc",
    "application/vnd.google-apps.spreadsheet": "Google Sheet",
    "application/vnd.google-apps.presentation": "Google Slides",
    "application/vnd.google-apps.form": "Google Form",
}


def get_recent_files(access_token: str, target_date: str = None) -> List[Dict]:
    """Fetch files the user modified on a given date (default: today)."""
    if target_date:
        day = datetime.strptime(target_date, "%Y-%m-%d")
    else:
        day = datetime.now()

    day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    # Only Google Workspace files (Docs, Sheets, Slides, Forms)
    mime_filter = " or ".join(
        f"mimeType='{m}'" for m in MIME_LABELS
    )
    query = (
        f"modifiedTime >= '{day_start.isoformat()}Z' and "
        f"modifiedTime < '{day_end.isoformat()}Z' and "
        f"({mime_filter}) and "
        f"'me' in owners"
    )

    resp = httpx.get(
        f"{DRIVE_API_BASE}/files",
        headers={"Authorization": f"Bearer {access_token}"},
        params={
            "q": query,
            "fields": "files(id,name,mimeType,modifiedTime,viewedByMeTime)",
            "orderBy": "modifiedTime desc",
            "pageSize": 50,
        },
    )

    if resp.status_code != 200:
        print(f"Drive API error: {resp.status_code} {resp.text}")
        return []

    raw_files = resp.json().get("files", [])
    files = []

    for f in raw_files:
        mime = f.get("mimeType", "")
        file_type = MIME_LABELS.get(mime, "File")
        modified = f.get("modifiedTime", "")

        mod_time = ""
        if modified:
            dt = datetime.fromisoformat(modified.replace("Z", "+00:00"))
            mod_time = dt.strftime("%H:%M")

        files.append({
            "name": f.get("name", "Untitled"),
            "type": file_type,
            "modified_time": mod_time,
            "mime_type": mime,
        })

    return files


def format_files_for_prompt(files: List[Dict], target_date: str = None) -> str:
    """Format Drive activity as text for the AI prompt."""
    if not files:
        return "No Google Drive activity found for this date."

    date_label = target_date or datetime.now().strftime("%Y-%m-%d")
    lines = [f"Google Drive activity for {date_label}:"]

    for i, f in enumerate(files, 1):
        line = f"{i}. [{f['type']}] {f['name']} (last edited {f['modified_time']})"
        lines.append(line)

    return "\n".join(lines)
