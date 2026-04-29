"""
Task Management Module — backed by Supabase PostgreSQL (in-memory fallback for local demo).
Stores initiatives (projects), tasks, multi-assignees, attachments, subtasks, notes.
Seed data mirrors Tariq's Thrive_Project_Tracker.xlsx (23 Apr 2026 snapshot).
"""

import os
import uuid
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path

from supabase import create_client
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

_client = None
_in_memory_tasks = {}
_use_memory = False
_supabase_available = True


# --- Project metadata (from Tariq's XLSX, 23 Apr 2026) ---

PROJECTS: List[Dict] = [
    {
        "name": "AI TimeKeeper",
        "category": "Time Capture",
        "status": "Needs attention",
        "champions": ["Hugh", "Michael"],
        "what_we_doing": "Make timesheets faster, efficient and better",
        "start_date": (date.today() - timedelta(days=60)).isoformat(),
        "end_date": (date.today() + timedelta(days=60)).isoformat(),
    },
    {
        "name": "ThriveMind",
        "category": "Knowledge & Content",
        "status": "In progress",
        "champions": ["Hugh", "LP", "Kyra"],
        "what_we_doing": "Institutional knowledge — a prompt away",
        "start_date": (date.today() - timedelta(days=45)).isoformat(),
        "end_date": (date.today() + timedelta(days=90)).isoformat(),
    },
    {
        "name": "Thrive Gems",
        "category": "Knowledge & Content",
        "status": "In progress",
        "champions": ["Anna", "Michael", "Amy", "Bianca"],
        "what_we_doing": "Specialist knowledge at your fingertips",
        "start_date": (date.today() - timedelta(days=40)).isoformat(),
        "end_date": (date.today() + timedelta(days=75)).isoformat(),
    },
    {
        "name": "ThriveFlows",
        "category": "Workflow & Coordination",
        "status": "In progress",
        "champions": ["Lucy", "Tiana", "Sophie"],
        "what_we_doing": "Making workflows simpler",
        "start_date": (date.today() - timedelta(days=30)).isoformat(),
        "end_date": (date.today() + timedelta(days=90)).isoformat(),
    },
    {
        "name": "Thrive Case Studies",
        "category": "Knowledge & Content",
        "status": "To be started",
        "champions": ["TBC"],
        "what_we_doing": "Case studies powered by NotebookLM",
        "start_date": (date.today() + timedelta(days=10)).isoformat(),
        "end_date": (date.today() + timedelta(days=120)).isoformat(),
    },
    {
        "name": "SlideFlow",
        "category": "Reporting & Delivery",
        "status": "To be started",
        "champions": ["TBC"],
        "what_we_doing": "Slide deck automation via Claude",
        "start_date": (date.today() + timedelta(days=14)).isoformat(),
        "end_date": (date.today() + timedelta(days=120)).isoformat(),
    },
    {
        "name": "Project Management",
        "category": "Workflow & Coordination",
        "status": "In progress",
        "champions": ["Erin", "Bianca", "Sam"],
        "what_we_doing": "Intelligent project management platform",
        "start_date": (date.today() - timedelta(days=20)).isoformat(),
        "end_date": (date.today() + timedelta(days=100)).isoformat(),
    },
    {
        "name": "Talent 360",
        "category": "People & Culture",
        "status": "To be started",
        "champions": ["Anna"],
        "what_we_doing": "Culture Currency 2.0",
        "start_date": (date.today() + timedelta(days=21)).isoformat(),
        "end_date": (date.today() + timedelta(days=150)).isoformat(),
    },
]


def get_project(name: str) -> Optional[Dict]:
    for p in PROJECTS:
        if p["name"].lower() == name.lower():
            return p
    return None


def get_projects_overview() -> List[Dict]:
    """Return each project with aggregated task counts for the Overall Board."""
    all_tasks = get_all_tasks()
    overview = []
    for p in PROJECTS:
        proj_tasks = [t for t in all_tasks if t.get("project") == p["name"]]
        by_status = {}
        for t in proj_tasks:
            s = t.get("status", "Not started")
            by_status[s] = by_status.get(s, 0) + 1
        total = len(proj_tasks)
        completed = by_status.get("Completed", 0)
        overview.append({
            **p,
            "task_count": total,
            "completed_count": completed,
            "progress_pct": int((completed / total) * 100) if total else 0,
            "by_status": by_status,
        })
    return overview


