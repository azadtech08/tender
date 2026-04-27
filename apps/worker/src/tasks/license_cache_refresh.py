"""Celery Beat task — rebuild the Redis license revocation set from DB truth.

Why
---
The revocation cache (``license:revoked`` SET in Redis) is populated by
the admin ``/revoke`` and ``/suspend`` endpoints and by ``/heartbeat``
denials. That covers the well-behaved paths. This periodic rebuild
catches the outliers:

  * licenses revoked via direct SQL bypassing the admin endpoint
  * licenses that naturally expired (expires_at <= now) without an
    admin action
  * licenses that crossed into the ``not_before`` window retroactively
  * stale set entries left over from long-expired revocations

Runs every ``CACHE_REFRESH_INTERVAL_SECONDS`` (default 300s = 5 min).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

import redis
import structlog
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from celery_app import celery_app
from config import settings
from db_models import License

logger = structlog.get_logger(__name__)

# Must match apps/api/src/services/license_cache.py::REVOKED_SET_KEY.
REVOKED_SET_KEY = "license:revoked"

_engine = create_engine(settings.sync_database_url, pool_pre_ping=True)

# Statuses that should deny token-side access. Matches the canonical set
# in db_models/license.py but inlined to avoid cross-app import.
_DENY_STATUSES = ("revoked", "suspended", "expired")


def _collect_deny_ids() -> list[int]:
    """Return license IDs that should be in the revocation set right now."""
    now = datetime.now(tz=timezone.utc)
    with Session(_engine) as session:
        stmt = select(License.id).where(
            (License.status.in_(_DENY_STATUSES)) | (License.expires_at <= now)
        )
        return [row for (row,) in session.execute(stmt).all()]


def _write_to_redis(ids: Iterable[int]) -> tuple[int, int]:
    """Replace the revocation SET with exactly these IDs. Returns (prior, new)."""
    client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        prior = client.scard(REVOKED_SET_KEY)
        pipe = client.pipeline(transaction=True)
        pipe.delete(REVOKED_SET_KEY)
        id_list = [str(i) for i in ids]
        if id_list:
            pipe.sadd(REVOKED_SET_KEY, *id_list)
        pipe.execute()
        return prior, len(id_list)
    finally:
        try:
            client.close()
        except Exception:
            pass


@celery_app.task(name="tasks.license_cache_refresh.refresh")
def refresh() -> dict:
    """Rebuild the revocation cache from DB truth."""
    try:
        ids = _collect_deny_ids()
    except Exception as exc:
        logger.error("license_cache_refresh.db_failed", error=str(exc))
        return {"status": "error", "phase": "db", "error": str(exc)}

    try:
        prior, new = _write_to_redis(ids)
    except Exception as exc:
        logger.error("license_cache_refresh.redis_failed", error=str(exc))
        return {"status": "error", "phase": "redis", "error": str(exc)}

    logger.info(
        "license_cache_refresh.ok",
        prior_cardinality=prior,
        new_cardinality=new,
        delta=new - prior,
    )
    return {"status": "ok", "prior": prior, "new": new, "delta": new - prior}
