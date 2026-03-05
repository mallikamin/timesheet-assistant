"""
Harvest project/task mapping engine.
Structure: Client = Project, with multiple Tasks underneath.
See /harvest-structure.md for full documentation.
"""
from typing import Dict, List

# Harvest structure: each entry is a project (= client) with its tasks.
# Update this when Tariq provides the full Harvest export.
HARVEST_PROJECTS = [
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
    # Dummy projects for POC testing
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


def get_all_projects_for_prompt() -> str:
    """Format all projects and their tasks for the AI system prompt."""
    lines = []
    for p in HARVEST_PROJECTS:
        lines.append(f"\nProject: {p['project']}")
        for t in p["tasks"]:
            lines.append(f"  [{t['code']}] {t['name']}")
    return "\n".join(lines)
