"""
Harvest project/task mapping engine.
Maps natural language project references to Harvest project codes.
"""
from typing import Dict, List, Optional

# Known Harvest projects (from screenshots + dummy data for POC)
HARVEST_PROJECTS = [
    {
        "client": "Acuity",
        "code": "6-1000",
        "project": "Acuity - Existing Business Growth FY26",
        "tasks": ["Strategy", "Client Management", "Reporting", "General"],
        "keywords": ["acuity", "existing", "existing business", "existing growth"],
    },
    {
        "client": "Acuity",
        "code": "6-1000",
        "project": "Acuity - New Business Growth FY26",
        "tasks": ["Pitching", "Proposals", "Lead Generation", "General"],
        "keywords": ["acuity new", "new business", "acuity pitch", "acuity proposal"],
    },
    {
        "client": "Acuity",
        "code": "6-1003",
        "project": "Acuity - Operations & Admin FY26",
        "tasks": ["Admin", "Operations", "Internal Meetings", "General"],
        "keywords": ["acuity ops", "acuity admin", "acuity operations", "acuity internal"],
    },
    {
        "client": "Afterpay Australia Pty Ltd",
        "code": "2-00049",
        "project": "Afterpay - AUNZ Retainer 2026",
        "tasks": ["PR", "Media Relations", "Content", "Reporting", "General"],
        "keywords": ["afterpay", "afterpay retainer", "afterpay aunz", "afterpay pr"],
    },
    {
        "client": "Afterpay Australia Pty Ltd",
        "code": "2-1099",
        "project": "Afterpay Arena Project",
        "tasks": ["Event Management", "Coordination", "Content", "General"],
        "keywords": ["afterpay arena", "arena project", "arena"],
    },
    {
        "client": "Afterpay Australia Pty Ltd",
        "code": "2-1100",
        "project": "Afterpay Ads Project - March 2026 - December 2026",
        "tasks": ["Campaign", "Creative", "Media Buying", "Reporting", "General"],
        "keywords": ["afterpay ads", "afterpay advertising", "afterpay campaign"],
    },
    {
        "client": "Afterpay Australia Pty Ltd",
        "code": "4-0048",
        "project": "Afterpay Animates",
        "tasks": ["Animation", "Creative", "Production", "General"],
        "keywords": ["afterpay animates", "animates", "afterpay animation"],
    },
    {
        "client": "Afterpay Australia Pty Ltd",
        "code": "4-0049",
        "project": "Afterpay NZ PR Retainer - March - December 2026",
        "tasks": ["PR", "Media Relations", "Content", "General"],
        "keywords": ["afterpay nz", "afterpay new zealand", "afterpay nz pr"],
    },
    {
        "client": "AGL",
        "code": "AGL-001",
        "project": "AGL - Existing Growth",
        "tasks": ["Strategy", "Client Management", "Reporting", "General"],
        "keywords": ["agl", "agl growth", "agl existing"],
    },
    # Dummy projects for POC testing
    {
        "client": "CommBank",
        "code": "CB-001",
        "project": "CommBank - Brand Campaign 2026",
        "tasks": ["Campaign", "Creative", "Strategy", "Media", "General"],
        "keywords": ["commbank", "commonwealth", "cba", "commbank brand"],
    },
    {
        "client": "Telstra",
        "code": "TEL-001",
        "project": "Telstra - Digital Transformation",
        "tasks": ["Digital", "Strategy", "Content", "Reporting", "General"],
        "keywords": ["telstra", "telstra digital"],
    },
    {
        "client": "Internal",
        "code": "INT-001",
        "project": "Internal - Operations & Admin",
        "tasks": ["Admin", "Team Meetings", "Training", "HR", "General"],
        "keywords": ["internal", "admin", "ops", "team meeting", "standup", "all hands", "training", "hr"],
    },
    {
        "client": "Internal",
        "code": "INT-002",
        "project": "Internal - Business Development",
        "tasks": ["Pitching", "Proposals", "Networking", "General"],
        "keywords": ["bizdev", "biz dev", "business development", "new client", "pitch"],
    },
]


def find_matching_projects(query: str) -> List[Dict]:
    """
    Find projects matching a natural language query.
    Returns list of matches with confidence scores.
    """
    query_lower = query.lower().strip()
    matches = []

    for project in HARVEST_PROJECTS:
        score = 0
        # Check client name
        if project["client"].lower() in query_lower:
            score += 50
        # Check keywords
        for keyword in project["keywords"]:
            if keyword in query_lower:
                score += 30
        # Check project name words
        for word in project["project"].lower().split():
            if len(word) > 3 and word in query_lower:
                score += 10

        if score > 0:
            matches.append({
                **project,
                "confidence": min(score, 100),
            })

    matches.sort(key=lambda x: x["confidence"], reverse=True)
    return matches


def get_all_projects_for_prompt() -> str:
    """Format all projects as a string for the AI system prompt."""
    lines = []
    current_client = None
    for p in HARVEST_PROJECTS:
        if p["client"] != current_client:
            current_client = p["client"]
            lines.append(f"\n{current_client}:")
        tasks_str = ", ".join(p["tasks"])
        lines.append(f"  [{p['code']}] {p['project']} (Tasks: {tasks_str})")
    return "\n".join(lines)
