"""
Harvest OAuth2 token management.
Handles token refresh and expiry checking for Harvest API access.
"""

import os
import time
from typing import Dict, Optional

import httpx

TOKEN_ENDPOINT = "https://id.getharvest.com/api/v2/oauth2/token"


def is_token_expired(harvest_token: Dict) -> bool:
    """Check if the access token is expired (with 60s buffer)."""
    expires_at = harvest_token.get("expires_at", 0)
    return time.time() > (expires_at - 60)


def refresh_access_token(refresh_token: str) -> Optional[Dict]:
    """Use a refresh token to get a new access token from Harvest."""
    client_id = os.getenv("HARVEST_CLIENT_ID", "")
    client_secret = os.getenv("HARVEST_CLIENT_SECRET", "")

    if not refresh_token or not client_id:
        return None

    try:
        resp = httpx.post(
            TOKEN_ENDPOINT,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            timeout=10,
        )

        if resp.status_code != 200:
            print(f"Harvest token refresh failed: {resp.status_code} {resp.text[:200]}")
            return None

        data = resp.json()
        return {
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token", refresh_token),  # Harvest may issue new refresh token
            "expires_at": time.time() + data.get("expires_in", 1209600),  # 14 days default
        }
    except Exception as e:
        print(f"Harvest token refresh error: {e}")
        return None


def ensure_valid_token(harvest_token: Dict) -> Optional[Dict]:
    """Return a valid token dict, refreshing if needed. Returns None if can't refresh."""
    if not harvest_token:
        return None

    if not is_token_expired(harvest_token):
        return harvest_token

    refresh_token = harvest_token.get("refresh_token", "")
    if not refresh_token:
        return None

    refreshed = refresh_access_token(refresh_token)
    if not refreshed:
        return None

    # Merge — keep the refresh_token (or use new one), update access_token and expires_at
    return refreshed
