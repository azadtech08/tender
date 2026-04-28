"""Client-facing license endpoints.

Phase 4: POST /api/license/activate — converts a pasted license key into a
signed PASETO token bound to the client's device fingerprint.

Public endpoint (no Bearer auth). Protected by:
  - Rate limit: 5 / minute per client IP
  - Rate limit: 10 / day per key-hash
  - CRC self-check on the pasted key (rejects typos before any DB call)
"""

from __future__ import annotations

import json as _json
import time as _time
from datetime import datetime, timezone
from functools import wraps
from typing import Annotated, Any, Callable, Optional

import structlog
from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import TokenData, get_current_user
from auth_admin import get_client_ip
from config import settings
from database import get_db
from db_models import (
    EVENT_ACTIVATE,
    EVENT_DENIED,
    EVENT_HEARTBEAT,
    REASON_DEVICE_LIMIT,
    REASON_FINGERPRINT_MISMATCH,
    REASON_INVALID_KEY,
    REASON_KEY_EXPIRED,
    REASON_KEY_REVOKED,
    REASON_KEY_SUSPENDED,
    REASON_RATE_LIMITED,
    STATUS_ACTIVE,
    STATUS_REVOKED,
    STATUS_SUSPENDED,
    License,
    LicenseActivation,
    LicenseDevice,
)
from schemas.license import (
    ActivateRequest,
    ActivateResponse,
    HeartbeatRequest,
    HeartbeatResponse,
    LicenseErrorResponse,
)
from services.license_cache import add_revoked
from services.license_enforcement import _get_public_keys
from services.license_keygen import hash_license_key, validate_license_key_format
from services.license_metrics import (
    license_activation_duration_seconds,
    license_activations_total,
    license_heartbeat_duration_seconds,
    license_heartbeats_total,
)
from services.license_signer import get_signer
from services.rate_limit import check_per_day, check_per_minute
try:
    from tenzo_licensing import (
        ExpiredLicenseError,
        InvalidSignatureError,
        LicenseError,
        NotYetValidError,
        UnknownKeyIdError,
        verify_license,
    )
except ImportError:
    class LicenseError(Exception): pass  # type: ignore[misc]
    class ExpiredLicenseError(LicenseError): pass  # type: ignore[misc]
    class InvalidSignatureError(LicenseError): pass  # type: ignore[misc]
    class NotYetValidError(LicenseError): pass  # type: ignore[misc]
    class UnknownKeyIdError(LicenseError): pass  # type: ignore[misc]
    def verify_license(*a, **k): raise LicenseError("tenzo_licensing not installed")  # type: ignore[misc]

logger = structlog.get_logger()
router = APIRouter()


# ── metrics decorator ────────────────────────────────────────────────────────


