"""
Quick test script to verify Thrive Harvest API connection.
"""
import os
import sys
from pathlib import Path

# Add poc directory to path
sys.path.insert(0, str(Path(__file__).parent / "poc"))

from dotenv import load_dotenv
load_dotenv("poc/.env")

import harvest_api

print("=" * 60)
print("THRIVE HARVEST API CONNECTION TEST")
print("=" * 60)

# Check configuration
print("\n1. Checking credentials...")
if harvest_api.is_configured():
    print("[OK] Credentials loaded")
    print(f"   Account ID: {os.getenv('HARVEST_ACCOUNT_ID')}")
    print(f"   Token: {os.getenv('HARVEST_ACCESS_TOKEN')[:20]}...")
else:
    print("[ERROR] Credentials missing")
    sys.exit(1)

# Test users endpoint
print("\n2. Testing users endpoint...")
try:
    users = harvest_api.get_users()
    if users:
        print(f"[OK] Found {len(users)} active users:")
        for u in users[:10]:  # Show first 10
            print(f"   - {u.get('first_name')} {u.get('last_name')} ({u.get('email')})")
    else:
        print("[WARN] No users found (or API error)")
except Exception as e:
    print(f"[ERROR] {e}")

# Test projects endpoint
print("\n3. Testing projects endpoint...")
try:
    projects = harvest_api.get_projects_with_tasks()
    if projects:
        print(f"[OK] Found {len(projects)} active projects:")
        for p in projects[:5]:  # Show first 5
            print(f"   - {p['project_name']} ({p['client_name']}) - {len(p['tasks'])} tasks")
    else:
        print("[WARN] No projects found (or API error)")
except Exception as e:
    print(f"[ERROR] {e}")

print("\n" + "=" * 60)
print("TEST COMPLETE")
print("=" * 60)
