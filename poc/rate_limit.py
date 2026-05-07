"""
Per-user token-bucket rate limiter for /api/chat.

Three layers of protection:
  1. Burst limit: BUCKET_CAPACITY chat calls, refilling REFILL_RATE/sec.
  2. Per-user daily Anthropic-token cap: DAILY_TOKEN_CAP, rolling 24h.
  3. Org-wide rolling-hour Anthropic-token ceiling: HOURLY_BUDGET_CEILING.

Layer 1 stops a single misbehaving client. Layers 2 and 3 stop a slow-burn
abuse pattern that would never trip Layer 1, and bound the worst-case
Anthropic invoice if a bug ships that loops forever.

In-memory only — fine for the current single-worker Render deploy. On the
upcoming VPS, swap for a Redis-backed implementation (public API stays
the same).
"""

import os
import threading
import time
from collections import deque
from typing import Deque, Dict, Tuple

BUCKET_CAPACITY = 30          # max burst (also starting tokens for new users)
REFILL_RATE = 30.0 / 60.0     # 30 chats per minute sustained = 0.5 tok/sec

# Anthropic-token budgets (input + output, billed tokens — cache_read counts
# at face value here for safety, even though Anthropic charges 10% on it).
DAILY_TOKEN_CAP = int(os.environ.get("DAILY_TOKEN_CAP", "500000"))
HOURLY_BUDGET_CEILING = int(os.environ.get("HOURLY_BUDGET_CEILING", "10000000"))
_DAY_SECS = 24 * 3600
_HOUR_SECS = 3600

_buckets: Dict[str, Tuple[float, float]] = {}   # email -> (current_tokens, last_seen_ts)
_lock = threading.Lock()

# Rolling token-spend windows. Each entry is (timestamp, tokens). Stale
# entries are evicted lazily on access.
_user_spend: Dict[str, Deque[Tuple[float, int]]] = {}
_org_spend: Deque[Tuple[float, int]] = deque()
_spend_lock = threading.Lock()


def check_and_consume(user_email: str, cost: float = 1.0) -> Tuple[bool, float]:
    """Try to consume `cost` tokens for `user_email`. Returns
    (allowed, retry_after_seconds). retry_after is 0 when allowed."""
    if not user_email:
        # Unauthenticated requests are blocked elsewhere by session check;
        # don't pollute the buckets dict with empty keys.
        return True, 0.0

    now = time.time()
    key = user_email.lower().strip()

    with _lock:
        tokens, last = _buckets.get(key, (BUCKET_CAPACITY, now))
        # Refill tokens earned since last check
        elapsed = now - last
        tokens = min(BUCKET_CAPACITY, tokens + elapsed * REFILL_RATE)

        if tokens >= cost:
            tokens -= cost
            _buckets[key] = (tokens, now)
            return True, 0.0

        # Not enough tokens — compute time until cost is available
        deficit = cost - tokens
        retry_after = deficit / REFILL_RATE
        _buckets[key] = (tokens, now)
        return False, retry_after


def _evict(window: Deque[Tuple[float, int]], now: float, horizon: float) -> int:
    """Drop entries older than `horizon` from the left and return the
    remaining sum. Mutates `window` in place."""
    cutoff = now - horizon
    while window and window[0][0] < cutoff:
        window.popleft()
    return sum(toks for _, toks in window)


def check_token_budget(user_email: str) -> Tuple[bool, str, int]:
    """Check Anthropic-token budgets BEFORE making a request. Returns
    (allowed, reason_when_blocked, retry_after_seconds).

    Two budgets enforced:
      - per-user 24h rolling tokens (DAILY_TOKEN_CAP)
      - org-wide 1h rolling tokens (HOURLY_BUDGET_CEILING)
    """
    now = time.time()
    key = (user_email or "").lower().strip()

    with _spend_lock:
        if key:
            user_window = _user_spend.get(key)
            user_used = _evict(user_window, now, _DAY_SECS) if user_window else 0
            if user_used >= DAILY_TOKEN_CAP:
                # The oldest entry will expire first; that's when budget reopens.
                oldest_ts = user_window[0][0] if user_window else now
                retry = max(60, int(_DAY_SECS - (now - oldest_ts)))
                return False, "daily_token_cap", retry

        org_used = _evict(_org_spend, now, _HOUR_SECS)
        if org_used >= HOURLY_BUDGET_CEILING:
            oldest_ts = _org_spend[0][0] if _org_spend else now
            retry = max(60, int(_HOUR_SECS - (now - oldest_ts)))
            return False, "org_hourly_budget", retry

    return True, "", 0


def record_token_usage(user_email: str, tokens: int) -> None:
    """Record `tokens` against the user's daily window and the org hourly
    window. Called after every Anthropic API call, summing
    input_tokens + output_tokens (cache_read counted at face value as a
    safety margin)."""
    if tokens <= 0:
        return
    now = time.time()
    key = (user_email or "").lower().strip()
    with _spend_lock:
        if key:
            window = _user_spend.setdefault(key, deque())
            window.append((now, tokens))
        _org_spend.append((now, tokens))


def usage_snapshot(user_email: str) -> Dict[str, int]:
    """Public: return current per-user and org rolling-window usage. Used
    by the admin endpoint to surface live spend without scraping JSONL."""
    now = time.time()
    key = (user_email or "").lower().strip()
    with _spend_lock:
        user_window = _user_spend.get(key)
        user_used = _evict(user_window, now, _DAY_SECS) if user_window else 0
        org_used = _evict(_org_spend, now, _HOUR_SECS)
    return {
        "user_daily_tokens": user_used,
        "user_daily_cap": DAILY_TOKEN_CAP,
        "org_hourly_tokens": org_used,
        "org_hourly_cap": HOURLY_BUDGET_CEILING,
    }


def reset(user_email: str) -> None:
    """Test/admin helper — drop a user's bucket and token windows."""
    if not user_email:
        return
    key = user_email.lower().strip()
    with _lock:
        _buckets.pop(key, None)
    with _spend_lock:
        _user_spend.pop(key, None)


def reset_all() -> None:
    """Test helper — drop every bucket and every spend window. Lets each
    test start from a clean slate without leaking state across tests."""
    with _lock:
        _buckets.clear()
    with _spend_lock:
        _user_spend.clear()
        _org_spend.clear()
