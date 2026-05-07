"""Admin licenses router — mint, list, view, extend, suspend, revoke licenses.

All endpoints require an authenticated admin (see auth_admin.get_admin_user)
and write to admin_audit_log on every mutation.

Endpoints:
  POST   /api/admin/licenses                          mint a new license
  GET    /api/admin/licenses                          list (filter, paginate)
  GET    /api/admin/licenses/{id}                     detail + counts
  GET    /api/admin/licenses/{id}/devices             bound devices
  GET    /api/admin/licenses/{id}/activations         recent activation events
  POST   /api/admin/licenses/{id}/revoke              status -> revoked
  POST   /api/admin/licenses/{id}/suspend             status -> suspended
  POST   /api/admin/licenses/{id}/reactivate          status -> active
  POST   /api/admin/licenses/{id}/extend              move expires_at forward
  POST   /api/admin/licenses/{id}/devices/{did}/revoke  revoke one device
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import TokenData
from auth_admin import get_admin_user, get_client_ip
from config import settings
from database import get_db
from db_models import (
    ACTION_DEVICE_REVOKE,
    ACTION_LICENSE_CREATE,
    ACTION_LICENSE_EXTEND,
    ACTION_LICENSE_REACTIVATE,
    ACTION_LICENSE_REVOKE,
    ACTION_LICENSE_SUSPEND,
    STATUS_ACTIVE,
    STATUS_REVOKED,
    STATUS_SUSPENDED,
    VALID_LICENSE_STATUSES,
    License,
    LicenseActivation,
    LicenseDevice,
)
from schemas.license import (
    LicenseActivationResponse,
    LicenseCreate,
    LicenseCreatedResponse,
    LicenseDetailResponse,
    LicenseDeviceResponse,
    LicenseExtend,
    LicenseListResponse,
    LicenseResponse,
    LicenseRevoke,
    LicenseSuspend,
)
from services.admin_audit import write_admin_audit
from services.license_abuse_detection import (
    SuspiciousIP,
    SuspiciousLicense,
    activity_summary,
    fingerprint_churn,
    invalid_key_spike,
    rapid_reactivation,
)
from services.license_cache import add_revoked, remove_revoked
from services.license_keygen import (
    generate_fingerprint_salt,
    generate_license_key,
    hash_license_key,
    key_prefix as derive_key_prefix,
)

router = APIRouter()


# ── helpers ──────────────────────────────────────────────────────────────────


async def _load_license_or_404(db: AsyncSession, license_id: int) -> License:
    result = await db.execute(select(License).where(License.id == license_id))
    lic = result.scalar_one_or_none()
    if lic is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="License not found"
        )
    return lic


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


# ── 1. POST /api/admin/licenses — mint ───────────────────────────────────────


@router.post(
    "",
    response_model=LicenseCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_license(
    body: LicenseCreate,
    request: Request,
    admin: Annotated[TokenData, Depends(get_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LicenseCreatedResponse:
    # Resolve the final expiry — either an absolute datetime or "now + N hours".
    now = _now()
    if body.duration_hours is not None:
        resolved_expires = now + timedelta(hours=body.duration_hours)
    else:
        resolved_expires = body.expires_at  # type: ignore[assignment]

    if resolved_expires <= now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="expires_at must be in the future",
        )

    raw_key = generate_license_key()
    license_row = License(
        tenant_id=body.tenant_id,
        key_hash=hash_license_key(raw_key),
        key_prefix=derive_key_prefix(raw_key),
        plan=body.plan,
        status=STATUS_ACTIVE,
        signing_kid=settings.license_active_kid,
        not_before=body.not_before or now,
        expires_at=resolved_expires,
        max_devices=body.max_devices,
        features=body.features,
        fingerprint_salt=generate_fingerprint_salt(),
    )
    db.add(license_row)
    await db.flush()  # populate license_row.id for the audit log

    await write_admin_audit(
        db,
        admin,
        ACTION_LICENSE_CREATE,
        target_tenant_id=body.tenant_id,
        target_license_id=license_row.id,
        payload={
            "plan": body.plan,
            "expires_at": resolved_expires.isoformat(),
            "duration_hours": body.duration_hours,
            "max_devices": body.max_devices,
            "notes": body.notes,
        },
        ip=get_client_ip(request),
    )
    await db.commit()
    await db.refresh(license_row)

    return LicenseCreatedResponse(
        license=LicenseResponse.model_validate(license_row),
        raw_key=raw_key,
    )


# ── 2. GET /api/admin/licenses — list ────────────────────────────────────────


@router.get("", response_model=LicenseListResponse)
async def list_licenses(
    admin: Annotated[TokenData, Depends(get_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Optional[str] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    plan: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> LicenseListResponse:
    if status_filter and status_filter not in VALID_LICENSE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"status must be one of {sorted(VALID_LICENSE_STATUSES)}",
        )

    base_query = select(License)
    if tenant_id:
        base_query = base_query.where(License.tenant_id == tenant_id)
    if status_filter:
        base_query = base_query.where(License.status == status_filter)
    if plan:
        base_query = base_query.where(License.plan == plan)

    count_query = select(func.count()).select_from(base_query.subquery())
    total = (await db.execute(count_query)).scalar_one()

    page_query = (
        base_query.order_by(License.created_at.desc()).limit(limit).offset(offset)
    )
    rows = (await db.execute(page_query)).scalars().all()

    return LicenseListResponse(
        items=[LicenseResponse.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


# ── 3. GET /api/admin/licenses/{id} — detail ─────────────────────────────────


@router.get("/{license_id}", response_model=LicenseDetailResponse)
async def get_license_detail(
    license_id: int,
    admin: Annotated[TokenData, Depends(get_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LicenseDetailResponse:
    lic = await _load_license_or_404(db, license_id)

    device_count = (
        await db.execute(
            select(func.count(LicenseDevice.id)).where(
                LicenseDevice.license_id == license_id
            )
        )
    ).scalar_one()
    active_device_count = (
        await db.execute(
            select(func.count(LicenseDevice.id)).where(
                LicenseDevice.license_id == license_id,
                LicenseDevice.revoked_at.is_(None),
            )
        )
    ).scalar_one()
    twenty_four_hours_ago = _now() - timedelta(hours=24)
    activations_24h = (
        await db.execute(
            select(func.count(LicenseActivation.id)).where(
                LicenseActivation.license_id == license_id,
                LicenseActivation.created_at >= twenty_four_hours_ago,
            )
        )
    ).scalar_one()

    return LicenseDetailResponse(
        license=LicenseResponse.model_validate(lic),
        device_count=device_count,
        active_device_count=active_device_count,
        activations_24h=activations_24h,
    )


# ── 4. GET /api/admin/licenses/{id}/devices ─────────────────────────────────


@router.get(
    "/{license_id}/devices",
    response_model=list[LicenseDeviceResponse],
)
async def list_license_devices(
    license_id: int,
    admin: Annotated[TokenData, Depends(get_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[LicenseDeviceResponse]:
    await _load_license_or_404(db, license_id)
    rows = (
        await db.execute(
            select(LicenseDevice)
            .where(LicenseDevice.license_id == license_id)
            .order_by(LicenseDevice.last_seen_at.desc())
        )
    ).scalars().all()
    return [LicenseDeviceResponse.model_validate(r) for r in rows]


# ── 5. GET /api/admin/licenses/{id}/activations ─────────────────────────────


@router.get(
    "/{license_id}/activations",
    response_model=list[LicenseActivationResponse],
)
async def list_license_activations(
    license_id: int,
    admin: Annotated[TokenData, Depends(get_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[LicenseActivationResponse]:
    await _load_license_or_404(db, license_id)
    rows = (
        await db.execute(
            select(LicenseActivation)
            .where(LicenseActivation.license_id == license_id)
            .order_by(LicenseActivation.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [LicenseActivationResponse.model_validate(r) for r in rows]


# ── 6. POST /api/admin/licenses/{id}/revoke ─────────────────────────────────


@router.post("/{license_id}/revoke", response_model=LicenseResponse)
async def revoke_license(
    license_id: int,
    body: LicenseRevoke,
    request: Request,
    admin: Annotated[TokenData, Depends(get_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LicenseResponse:
    lic = await _load_license_or_404(db, license_id)
    lic.status = STATUS_REVOKED
    lic.revoked_at = _now()
    lic.revoked_reason = body.reason

    await write_admin_audit(
        db,
        admin,
        ACTION_LICENSE_REVOKE,
        target_tenant_id=lic.tenant_id,
        target_license_id=lic.id,
        payload={"reason": body.reason},
        ip=get_client_ip(request),
    )
    await db.commit()
    await db.refresh(lic)
    # Phase 6: push to revocation cache so token-bearing clients deny within
    # seconds rather than waiting for the next heartbeat to discover it.
    await add_revoked(lic.id)
    return LicenseResponse.model_validate(lic)


# ── 7. POST /api/admin/licenses/{id}/suspend ────────────────────────────────


@router.post("/{license_id}/suspend", response_model=LicenseResponse)
async def suspend_license(
    license_id: int,
    body: LicenseSuspend,
    request: Request,
    admin: Annotated[TokenData, Depends(get_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LicenseResponse:
    lic = await _load_license_or_404(db, license_id)
    if lic.status == STATUS_REVOKED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot suspend a revoked license",
        )
    lic.status = STATUS_SUSPENDED

    await write_admin_audit(
        db,
        admin,
        ACTION_LICENSE_SUSPEND,
        target_tenant_id=lic.tenant_id,
        target_license_id=lic.id,
        payload={"reason": body.reason},
        ip=get_client_ip(request),
    )
    await db.commit()
    await db.refresh(lic)
    # Phase 6: suspended licenses also belong in the revocation set.
    await add_revoked(lic.id)
    return LicenseResponse.model_validate(lic)


# ── 8. POST /api/admin/licenses/{id}/reactivate ─────────────────────────────


@router.post("/{license_id}/reactivate", response_model=LicenseResponse)
async def reactivate_license(
    license_id: int,
    request: Request,
    admin: Annotated[TokenData, Depends(get_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LicenseResponse:
    lic = await _load_license_or_404(db, license_id)
    if lic.status == STATUS_REVOKED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot reactivate a revoked license — issue a new one",
        )
    if lic.expires_at <= _now():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="License has expired — extend it before reactivating",
        )
    lic.status = STATUS_ACTIVE

    await write_admin_audit(
        db,
        admin,
        ACTION_LICENSE_REACTIVATE,
        target_tenant_id=lic.tenant_id,
        target_license_id=lic.id,
        ip=get_client_ip(request),
    )
    await db.commit()
    await db.refresh(lic)
    # Phase 6: undo any prior revocation-cache entry.
    await remove_revoked(lic.id)
    return LicenseResponse.model_validate(lic)


# ── 9. POST /api/admin/licenses/{id}/extend ─────────────────────────────────


@router.post("/{license_id}/extend", response_model=LicenseResponse)
async def extend_license(
    license_id: int,
    body: LicenseExtend,
    request: Request,
    admin: Annotated[TokenData, Depends(get_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LicenseResponse:
    lic = await _load_license_or_404(db, license_id)

    # Resolve the new expiry — either absolute datetime or "now + N hours".
    now = _now()
    if body.duration_hours is not None:
        new_expires = now + timedelta(hours=body.duration_hours)
    else:
        new_expires = body.new_expires_at  # type: ignore[assignment]

    if new_expires <= now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="new_expires_at must be in the future",
        )

    old_expires = lic.expires_at
    lic.expires_at = new_expires

    await write_admin_audit(
        db,
        admin,
        ACTION_LICENSE_EXTEND,
        target_tenant_id=lic.tenant_id,
        target_license_id=lic.id,
        payload={
            "old_expires_at": old_expires.isoformat(),
            "new_expires_at": new_expires.isoformat(),
            "duration_hours": body.duration_hours,
            "reason": body.reason,
        },
        ip=get_client_ip(request),
    )
    await db.commit()
    await db.refresh(lic)
    return LicenseResponse.model_validate(lic)


# ── Phase 7: admin stats endpoints ──────────────────────────────────────────


@router.get("/stats/summary")
async def get_stats_summary(
    admin: Annotated[TokenData, Depends(get_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """High-level activity dashboard: counts of activations/heartbeats/denials."""
    return await activity_summary(db)


@router.get("/stats/suspicious")
async def get_stats_suspicious(
    admin: Annotated[TokenData, Depends(get_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    window_hours: int = Query(default=24, ge=1, le=168),
) -> dict:
    """Licenses matching abuse heuristics + IPs hammering INVALID_KEY.

    Not an alert — a query surface. Wire your ops alerting (Alertmanager,
    Sentry) to Prometheus metrics for actual paging.
    """
    churn = await fingerprint_churn(db, window_hours=window_hours)
    rapid = await rapid_reactivation(db, window_hours=window_hours)
    invalid_ips = await invalid_key_spike(db, window_hours=1)

    def _lic(rows: list[SuspiciousLicense]) -> list[dict]:
        return [
            {
                "license_id": r.license_id,
                "tenant_id": r.tenant_id,
                "plan": r.plan,
                "fingerprint_count_24h": r.fingerprint_count_24h,
                "activation_count_24h": r.activation_count_24h,
                "last_event_at": r.last_event_at.isoformat() if r.last_event_at else None,
            }
            for r in rows
        ]

    def _ip(rows: list[SuspiciousIP]) -> list[dict]:
        return [
            {
                "ip": r.ip,
                "invalid_key_count_1h": r.invalid_key_count_1h,
                "distinct_key_prefixes": r.distinct_key_prefixes,
            }
            for r in rows
        ]

    return {
        "window_hours": window_hours,
        "fingerprint_churn": _lic(churn),
        "rapid_reactivation": _lic(rapid),
        "invalid_key_spike": _ip(invalid_ips),
    }


# ── 10. POST /api/admin/licenses/{id}/devices/{did}/revoke ──────────────────


@router.post(
    "/{license_id}/devices/{device_id}/revoke",
    response_model=LicenseDeviceResponse,
)
async def revoke_device(
    license_id: int,
    device_id: int,
    request: Request,
    admin: Annotated[TokenData, Depends(get_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LicenseDeviceResponse:
    await _load_license_or_404(db, license_id)
    result = await db.execute(
        select(LicenseDevice).where(
            LicenseDevice.id == device_id,
            LicenseDevice.license_id == license_id,
        )
    )
    device = result.scalar_one_or_none()
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found for this license",
        )
    device.revoked_at = _now()

    await write_admin_audit(
        db,
        admin,
        ACTION_DEVICE_REVOKE,
        target_tenant_id=device.tenant_id,
        target_license_id=license_id,
        payload={
            "device_id": device_id,
            "fingerprint_prefix": device.fingerprint[:16],
        },
        ip=get_client_ip(request),
    )
    await db.commit()
    await db.refresh(device)
    return LicenseDeviceResponse.model_validate(device)
