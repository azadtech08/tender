"""Redis-backed sliding-window rate limiter.

Uses simple INCR + EXPIRE. Two helpers:
  * ``check_per_minute(key, limit)``   — bucket per minute
  * ``check_per_day(key, limit)``      — bucket per UTC calendar day

Each helper returns ``True`` if the call is allowed (counter incremented),
``False`` if the limit is exhausted. Failures to talk to Redis are treated
as ``allowed`` to avoid hard-failing the request path on infra hiccups —
log the error, keep going. (Per Phase 0 §3.1 spirit: don't deny customers
because of our outages.)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import redis.asyncio as redis_async
import structlog

from config import settings

logger = structlog.get_logger()

_redis_client: Optional[redis_async.Redis] = None


def _get_client() -> redis_async.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis_async.from_url(
            settings.redis_url, decode_responses=True
        )
    return _redis_client


async def _incr_with_expire(bucket_key: str, ttl_seconds: int, limit: int) -> bool:
    """Atomically increment the bucket and set TTL on first hit.

    Returns True if the post-increment count is <= limit.
    """
    try:
        client = _get_client()
        async with client.pipeline(transaction=True) as pipe:
            pipe.incr(bucket_key)
            pipe.expire(bucket_key, ttl_seconds, nx=True)
            count, _ = await pipe.execute()
        return int(count) <= limit
    except Exception as exc:
        logger.warning(
            "rate_limit.redis_error_fail_open",
            bucket=bucket_key,
            error=str(exc),
        )
        return True  # fail open


async def check_per_minute(key: str, limit: int) -> bool:
    """Bucket: per UTC minute. Returns True if allowed."""
    minute = datetime.now(tz=timezone.utc).strftime("%Y%m%d%H%M")
    bucket = f"rl:min:{key}:{minute}"
    return await _incr_with_expire(bucket, ttl_seconds=70, limit=limit)


async def check_per_day(key: str, limit: int) -> bool:
    """Bucket: per UTC calendar day. Returns True if allowed."""
    day = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
    bucket = f"rl:day:{key}:{day}"
    # 25h TTL — a day plus an hour, so the bucket cleanly retires.
    return await _incr_with_expire(bucket, ttl_seconds=90_000, limit=limit)


async def reset_for_tests(key: str) -> None:
    """Test hook — wipe both per-minute and per-day buckets for a key."""
    try:
        client = _get_client()
        # SCAN-based delete to catch any time-suffixed key.
        cursor = 0
        while True:
            cursor, keys = await client.scan(cursor=cursor, match=f"rl:*:{key}:*")
            if keys:
                await client.delete(*keys)
            if cursor == 0:
                break
    except Exception:
        pass
