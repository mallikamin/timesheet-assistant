"""
Time Logging AI Assistant - POC Backend
FastAPI server with Claude-powered conversational timesheet assistant.
Google SSO authentication.
"""

import json
import os
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import anthropic
import uvicorn
from authlib.integrations.starlette_client import OAuth
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

import calendar_sync
import drive_sync
import gmail_sync
import harvest_api
import harvest_mock
import sheets_sync
from project_mapping import get_all_projects_for_prompt

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

app = FastAPI(title="Timesheet Assistant POC")
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "timesheet-poc-secret-key-2026"),
)
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Google OAuth
oauth = OAuth()
oauth.register(
    name="google",
    client_id=os.getenv("GOOGLE_CLIENT_ID", ""),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET", ""),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={
        "scope": "openid email profile https://www.googleapis.com/auth/calendar.readonly https://www.googleapis.com/auth/drive.metadata.readonly https://www.googleapis.com/auth/gmail.readonly",
    },
)

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

PILOT_USERS = ["Tariq Munir", "Malik Amin", "Jawad Saleem"]

SYSTEM_PROMPT = f"""You are a friendly, efficient timesheet assistant for a PR and communications agency based in Australia/New Zealand. Users tell you what they worked on in natural language (voice or text), and you help log their time into Harvest.

IMPORTANT — Harvest structure:
- Each "Project" below is a client/project (e.g. Acuity, Afterpay).
- Under each project are specific TASKS (e.g. "Existing Business Growth FY26").
- When logging time, you MUST identify both the project AND the specific task.

Your conversation flow:
1. Listen to what the user says they worked on.
2. Identify the project. If unclear, ask which project.
3. Once you know the project, present the available tasks for that project and ask which one. List them as numbered options so the user can just reply with a number.
4. If the user already mentioned enough detail to match a specific task, skip asking and confirm instead.
5. Ask for duration if not mentioned.
6. When you have project + task + hours, log the entry.

Example flow:
- User: "Spent 2 hours on Acuity stuff"
- You: "No worries! Which Acuity task was this for?
  1. Existing Business Growth FY26
  2. New Business Growth FY26
  3. Operations & Admin FY26"
- User: "1"
- You: "Got it — 2 hours on Acuity, Existing Business Growth FY26. Logging that now." [creates entry]

Rules:
- Minimum time block is 5 minutes (0.08 hours). Round up to nearest 5 minutes.
- Default date is today ({date.today().strftime('%A, %d/%m/%Y')}) unless the user specifies otherwise.
- Use DD/MM/YYYY date format (Australian standard).
- Understand AU/NZ English: "arvo" = afternoon, "brekkie" = breakfast, "reckon" = think, "heaps" = a lot, "keen" = eager, "no worries" = understood, "suss out" = investigate.
- When a user mentions multiple items, handle each one separately.
- If they don't mention duration, ask "How long did you spend on that?"
- Be warm and professional. Use first names.
- Ask as many clarifying questions as needed to get the right project, task, and hours. Never guess.

When you're ready to log an entry, include this exact JSON format in your response (the system will parse it):
```ENTRY
{{{{
  "client": "Project Name",
  "project_code": "TASK-CODE",
  "project_name": "Task Name",
  "task": "Task Name",
  "hours": 1.5,
  "notes": "Description of work done",
  "date": "YYYY-MM-DD",
  "status": "Draft"
}}}}
```

Field mapping:
- "client" = the project name (e.g. "Acuity", "Afterpay")
- "project_code" = the task code (e.g. "6-1000", "2-1099")
- "project_name" = the task name (e.g. "Existing Business Growth FY26")
- "task" = same as project_name for now

If confidence is low, set status to "Needs Review" instead of "Draft".

You can log multiple entries in one response — just include multiple ```ENTRY blocks.

Available Projects and Tasks:
{get_all_projects_for_prompt()}

Pilot users: {', '.join(PILOT_USERS)}
"""


def get_current_user(request: Request) -> Optional[Dict]:
    """Get the logged-in user from session."""
    return request.session.get("user")


class ChatRequest(BaseModel):
    user: str
    message: str
    history: List[Dict] = []


class ChatResponse(BaseModel):
    response: str
    entries_created: List[Dict] = []


def save_entry_everywhere(user: str, entry_data: Dict, user_email: str = "") -> Dict:
    """Save an entry as Draft to Supabase and Google Sheets. Harvest push happens on approval."""
    entry = harvest_mock.create_draft_entry(
        user=user,
        client=entry_data.get("client", "Unknown"),
        project_code=entry_data.get("project_code", ""),
        project_name=entry_data.get("project_name", ""),
        task=entry_data.get("task", "General"),
        hours=float(entry_data.get("hours", 0)),
        notes=entry_data.get("notes", ""),
        entry_date=entry_data.get("date", date.today().isoformat()),
        status=entry_data.get("status", "Draft"),
    )
    # Sync to Google Sheet (draft only — no Harvest push until approved)
    sheets_sync.sync_entry_to_sheet(entry)
    return entry


