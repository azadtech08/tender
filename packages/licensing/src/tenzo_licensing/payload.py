"""License token payload schema.

A ``LicensePayload`` is the signed body of a Tenzo license token. It is
immutable, strictly validated, and round-trips to canonical JSON for
embedding in a PASETO v4.public token.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DeviceBindingMode(StrEnum):
    NONE = "none"
    HWID = "hwid"
    IP_CIDR = "ip_cidr"


class LicensePayload(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        use_enum_values=False,
    )

    lic_id: str = Field(min_length=1, max_length=64)
    tenant_id: str = Field(min_length=1, max_length=64)
    plan: str = Field(min_length=1, max_length=32)

    issued_at: datetime
    not_before: datetime
    expires_at: datetime

    features: dict[str, Any] = Field(default_factory=dict)

    device_binding_mode: DeviceBindingMode = DeviceBindingMode.NONE
    bound_fingerprints: list[str] = Field(default_factory=list)
    max_devices: int = Field(default=1, ge=1, le=1000)
    fingerprint_salt: str = Field(min_length=16, max_length=128)

    nonce: str = Field(min_length=16, max_length=64)

    @field_validator("issued_at", "not_before", "expires_at")
    @classmethod
    def _ensure_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            msg = "datetime must be timezone-aware (UTC)"
            raise ValueError(msg)
        return v.astimezone(timezone.utc)

    @model_validator(mode="after")
    def _check_temporal_order(self) -> "LicensePayload":
        if self.not_before > self.expires_at:
            msg = "not_before cannot be after expires_at"
            raise ValueError(msg)
        return self

    def to_json_bytes(self) -> bytes:
        return self.model_dump_json().encode("utf-8")

    @classmethod
    def from_json_bytes(cls, data: bytes) -> "LicensePayload":
        return cls.model_validate_json(data)
