"""Sharing & brute-force detection queries.

These are not alerts — they're SQL-backed query helpers the admin UI
(and Prometheus scrape job) can surface. Actual paging/alerting belongs
to your ops stack (Prometheus Alertmanager, Sentry, etc.).

Heuristics:
  * **fingerprint churn** — same license seeing heartbeats from > N
    distinct fingerprints in the last 24h → likely shared key.
  * **IP spread** — same license seeing activations from > N distinct
    /24 IP ranges in the last 24h → geographic impossibility.
  * **invalid-key spike** — one IP hitting activate with many different
    invalid keys in a window → brute force.
  * **rapid reactivation churn** — one license reactivating > N times in
    24h → desperate client, misconfigured scheduler, or abuse.

All queries are admin-scoped (cross-tenant) and should be called behind
``get_admin_user``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db_models import (
    EVENT_ACTIVATE,
    EVENT_DENIED,
    EVENT_HEARTBEAT,
    REASON_INVALID_KEY,
    License,
    LicenseActivation,
)

# ── Thresholds — tune in one place ───────────────────────────────────────────

FINGERPRINT_CHURN_THRESHOLD = 5          # > N distinct fps per license in 24h
IP_SPREAD_THRESHOLD = 5                  # > N distinct /24s per license in 24h
INVALID_KEY_SPIKE_THRESHOLD = 20         # > N invalid-key attempts per IP in 1h
RAPID_REACTIVATION_THRESHOLD = 10        # > N activations per license in 24h


@dataclass(frozen=True)
class SuspiciousLicense:
    license_id: int
    tenant_id: str
    plan: str
    fingerprint_count_24h: int
    ip_24_count_24h: int
    activation_count_24h: int
    last_event_at: datetime | None


@dataclass(frozen=True)
class SuspiciousIP:
    ip: str
    invalid_key_count_1h: int
    distinct_key_prefixes: int


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _ip24(ip: str) -> str:
    """Collapse an IPv4 to its /24 prefix (best-effort — IPv6 left as-is)."""
    if ":" in ip:
        return ip
    parts = ip.split(".")
    if len(parts) == 4:
        return ".".join(parts[:3]) + ".0/24"
    return ip


async def fingerprint_churn(
    db: AsyncSession,
    *,
    window_hours: int = 24,
    threshold: int = FINGERPRINT_CHURN_THRESHOLD,
) -> list[SuspiciousLicense]:
    """Licenses with >N distinct heartbeat fingerprints in the window."""
    since = _now() - timedelta(hours=window_hours)

    # Per-license counts.
    stmt = (
        select(
            LicenseActivation.license_id,
            License.tenant_id,
            License.plan,
            func.count(func.distinct(LicenseActivation.fingerprint)).label("fp_count"),
            func.count(LicenseActivation.id).label("event_count"),
            func.max(LicenseActivation.created_at).label("last_at"),
        )
        .join(License, License.id == LicenseActivation.license_id)
        .where(
            LicenseActivation.created_at >= since,
            LicenseActivation.event.in_([EVENT_ACTIVATE, EVENT_HEARTBEAT]),
            LicenseActivation.fingerprint.isnot(None),
        )
        .group_by(LicenseActivation.license_id, License.tenant_id, License.plan)
        .having(func.count(func.distinct(LicenseActivation.fingerprint)) > threshold)
        .order_by(func.count(func.distinct(LicenseActivation.fingerprint)).desc())
    )

    rows = (await db.execute(stmt)).all()
    out: list[SuspiciousLicense] = []
    for r in rows:
        out.append(
            SuspiciousLicense(
                license_id=r.license_id,
                tenant_id=r.tenant_id,
                plan=r.plan,
                fingerprint_count_24h=r.fp_count,
                ip_24_count_24h=0,
                activation_count_24h=r.event_count,
                last_event_at=r.last_at,
            )
        )
    return out


async def rapid_reactivation(
    db: AsyncSession,
    *,
    window_hours: int = 24,
    threshold: int = RAPID_REACTIVATION_THRESHOLD,
) -> list[SuspiciousLicense]:
    """Licenses with >N activate events (not heartbeats) in the window."""
    since = _now() - timedelta(hours=window_hours)

    stmt = (
        select(
            LicenseActivation.license_id,
            License.tenant_id,
            License.plan,
            func.count(LicenseActivation.id).label("act_count"),
            func.max(LicenseActivation.created_at).label("last_at"),
        )
        .join(License, License.id == LicenseActivation.license_id)
        .where(
            LicenseActivation.created_at >= since,
            LicenseActivation.event == EVENT_ACTIVATE,
        )
        .group_by(LicenseActivation.license_id, License.tenant_id, License.plan)
        .having(func.count(LicenseActivation.id) > threshold)
        .order_by(func.count(LicenseActivation.id).desc())
    )

    rows = (await db.execute(stmt)).all()
    return [
        SuspiciousLicense(
            license_id=r.license_id,
            tenant_id=r.tenant_id,
            plan=r.plan,
            fingerprint_count_24h=0,
            ip_24_count_24h=0,
            activation_count_24h=r.act_count,
            last_event_at=r.last_at,
        )
        for r in rows
    ]


async def invalid_key_spike(
    db: AsyncSession,
    *,
    window_hours: int = 1,
    threshold: int = INVALID_KEY_SPIKE_THRESHOLD,
) -> list[SuspiciousIP]:
    """IPs that triggered >N INVALID_KEY denials in the window.

    Note: INVALID_KEY denials for *unknown* keys (no license_id) only emit
    structlog events, so they won't appear in license_activations. This
    query catches INVALID_KEY against *known* licenses — which by itself
    is interesting (wrong key for existing license) but is a lower-signal
    proxy for brute force. Pair with structlog sampling in prod.
    """
    since = _now() - timedelta(hours=window_hours)

    stmt = (
        select(
            LicenseActivation.ip,
            func.count(LicenseActivation.id).label("cnt"),
            func.count(func.distinct(LicenseActivation.license_id)).label("distinct_licenses"),
        )
        .where(
            LicenseActivation.created_at >= since,
            LicenseActivation.event == EVENT_DENIED,
            LicenseActivation.reason == REASON_INVALID_KEY,
            LicenseActivation.ip.isnot(None),
        )
        .group_by(LicenseActivation.ip)
        .having(func.count(LicenseActivation.id) > threshold)
        .order_by(func.count(LicenseActivation.id).desc())
    )

    rows = (await db.execute(stmt)).all()
    return [
        SuspiciousIP(
            ip=r.ip or "unknown",
            invalid_key_count_1h=r.cnt,
            distinct_key_prefixes=r.distinct_licenses,
        )
        for r in rows
    ]


async def activity_summary(db: AsyncSession) -> dict[str, Any]:
    """High-level summary the admin dashboard can display at the top.

    Cheap single-query aggregate:
      - activations in last hour / 24h
      - heartbeats in last hour / 24h
      - denials in last 24h (by reason, top 5)
      - distinct licenses seen in last 24h
    """
    now = _now()
    hour_ago = now - timedelta(hours=1)
    day_ago = now - timedelta(hours=24)

    # Single query: counts bucketed by event and time window.
    rows = (await db.execute(
        select(
            LicenseActivation.event,
            LicenseActivation.reason,
            func.count(
                case((LicenseActivation.created_at >= hour_ago, 1))
            ).label("cnt_1h"),
            func.count().label("cnt_24h"),
        )
        .where(LicenseActivation.created_at >= day_ago)
        .group_by(LicenseActivation.event, LicenseActivation.reason)
    )).all()

    activate_1h = heartbeat_1h = deny_1h = 0
    activate_24h = heartbeat_24h = deny_24h = 0
    denials_by_reason: dict[str, int] = {}

    for r in rows:
        if r.event == EVENT_ACTIVATE:
            activate_1h += r.cnt_1h
            activate_24h += r.cnt_24h
        elif r.event == EVENT_HEARTBEAT:
            heartbeat_1h += r.cnt_1h
            heartbeat_24h += r.cnt_24h
        elif r.event == EVENT_DENIED:
            deny_1h += r.cnt_1h
            deny_24h += r.cnt_24h
            if r.reason:
                denials_by_reason[r.reason] = denials_by_reason.get(r.reason, 0) + r.cnt_24h

    distinct_licenses = (await db.execute(
        select(func.count(func.distinct(LicenseActivation.license_id)))
        .where(LicenseActivation.created_at >= day_ago)
    )).scalar_one()

    top_reasons = sorted(
        denials_by_reason.items(), key=lambda kv: kv[1], reverse=True
    )[:5]

    return {
        "window_now": now.isoformat(),
        "activations": {"1h": activate_1h, "24h": activate_24h},
        "heartbeats": {"1h": heartbeat_1h, "24h": heartbeat_24h},
        "denials": {
            "1h": deny_1h,
            "24h": deny_24h,
            "top_reasons_24h": [{"reason": k, "count": v} for k, v in top_reasons],
        },
        "distinct_licenses_24h": distinct_licenses,
    }