def parse_entries_from_response(text: str) -> Tuple[str, List[Dict]]:
    """Extract ENTRY JSON blocks from Claude's response."""
    entries = []
    clean_text = text

    while "```ENTRY" in clean_text:
        start = clean_text.index("```ENTRY")
        end = clean_text.index("```", start + 8)
        json_str = clean_text[start + 8:end].strip()
        try:
            entry_data = json.loads(json_str)
            entries.append(entry_data)
        except json.JSONDecodeError:
            pass
        clean_text = clean_text[:start] + clean_text[end + 3:]

    return clean_text.strip(), entries


# --- Auth Routes ---

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse(url="/")
    return templates.TemplateResponse(request=request, name="login.html")


@app.get("/auth/google")
async def auth_google(request: Request):
    redirect_uri = request.url_for("auth_callback")
    return await oauth.google.authorize_redirect(
        request, redirect_uri, access_type="offline", prompt="consent"
    )


@app.get("/auth/callback")
async def auth_callback(request: Request):
    token = await oauth.google.authorize_access_token(request)
    userinfo = token.get("userinfo")
    if not userinfo:
        return RedirectResponse(url="/login")

    # Store user info in session
    request.session["user"] = {
        "email": userinfo["email"],
        "name": userinfo.get("name", userinfo["email"].split("@")[0]),
        "picture": userinfo.get("picture", ""),
    }
    # Store Google OAuth tokens for Calendar API access
    request.session["google_token"] = {
        "access_token": token.get("access_token", ""),
        "refresh_token": token.get("refresh_token", ""),
        "expires_at": token.get("expires_at", 0),
    }
    return RedirectResponse(url="/")


@app.get("/auth/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login")


# --- App Routes ---

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "user": user,
            "users": PILOT_USERS,
            "today": date.today().strftime("%A, %d/%m/%Y"),
        },
    )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request):
    user = get_current_user(request)
    if not user:
        return ChatResponse(response="Please log in first.", entries_created=[])

    # Build messages for Claude
    messages = []
    for msg in req.history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": req.message})

    # Call Claude
    response = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=messages,
    )

    ai_text = response.content[0].text

    # Parse any entries from the response
    display_text, entries_data = parse_entries_from_response(ai_text)

    # Save chat messages to Supabase
    harvest_mock.save_chat_message(req.user, "user", req.message)
    harvest_mock.save_chat_message(req.user, "assistant", display_text)

    # Save entries to Supabase + Sheets + Harvest
    created_entries = []
    for entry_data in entries_data:
        entry = save_entry_everywhere(req.user, entry_data, user_email=user.get("email", ""))
        created_entries.append(entry)

    return ChatResponse(response=display_text, entries_created=created_entries)


@app.post("/api/entries/approve-all")
async def approve_all_entries(request: Request):
    """Approve all draft entries for the current user."""
    user = get_current_user(request)
    if not user:
        return {"success": False, "error": "Not authenticated"}

    body = await request.json()
    user_name = body.get("user", user.get("name", ""))
    user_email = user.get("email", "")

    entries = harvest_mock.get_entries(user=user_name)
    drafts = [e for e in entries if e.get("status") in ("Draft", "Needs Review")]

    results = []
    for entry in drafts:
        harvest_user_id = harvest_api.resolve_user_id(user_email) if user_email else None
        harvest_entry = harvest_api.push_entry(
            client_name=entry.get("client", ""),
            task_name=entry.get("project_name", entry.get("task", "")),
            spent_date=entry.get("date", date.today().isoformat()),
            hours=float(entry.get("hours", 0)),
            notes=entry.get("notes", ""),
            user_id=harvest_user_id,
        )

        if harvest_entry:
            harvest_mock.update_entry(entry["id"], status="Approved", harvest_id=harvest_entry["id"])
            sheets_sync.update_entry_status_in_sheet(entry["id"], "Approved")
            results.append({"id": entry["id"], "approved": True})
        else:
            results.append({"id": entry["id"], "approved": False})

    return {"success": True, "results": results}


@app.get("/api/entries/{user}")
async def get_entries(user: str, entry_date: str = None):
    entries = harvest_mock.get_entries(user=user, entry_date=entry_date)
    summary = harvest_mock.get_user_summary(user=user, entry_date=entry_date)
    return {"entries": entries, "summary": summary}


