"""License enforcement — the hot-path gate every protected route runs through.

Two entry points:

  * ``Depends(require_valid_license)`` — the standard SaaS path. Reads
    ``current_user.tenant_id`` (from Clerk JWT or local HS256), looks up an
    active License row, returns a ``LicenseGuard`` that the route uses for
    feature checks and usage counters.

  * ``Depends(verify_license_token)`` — for non-Clerk clients (future
    desktop/agent). Reads an ``X-License-Token`` header, verifies the
    PASETO signature with the cached public key, returns a guard built
    from the token's payload (no DB read on the hot path).

Behaviour is gated by ``settings.licensing_mode``:

  * ``off`` (default)    — every guard is unrestricted; existing flows unchanged.
  * ``warn``             — log denials, still return unrestricted guard.
  * ``enforce``          — 402 / 429 on failure.

This lets us ship the code in ``off``, flip to ``warn`` to see what would
have been denied, then ``enforce`` once the noise is gone (Phase 0 §8 rollout).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Optional

import structlog
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
try:
    from tenzo_licensing import (
        ExpiredLicenseError,
        InvalidSignatureError,
        LicenseError,
        LicensePayload,
        NotYetValidError,
        PublicKey,
        UnknownKeyIdError,
        load_public_key_from_file,
        verify_license,
    )
    _LICENSING_SDK_AVAILABLE = True
except ImportError:
    _LICENSING_SDK_AVAILABLE = False

    class LicenseError(Exception): pass  # type: ignore[no-redef]
    class ExpiredLicenseError(LicenseError): pass  # type: ignore[no-redef]
    class InvalidSignatureError(LicenseError): pass  # type: ignore[no-redef]
    class NotYetValidError(LicenseError): pass  # type: ignore[no-redef]
    class UnknownKeyIdError(LicenseError): pass  # type: ignore[no-redef]
    class LicensePayload: pass  # type: ignore[no-redef]
    class PublicKey: pass  # type: ignore[no-redef]

    def load_public_key_from_file(*args, **kwargs):  # type: ignore[no-redef]
        return None

    def verify_license(*args, **kwargs):  # type: ignore[no-redef]
        raise LicenseError("tenzo_licensing SDK not installed")

from auth import TokenData, get_current_user
from config import settings
from database import get_db
from db_models import (
    STATUS_ACTIVE,
    License,
    LicenseUsageCounter,
)
from services.license_cache import is_revoked
from services.license_features import merge_features
from services.license_metrics import (
    license_enforcement_checks_total,
    license_feature_denials_total,
    license_usage_limit_denials_total,
)

logger = structlog.get_logger()

# ── public-key keystore (lazy-loaded singleton) ──────────────────────────────

_public_keys: dict[str, PublicKey] = {}


def _get_public_keys() -> dict[str, PublicKey]:
    """Return the active keyset {kid: PublicKey}, loading from disk on first use."""
    global _public_keys
    if not _public_keys:
        path = Path(settings.license_public_key_path)
        if path.exists():
            _public_keys[settings.license_active_kid] = load_public_key_from_file(
                settings.license_active_kid, path
            )
            logger.info(
                "license_enforcement.public_keys_loaded",
                kid=settings.license_active_kid,
                path=str(path),
            )
        else:
            logger.warning(
                "license_enforcement.public_key_missing",
                path=str(path),
            )
    return _public_keys


def reset_public_keys_for_tests() -> None:
    global _public_keys
    _public_keys = {}


# ── LicenseGuard ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LicenseGuard:
    """Returned by the dependency. Carries the effective entitlement state."""

    license_id: Optional[int]
    tenant_id: str
    plan: str
    features: dict[str, Any] = field(default_factory=dict)
    bypass: bool = False  # True under modes 'off' and 'warn'

    @classmethod
    def unrestricted(cls, tenant_id: str = "") -> "LicenseGuard":
        return cls(
            license_id=None,
            tenant_id=tenant_id,
            plan="bypass",
            features={},
            bypass=True,
        )

    @classmethod
    def from_license_row(cls, lic: License) -> "LicenseGuard":
        return cls(
            license_id=lic.id,
            tenant_id=lic.tenant_id,
            plan=lic.plan,
            features=merge_features(lic.plan, lic.features),
        )

    @classmethod
    def from_payload(cls, payload: LicensePayload) -> "LicenseGuard":
        try:
            license_id = int(payload.lic_id)
        except (TypeError, ValueError):
            license_id = None
        return cls(
            license_id=license_id,
            tenant_id=payload.tenant_id,
            plan=payload.plan,
            features=merge_features(payload.plan, payload.features),
        )

    # ── instance helpers ─────────────────────────────────────────────────────

    def require_feature(self, feature: str) -> None:
        """Raise 402 FEATURE_NOT_LICENSED if the feature isn't enabled.

        In ``off``/``warn`` mode this is a no-op (with a log line under warn).
        """
        if self.bypass:
            return
        if not self.features.get(feature):
            try:
                license_feature_denials_total.labels(
                    plan=self.plan, feature=feature
                ).inc()
            except Exception:
                pass
            if settings.licensing_mode == "warn":
                logger.warning(
                    "license.feature_not_licensed_warn",
                    tenant_id=self.tenant_id,
                    plan=self.plan,
                    feature=feature,
                )
                return
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "error": "FEATURE_NOT_LICENSED",
                    "message": (
                        f"Feature '{feature}' is not included in your plan "
                        f"({self.plan}). Upgrade to access it."
                    ),
                    "feature": feature,
                    "plan": self.plan,
                },
            )

    async def check_and_increment(
        self,
        db: AsyncSession,
        counter: str,
        *,
        max_key: Optional[str] = None,
        n: int = 1,
        period: str = "month",
    ) -> int:
        """Atomically bump a usage counter for the current bucket.

        If ``max_key`` is provided (e.g. ``"max_runs_per_month"``) and the
        post-increment count would exceed the limit, raises 429
        ``USAGE_LIMIT_EXCEEDED``. ``None`` limit value means unlimited.

        ``period`` is ``"month"`` (period_start = first of UTC month) or
        ``"day"`` (period_start = today UTC).

        Returns the post-increment count. In bypass modes returns 0 and
        skips the DB write entirely.
        """
        if self.bypass or self.license_id is None:
            return 0

        period_start = _period_start(period)
        max_value: Optional[int] = self.features.get(max_key) if max_key else None

        # Fetch current count first so we can deny BEFORE incrementing.
        current = await db.execute(
            select(LicenseUsageCounter.count).where(
                LicenseUsageCounter.license_id == self.license_id,
                LicenseUsageCounter.period_start == period_start,
                LicenseUsageCounter.counter_name == counter,
            )
        )
        current_count: int = current.scalar_one_or_none() or 0

        if max_value is not None and current_count + n > max_value:
            try:
                license_usage_limit_denials_total.labels(
                    counter=counter, plan=self.plan
                ).inc()
            except Exception:
                pass
            if settings.licensing_mode == "warn":
                logger.warning(
                    "license.usage_limit_exceeded_warn",
                    tenant_id=self.tenant_id,
                    license_id=self.license_id,
                    counter=counter,
                    current=current_count,
                    requested=n,
                    limit=max_value,
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "error": "USAGE_LIMIT_EXCEEDED",
                        "message": (
                            f"Usage limit reached: {counter}={current_count}/"
                            f"{max_value} for this {period}."
                        ),
                        "counter": counter,
                        "current": current_count,
                        "limit": max_value,
                        "period": period,
                    },
                )

        # UPSERT — atomic increment.
        stmt = (
            pg_insert(LicenseUsageCounter)
            .values(
                license_id=self.license_id,
                period_start=period_start,
                counter_name=counter,
                tenant_id=self.tenant_id,
                count=n,
            )
            .on_conflict_do_update(
                index_elements=["license_id", "period_start", "counter_name"],
                set_={
                    "count": LicenseUsageCounter.count + n,
                },
            )
            .returning(LicenseUsageCounter.count)
        )
        result = await db.execute(stmt)
        new_count: int = result.scalar_one()
        await db.commit()
        return new_count


# ── period helpers ───────────────────────────────────────────────────────────


def _period_start(period: str) -> date:
    today = datetime.now(tz=timezone.utc).date()
    if period == "month":
        return today.replace(day=1)
    if period == "day":
        return today
    msg = f"unknown period {period!r}"
    raise ValueError(msg)


# ── Dependencies ─────────────────────────────────────────────────────────────


def _no_active_license_response() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        detail={
            "error": "LICENSE_REQUIRED",
            "message": (
                "No active license for your workspace. "
                "Contact your administrator or upgrade your subscription."
            ),
        },
    )


def _expired_license_response(expires_at: datetime) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        detail={
            "error": "LICENSE_EXPIRED",
            "message": f"Your license expired at {expires_at.isoformat()}.",
            "expired_at": expires_at.isoformat(),
        },
    )


def _bump_check(mode: str, result: str) -> None:
    """Best-effort metric increment — never raises."""
    try:
        license_enforcement_checks_total.labels(mode=mode, result=result).inc()
    except Exception:
        pass


async def require_valid_license(
    user: Annotated[TokenData, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LicenseGuard:
    """Look up an active License row for the caller's tenant_id.

    Mode handling:
      * ``off``      → unrestricted guard, no DB read
      * ``warn``     → unrestricted guard, log denial
      * ``enforce``  → 402 LICENSE_REQUIRED on missing/expired/revoked
    """
    mode = settings.licensing_mode

    if mode == "off":
        _bump_check(mode, "bypass")
        return LicenseGuard.unrestricted(user.tenant_id)

    now = datetime.now(tz=timezone.utc)
    result = await db.execute(
        select(License)
        .where(
            License.tenant_id == user.tenant_id,
            License.status == STATUS_ACTIVE,
        )
        .order_by(License.expires_at.desc())
        .limit(1)
    )
    lic = result.scalar_one_or_none()

    if lic is None:
        _bump_check(mode, "deny_no_license")
        if mode == "warn":
            logger.warning(
                "license.no_active_license_warn",
                tenant_id=user.tenant_id,
                user_id=user.user_id,
            )
            return LicenseGuard.unrestricted(user.tenant_id)
        raise _no_active_license_response()

    if lic.expires_at <= now:
        _bump_check(mode, "deny_expired")
        if mode == "warn":
            logger.warning(
                "license.expired_warn",
                tenant_id=user.tenant_id,
                license_id=lic.id,
                expires_at=lic.expires_at.isoformat(),
            )
            return LicenseGuard.unrestricted(user.tenant_id)
        raise _expired_license_response(lic.expires_at)

    if lic.not_before > now:
        _bump_check(mode, "deny_not_yet_valid")
        if mode == "warn":
            logger.warning(
                "license.not_yet_valid_warn",
                tenant_id=user.tenant_id,
                license_id=lic.id,
                not_before=lic.not_before.isoformat(),
            )
            return LicenseGuard.unrestricted(user.tenant_id)
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "LICENSE_NOT_YET_VALID",
                "message": f"License not valid until {lic.not_before.isoformat()}.",
                "not_before": lic.not_before.isoformat(),
            },
        )

    _bump_check(mode, "allow")
    return LicenseGuard.from_license_row(lic)


async def verify_license_token(
    x_license_token: Annotated[Optional[str], Header(alias="X-License-Token")] = None,
) -> LicenseGuard:
    """Verify a PASETO token from the X-License-Token header.

    For non-Clerk clients (future desktop/agent). Stateless: no DB read on
    the hot path, just signature + expiry verification with the cached
    public key.

    Behaviour under modes mirrors require_valid_license, except in ``off``
    mode the header is ignored (still returns unrestricted). In ``enforce``
    mode the header MUST be present and valid.
    """
    mode = settings.licensing_mode
    if mode == "off":
        return LicenseGuard.unrestricted("")

    if not x_license_token:
        if mode == "warn":
            logger.warning("license.token_missing_warn")
            return LicenseGuard.unrestricted("")
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "LICENSE_REQUIRED",
                "message": "X-License-Token header is required.",
            },
        )

    try:
        payload = verify_license(x_license_token, _get_public_keys())
    except ExpiredLicenseError as e:
        if mode == "warn":
            logger.warning("license.token_expired_warn", error=str(e))
            return LicenseGuard.unrestricted("")
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={"error": "LICENSE_EXPIRED", "message": str(e)},
        ) from e
    except NotYetValidError as e:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={"error": "LICENSE_NOT_YET_VALID", "message": str(e)},
        ) from e
    except (InvalidSignatureError, UnknownKeyIdError, LicenseError) as e:
        if mode == "warn":
            logger.warning("license.token_invalid_warn", error=str(e))
            return LicenseGuard.unrestricted("")
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={"error": "LICENSE_INVALID", "message": "Token failed verification."},
        ) from e

    # ── Phase 6: revocation cache check ──────────────────────────────────────
    # The token's signature passed but the license may have been revoked
    # since issuance. The cache is updated by /heartbeat denials and admin
    # /revoke calls — this lets us deny within seconds instead of waiting
    # for the token to expire (up to 30d).
    try:
        license_id_int = int(payload.lic_id)
    except (TypeError, ValueError):
        license_id_int = None
    if license_id_int is not None and await is_revoked(license_id_int):
        if mode == "warn":
            logger.warning(
                "license.token_revoked_warn",
                license_id=license_id_int,
                tenant_id=payload.tenant_id,
            )
            return LicenseGuard.unrestricted(payload.tenant_id)
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "LICENSE_REVOKED",
                "message": "License has been revoked. Re-activate from a current key.",
            },
        )

    return LicenseGuard.from_payload(payload)
