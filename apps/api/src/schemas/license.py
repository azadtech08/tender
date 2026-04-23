"""Pydantic request/response schemas for the licenses API.

Includes:
  - Admin schemas (Phase 3): Create/Extend/Revoke/Suspend, Response/Detail/List
  - Client schemas (Phase 4): Activate request/response, error responses with
    stable error codes
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ── Requests ─────────────────────────────────────────────────────────────────


class LicenseCreate(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=36)
    plan: str = Field(min_length=1, max_length=32)
    expires_at: datetime
    not_before: Optional[datetime] = None
    max_devices: int = Field(default=1, ge=1, le=1000)
    features: dict[str, Any] = Field(default_factory=dict)
    notes: Optional[str] = Field(default=None, max_length=500)


class LicenseExtend(BaseModel):
    new_expires_at: datetime
    reason: Optional[str] = Field(default=None, max_length=200)


class LicenseRevoke(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=200)


class LicenseSuspend(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=200)


# ── Responses ────────────────────────────────────────────────────────────────


class LicenseResponse(BaseModel):
    """Safe representation — no key_hash, no signing material."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    key_prefix: str
    plan: str
    status: str
    signing_kid: str
    not_before: datetime
    expires_at: datetime
    max_devices: int
    features: dict[str, Any]
    issued_by_admin_id: Optional[int]
    revoked_at: Optional[datetime]
    revoked_reason: Optional[str]
    created_at: datetime
    updated_at: datetime


class LicenseCreatedResponse(BaseModel):
    """Returned ONCE on creation — includes the plaintext key.

    The plaintext key is never retrievable after this response is sent.
    """

    license: LicenseResponse
    raw_key: str = Field(
        description=(
            "Plaintext license key — store securely and share with the "
            "customer. This will NEVER be shown again."
        )
    )


class LicenseDetailResponse(BaseModel):
    """License + counts for the detail view."""

    license: LicenseResponse
    device_count: int
    active_device_count: int
    activations_24h: int


class LicenseListResponse(BaseModel):
    items: list[LicenseResponse]
    total: int
    limit: int
    offset: int


class LicenseDeviceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    license_id: int
    fingerprint: str
    hostname: Optional[str]
    platform: Optional[str]
    first_seen_at: datetime
    last_seen_at: datetime
    last_ip: Optional[str]
    revoked_at: Optional[datetime]


class LicenseActivationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    license_id: int
    fingerprint: Optional[str]
    event: str
    reason: Optional[str]
    ip: Optional[str]
    created_at: datetime


# ── Phase 4: client activation ───────────────────────────────────────────────


class ActivateRequest(BaseModel):
    """Body of POST /api/license/activate."""

    key: str = Field(min_length=20, max_length=64)
    fingerprint: str = Field(min_length=16, max_length=128)
    hostname: Optional[str] = Field(default=None, max_length=255)
    platform: Optional[str] = Field(default=None, max_length=32)


class ActivateResponse(BaseModel):
    """Successful activation response."""

    token: str = Field(description="Signed PASETO v4.public license token")
    expires_at: datetime
    heartbeat_after_seconds: int
    plan: str
    features: dict[str, Any]
    license_id: int
    bound_fingerprint: str


class LicenseErrorResponse(BaseModel):
    """Stable error envelope for licensing endpoints.

    The `error` field is a machine-stable code clients should branch on.
    The `message` is human-readable and may change.
    """

    error: str = Field(
        description=(
            "Stable error code: INVALID_KEY | KEY_EXPIRED | KEY_REVOKED | "
            "KEY_SUSPENDED | KEY_NOT_YET_VALID | DEVICE_LIMIT_EXCEEDED | "
            "DEVICE_REVOKED | FINGERPRINT_MISMATCH | TOKEN_INVALID | "
            "RATE_LIMITED | SIGNING_FAILED"
        )
    )
    message: str
    retry_after_seconds: Optional[int] = None


# ── Phase 6: heartbeat ───────────────────────────────────────────────────────


class HeartbeatRequest(BaseModel):
    """Body of POST /api/license/heartbeat.

    The client posts its current signed token + the device fingerprint it
    was activated under. Lightweight telemetry helps anti-sharing analysis
    in Phase 7.
    """

    token: str = Field(min_length=20, description="Currently held license token")
    fingerprint: str = Field(min_length=16, max_length=128)
    version: Optional[str] = Field(default=None, max_length=32)
    platform: Optional[str] = Field(default=None, max_length=32)


class HeartbeatResponse(BaseModel):
    """Successful heartbeat — refreshed token and current schedule."""

    token: str = Field(description="Newly-signed license token; replaces old one")
    expires_at: datetime
    heartbeat_after_seconds: int
    server_now: datetime = Field(
        description=(
            "Server's current UTC timestamp — clients should reset their "
            "grace-period clock to this rather than trusting their own."
        )
    )
    plan: str
    features: dict[str, Any]
    license_id: int