def _instrument(counter, duration_hist) -> Callable:
    """Decorator: count a FastAPI handler's outcomes and observe its duration.

    Derives the Prometheus ``result`` label from the response:
      * 2xx → ``"success"``
      * everything else → body's ``error`` field if present, else ``"error"``

    Metrics are observed in a finally block so they record even on exceptions.
    """

    def decorator(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            t0 = _time.monotonic()
            result_label = "error"
            try:
                resp = await fn(*args, **kwargs)
                status_code = getattr(resp, "status_code", 200)
                if 200 <= status_code < 300:
                    result_label = "success"
                else:
                    try:
                        body = getattr(resp, "body", b"{}") or b"{}"
                        result_label = _json.loads(body).get("error", "error")
                    except Exception:
                        pass
                return resp
            finally:
                try:
                    counter.labels(result=result_label).inc()
                    duration_hist.observe(_time.monotonic() - t0)
                except Exception:
                    # Metrics must never break the request path.
                    pass

        return wrapper

    return decorator


# ── helpers ──────────────────────────────────────────────────────────────────


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _err(
    error: str,
    message: str,
    *,
    http_status: int,
    retry_after_seconds: Optional[int] = None,
    metric: Optional[Any] = None,
) -> JSONResponse:
    """Build a structured error response.

    If ``metric`` is a Prometheus Counter, its ``{result}`` label is bumped
    with the ``error`` code so callers get accurate Prometheus labels.
    """
    if metric is not None:
        try:
            metric.labels(result=error).inc()
        except Exception:
            pass  # metrics must never break the request path
    payload = LicenseErrorResponse(
        error=error,
        message=message,
        retry_after_seconds=retry_after_seconds,
    ).model_dump(exclude_none=True)
    headers = {}
    if retry_after_seconds:
        headers["Retry-After"] = str(retry_after_seconds)
    return JSONResponse(content=payload, status_code=http_status, headers=headers)


async def _log_activation(
    db: AsyncSession,
    *,
    license_id: Optional[int],
    tenant_id: Optional[str],
    fingerprint: Optional[str],
    event: str,
    reason: Optional[str],
    ip: Optional[str],
    user_agent: Optional[str],
) -> None:
    """Append a license_activations row. Caller commits."""
    if license_id is None or tenant_id is None:
        # Without a known license we have nowhere RLS-clean to land the row.
        # These denials (INVALID_KEY) are rate-limited so the noise is bounded;
        # they're captured in structlog instead.
        logger.info(
            "license.activation_denied_unknown",
            event_type=event,
            reason=reason,
            ip=ip,
            fingerprint_prefix=(fingerprint or "")[:16],
        )
        return
    db.add(
        LicenseActivation(
            tenant_id=tenant_id,
            license_id=license_id,
            fingerprint=fingerprint,
            event=event,
            reason=reason,
            ip=ip,
            user_agent=user_agent,
        )
    )


# ── POST /api/license/activate ───────────────────────────────────────────────


@router.post(
    "/activate",
    response_model=ActivateResponse,
    responses={
        400: {"model": LicenseErrorResponse},
        403: {"model": LicenseErrorResponse},
        404: {"model": LicenseErrorResponse},
        409: {"model": LicenseErrorResponse},
        429: {"model": LicenseErrorResponse},
        500: {"model": LicenseErrorResponse},
    },
)
@_instrument(license_activations_total, license_activation_duration_seconds)
async def activate_license(
    body: ActivateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    client_ip = get_client_ip(request)
    user_agent = request.headers.get("User-Agent")

    # ── 1. Per-IP rate limit ────────────────────────────────────────────────
    if not await check_per_minute(
        f"activate:ip:{client_ip}", settings.license_activate_rate_per_ip_per_min
    ):
        return _err(
            REASON_RATE_LIMITED,
            "Too many activation attempts from this IP. Try again in a minute.",
            http_status=status.HTTP_429_TOO_MANY_REQUESTS,
            retry_after_seconds=60,
        )

    # ── 2. CRC self-check on the pasted key ─────────────────────────────────
    if not validate_license_key_format(body.key):
        await _log_activation(
            db,
            license_id=None,
            tenant_id=None,
            fingerprint=body.fingerprint,
            event=EVENT_DENIED,
            reason=REASON_INVALID_KEY,
            ip=client_ip,
            user_agent=user_agent,
        )
        return _err(
            REASON_INVALID_KEY,
            "License key is malformed. Check for typos and try again.",
            http_status=status.HTTP_400_BAD_REQUEST,
        )

    # ── 3. Per-key-hash rate limit (after CRC, so garbage keys don't burn it) ──
    key_hash = hash_license_key(body.key)
    if not await check_per_day(
        f"activate:key:{key_hash}", settings.license_activate_rate_per_key_per_day
    ):
        return _err(
            REASON_RATE_LIMITED,
            "Too many activation attempts for this license today.",
            http_status=status.HTTP_429_TOO_MANY_REQUESTS,
            retry_after_seconds=3600,
        )

    # ── 4. Look up the license ──────────────────────────────────────────────
    result = await db.execute(select(License).where(License.key_hash == key_hash))
    lic: Optional[License] = result.scalar_one_or_none()
    if lic is None:
        await _log_activation(
            db,
            license_id=None,
            tenant_id=None,
            fingerprint=body.fingerprint,
            event=EVENT_DENIED,
            reason=REASON_INVALID_KEY,
            ip=client_ip,
            user_agent=user_agent,
        )
        await db.commit()
        return _err(
            REASON_INVALID_KEY,
            "License key not recognised.",
            http_status=status.HTTP_404_NOT_FOUND,
        )

    # ── 5. Status / time checks ─────────────────────────────────────────────
    now = _now()
    deny_reason: Optional[tuple[str, str, int]] = None
    if lic.status == STATUS_REVOKED:
        deny_reason = (
            REASON_KEY_REVOKED,
            "This license has been revoked.",
            status.HTTP_403_FORBIDDEN,
        )
    elif lic.status == STATUS_SUSPENDED:
        deny_reason = (
            REASON_KEY_SUSPENDED,
            "This license is suspended. Contact support.",
            status.HTTP_403_FORBIDDEN,
        )
    elif lic.expires_at <= now:
        deny_reason = (
            REASON_KEY_EXPIRED,
            f"License expired at {lic.expires_at.isoformat()}.",
            status.HTTP_403_FORBIDDEN,
        )
    elif lic.not_before > now:
        deny_reason = (
            "KEY_NOT_YET_VALID",
            f"License not valid until {lic.not_before.isoformat()}.",
            status.HTTP_403_FORBIDDEN,
        )

    if deny_reason is not None:
        reason_code, msg, http_status = deny_reason
        await _log_activation(
            db,
            license_id=lic.id,
            tenant_id=lic.tenant_id,
            fingerprint=body.fingerprint,
            event=EVENT_DENIED,
            reason=reason_code,
            ip=client_ip,
            user_agent=user_agent,
        )
        await db.commit()
        return _err(reason_code, msg, http_status=http_status)

    # ── 6. Device binding ───────────────────────────────────────────────────
    device_result = await db.execute(
        select(LicenseDevice).where(
            LicenseDevice.license_id == lic.id,
            LicenseDevice.fingerprint == body.fingerprint,
        )
    )
    device: Optional[LicenseDevice] = device_result.scalar_one_or_none()

    if device is not None and device.revoked_at is not None:
        await _log_activation(
            db,
            license_id=lic.id,
            tenant_id=lic.tenant_id,
            fingerprint=body.fingerprint,
            event=EVENT_DENIED,
            reason="DEVICE_REVOKED",
            ip=client_ip,
            user_agent=user_agent,
        )
        await db.commit()
        return _err(
            "DEVICE_REVOKED",
            "This device's binding to the license was revoked. Contact support.",
            http_status=status.HTTP_403_FORBIDDEN,
        )

    if device is None:
        # Slot check — count ACTIVE (non-revoked) devices.
        from sqlalchemy import func

        active_count = (
            await db.execute(
                select(func.count(LicenseDevice.id)).where(
                    LicenseDevice.license_id == lic.id,
                    LicenseDevice.revoked_at.is_(None),
                )
            )
        ).scalar_one()
        if active_count >= lic.max_devices:
            await _log_activation(
                db,
                license_id=lic.id,
                tenant_id=lic.tenant_id,
                fingerprint=body.fingerprint,
                event=EVENT_DENIED,
                reason=REASON_DEVICE_LIMIT,
                ip=client_ip,
                user_agent=user_agent,
            )
            await db.commit()
            return _err(
                REASON_DEVICE_LIMIT,
                f"Maximum {lic.max_devices} devices already bound. "
                f"Revoke an existing device or contact support.",
                http_status=status.HTTP_409_CONFLICT,
            )
        device = LicenseDevice(
            tenant_id=lic.tenant_id,
            license_id=lic.id,
            fingerprint=body.fingerprint,
            hostname=body.hostname,
            platform=body.platform,
            first_seen_at=now,
            last_seen_at=now,
            last_ip=client_ip,
            last_user_agent=user_agent,
        )
        db.add(device)
    else:
        device.last_seen_at = now
        device.last_ip = client_ip
        device.last_user_agent = user_agent
        if body.hostname:
            device.hostname = body.hostname
        if body.platform:
            device.platform = body.platform

    # ── 7. Mint and return signed token ─────────────────────────────────────
    try:
        signer = get_signer()
        token, token_exp = signer.mint_token(
            lic, fingerprint=body.fingerprint
        )
    except Exception as exc:
        logger.error("license.signing_failed", error=str(exc), license_id=lic.id)
        return _err(
            "SIGNING_FAILED",
            "Internal signing error — please try again or contact support.",
            http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    await _log_activation(
        db,
        license_id=lic.id,
        tenant_id=lic.tenant_id,
        fingerprint=body.fingerprint,
        event=EVENT_ACTIVATE,
        reason=None,
        ip=client_ip,
        user_agent=user_agent,
    )
    await db.commit()

    logger.info(
        "license.activated",
        license_id=lic.id,
        tenant_id=lic.tenant_id,
        plan=lic.plan,
        fingerprint_prefix=body.fingerprint[:16],
        ip=client_ip,
    )

    return JSONResponse(
        content=ActivateResponse(
            token=token,
            expires_at=token_exp,
            heartbeat_after_seconds=settings.license_heartbeat_interval_seconds,
            plan=lic.plan,
            features=dict(lic.features or {}),
            license_id=lic.id,
            bound_fingerprint=body.fingerprint,
        ).model_dump(mode="json"),
        status_code=status.HTTP_200_OK,
    )


# ── POST /api/license/heartbeat ──────────────────────────────────────────────


@router.post(
    "/heartbeat",
    response_model=HeartbeatResponse,
    responses={
        400: {"model": LicenseErrorResponse},
        402: {"model": LicenseErrorResponse},
        403: {"model": LicenseErrorResponse},
        404: {"model": LicenseErrorResponse},
        429: {"model": LicenseErrorResponse},
    },
)
@_instrument(license_heartbeats_total, license_heartbeat_duration_seconds)
async def heartbeat_license(
    body: HeartbeatRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Refresh a license token and check for revocation/suspension/expiry.

    Clients call this every ``license_heartbeat_interval_seconds`` (default
    6h). On success, returns a freshly-signed token; on revocation /
    suspension / expiry, returns an error so the client can move to deny
    state immediately (before its grace period elapses).
    """
    client_ip = get_client_ip(request)
    user_agent = request.headers.get("User-Agent")

    # ── 1. Verify token signature + decode ──────────────────────────────────
    try:
        payload = verify_license(
            body.token,
            _get_public_keys(),
            leeway_seconds=300,
        )
    except ExpiredLicenseError:
        return _err(
            REASON_KEY_EXPIRED,
            "Token has expired. Re-activate the license to obtain a new one.",
            http_status=status.HTTP_403_FORBIDDEN,
        )
    except NotYetValidError as e:
        return _err(
            "KEY_NOT_YET_VALID",
            str(e),
            http_status=status.HTTP_403_FORBIDDEN,
        )
    except (InvalidSignatureError, UnknownKeyIdError, LicenseError):
        return _err(
            "TOKEN_INVALID",
            "Token failed signature verification. Re-activate the license.",
            http_status=status.HTTP_403_FORBIDDEN,
        )

    # ── 2. Token must reference a real license id ───────────────────────────
    try:
        license_id = int(payload.lic_id)
    except (TypeError, ValueError):
        return _err(
            "TOKEN_INVALID",
            "Token references an invalid license id.",
            http_status=status.HTTP_403_FORBIDDEN,
        )

    # ── 3. Per-license rate limit (60/hour ≈ 1/min generous cap) ────────────
    if not await check_per_minute(f"heartbeat:lic:{license_id}", limit=10):
        return _err(
            REASON_RATE_LIMITED,
            "Too many heartbeats for this license. Reduce your client's cadence.",
            http_status=status.HTTP_429_TOO_MANY_REQUESTS,
            retry_after_seconds=60,
        )

    # ── 4. Fingerprint must match what was bound at activation ──────────────
    if payload.bound_fingerprints and body.fingerprint not in payload.bound_fingerprints:
        await _log_activation(
            db,
            license_id=license_id,
            tenant_id=payload.tenant_id,
            fingerprint=body.fingerprint,
            event=EVENT_DENIED,
            reason=REASON_FINGERPRINT_MISMATCH,
            ip=client_ip,
            user_agent=user_agent,
        )
        await db.commit()
        return _err(
            "FINGERPRINT_MISMATCH",
            "Token was issued for a different device. Re-activate from this device.",
            http_status=status.HTTP_403_FORBIDDEN,
        )

    # ── 5. Fresh DB lookup for current license status ───────────────────────
    result = await db.execute(select(License).where(License.id == license_id))
    lic: Optional[License] = result.scalar_one_or_none()
    if lic is None:
        # License row was deleted entirely — treat as revocation, push to cache.
        await add_revoked(license_id)
        return _err(
            REASON_KEY_REVOKED,
            "License no longer exists.",
            http_status=status.HTTP_403_FORBIDDEN,
        )

    now = _now()
    deny_reason: Optional[tuple[str, str]] = None
    if lic.status == STATUS_REVOKED:
        deny_reason = (REASON_KEY_REVOKED, "This license has been revoked.")
    elif lic.status == STATUS_SUSPENDED:
        deny_reason = (
            REASON_KEY_SUSPENDED,
            "This license is suspended. Contact support.",
        )
    elif lic.expires_at <= now:
        deny_reason = (
            REASON_KEY_EXPIRED,
            f"License expired at {lic.expires_at.isoformat()}.",
        )

    if deny_reason is not None:
        reason_code, msg = deny_reason
        await add_revoked(license_id)  # so token-bearing clients learn fast
        await _log_activation(
            db,
            license_id=license_id,
            tenant_id=lic.tenant_id,
            fingerprint=body.fingerprint,
            event=EVENT_DENIED,
            reason=reason_code,
            ip=client_ip,
            user_agent=user_agent,
        )
        await db.commit()
        return _err(reason_code, msg, http_status=status.HTTP_403_FORBIDDEN)

    # ── 6. Touch the device row & log heartbeat ─────────────────────────────
    device_row = (
        await db.execute(
            select(LicenseDevice).where(
                LicenseDevice.license_id == license_id,
                LicenseDevice.fingerprint == body.fingerprint,
            )
        )
    ).scalar_one_or_none()
    if device_row is not None and device_row.revoked_at is not None:
        await add_revoked(license_id)
        return _err(
            "DEVICE_REVOKED",
            "This device has been revoked. Re-activate from another device or contact support.",
            http_status=status.HTTP_403_FORBIDDEN,
        )
    if device_row is not None:
        device_row.last_seen_at = now
        device_row.last_ip = client_ip
        device_row.last_user_agent = user_agent
        if body.platform:
            device_row.platform = body.platform

    await _log_activation(
        db,
        license_id=license_id,
        tenant_id=lic.tenant_id,
        fingerprint=body.fingerprint,
        event=EVENT_HEARTBEAT,
        reason=None,
        ip=client_ip,
        user_agent=user_agent,
    )

    # ── 7. Mint refreshed token and return ──────────────────────────────────
    try:
        signer = get_signer()
        new_token, new_exp = signer.mint_token(lic, fingerprint=body.fingerprint)
    except Exception as exc:
        logger.error("license.heartbeat_signing_failed", error=str(exc), license_id=lic.id)
        await db.rollback()
        return _err(
            "SIGNING_FAILED",
            "Internal signing error during heartbeat.",
            http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    await db.commit()

    logger.info(
        "license.heartbeat_ok",
        license_id=license_id,
        tenant_id=lic.tenant_id,
        fingerprint_prefix=body.fingerprint[:16],
        version=body.version,
    )

    return JSONResponse(
        content=HeartbeatResponse(
            token=new_token,
            expires_at=new_exp,
            heartbeat_after_seconds=settings.license_heartbeat_interval_seconds,
            server_now=now,
            plan=lic.plan,
            features=dict(lic.features or {}),
            license_id=lic.id,
        ).model_dump(mode="json"),
        status_code=status.HTTP_200_OK,
    )


# ── GET /api/license/status ──────────────────────────────────────────────────


@router.get("/status")
async def license_status(
    current_user: Annotated[TokenData, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """Return the active license for the caller's tenant.

    Two-pass lookup (no RLS — uses get_db):
      1. License.tenant_id == JWT tenant_id (org-assigned license)
      2. LicenseDevice.fingerprint == JWT user_id (self-activated key)
    """
    now = _now()

    # Pass 1 — license explicitly assigned to this tenant
    result = await db.execute(
        select(License).where(
            License.tenant_id == current_user.tenant_id,
            License.status == STATUS_ACTIVE,
            License.expires_at > now,
        )
    )
    lic: Optional[License] = result.scalar_one_or_none()

    # Pass 2 — user activated a key themselves (fingerprint == Clerk user_id)
    if lic is None:
        device_res = await db.execute(
            select(LicenseDevice)
            .join(License, LicenseDevice.license_id == License.id)
            .where(
                LicenseDevice.fingerprint == current_user.user_id,
                LicenseDevice.revoked_at.is_(None),
                License.status == STATUS_ACTIVE,
                License.expires_at > now,
            )
        )
        device = device_res.scalar_one_or_none()
        if device is not None:
            lic_res = await db.execute(
                select(License).where(License.id == device.license_id)
            )
            lic = lic_res.scalar_one_or_none()

    if lic is None:
        return JSONResponse(content={"active": False, "plan": None, "expires_at": None})

    return JSONResponse(content={
        "active": True,
        "plan": lic.plan,
        "expires_at": lic.expires_at.isoformat(),
        "features": dict(lic.features or {}),
        "license_id": lic.id,
    })
