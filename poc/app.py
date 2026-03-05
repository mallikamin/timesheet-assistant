"""
Time Logging AI Assistant - POC Backend
FastAPI server with Claude-powered conversational timesheet assistant.
"""

import json
import os
from datetime import date
from typing import Dict, List, Optional, Tuple

import anthropic
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import harvest_mock
from project_mapping import get_all_projects_for_prompt

load_dotenv()

app = FastAPI(title="Timesheet Assistant POC")
templates = Jinja2Templates(directory="templates")

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

PILOT_USERS = ["Tariq Munir", "Malik Amin", "Jawad Saleem"]

SYSTEM_PROMPT = f"""You are a friendly, efficient timesheet assistant for a PR and communications agency based in Australia/New Zealand. Users tell you what they worked on in natural language (voice or text), and you help log their time into Harvest.

Your job:
1. Listen to what the user says they worked on.
2. Extract: client/project, task type, duration, date, and notes.
3. Match their description to the correct Harvest project from the list below.
4. If anything is unclear or ambiguous, ASK a clarifying question before logging. Be conversational but concise.
5. When you have enough info, create the entry by responding with a JSON block.

Rules:
- Minimum time block is 5 minutes (0.08 hours). Round up to nearest 5 minutes.
- Default date is today ({date.today().strftime('%A, %d/%m/%Y')}) unless the user specifies otherwise.
- Use DD/MM/YYYY date format (Australian standard).
- Understand AU/NZ English: "arvo" = afternoon, "brekkie" = breakfast, "reckon" = think, "heaps" = a lot, "keen" = eager, "no worries" = understood, "suss out" = investigate.
- When a user mentions multiple tasks, handle each one separately.
- If you can't confidently match to a project, ask which one they mean.
- If a user says something like "worked on Acuity" but there are multiple Acuity projects, ask which one.
- If they don't mention duration, ask "How long did you spend on that?"
- Be warm and professional. Use first names.

When you're ready to log an entry, include this exact JSON format in your response (the system will parse it):
```ENTRY
{{
  "client": "Client Name",
  "project_code": "CODE",
  "project_name": "Full Project Name",
  "task": "Task Type",
  "hours": 1.5,
  "notes": "Description of work done",
  "date": "YYYY-MM-DD",
  "status": "Draft"
}}
```

If confidence is low, set status to "Needs Review" instead of "Draft".

You can log multiple entries in one response — just include multiple ```ENTRY blocks.

Available Harvest Projects:
{get_all_projects_for_prompt()}

Pilot users: {', '.join(PILOT_USERS)}
"""


class ChatRequest(BaseModel):
    user: str
    message: str
    history: List[Dict] = []


class ChatResponse(BaseModel):
    response: str
    entries_created: List[Dict] = []


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


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "users": PILOT_USERS,
        "today": date.today().strftime("%A, %d/%m/%Y"),
    })


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    # Build messages for Claude
    messages = []
    for msg in req.history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": req.message})

    # Call Claude
    response = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=1024,
        system=SYSTEM_PROMPT.replace("USER_NAME", req.user),
        messages=messages,
    )

    ai_text = response.content[0].text

    # Parse any entries from the response
    display_text, entries_data = parse_entries_from_response(ai_text)

    # Save chat messages to Supabase
    harvest_mock.save_chat_message(req.user, "user", req.message)
    harvest_mock.save_chat_message(req.user, "assistant", display_text)

    # Save entries to Supabase
    created_entries = []
    for entry_data in entries_data:
        entry = harvest_mock.create_draft_entry(
            user=req.user,
            client=entry_data.get("client", "Unknown"),
            project_code=entry_data.get("project_code", ""),
            project_name=entry_data.get("project_name", ""),
            task=entry_data.get("task", "General"),
            hours=float(entry_data.get("hours", 0)),
            notes=entry_data.get("notes", ""),
            entry_date=entry_data.get("date", date.today().isoformat()),
            status=entry_data.get("status", "Draft"),
        )
        created_entries.append(entry)

    return ChatResponse(response=display_text, entries_created=created_entries)


@app.get("/api/entries/{user}")
async def get_entries(user: str, entry_date: str = None):
    entries = harvest_mock.get_entries(user=user, entry_date=entry_date)
    summary = harvest_mock.get_user_summary(user=user, entry_date=entry_date)
    return {"entries": entries, "summary": summary}


@app.delete("/api/entries/{entry_id}")
async def delete_entry(entry_id: str):
    success = harvest_mock.delete_entry(entry_id)
    return {"success": success}


@app.put("/api/entries/{entry_id}")
async def update_entry(entry_id: str, request: Request):
    body = await request.json()
    entry = harvest_mock.update_entry(entry_id, **body)
    return {"entry": entry, "success": entry is not None}


if __name__ == "__main__":
    print("\n  Timesheet Assistant POC")
    print(f"  Open http://localhost:8080 in your browser\n")
    uvicorn.run(app, host="127.0.0.1", port=8080)
