"""Redis-backed revocation cache for fast token-side revocation checks.

Why this exists
---------------
``require_valid_license`` (Phase 5) does a fresh Postgres lookup on every
protected request, so revocation already propagates within ONE request for
the Clerk SaaS path. ``verify_license_token`` (Phase 5, Model B path) only
checks the cryptographic signature on the hot path — it never touches the
DB. Without this cache, a revoked license's signed token would keep working
until its built-in ``exp`` (up to 30 days).

Design
------
* A single Redis SET ``license:revoked`` holds revoked license IDs.
* Each membership entry is added with a TTL via a parallel string key
  ``license:revoked:<id>`` so old entries fall off after the longest possible
  token TTL (default 30d). The SET itself is rebuilt by the periodic refresh
  task (Phase 6 follow-up) and trimmed lazily.
* ``add_revoked`` is called from the admin /revoke endpoint and from the
  /heartbeat endpoint (when it discovers a revocation).
* ``is_revoked`` is called from ``verify_license_token`` after signature
  passes — it's an O(1) SISMEMBER.
* On Redis errors we **fail open** (return False from is_revoked, succeed on
  add_revoked silently). The DB is the source of truth; the cache is an
  optimization, not a correctness boundary.
"""

from __future__ import annotations

from typing import Iterable, Optional

import redis.asyncio as redis_async
import structlog

from config import settings

logger = structlog.get_logger()

REVOKED_SET_KEY = "license:revoked"
DEFAULT_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days — matches max token TTL

_redis_client: Optional[redis_async.Redis] = None


def _client() -> redis_async.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis_async.from_url(
            settings.redis_url, decode_responses=True
        )
    return _redis_client


async def add_revoked(license_id: int, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
    """Mark a license as revoked. Idempotent. Fails open on Redis errors."""
    try:
        c = _client()
        async with c.pipeline(transaction=False) as pipe:
            pipe.sadd(REVOKED_SET_KEY, str(license_id))
            # TTL hint string — used by the eventual refresh job to trim stale
            # entries; not required for correctness.
            pipe.set(f"{REVOKED_SET_KEY}:{license_id}", "1", ex=ttl_seconds)
            await pipe.execute()
        logger.info("license_cache.revoked_added", license_id=license_id)
    except Exception as exc:
        logger.warning(
            "license_cache.add_revoked_failed",
            license_id=license_id,
            error=str(exc),
        )


async def is_revoked(license_id: int) -> bool:
    """Return True iff the license is in the revocation set. Fail-open on errors."""
    try:
        return bool(await _client().sismember(REVOKED_SET_KEY, str(license_id)))
    except Exception as exc:
        logger.warning(
            "license_cache.is_revoked_failed_fail_open",
            license_id=license_id,
            error=str(exc),
        )
        return False


async def remove_revoked(license_id: int) -> None:
    """Reverse a revocation (e.g., after admin reactivates). Best-effort."""
    try:
        c = _client()
        async with c.pipeline(transaction=False) as pipe:
            pipe.srem(REVOKED_SET_KEY, str(license_id))
            pipe.delete(f"{REVOKED_SET_KEY}:{license_id}")
            await pipe.execute()
    except Exception as exc:
        logger.warning(
            "license_cache.remove_revoked_failed",
            license_id=license_id,
            error=str(exc),
        )


async def bulk_replace(license_ids: Iterable[int]) -> int:
    """Replace the entire revocation set with the given IDs.

    Used by the periodic refresh job (Phase 6 follow-up) to rebuild from DB
    truth. Returns the number of IDs written.
    """
    ids = [str(i) for i in license_ids]
    try:
        c = _client()
        async with c.pipeline(transaction=True) as pipe:
            pipe.delete(REVOKED_SET_KEY)
            if ids:
                pipe.sadd(REVOKED_SET_KEY, *ids)
            await pipe.execute()
        logger.info("license_cache.bulk_replaced", count=len(ids))
        return len(ids)
    except Exception as exc:
        logger.warning(
            "license_cache.bulk_replace_failed",
            error=str(exc),
            count=len(ids),
        )
        return 0


async def clear_for_tests() -> None:
    """Test hook — wipe the revocation set."""
    try:
        c = _client()
        await c.delete(REVOKED_SET_KEY)
        # Also delete TTL hint keys
        cursor = 0
        while True:
            cursor, keys = await c.scan(cursor=cursor, match=f"{REVOKED_SET_KEY}:*")
            if keys:
                await c.delete(*keys)
            if cursor == 0:
                break
    except Exception:
        pass
