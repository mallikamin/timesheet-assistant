"""
Seed Harvest account with dummy Thrive PR data.
Run once: python seed_harvest.py
"""
import json
import time

import httpx

TOKEN = "4285603.pt.xlhJYsPpa9XeCM-ObI34H_QkbJmymObCq66vBnhZpfBoOTRVObDY73qhVmYXO2D-V-pnGz0Wju3g4ThAfEDHVA"
ACCOUNT_ID = "2175490"
BASE = "https://api.harvestapp.com/api/v2"
HEADERS = {
    "Harvest-Account-ID": ACCOUNT_ID,
    "Authorization": f"Bearer {TOKEN}",
    "User-Agent": "ThriveTimesheet",
    "Content-Type": "application/json",
}

# Thrive's structure: client -> project -> tasks
THRIVE_STRUCTURE = {
    "Acuity": [
        "Existing Business Growth FY26",
        "New Business Growth FY26",
        "Operations & Admin FY26",
    ],
    "Afterpay": [
        "AUNZ Retainer 2026",
        "Arena Project",
        "Ads Project Mar-Dec 2026",
        "NZ PR Retainer Mar-Dec 2026",
    ],
    "AGL": [
        "Existing Growth",
    ],
    "CommBank": [
        "Brand Campaign 2026",
    ],
    "Telstra": [
        "Digital Transformation",
    ],
    "Thrive (Internal)": [
        "Operations & Admin",
        "Business Development",
    ],
}


def api(method, path, data=None):
    """Make Harvest API call with rate limit handling."""
    time.sleep(0.2)  # respect rate limits
    if method == "GET":
        r = httpx.get(f"{BASE}{path}", headers=HEADERS)
    elif method == "POST":
        r = httpx.post(f"{BASE}{path}", headers=HEADERS, json=data)
    if r.status_code >= 400:
        print(f"  ERROR {r.status_code}: {r.text[:200]}")
        return None
    return r.json()


def main():
    print("=== Seeding Harvest Account ===\n")

    # Step 1: Create clients
    print("--- Creating Clients ---")
    client_ids = {}
    for name in THRIVE_STRUCTURE:
        result = api("POST", "/clients", {"name": name, "currency": "AUD"})
        if result:
            client_ids[name] = result["id"]
            print(f"  Client: {name} -> ID {result['id']}")

    # Step 2: Create global tasks
    print("\n--- Creating Tasks ---")
    all_task_names = set()
    for tasks in THRIVE_STRUCTURE.values():
        all_task_names.update(tasks)

    task_ids = {}
    # Check existing tasks first
    existing = api("GET", "/tasks")
    if existing:
        for t in existing["tasks"]:
            task_ids[t["name"]] = t["id"]
            print(f"  Existing task: {t['name']} -> ID {t['id']}")

    for task_name in sorted(all_task_names):
        if task_name in task_ids:
            continue
        result = api("POST", "/tasks", {
            "name": task_name,
            "billable_by_default": True,
            "is_default": False,
        })
        if result:
            task_ids[result["name"]] = result["id"]
            print(f"  Created task: {result['name']} -> ID {result['id']}")

    # Step 3: Create projects (one per client) and assign tasks
    print("\n--- Creating Projects & Assigning Tasks ---")
    for client_name, task_list in THRIVE_STRUCTURE.items():
        if client_name not in client_ids:
            print(f"  SKIP {client_name} — no client ID")
            continue

        # Create project
        project = api("POST", "/projects", {
            "client_id": client_ids[client_name],
            "name": client_name,
            "is_billable": True,
            "bill_by": "Project",
            "budget_by": "none",
        })
        if not project:
            print(f"  FAILED to create project for {client_name}")
            continue

        project_id = project["id"]
        print(f"  Project: {client_name} -> ID {project_id}")

        # Assign tasks to project
        for task_name in task_list:
            if task_name not in task_ids:
                print(f"    SKIP task {task_name} — no task ID")
                continue
            assignment = api("POST", f"/projects/{project_id}/task_assignments", {
                "task_id": task_ids[task_name],
            })
            if assignment:
                print(f"    Assigned: {task_name} (task_id={task_ids[task_name]})")

    # Step 4: Print summary
    print("\n=== Summary ===")
    projects = api("GET", "/projects")
    if projects:
        for p in projects["projects"]:
            client_name = p["client"]["name"] if p["client"] else "No client"
            print(f"\n  Project: {p['name']} (ID: {p['id']}) — Client: {client_name}")
            assignments = api("GET", f"/projects/{p['id']}/task_assignments")
            if assignments:
                for a in assignments["task_assignments"]:
                    print(f"    Task: {a['task']['name']} (task_id: {a['task']['id']})")

    print("\n=== Done! ===")


if __name__ == "__main__":
    main()
