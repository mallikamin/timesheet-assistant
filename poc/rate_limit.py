"""
Per-user token-bucket rate limiter for /api/chat.

Each user gets BUCKET_CAPACITY tokens, refilling at REFILL_RATE/sec. Each
chat call costs 1 token. When empty, the call is denied with a Retry-After
hint in seconds.

In-memory only — fine for the current single-worker Render deploy. On the
upcoming VPS with multiple workers, swap for a Redis-backed implementation
(public API stays the same: check_and_consume(email) -> (allowed, retry_after)).

Why this exists: stops a runaway loop or abusive user from blowing through
the Anthropic budget. 30/min sustained + 30 burst is plenty for real chat
use; an actual user can't physically chat that fast.
"""

import threading
import time
from typing import Dict, Tuple

BUCKET_CAPACITY = 30          # max burst (also starting tokens for new users)
REFILL_RATE = 30.0 / 60.0     # 30 chats per minute sustained = 0.5 tok/sec

_buckets: Dict[str, Tuple[float, float]] = {}   # email -> (current_tokens, last_seen_ts)
_lock = threading.Lock()


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


def reset(user_email: str) -> None:
    """Test/admin helper — drop a user's bucket so the next call sees a full one."""
    if not user_email:
        return
    with _lock:
        _buckets.pop(user_email.lower().strip(), None)
