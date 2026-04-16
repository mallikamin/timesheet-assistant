"""
Task Management Module — backed by Supabase PostgreSQL.
Stores tasks, assignments, and cross-department workflows.
Supports AI timesheet sync prompts for overdue/unstarted tasks.
"""

import os
import uuid
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path

from supabase import create_client
from dotenv import load_dotenv

# Load environment variables
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

_client = None
_in_memory_tasks = {}  # Fallback for demo when Supabase table doesn't exist
_use_memory = False  # Flag to switch to in-memory mode
_supabase_available = True  # Track if Supabase is available


def _get_client():
    """Get Supabase client (or None if unavailable)."""
    global _client, _supabase_available
    if _client is None and _supabase_available:
        try:
            if not SUPABASE_URL or not SUPABASE_KEY:
                print("⚠️  Supabase credentials missing, using in-memory storage")
                _supabase_available = False
                return None
            _client = create_client(SUPABASE_URL, SUPABASE_KEY)
        except Exception as e:
            print(f"⚠️  Supabase connection failed: {e}")
            _supabase_available = False
            return None
    return _client


# --- Task CRUD ---

def create_task(
    title: str,
    project: str,
    assignees: list = None,  # Multiple assignees now
    status: str = "To Do",
    priority: str = "Medium",
    due_date: str = None,
    budget: float = 0.0,
    description: str = "",
    notes: str = "",
    attachments: list = None,  # [{"name": "file.pdf", "url": "https://..."}, ...]
    subtasks: list = None,  # [{"title": "Subtask 1", "done": False}, ...]
    parent_task_id: str = None,  # For subtasks
    created_by: str = "System",
) -> Dict:
    """Create a new task."""
    task = {
        "id": str(uuid.uuid4())[:8],
        "title": title,
        "project": project,
        "assignees": assignees or [],  # List of assignee names
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
        "hours_logged": 0.0,
    }
    global _use_memory, _in_memory_tasks

    sb = _get_client()
    if sb:
        try:
            result = sb.table("tasks").insert(task).execute()
            return result.data[0] if result.data else task
        except Exception as e:
            # Table might not exist yet — log and fall back
            if not _use_memory:
                print(f"⚠️  Supabase insert failed (falling back to in-memory): {e}")
                _use_memory = True

    # In-memory fallback
    _in_memory_tasks[task["id"]] = task
    if _use_memory and len(_in_memory_tasks) == 1:
        print("✓ Using in-memory task storage (Supabase table not ready)")
    return task


def get_task(task_id: str) -> Optional[Dict]:
    """Get a single task by ID."""
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
    """Get tasks, optionally filtered."""
    global _use_memory, _in_memory_tasks

    # Use in-memory storage if enabled
    if _use_memory:
        tasks = list(_in_memory_tasks.values())
        # Apply filters
        if project:
            tasks = [t for t in tasks if t.get("project") == project]
        if assignee:
            tasks = [t for t in tasks if assignee in t.get("assignees", [])]
        if status:
            tasks = [t for t in tasks if t.get("status") == status]
        # Sort by created_at
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
    """Update a task by ID."""
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
    """Delete a task by ID."""
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


# --- Task Grouping & Filtering ---

def get_tasks_by_status() -> Dict[str, List[Dict]]:
    """Get all tasks grouped by status."""
    all_tasks = get_all_tasks()
    grouped = {
        "To Do": [],
        "Working": [],
        "Review": [],
        "Done": [],
    }
    for task in all_tasks:
        status = task.get("status", "To Do")
        if status not in grouped:
            grouped[status] = []
        grouped[status].append(task)
    return grouped


def get_tasks_assigned_to(assignee: str) -> List[Dict]:
    """Get all tasks assigned to a user."""
    return get_all_tasks(assignee=assignee)


def get_tasks_by_project(project: str) -> List[Dict]:
    """Get all tasks for a project."""
    return get_all_tasks(project=project)


# --- AI Timesheet Sync ---

def get_sync_prompt_for_user(user: str) -> Optional[Dict]:
    """
    Get AI timesheet sync prompt for a user.
    Returns task assignment/reminder if user has unstarted/overdue tasks.
    """
    tasks = get_tasks_assigned_to(user)
    today = date.today()

    overdue = []
    due_soon = []
    unstarted = []

    for task in tasks:
        if task.get("status") == "Done":
            continue  # Skip completed tasks

        due = datetime.fromisoformat(task.get("due_date", "2099-12-31")).date()
        days_left = (due - today).days

        if days_left < 0:
            overdue.append(task)
        elif days_left == 0:
            due_soon.append(task)
        elif task.get("status") == "To Do":
            unstarted.append(task)

    # Build prompt
    if overdue:
        task = overdue[0]
        return {
            "type": "overdue",
            "task_id": task.get("id"),
            "message": f"G'day! You were assigned '{task.get('title')}' (due {task.get('due_date')}), but no updates yet. Have you started on it?",
            "task": task,
        }

    if due_soon:
        task = due_soon[0]
        return {
            "type": "due_soon",
            "task_id": task.get("id"),
            "message": f"Quick heads up: '{task.get('title')}' is due TODAY. Any progress to log?",
            "task": task,
        }

    if unstarted and len(unstarted) >= 2:
        return {
            "type": "many_unstarted",
            "count": len(unstarted),
            "message": f"You've got {len(unstarted)} tasks still in To Do. Want to tackle any of them today?",
            "tasks": unstarted,
        }

    return None


