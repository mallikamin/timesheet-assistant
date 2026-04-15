"""
Detailed Harvest API test with full error messages.
"""
import os
import httpx
from dotenv import load_dotenv

load_dotenv("poc/.env")

HARVEST_BASE = "https://api.harvestapp.com/api/v2"

token = os.getenv("HARVEST_ACCESS_TOKEN")
account_id = os.getenv("HARVEST_ACCOUNT_ID")

print("=" * 60)
print("DETAILED HARVEST API TEST")
print("=" * 60)
print(f"Account ID: {account_id}")
print(f"Token: {token[:30]}..." if token else "Token: MISSING")
print()

headers = {
    "Harvest-Account-ID": account_id,
    "Authorization": f"Bearer {token}",
    "User-Agent": "ThriveTimesheet",
}

# Test 1: Get current user (simplest endpoint)
print("1. Testing /users/me (current user)...")
try:
    resp = httpx.get(f"{HARVEST_BASE}/users/me", headers=headers, timeout=10)
    print(f"   Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"   [OK] Logged in as: {data.get('first_name')} {data.get('last_name')} ({data.get('email')})")
    else:
        print(f"   [ERROR] Response: {resp.text[:300]}")
except Exception as e:
    print(f"   [ERROR] Exception: {e}")

# Test 2: Get users
print("\n2. Testing /users...")
try:
    resp = httpx.get(f"{HARVEST_BASE}/users", headers=headers, params={"is_active": "true"}, timeout=10)
    print(f"   Status: {resp.status_code}")
    if resp.status_code == 200:
        users = resp.json().get("users", [])
        print(f"   [OK] Found {len(users)} users")
        for u in users[:5]:
            print(f"      - {u.get('first_name')} {u.get('last_name')} ({u.get('email')})")
    else:
        print(f"   [ERROR] Response: {resp.text[:300]}")
except Exception as e:
    print(f"   [ERROR] Exception: {e}")

# Test 3: Get projects
print("\n3. Testing /projects...")
try:
    resp = httpx.get(f"{HARVEST_BASE}/projects", headers=headers, params={"is_active": "true"}, timeout=10)
    print(f"   Status: {resp.status_code}")
    if resp.status_code == 200:
        projects = resp.json().get("projects", [])
        print(f"   [OK] Found {len(projects)} projects")
        for p in projects[:5]:
            print(f"      - {p.get('name')} (Client: {p.get('client', {}).get('name', 'N/A')})")
    else:
        print(f"   [ERROR] Response: {resp.text[:300]}")
except Exception as e:
    print(f"   [ERROR] Exception: {e}")

print("\n" + "=" * 60)
print("TEST COMPLETE")
print("=" * 60)