@app.delete("/api/entries/{entry_id}")
async def delete_entry(entry_id: str):
    # Check if entry has a Harvest ID before deleting
    entries = harvest_mock.get_entries()
    harvest_id = None
    for e in entries:
        if e.get("id") == entry_id and e.get("harvest_id"):
            harvest_id = e["harvest_id"]
            break
    success = harvest_mock.delete_entry(entry_id)
    if success:
        sheets_sync.delete_entry_from_sheet(entry_id)
        if harvest_id:
            harvest_api.delete_time_entry(int(harvest_id))
    return {"success": success}


@app.put("/api/entries/{entry_id}")
async def update_entry(entry_id: str, request: Request):
    body = await request.json()
    entry = harvest_mock.update_entry(entry_id, **body)
    if entry and "status" in body:
        sheets_sync.update_entry_status_in_sheet(entry_id, body["status"])
    return {"entry": entry, "success": entry is not None}


@app.post("/api/entries/{entry_id}/approve")
async def approve_entry(entry_id: str, request: Request):
    """Approve a draft entry: push to Harvest, update status."""
    user = get_current_user(request)
    if not user:
        return {"success": False, "error": "Not authenticated"}

    # Find the entry
    entries = harvest_mock.get_entries()
    entry = None
    for e in entries:
        if e.get("id") == entry_id:
            entry = e
            break

    if not entry:
        return {"success": False, "error": "Entry not found"}

    if entry.get("status") == "Approved":
        return {"success": False, "error": "Already approved"}

    # Push to Harvest
    user_email = user.get("email", "")
    harvest_user_id = harvest_api.resolve_user_id(user_email) if user_email else None
    harvest_entry = harvest_api.push_entry(
        client_name=entry.get("client", ""),
        task_name=entry.get("project_name", entry.get("task", "")),
        spent_date=entry.get("date", date.today().isoformat()),
        hours=float(entry.get("hours", 0)),
        notes=entry.get("notes", ""),
        user_id=harvest_user_id,
    )

    if not harvest_entry:
        return {"success": False, "error": "Failed to push to Harvest"}

    # Update Supabase
    harvest_mock.update_entry(entry_id, status="Approved", harvest_id=harvest_entry["id"])
    # Update Google Sheet
    sheets_sync.update_entry_status_in_sheet(entry_id, "Approved")

    return {"success": True, "harvest_id": harvest_entry["id"]}


@app.get("/api/calendar/events")
async def get_calendar_events(request: Request, target_date: str = None):
    """Fetch the user's Google Calendar events for a given date."""
    user = get_current_user(request)
    if not user:
        return {"error": "Not authenticated", "events": []}

    google_token = request.session.get("google_token")
    if not google_token or not google_token.get("access_token"):
        return {"error": "no_calendar_access", "events": []}

    # Refresh token if expired
    valid_token = calendar_sync.ensure_valid_token(google_token)
    if not valid_token:
        return {"error": "token_expired", "events": []}

    # Update session with refreshed token
    request.session["google_token"] = valid_token

    events = calendar_sync.get_events(valid_token["access_token"], target_date)
    return {"events": events, "date": target_date or date.today().isoformat()}


@app.post("/api/calendar/suggest")
async def suggest_from_calendar(request: Request):
    """Fetch calendar events and ask Claude to suggest time entries."""
    user = get_current_user(request)
    if not user:
        return ChatResponse(response="Please log in first.", entries_created=[])

    body = await request.json()
    target_date = body.get("date")
    history = body.get("history", [])

    # Get calendar events
    google_token = request.session.get("google_token")
    if not google_token or not google_token.get("access_token"):
        return ChatResponse(
            response="I don't have access to your calendar. Please sign out and sign back in to grant calendar permission.",
            entries_created=[],
        )

    valid_token = calendar_sync.ensure_valid_token(google_token)
    if not valid_token:
        return ChatResponse(
            response="Your calendar access has expired. Please sign out and sign back in.",
            entries_created=[],
        )

    request.session["google_token"] = valid_token
    events = calendar_sync.get_events(valid_token["access_token"], target_date)

    if not events:
        return ChatResponse(
            response="No calendar events found for today. Tell me what you worked on and I'll log it manually.",
            entries_created=[],
        )

    # Format events and ask Claude to suggest entries
    events_text = calendar_sync.format_events_for_prompt(events, target_date)
    calendar_prompt = (
        f"I just pulled my calendar. Here are my events:\n\n{events_text}\n\n"
        "Can you suggest time entries for these? Map them to the Harvest projects where possible."
    )

    messages = []
    for msg in history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": calendar_prompt})

    response = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=messages,
    )

    ai_text = response.content[0].text
    display_text, entries_data = parse_entries_from_response(ai_text)

    # Save chat
    harvest_mock.save_chat_message(user["name"], "user", calendar_prompt)
    harvest_mock.save_chat_message(user["name"], "assistant", display_text)

    # Save entries to Supabase + Sheets + Harvest
    created_entries = []
    for entry_data in entries_data:
        entry = save_entry_everywhere(user["name"], entry_data, user_email=user.get("email", ""))
        created_entries.append(entry)

    return ChatResponse(response=display_text, entries_created=created_entries)


