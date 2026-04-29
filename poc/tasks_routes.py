"""
Task Management API Routes
Endpoints for task CRUD, project metadata, and sync prompts.
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import tasks

router = APIRouter(prefix="/api", tags=["tasks"])


class TaskCreate(BaseModel):
    title: str
    project: str
    assignees: List[str] = []
    status: str = "Not started"
    priority: str = "Medium"
    due_date: Optional[str] = None
    budget: float = 0.0
    description: str = ""
    notes: str = ""
    attachments: List[dict] = []
    subtasks: List[dict] = []
    created_by: str = "System"


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    project: Optional[str] = None
    assignees: Optional[List[str]] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[str] = None
    budget: Optional[float] = None
    description: Optional[str] = None
    notes: Optional[str] = None
    attachments: Optional[List[dict]] = None
    subtasks: Optional[List[dict]] = None
    hours_logged: Optional[float] = None


# --- Projects (Overall Board) ---

@router.get("/projects")
async def list_projects():
    """Projects overview with aggregated task counts for the Board view."""
    return tasks.get_projects_overview()


@router.get("/projects/{name}")
async def get_project(name: str):
    p = tasks.get_project(name)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    proj_tasks = tasks.get_tasks_by_project(p["name"])
    return {**p, "tasks": proj_tasks}


# --- Tasks ---

@router.get("/tasks")
async def list_tasks(
    project: Optional[str] = None,
    assignee: Optional[str] = None,
    status: Optional[str] = None,
):
    return tasks.get_all_tasks(project=project, assignee=assignee, status=status)


@router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    task = tasks.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("/tasks")
async def create_task(body: TaskCreate):
    return tasks.create_task(
        title=body.title, project=body.project, assignees=body.assignees,
        status=body.status, priority=body.priority, due_date=body.due_date,
        budget=body.budget, description=body.description, notes=body.notes,
        attachments=body.attachments, subtasks=body.subtasks, created_by=body.created_by,
    )


@router.patch("/tasks/{task_id}")
async def update_task(task_id: str, body: TaskUpdate):
    update_data = {k: v for k, v in body.dict().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    task = tasks.update_task(task_id, **update_data)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found or update failed")
    return task


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    success = tasks.delete_task(task_id)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "deleted", "id": task_id}


@router.get("/tasks/grouped/by-status")
async def tasks_by_status():
    return tasks.get_tasks_by_status()


@router.get("/user/{username}/tasks")
async def user_tasks(username: str):
    return tasks.get_tasks_assigned_to(username)


@router.get("/user/{username}/sync-prompt")
async def sync_prompt(username: str):
    prompt = tasks.get_sync_prompt_for_user(username)
    if not prompt:
        return {"type": "none", "message": "All caught up! No pending tasks."}
    return prompt
