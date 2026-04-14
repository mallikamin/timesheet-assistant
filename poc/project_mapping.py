"""
Harvest project/task mapping engine.
Pulls live data from Harvest API when available, falls back to hardcoded.
Structure: Client = Project, with multiple Tasks underneath.
"""
from typing import Dict, List

import harvest_api

# Hardcoded fallback — used when Harvest API is not configured or unavailable
HARVEST_PROJECTS_FALLBACK = [
    {
        "project": "Acuity",
        "keywords": ["acuity"],
        "tasks": [
            {"code": "6-1000", "name": "Existing Business Growth FY26", "keywords": ["existing", "existing business", "existing growth"]},
            {"code": "6-1000", "name": "New Business Growth FY26", "keywords": ["new business", "new growth", "pitch", "proposal"]},
            {"code": "6-1003", "name": "Operations & Admin FY26", "keywords": ["ops", "admin", "operations", "internal"]},
        ],
    },
    {
        "project": "Afterpay",
        "keywords": ["afterpay"],
        "tasks": [
            {"code": "2-00049", "name": "AUNZ Retainer 2026", "keywords": ["retainer", "aunz", "pr"]},
            {"code": "2-1099", "name": "Arena Project", "keywords": ["arena"]},
            {"code": "2-1100", "name": "Ads Project Mar-Dec 2026", "keywords": ["ads", "advertising", "campaign"]},
            {"code": "4-0048", "name": "Animates", "keywords": ["animates", "animation"]},
            {"code": "4-0049", "name": "NZ PR Retainer Mar-Dec 2026", "keywords": ["nz", "new zealand", "nz pr"]},
        ],
    },
    {
        "project": "AGL",
        "keywords": ["agl"],
        "tasks": [
            {"code": "AGL-001", "name": "Existing Growth", "keywords": ["growth", "existing"]},
        ],
    },
    {
        "project": "CommBank",
        "keywords": ["commbank", "commonwealth", "cba"],
        "tasks": [
            {"code": "CB-001", "name": "Brand Campaign 2026", "keywords": ["brand", "campaign", "creative"]},
        ],
    },
    {
        "project": "Telstra",
        "keywords": ["telstra"],
        "tasks": [
            {"code": "TEL-001", "name": "Digital Transformation", "keywords": ["digital", "transformation"]},
        ],
    },
    {
        "project": "Internal",
        "keywords": ["internal", "admin", "ops", "team meeting", "standup", "all hands", "training", "hr"],
        "tasks": [
            {"code": "INT-001", "name": "Operations & Admin", "keywords": ["admin", "ops", "meeting", "standup", "all hands", "training", "hr"]},
            {"code": "INT-002", "name": "Business Development", "keywords": ["bizdev", "biz dev", "business development", "new client", "pitch", "networking"]},
        ],
    },
]


def _load_from_harvest(access_token: str = None) -> List[Dict]:
    """Pull live project/task data from Harvest API and format for the prompt."""
    if not harvest_api.is_configured() and not access_token:
        return []

    projects = harvest_api.get_projects_with_tasks(access_token)
    if not projects:
        return []

    result = []
    for p in projects:
        # Skip the default Example Project
        if p["project_name"] == "Example Project":
            continue
        # Filter to only our custom tasks (skip Harvest defaults like Design, Programming)
        default_tasks = {"Design", "Programming", "Marketing", "Project Management", "Vacation"}
        custom_tasks = [t for t in p["tasks"] if t["task_name"] not in default_tasks]

        if not custom_tasks:
            continue

        result.append({
            "project": p["project_name"],
            "keywords": [p["project_name"].lower().split("(")[0].strip()],
            "tasks": [
                {
                    "code": f"{p['project_id']}-{t['task_id']}",
                    "name": t["task_name"],
                    "keywords": [w.lower() for w in t["task_name"].split() if len(w) > 2],
                    "harvest_project_id": p["project_id"],
                    "harvest_task_id": t["task_id"],
                }
                for t in custom_tasks
            ],
        })

    return result


def get_projects(access_token: str = None) -> List[Dict]:
    """Get project list — live from Harvest if available, otherwise fallback."""
    live = _load_from_harvest(access_token)
    if live:
        return live
    return HARVEST_PROJECTS_FALLBACK


def get_all_projects_for_prompt(access_token: str = None) -> str:
    """Format all projects and their tasks for the AI system prompt."""
    projects = get_projects(access_token)
    lines = []
    for p in projects:
        lines.append(f"\nProject: {p['project']}")
        for t in p["tasks"]:
            lines.append(f"  [{t['code']}] {t['name']}")
    return "\n".join(lines)