@app.post("/api/drive/suggest")
async def suggest_from_drive(request: Request):
    """Fetch Drive activity and ask Claude to suggest time entries."""
    user = get_current_user(request)
    if not user:
        return ChatResponse(response="Please log in first.", entries_created=[])

    body = await request.json()
    target_date = body.get("date")
    history = body.get("history", [])

    google_token = request.session.get("google_token")
    if not google_token or not google_token.get("access_token"):
        return ChatResponse(
            response="I don't have access to your Google Drive. Please sign out and sign back in to grant permission.",
            entries_created=[],
        )

    valid_token = calendar_sync.ensure_valid_token(google_token)
    if not valid_token:
        return ChatResponse(
            response="Your Google access has expired. Please sign out and sign back in.",
            entries_created=[],
        )

    request.session["google_token"] = valid_token
    files = drive_sync.get_recent_files(valid_token["access_token"], target_date)

    if not files:
        return ChatResponse(
            response="No Google Drive activity found for today. Tell me what you worked on and I'll log it manually.",
            entries_created=[],
        )

    files_text = drive_sync.format_files_for_prompt(files, target_date)
    drive_prompt = (
        f"I just pulled my Google Drive activity. Here are the files I edited today:\n\n{files_text}\n\n"
        "Can you suggest time entries based on these? Map them to the Harvest projects where possible. "
        "Ask me about anything you're unsure of."
    )

    messages = []
    for msg in history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": drive_prompt})

    response = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=messages,
    )

    ai_text = response.content[0].text
    display_text, entries_data = parse_entries_from_response(ai_text)

    harvest_mock.save_chat_message(user["name"], "user", drive_prompt)
    harvest_mock.save_chat_message(user["name"], "assistant", display_text)

    # Save entries to Supabase + Sheets + Harvest
    created_entries = []
    for entry_data in entries_data:
        entry = save_entry_everywhere(user["name"], entry_data, user_email=user.get("email", ""))
        created_entries.append(entry)

    return ChatResponse(response=display_text, entries_created=created_entries)


@app.post("/api/gmail/suggest")
async def suggest_from_gmail(request: Request):
    """Fetch email activity and ask Claude to suggest time entries."""
    user = get_current_user(request)
    if not user:
        return ChatResponse(response="Please log in first.", entries_created=[])

    body = await request.json()
    target_date = body.get("date")
    history = body.get("history", [])

    google_token = request.session.get("google_token")
    if not google_token or not google_token.get("access_token"):
        return ChatResponse(
            response="I don't have access to your Gmail. Please sign out and sign back in to grant permission.",
            entries_created=[],
        )

    valid_token = calendar_sync.ensure_valid_token(google_token)
    if not valid_token:
        return ChatResponse(
            response="Your Google access has expired. Please sign out and sign back in.",
            entries_created=[],
        )

    request.session["google_token"] = valid_token
    emails = gmail_sync.get_recent_emails(valid_token["access_token"], target_date)

    if not emails:
        return ChatResponse(
            response="No email activity found for today. Tell me what you worked on and I'll log it manually.",
            entries_created=[],
        )

    emails_text = gmail_sync.format_emails_for_prompt(emails, target_date)
    gmail_prompt = (
        f"I just pulled my email activity. Here are the emails from today:\n\n{emails_text}\n\n"
        "Can you suggest time entries based on these? Map them to the Harvest projects where possible. "
        "Group related emails together and estimate time spent. Ask me about anything you're unsure of."
    )

    messages = []
    for msg in history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": gmail_prompt})

    response = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=messages,
    )

    ai_text = response.content[0].text
    display_text, entries_data = parse_entries_from_response(ai_text)

    harvest_mock.save_chat_message(user["name"], "user", gmail_prompt)
    harvest_mock.save_chat_message(user["name"], "assistant", display_text)

    created_entries = []
    for entry_data in entries_data:
        entry = save_entry_everywhere(user["name"], entry_data, user_email=user.get("email", ""))
        created_entries.append(entry)

    return ChatResponse(response=display_text, entries_created=created_entries)


@app.get("/api/me")
async def get_me(request: Request):
    user = get_current_user(request)
    if not user:
        return {"authenticated": False}
    has_calendar = bool(request.session.get("google_token", {}).get("access_token"))
    return {"authenticated": True, "has_calendar": has_calendar, **user}


if __name__ == "__main__":
    print("\n  Timesheet Assistant POC")
    print(f"  Open http://localhost:8080 in your browser\n")
    uvicorn.run(app, host="127.0.0.1", port=8080)