# --- Seed Data ---

def seed_tasks():
    """Populate tasks table with demo data."""
    team = ["Tariq Munir", "Lauren Pallotta", "Shivasha Dalpatadu", "Hugh", "Miles", "Michael"]
    projects = ["Afterpay AUNZ Campaign", "AGL Campaign Q2", "Acuity Operations FY26"]

    tasks_data = [
        {
            "title": "Review Q2 strategy deck",
            "project": "Afterpay AUNZ Campaign",
            "assignees": ["Tariq Munir"],
            "status": "To Do",
            "priority": "High",
            "due_date": (date.today() + timedelta(days=3)).isoformat(),
            "budget": 2400.0,
            "description": "Review and approve Q2 strategic direction",
            "notes": "Need CFO sign-off before distribution",
            "attachments": [{"name": "Q2_Strategy.pdf", "url": "https://example.com/Q2_Strategy.pdf"}],
            "subtasks": [
                {"title": "Review financials section", "done": False},
                {"title": "Approve messaging", "done": False},
            ],
        },
        {
            "title": "Update creative briefs",
            "project": "Afterpay AUNZ Campaign",
            "assignees": ["Lauren Pallotta", "Hugh"],
            "status": "To Do",
            "priority": "High",
            "due_date": (date.today() + timedelta(days=5)).isoformat(),
            "budget": 1800.0,
            "description": "Refresh creative direction and brief designers",
            "notes": "Coordinate with design team before finalizing",
            "attachments": [],
            "subtasks": [
                {"title": "Update tone of voice", "done": False},
                {"title": "Create design specs", "done": True},
            ],
        },
        {
            "title": "Client presentation deck",
            "project": "Afterpay AUNZ Campaign",
            "assignees": ["Shivasha Dalpatadu", "Tariq Munir"],
            "status": "Working",
            "priority": "High",
            "due_date": (date.today() + timedelta(days=2)).isoformat(),
            "budget": 3200.0,
            "description": "Prepare and finalize presentation for Afterpay stakeholders",
            "notes": "Client meeting scheduled for Tuesday",
            "attachments": [
                {"name": "Draft_Presentation.pptx", "url": "https://example.com/Draft_Presentation.pptx"},
                {"name": "Brand_Assets.zip", "url": "https://example.com/Brand_Assets.zip"},
            ],
            "subtasks": [
                {"title": "Add case studies", "done": True},
                {"title": "Finalize numbers", "done": False},
                {"title": "Get legal review", "done": False},
            ],
        },
        {
            "title": "Social media assets",
            "project": "AGL Campaign Q2",
            "assignees": ["Hugh", "Miles"],
            "status": "Working",
            "priority": "Medium",
            "due_date": (date.today() + timedelta(days=4)).isoformat(),
            "budget": 2600.0,
            "description": "Design and finalize social media creative for AGL campaign",
            "notes": "Use new brand colors",
            "attachments": [],
            "subtasks": [{"title": "Instagram post designs", "done": False}],
        },
        {
            "title": "Campaign performance report",
            "project": "AGL Campaign Q2",
            "assignees": ["Miles"],
            "status": "Working",
            "priority": "Medium",
            "due_date": (date.today() + timedelta(days=6)).isoformat(),
            "budget": 1500.0,
            "description": "Compile weekly performance metrics and analysis",
            "notes": "Include ROI calculations",
            "attachments": [{"name": "Weekly_Metrics.xlsx", "url": "https://example.com/Weekly_Metrics.xlsx"}],
            "subtasks": [],
        },
        {
            "title": "Email campaign templates",
            "project": "Acuity Operations FY26",
            "assignees": ["Michael", "Lauren Pallotta"],
            "status": "Review",
            "priority": "Medium",
            "due_date": (date.today() + timedelta(days=1)).isoformat(),
            "budget": 2200.0,
            "description": "Design responsive email templates for Q2 campaigns",
            "notes": "Test across Outlook, Gmail, Apple Mail",
            "attachments": [],
            "subtasks": [
                {"title": "Mobile responsive design", "done": True},
                {"title": "Dark mode support", "done": False},
            ],
        },
        {
            "title": "Website copy updates",
            "project": "Acuity Operations FY26",
            "assignees": ["Lauren Pallotta"],
            "status": "Review",
            "priority": "Low",
            "due_date": (date.today() + timedelta(days=7)).isoformat(),
            "budget": 1600.0,
            "description": "Update homepage and service page copy",
            "notes": "SEO review needed",
            "attachments": [],
            "subtasks": [],
        },
        {
            "title": "Brand guidelines refresh",
            "project": "Afterpay AUNZ Campaign",
            "assignees": ["Tariq Munir", "Hugh"],
            "status": "Done",
            "priority": "Medium",
            "due_date": (date.today() - timedelta(days=3)).isoformat(),
            "budget": 3500.0,
            "description": "Completed brand style guide update",
            "notes": "Approved by CFO on Apr 12",
            "attachments": [{"name": "Brand_Guidelines_Final.pdf", "url": "https://example.com/Brand_Guidelines_Final.pdf"}],
            "subtasks": [{"title": "Logo usage guide", "done": True}],
        },
    ]

    for task_data in tasks_data:
        create_task(**task_data)

    print(f"Seeded {len(tasks_data)} demo tasks with attachments, notes, subtasks, and multiple assignees")


if __name__ == "__main__":
    seed_tasks()