def _get_client():
    global _client, _supabase_available
    if _client is None and _supabase_available:
        try:
            if not SUPABASE_URL or not SUPABASE_KEY:
                print("[WARN] Supabase credentials missing, using in-memory storage")
                _supabase_available = False
                return None
            _client = create_client(SUPABASE_URL, SUPABASE_KEY)
        except Exception as e:
            print(f"[WARN] Supabase connection failed: {e}")
            _supabase_available = False
            return None
    return _client


# --- Task CRUD ---

def create_task(
    title: str,
    project: str,
    assignees: list = None,
    status: str = "Not started",
    priority: str = "Medium",
    due_date: str = None,
    budget: float = 0.0,
    description: str = "",
    notes: str = "",
    attachments: list = None,
    subtasks: list = None,
    parent_task_id: str = None,
    created_by: str = "System",
    hours_logged: float = 0.0,
) -> Dict:
    task = {
        "id": str(uuid.uuid4())[:8],
        "title": title,
        "project": project,
        "assignees": assignees or [],
        "status": status,
        "priority": priority,
        "due_date": due_date or date.today().isoformat(),
        "budget": budget,
        "description": description,
        "notes": notes,
        "attachments": attachments or [],
        "subtasks": subtasks or [],
        "parent_task_id": parent_task_id,
        "created_by": created_by,
        "created_at": datetime.now().isoformat(),
        "hours_logged": hours_logged,
    }
    global _use_memory, _in_memory_tasks

    sb = _get_client()
    if sb:
        try:
            result = sb.table("tasks").insert(task).execute()
            return result.data[0] if result.data else task
        except Exception as e:
            if not _use_memory:
                print(f"[WARN] Supabase insert failed (falling back to in-memory): {e}")
                _use_memory = True

    _in_memory_tasks[task["id"]] = task
    if _use_memory and len(_in_memory_tasks) == 1:
        print("[OK] Using in-memory task storage (Supabase table not ready)")
    return task


def get_task(task_id: str) -> Optional[Dict]:
    global _use_memory, _in_memory_tasks
    if _use_memory:
        return _in_memory_tasks.get(task_id)
    try:
        sb = _get_client()
        result = sb.table("tasks").select("*").eq("id", task_id).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        print(f"get_task error: {e}")
        return None


def get_all_tasks(project: str = None, assignee: str = None, status: str = None) -> List[Dict]:
    global _use_memory, _in_memory_tasks
    if _use_memory:
        tasks = list(_in_memory_tasks.values())
        if project:
            tasks = [t for t in tasks if t.get("project") == project]
        if assignee:
            tasks = [t for t in tasks if assignee in t.get("assignees", [])]
        if status:
            tasks = [t for t in tasks if t.get("status") == status]
        tasks.sort(key=lambda t: t.get("created_at", ""))
        return tasks
    try:
        sb = _get_client()
        query = sb.table("tasks").select("*")
        if project:
            query = query.eq("project", project)
        if assignee:
            query = query.contains("assignees", [assignee])
        if status:
            query = query.eq("status", status)
        query = query.order("created_at", desc=False)
        result = query.execute()
        return result.data or []
    except Exception as e:
        print(f"get_all_tasks error: {e}")
        return []


def update_task(task_id: str, **kwargs) -> Optional[Dict]:
    global _use_memory, _in_memory_tasks
    if _use_memory:
        if task_id in _in_memory_tasks:
            _in_memory_tasks[task_id].update(kwargs)
            return _in_memory_tasks[task_id]
        return None
    try:
        sb = _get_client()
        result = sb.table("tasks").update(kwargs).eq("id", task_id).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        print(f"update_task error: {e}")
        return None


def delete_task(task_id: str) -> bool:
    global _use_memory, _in_memory_tasks
    if _use_memory:
        if task_id in _in_memory_tasks:
            del _in_memory_tasks[task_id]
            return True
        return False
    try:
        sb = _get_client()
        result = sb.table("tasks").delete().eq("id", task_id).execute()
        return bool(result.data)
    except Exception as e:
        print(f"delete_task error: {e}")
        return False


