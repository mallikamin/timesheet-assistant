"""
Harvest Account Data Snapshot Tool

Exports current Harvest account state (projects, tasks, users, time entries)
for safe testing comparison and rollback verification.

Usage:
    # Before testing (take baseline snapshot)
    python harvest_snapshot.py --before --token YOUR_HARVEST_TOKEN

    # After testing (take comparison snapshot)
    python harvest_snapshot.py --after --token YOUR_HARVEST_TOKEN

    # Compare results
    python harvest_snapshot.py --compare before.json after.json
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

# Add poc to path so we can import harvest_api
sys.path.insert(0, str(Path(__file__).parent / "poc"))

import harvest_api


def take_snapshot(access_token: str = None, snapshot_name: str = "before") -> str:
    """
    Export current Harvest account state.

    Args:
        access_token: Optional OAuth token (for testing). Falls back to PAT if None.
        snapshot_name: "before" or "after" - used in filename

    Returns:
        Filename of saved snapshot
    """
    print(f"\n{'='*60}")
    print(f"Taking Harvest snapshot: {snapshot_name}")
    print(f"{'='*60}")

    print("Fetching users...")
    users = harvest_api.get_users(access_token)
    print(f"  ✓ {len(users)} users")

    print("Fetching projects and tasks...")
    projects = harvest_api.get_projects_with_tasks(access_token)
    print(f"  ✓ {len(projects)} projects")

    print("Fetching time entries...")
    time_entries = harvest_api.get_time_entries(access_token=access_token)
    print(f"  ✓ {len(time_entries)} time entries")

    # Build snapshot
    snapshot = {
        "timestamp": datetime.now().isoformat(),
        "snapshot_name": snapshot_name,
        "harvest_account_id": os.getenv("HARVEST_ACCOUNT_ID"),
        "summary": {
            "total_users": len(users),
            "total_projects": len(projects),
            "total_tasks": sum(len(p["tasks"]) for p in projects),
            "total_time_entries": len(time_entries),
        },
        "users": [
            {
                "id": u["id"],
                "name": f"{u.get('first_name', '')} {u.get('last_name', '')}".strip(),
                "email": u.get("email"),
                "is_active": u.get("is_active"),
                "is_admin": u.get("is_admin"),
            }
            for u in users
        ],
        "projects": [
            {
                "id": p["project_id"],
                "name": p["project_name"],
                "client": p["client_name"],
                "task_count": len(p["tasks"]),
                "tasks": [
                    {"id": t["task_id"], "name": t["task_name"]}
                    for t in p["tasks"]
                ],
            }
            for p in projects
        ],
        "time_entries": [
            {
                "id": e["id"],
                "user_id": e.get("user", {}).get("id"),
                "user_name": e.get("user", {}).get("name"),
                "project_id": e.get("project", {}).get("id"),
                "project_name": e.get("project", {}).get("name"),
                "task_id": e.get("task", {}).get("id"),
                "task_name": e.get("task", {}).get("name"),
                "spent_date": e.get("spent_date"),
                "hours": e.get("hours"),
                "notes": e.get("notes", "")[:100],  # First 100 chars only
            }
            for e in time_entries
        ],
    }

    # Save to file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"harvest_snapshot_{snapshot_name}_{timestamp}.json"

    with open(filename, "w") as f:
        json.dump(snapshot, f, indent=2)

    print(f"\n✅ Snapshot saved: {filename}")
    print(f"\nSnapshot Summary:")
    print(f"  Account ID: {snapshot['harvest_account_id']}")
    print(f"  Users: {snapshot['summary']['total_users']}")
    print(f"  Projects: {snapshot['summary']['total_projects']}")
    print(f"  Tasks: {snapshot['summary']['total_tasks']}")
    print(f"  Time Entries: {snapshot['summary']['total_time_entries']}")

    return filename


def compare_snapshots(before_file: str, after_file: str) -> Dict[str, Any]:
    """
    Compare two snapshots and identify changes.

    Args:
        before_file: Path to "before" snapshot JSON
        after_file: Path to "after" snapshot JSON

    Returns:
        Dictionary with comparison results
    """
    print(f"\n{'='*60}")
    print("Comparing Harvest Snapshots")
    print(f"{'='*60}")

    with open(before_file) as f:
        before = json.load(f)
    with open(after_file) as f:
        after = json.load(f)

    print(f"Before: {before['timestamp']}")
    print(f"After:  {after['timestamp']}")

    # Compare time entries
    before_entries = {e["id"]: e for e in before["time_entries"]}
    after_entries = {e["id"]: e for e in after["time_entries"]}

    created_ids = set(after_entries.keys()) - set(before_entries.keys())
    deleted_ids = set(before_entries.keys()) - set(after_entries.keys())
    unchanged_ids = set(before_entries.keys()) & set(after_entries.keys())

    # Compare projects
    before_projects = {p["id"]: p for p in before["projects"]}
    after_projects = {p["id"]: p for p in after["projects"]}

    new_projects = set(after_projects.keys()) - set(before_projects.keys())
    deleted_projects = set(before_projects.keys()) - set(after_projects.keys())

    # Compile results
    results = {
        "time_entries": {
            "created": len(created_ids),
            "deleted": len(deleted_ids),
            "unchanged": len(unchanged_ids),
            "created_entries": [after_entries[eid] for eid in created_ids],
            "deleted_entries": [before_entries[eid] for eid in deleted_ids],
        },
        "projects": {
            "created": len(new_projects),
            "deleted": len(deleted_projects),
            "created_projects": [after_projects[pid] for pid in new_projects],
            "deleted_projects": [before_projects[pid] for pid in deleted_projects],
        },
    }

    # Print results
    print(f"\n{'='*40}")
    print("TIME ENTRIES")
    print(f"{'='*40}")
    print(f"Created: {results['time_entries']['created']}")
    if created_ids:
        for e in results["time_entries"]["created_entries"]:
            print(
                f"  ✓ [{e['id']}] {e['user_name']} - "
                f"{e['project_name']}/{e['task_name']} - {e['hours']}h"
            )
    else:
        print("  (none)")

    print(f"\nDeleted: {results['time_entries']['deleted']}")
    if deleted_ids:
        for e in results["time_entries"]["deleted_entries"]:
            print(
                f"  ✗ [{e['id']}] {e['user_name']} - "
                f"{e['project_name']}/{e['task_name']} - {e['hours']}h"
            )
    else:
        print("  (none)")

    print(f"\nUnchanged: {results['time_entries']['unchanged']}")

    print(f"\n{'='*40}")
    print("PROJECTS")
    print(f"{'='*40}")
    print(f"Created: {results['projects']['created']}")
    if new_projects:
        for p in results["projects"]["created_projects"]:
            print(f"  ✓ [{p['id']}] {p['name']} ({p['client']})")
    else:
        print("  (none)")

    print(f"\nDeleted: {results['projects']['deleted']}")
    if deleted_projects:
        for p in results["projects"]["deleted_projects"]:
            print(f"  ✗ [{p['id']}] {p['name']} ({p['client']})")
    else:
        print("  (none)")

    # Summary
    print(f"\n{'='*40}")
    print("SUMMARY")
    print(f"{'='*40}")
    total_changes = (
        results["time_entries"]["created"]
        + results["time_entries"]["deleted"]
        + results["projects"]["created"]
        + results["projects"]["deleted"]
    )

    if total_changes == 0:
        print("✅ NO CHANGES DETECTED - Account is identical")
    else:
        print(f"⚠️  {total_changes} changes detected:")
        print(f"   Time Entries: +{results['time_entries']['created']}, "
              f"-{results['time_entries']['deleted']}")
        print(f"   Projects: +{results['projects']['created']}, "
              f"-{results['projects']['deleted']}")

    # Save comparison to file
    comparison_file = f"harvest_comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(comparison_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n✅ Comparison saved: {comparison_file}")

    return results


def main():
    """CLI interface for snapshot tool."""
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    if command == "--before":
        # Take "before" snapshot
        token = None
        if "--token" in sys.argv:
            idx = sys.argv.index("--token")
            token = sys.argv[idx + 1]
        take_snapshot(token, "before")

    elif command == "--after":
        # Take "after" snapshot
        token = None
        if "--token" in sys.argv:
            idx = sys.argv.index("--token")
            token = sys.argv[idx + 1]
        take_snapshot(token, "after")

    elif command == "--compare":
        # Compare two snapshots
        if len(sys.argv) < 4:
            print("Usage: python harvest_snapshot.py --compare before.json after.json")
            sys.exit(1)
        before_file = sys.argv[2]
        after_file = sys.argv[3]
        compare_snapshots(before_file, after_file)

    elif command == "--help":
        print(__doc__)

    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
