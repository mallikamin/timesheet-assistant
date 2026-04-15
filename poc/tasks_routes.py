"""
Task Management API Routes
Endpoints for task CRUD, filtering, and sync prompts.
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import tasks

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


# --- Request/Response Models ---

class TaskCreate(BaseModel):
    title: str
    project: str
    assignee: str
    status: str = "To Do"
    priority: str = "Medium"
    due_date: Optional[str] = None
    budget: float = 0.0
    description: str = ""
    created_by: str = "System"


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    project: Optional[str] = None
    assignee: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[str] = None
    budget: Optional[float] = None
    description: Optional[str] = None
    hours_logged: Optional[float] = None


# --- Routes ---

@router.get("")
async def list_tasks(
    project: Optional[str] = None,
    assignee: Optional[str] = None,
    status: Optional[str] = None,
):
    """Get all tasks, optionally filtered."""
    return tasks.get_all_tasks(project=project, assignee=assignee, status=status)


@router.get("/{task_id}")
async def get_task(task_id: str):
    """Get a single task by ID."""
    task = tasks.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("")
async def create_task(body: TaskCreate):
    """Create a new task."""
    task = tasks.create_task(
        title=body.title,
        project=body.project,
        assignee=body.assignee,
        status=body.status,
        priority=body.priority,
        due_date=body.due_date,
        budget=body.budget,
        description=body.description,
        created_by=body.created_by,
    )
    return task


@router.patch("/{task_id}")
async def update_task(task_id: str, body: TaskUpdate):
    """Update a task by ID."""
    update_data = {k: v for k, v in body.dict().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    task = tasks.update_task(task_id, **update_data)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found or update failed")
    return task


@router.delete("/{task_id}")
async def delete_task(task_id: str):
    """Delete a task by ID."""
    success = tasks.delete_task(task_id)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "deleted", "id": task_id}


@router.get("/grouped/by-status")
async def get_tasks_by_status():
    """Get all tasks grouped by status (for Kanban view)."""
    return tasks.get_tasks_by_status()


@router.get("/user/{username}/tasks")
async def get_user_tasks(username: str):
    """Get all tasks assigned to a user."""
    return tasks.get_tasks_assigned_to(username)


@router.get("/user/{username}/sync-prompt")
async def get_sync_prompt(username: str):
    """
    Get AI timesheet sync prompt for a user.
    Returns task reminder if they have unstarted/overdue tasks.
    """
    prompt = tasks.get_sync_prompt_for_user(username)
    if not prompt:
        return {
            "type": "none",
            "message": "All caught up! No pending tasks.",
        }
    return prompt