# --- Grouping / filtering ---

def get_tasks_by_status() -> Dict[str, List[Dict]]:
    all_tasks = get_all_tasks()
    grouped = {
        "Not started": [],
        "In progress": [],
        "Blocked": [],
        "Needs attention": [],
        "Completed": [],
    }
    for task in all_tasks:
        s = task.get("status", "Not started")
        grouped.setdefault(s, []).append(task)
    return grouped


def get_tasks_assigned_to(assignee: str) -> List[Dict]:
    return get_all_tasks(assignee=assignee)


def get_tasks_by_project(project: str) -> List[Dict]:
    return get_all_tasks(project=project)


# --- AI sync prompts ---

def get_sync_prompt_for_user(user: str) -> Optional[Dict]:
    tasks = get_tasks_assigned_to(user)
    today = date.today()
    overdue, due_soon, unstarted = [], [], []
    for task in tasks:
        if task.get("status") == "Completed":
            continue
        try:
            due = datetime.fromisoformat(task.get("due_date", "2099-12-31")).date()
        except Exception:
            continue
        days_left = (due - today).days
        if days_left < 0:
            overdue.append(task)
        elif days_left == 0:
            due_soon.append(task)
        elif task.get("status") == "Not started":
            unstarted.append(task)

    if overdue:
        t = overdue[0]
        return {"type": "overdue", "task_id": t.get("id"),
                "message": f"G'day! You were assigned '{t.get('title')}' (due {t.get('due_date')}), but no updates yet. Have you started on it?",
                "task": t}
    if due_soon:
        t = due_soon[0]
        return {"type": "due_soon", "task_id": t.get("id"),
                "message": f"Quick heads up: '{t.get('title')}' is due TODAY. Any progress to log?",
                "task": t}
    if unstarted and len(unstarted) >= 2:
        return {"type": "many_unstarted", "count": len(unstarted),
                "message": f"You've got {len(unstarted)} tasks still Not started. Want to tackle any of them today?",
                "tasks": unstarted}
    return None


# --- Seed (mirrors Tariq's XLSX — 8 initiatives, 24 tasks total) ---

