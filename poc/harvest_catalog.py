"""Harvest catalog — single source of truth for project + task naming.

Loaded from `data/harvest_master/projects_2026-05-06.csv` (107 active
projects from Thrive's Harvest account 310089). The constants below for
LEAVE and INTERNAL_PROJECTS were derived from
`time_report_rolling12mo_2026-05-06.xlsx` — the actual usage-ranked task
names people log to.

Use this module for:
  - System prompt examples (so the AI generates names that match Harvest)
  - Resolver fallback when live Harvest fetch is unavailable
  - Tests that need a real project structure without mocking the API

Live runtime resolution still goes through harvest_api.get_projects_with_tasks
against the actual Harvest API — this catalog is a frozen snapshot for
prompt-time + offline-time ground truth.

To refresh: drop new exports into data/harvest_master/ with a new date
suffix and update the CATALOG_DATE + file paths below.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

CATALOG_DATE = "2026-05-06"
_CATALOG_DIR = Path(__file__).parent / "data" / "harvest_master"
_PROJECTS_CSV = _CATALOG_DIR / f"projects_{CATALOG_DATE}.csv"


# --- Leave: ground-truth from the FY26 time report (1,852 entries) ---

LEAVE_PROJECT_NAME = "Thrive Leave FY26"
LEAVE_PROJECT_CODE = "3-0006"
LEAVE_PROJECT_CLIENT = "Thrive PR"

# Ordered by usage in the last 12 months (verified against /users/me/
# project_assignments diagnostic 2026-05-06 — Maternity Leave was
# missing from time-report data because no one logged it in the 12mo
# window, but it's an active task assignment in Harvest). The "Leave - "
# prefix is the Harvest convention — the AI must generate task names
# with this prefix or the resolver substring-fallback will kick in.
LEAVE_TASKS: Tuple[str, ...] = (
    "Leave - Annual Leave",
    "Leave - Public Holiday Leave",
    "Leave - Sick / Carer Leave",
    "Leave - Friday 4pm Finish",
    "Leave - Unpaid Leave",
    "Leave - Time in Lieu Leave",
    "Leave - Wellness Day Leave",
    "Leave - Compassionate Leave (paid)",
    "Leave - Compassionate Leave (unpaid)",
    "Leave - Maternity Leave",
    "Leave - Jury Duty Leave",
)

# Natural-language phrase -> canonical Harvest task name. Used by the
# prompt to guide the AI; the resolver itself relies on substring match.
LEAVE_PHRASE_TO_TASK: Dict[str, str] = {
    "annual leave": "Leave - Annual Leave",
    "annual": "Leave - Annual Leave",
    "vacation": "Leave - Annual Leave",
    "holiday off": "Leave - Annual Leave",
    "sick leave": "Leave - Sick / Carer Leave",
    "sick": "Leave - Sick / Carer Leave",
    "carer leave": "Leave - Sick / Carer Leave",
    "carers leave": "Leave - Sick / Carer Leave",
    "carer": "Leave - Sick / Carer Leave",
    "public holiday": "Leave - Public Holiday Leave",
    "phl": "Leave - Public Holiday Leave",
    "unpaid leave": "Leave - Unpaid Leave",
    "unpaid": "Leave - Unpaid Leave",
    "time in lieu": "Leave - Time in Lieu Leave",
    "til": "Leave - Time in Lieu Leave",
    "lieu": "Leave - Time in Lieu Leave",
    "wellness day": "Leave - Wellness Day Leave",
    "wellness": "Leave - Wellness Day Leave",
    "mental health day": "Leave - Wellness Day Leave",
    "compassionate leave": "Leave - Compassionate Leave (paid)",
    "compassionate": "Leave - Compassionate Leave (paid)",
    "funeral leave": "Leave - Compassionate Leave (paid)",
    "funeral": "Leave - Compassionate Leave (paid)",
    "bereavement": "Leave - Compassionate Leave (paid)",
    "jury duty": "Leave - Jury Duty Leave",
    "jury": "Leave - Jury Duty Leave",
    "maternity leave": "Leave - Maternity Leave",
    "maternity": "Leave - Maternity Leave",
    "parental leave": "Leave - Maternity Leave",
    "friday 4pm": "Leave - Friday 4pm Finish",
    "friday finish": "Leave - Friday 4pm Finish",
    "early friday": "Leave - Friday 4pm Finish",
}


# --- Internal Thrive projects: ground-truth from the 12mo time report ---
# Tuple format: (project_name, project_code, top_tasks_by_usage)

INTERNAL_PROJECTS: Tuple[Tuple[str, str, Tuple[str, ...]], ...] = (
    ("Thrive Operation FY26", "3-0011", (
        "Thrive Operation - Office Management",
        "Thrive Operation - Reporting & WIPs",
        "Thrive Operation - e-Sign Management",
        "Thrive Operation - ELT Management",
        "Thrive Operation - Property Management",
    )),
    ("Thrive P&C Operation FY26", "3-0012", (
        "Thrive P&C - Reporting & WIPs",
        "Thrive P&C - Recruitment",
        "Thrive P&C - Employee Reviews",
        "Thrive P&C - Policy Development",
    )),
    ("Thrive Finance Operation FY26", "3-0013", (
        "Thrive Finance - Bank Reconciliation",
        "Thrive Finance - Bills & Accounts Payable",
        "Thrive Finance - Systems & Process Improvement",
        "Thrive Finance - Estimates + Invoicing",
        "Thrive Finance - Accounts Receivables",
        "Thrive Finance - Payroll",
        "Thrive Finance - Tax and Accounting",
    )),
    ("Thrive Finance Support FY26", "3-0014", (
        "Thrive Finance - Reporting & WIPs",
    )),
    ("Thrive Learning & Development FY26", "3-0001", (
        "Thrive L&D - Weekly Planning",
        "Thrive L&D - Peer Support",
        "Thrive L&D - Agency WIPs",
        "Thrive L&D - Local WIPs",
        "Thrive L&D - New Staff Induction",
        "Thrive L&D - Innovation and Research",
        "Thrive L&D - Intern Program",
        "Thrive L&D - On-the-Job Training",
        "Thrive L&D - Industry Networking and Training",
        "Thrive L&D - SLT WIPs",
    )),
    ("Thrive Culture & Social FY26", "3-0002", (
        "Thrive Culture - Thrive O’Clock",
        "Thrive Culture - Social Events",
        "Thrive Culture - Office Support",
    )),
    ("Thrive Social Media & Content FY26", "3-0003", (
        "Thrive Content - Social Media & Content",
        "Thrive Content - Case Studies",
        "Thrive Content - Reporting",
    )),
    ("Thrive Marketing & Brand FY26", "3-0016", (
        "Thrive Brand - Content Development",
        "Thrive Brand - Reporting & WIPs",
        "Thrive Brand - Template Updates",
        "Thrive Brand - Industry Awards",
    )),
    ("Thrive IT Operation FY26", "3-0015", (
        "Thrive IT - Daily Support",
        "Thrive IT - Reporting & WIPs",
        "Thrive IT - Tech Supplier Management",
        "Thrive IT - Hardware Setup and Support",
    )),
    ("Thrive IT Support FY26", "3-0005", (
        "Thrive IT - System Issues and Support",
    )),
    ("Thrive ELT FY26", "3-0018", (
        "Thrive ELT - WOB, WIP & Planning Meetings",
        "Thrive ELT - ESP",
    )),
    ("Thrive Legal Operation FY26", "3-0017", (
        "Thrive Legal - IP",
    )),
    ("Thrive New Business - Existing Growth FY26", "3-0004", (
        "Thrive Existing Growth - <client name>",
    )),
    ("Thrive New Business - New Growth FY26", "3-0004", (
        "Thrive Growth - Reporting & WIPs",
        "Thrive Growth - Creating Creds Decks",
        "Thrive Growth - Outreach",
        "Thrive Growth - Inbound Enquiries",
        "Thrive Growth - External Meetings",
    )),
    ("Thrive Innovation Project", "", (
        "Thrive - Digital Champions",
        "Thrive - Innovation Project",
    )),
)


@dataclass(frozen=True)
class Project:
    code: str
    name: str
    client: str


_projects_cache: Optional[List[Project]] = None


def _load_projects() -> List[Project]:
    """Read the projects CSV. Lazy-loaded + memoised."""
    global _projects_cache
    if _projects_cache is not None:
        return _projects_cache
    if not _PROJECTS_CSV.exists():
        _projects_cache = []
        return _projects_cache
    out: List[Project] = []
    with _PROJECTS_CSV.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            out.append(Project(
                code=(row.get("Project Code") or "").strip(),
                name=(row.get("Project") or "").strip(),
                client=(row.get("Client") or "").strip(),
            ))
    _projects_cache = out
    return out


def all_projects() -> List[Project]:
    """All 107 active projects from the latest snapshot."""
    return list(_load_projects())


def find_project(phrase: str) -> Optional[Project]:
    """Find an active project by exact-or-substring match against project
    name or client name. Returns the first match or None.

    Used by the resolver as a fallback when live Harvest fetch fails."""
    if not phrase:
        return None
    p_lower = phrase.strip().lower()
    projects = _load_projects()
    # Tier 1: exact match on project name
    for p in projects:
        if p.name.lower() == p_lower:
            return p
    # Tier 2: exact match on client name (returns first project for that client)
    for p in projects:
        if p.client.lower() == p_lower:
            return p
    # Tier 3: substring match on project name
    for p in projects:
        if p_lower in p.name.lower():
            return p
    # Tier 4: substring match on client name (returns first project for that client)
    for p in projects:
        if p_lower in p.client.lower():
            return p
    return None


def find_project_candidates(phrase: str, limit: int = 5) -> List[Project]:
    """Return up to `limit` projects whose name or client matches `phrase`
    by substring. Used to surface "did you mean X?" candidates in error
    messages when exact resolution fails."""
    if not phrase:
        return []
    p_lower = phrase.strip().lower()
    seen = set()
    out: List[Project] = []
    for p in _load_projects():
        if p_lower in p.name.lower() or p_lower in p.client.lower():
            key = (p.client, p.name)
            if key not in seen:
                seen.add(key)
                out.append(p)
                if len(out) >= limit:
                    break
    return out


def leave_task_for_phrase(phrase: str) -> Optional[str]:
    """Map a natural-language leave description to the canonical Harvest
    task name. Returns None if no leave keyword is recognised."""
    if not phrase:
        return None
    p_lower = phrase.lower()
    for kw, task in LEAVE_PHRASE_TO_TASK.items():
        if kw in p_lower:
            return task
    return None