def seed_tasks():
    today = date.today()

    def d(days):
        return (today + timedelta(days=days)).isoformat()

    seed = [
        # AI TimeKeeper
        {"title": "Build POC", "project": "AI TimeKeeper", "assignees": ["Hugh", "Michael"],
         "status": "Completed", "priority": "High", "due_date": d(-5), "budget": 12000,
         "description": "Proof of concept for AI-assisted time logging",
         "notes": "Delivered Apr 2026 — demoed to CFO", "hours_logged": 48,
         "attachments": [{"name": "POC_Demo_Report.pdf", "url": "#"}],
         "subtasks": [{"title": "FastAPI backend", "done": True},
                      {"title": "Google SSO", "done": True},
                      {"title": "Claude integration", "done": True}]},
        {"title": "Harvest API access", "project": "AI TimeKeeper", "assignees": ["Michael"],
         "status": "Completed", "priority": "High", "due_date": d(-3), "budget": 3500,
         "description": "OAuth2 integration with Thrive Harvest account 310089",
         "notes": "Pulls 51+ live client projects", "hours_logged": 22,
         "attachments": [], "subtasks": [{"title": "OAuth2 app registered", "done": True},
                                          {"title": "Token refresh logic", "done": True}]},
        {"title": "Business user testing", "project": "AI TimeKeeper", "assignees": ["Hugh", "Tariq Munir"],
         "status": "In progress", "priority": "High", "due_date": d(14), "budget": 8000,
         "description": "Pilot with 5 Thrive team members",
         "notes": "Awaiting Forecast API access and pilot user list", "hours_logged": 6,
         "attachments": [], "subtasks": [{"title": "Pilot user list", "done": False},
                                          {"title": "Consent forms", "done": False},
                                          {"title": "Feedback collection", "done": False}]},
        {"title": "Full agency rollout", "project": "AI TimeKeeper", "assignees": ["Hugh"],
         "status": "Not started", "priority": "Medium", "due_date": d(60), "budget": 15000,
         "description": "AU/NZ-wide deployment to all staff",
         "notes": "Pending pilot results", "hours_logged": 0,
         "attachments": [], "subtasks": []},

        # ThriveMind
        {"title": "Squads established", "project": "ThriveMind", "assignees": ["Hugh", "LP"],
         "status": "Completed", "priority": "High", "due_date": d(-8), "budget": 4000,
         "description": "Cross-functional knowledge squads formed",
         "notes": "5 squads live", "hours_logged": 16, "attachments": [], "subtasks": []},
        {"title": "Team adoption", "project": "ThriveMind", "assignees": ["Kyra", "LP"],
         "status": "In progress", "priority": "High", "due_date": d(21), "budget": 6500,
         "description": "Drive daily usage across AU/NZ teams",
         "notes": "60% adoption week-over-week", "hours_logged": 12,
         "attachments": [], "subtasks": [{"title": "Champion training", "done": True},
                                          {"title": "Usage dashboard", "done": False}]},
        {"title": "Playbook documentation", "project": "ThriveMind", "assignees": ["Hugh", "Kyra"],
         "status": "In progress", "priority": "Medium", "due_date": d(35), "budget": 5500,
         "description": "Document prompts, patterns, and guardrails",
         "notes": "Draft 40% complete", "hours_logged": 9, "attachments": [], "subtasks": []},

        # Thrive Gems
        {"title": "Squads established", "project": "Thrive Gems", "assignees": ["Anna", "Michael"],
         "status": "Completed", "priority": "High", "due_date": d(-10), "budget": 3500,
         "description": "Specialist squads formed across practices",
         "notes": "", "hours_logged": 14, "attachments": [], "subtasks": []},
        {"title": "Gem training on Thrive content", "project": "Thrive Gems", "assignees": ["Amy", "Bianca"],
         "status": "In progress", "priority": "High", "due_date": d(18), "budget": 7000,
         "description": "Train Gems on Thrive case content, tone, IP",
         "notes": "Ingested 40% of archive", "hours_logged": 11,
         "attachments": [], "subtasks": [{"title": "Archive ingestion", "done": False},
                                          {"title": "Prompt library", "done": False}]},
        {"title": "Team adoption", "project": "Thrive Gems", "assignees": ["Anna"],
         "status": "In progress", "priority": "Medium", "due_date": d(40), "budget": 4500,
         "description": "Drive daily Gem usage across teams",
         "notes": "", "hours_logged": 4, "attachments": [], "subtasks": []},

        # ThriveFlows
        {"title": "Squads established", "project": "ThriveFlows", "assignees": ["Lucy"],
         "status": "Completed", "priority": "High", "due_date": d(-6), "budget": 3000,
         "description": "Workflow design squads formed",
         "notes": "", "hours_logged": 10, "attachments": [], "subtasks": []},
        {"title": "Workflow mapping", "project": "ThriveFlows", "assignees": ["Tiana", "Sophie"],
         "status": "In progress", "priority": "High", "due_date": d(22), "budget": 8500,
         "description": "Map current-state and future-state workflows",
         "notes": "3 of 8 workflows mapped", "hours_logged": 18,
         "attachments": [], "subtasks": [{"title": "Campaign delivery workflow", "done": True},
                                          {"title": "Client onboarding workflow", "done": False}]},
        {"title": "Team adoption", "project": "ThriveFlows", "assignees": ["Lucy", "Sophie"],
         "status": "Needs attention", "priority": "High", "due_date": d(28), "budget": 5000,
         "description": "Rollout adoption stalled — change management needed",
         "notes": "Escalated to CFO — needs exec sponsor", "hours_logged": 3,
         "attachments": [], "subtasks": []},

        # Thrive Case Studies
        {"title": "Assign business owner", "project": "Thrive Case Studies", "assignees": [],
         "status": "Blocked", "priority": "High", "due_date": d(7), "budget": 0,
         "description": "Ownership assignment blocked on exec review",
         "notes": "Waiting for MD decision", "hours_logged": 0,
         "attachments": [], "subtasks": []},
        {"title": "NotebookLM setup", "project": "Thrive Case Studies", "assignees": [],
         "status": "Not started", "priority": "Medium", "due_date": d(30), "budget": 2500,
         "description": "Set up NotebookLM workspaces per practice",
         "notes": "", "hours_logged": 0, "attachments": [], "subtasks": []},
        {"title": "Content ingestion", "project": "Thrive Case Studies", "assignees": [],
         "status": "Not started", "priority": "Medium", "due_date": d(60), "budget": 6000,
         "description": "Ingest case study archive into NotebookLM",
         "notes": "", "hours_logged": 0, "attachments": [], "subtasks": []},

        # SlideFlow
        {"title": "Identify Claude specialist", "project": "SlideFlow", "assignees": [],
         "status": "Blocked", "priority": "High", "due_date": d(10), "budget": 0,
         "description": "Need named owner with Claude API experience",
         "notes": "Pending hire / assignment", "hours_logged": 0,
         "attachments": [], "subtasks": []},
        {"title": "Template build", "project": "SlideFlow", "assignees": [],
         "status": "Not started", "priority": "Medium", "due_date": d(45), "budget": 8000,
         "description": "Build brand-aligned deck templates",
         "notes": "", "hours_logged": 0, "attachments": [], "subtasks": []},
        {"title": "Pilot — Sydney location", "project": "SlideFlow", "assignees": [],
         "status": "Not started", "priority": "Low", "due_date": d(75), "budget": 5000,
         "description": "Sydney office pilot",
         "notes": "", "hours_logged": 0, "attachments": [], "subtasks": []},

        # Project Management
        {"title": "Wireframe demo", "project": "Project Management",
         "assignees": ["Erin", "Sam"],
         "status": "In progress", "priority": "High", "due_date": d(3), "budget": 4500,
         "description": "Interactive wireframe for CEO demo",
         "notes": "Demo scheduled for this week", "hours_logged": 14,
         "attachments": [{"name": "Wireframe_v2.pdf", "url": "#"}],
         "subtasks": [{"title": "Overall Board view", "done": True},
                      {"title": "Gantt view", "done": True},
                      {"title": "Calendar view", "done": True},
                      {"title": "Project drill-down", "done": True}]},
        {"title": "Platform evaluation", "project": "Project Management",
         "assignees": ["Bianca", "Sam"],
         "status": "In progress", "priority": "Medium", "due_date": d(25), "budget": 6000,
         "description": "Evaluate Monday.com, Asana, ClickUp, and in-house build",
         "notes": "Scoring matrix 70% complete", "hours_logged": 11,
         "attachments": [], "subtasks": []},
        {"title": "Pilot rollout", "project": "Project Management",
         "assignees": ["Erin"],
         "status": "Not started", "priority": "Medium", "due_date": d(55), "budget": 7500,
         "description": "Roll out selected platform to 2 practices",
         "notes": "", "hours_logged": 0, "attachments": [], "subtasks": []},

        # Talent 360
        {"title": "Process mapping", "project": "Talent 360", "assignees": ["Anna"],
         "status": "Not started", "priority": "Medium", "due_date": d(30), "budget": 4000,
         "description": "Map current Culture Currency flow",
         "notes": "", "hours_logged": 0, "attachments": [], "subtasks": []},
        {"title": "Business case", "project": "Talent 360", "assignees": ["Anna"],
         "status": "Not started", "priority": "Medium", "due_date": d(50), "budget": 3500,
         "description": "Build v2.0 business case for exec sign-off",
         "notes": "", "hours_logged": 0, "attachments": [], "subtasks": []},
        {"title": "Pilot design", "project": "Talent 360", "assignees": ["Anna"],
         "status": "Not started", "priority": "Low", "due_date": d(80), "budget": 5500,
         "description": "Design pilot cohort + rewards structure",
         "notes": "", "hours_logged": 0, "attachments": [], "subtasks": []},
    ]

    for task_data in seed:
        create_task(**task_data)

    print(f"Seeded {len(seed)} tasks across {len(PROJECTS)} initiatives (Thrive Project Tracker)")


if __name__ == "__main__":
    seed_tasks()
