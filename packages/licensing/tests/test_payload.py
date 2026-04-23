from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from tenzo_licensing import DeviceBindingMode, LicensePayload


def _base_payload_kwargs() -> dict:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return dict(
        lic_id="lic_x",
        tenant_id="tenant-x",
        plan="pro",
        issued_at=now,
        not_before=now,
        expires_at=now + timedelta(days=1),
        fingerprint_salt="a" * 32,
        nonce="b" * 32,
    )


class TestRoundtrip:
    def test_json_roundtrip_equal(self, sample_payload: LicensePayload) -> None:
        restored = LicensePayload.from_json_bytes(sample_payload.to_json_bytes())
        assert restored == sample_payload

    def test_json_is_utf8_bytes(self, sample_payload: LicensePayload) -> None:
        data = sample_payload.to_json_bytes()
        assert isinstance(data, bytes)
        # Must be valid JSON
        assert data.startswith(b"{")


class TestTimezoneHandling:
    def test_rejects_naive_datetime(self) -> None:
        kwargs = _base_payload_kwargs()
        kwargs["issued_at"] = datetime(2026, 1, 1)  # naive
        with pytest.raises(ValidationError, match="timezone-aware"):
            LicensePayload(**kwargs)

    def test_coerces_non_utc_to_utc(self) -> None:
        ist = timezone(timedelta(hours=5, minutes=30))
        kwargs = _base_payload_kwargs()
        kwargs["issued_at"] = datetime(2026, 1, 1, 12, 0, tzinfo=ist)
        kwargs["not_before"] = kwargs["issued_at"]
        kwargs["expires_at"] = kwargs["issued_at"] + timedelta(days=1)
        p = LicensePayload(**kwargs)
        assert p.issued_at.tzinfo == timezone.utc


class TestValidation:
    def test_rejects_extra_fields(self) -> None:
        kwargs = _base_payload_kwargs()
        kwargs["sneaky"] = "field"
        with pytest.raises(ValidationError):
            LicensePayload(**kwargs)

    def test_rejects_not_before_after_expires_at(self) -> None:
        kwargs = _base_payload_kwargs()
        kwargs["not_before"] = kwargs["expires_at"] + timedelta(hours=1)
        with pytest.raises(ValidationError, match="not_before"):
            LicensePayload(**kwargs)

    def test_is_frozen(self, sample_payload: LicensePayload) -> None:
        with pytest.raises(ValidationError):
            sample_payload.plan = "enterprise"  # type: ignore[misc]

    def test_rejects_short_fingerprint_salt(self) -> None:
        kwargs = _base_payload_kwargs()
        kwargs["fingerprint_salt"] = "short"
        with pytest.raises(ValidationError):
            LicensePayload(**kwargs)

    def test_rejects_short_nonce(self) -> None:
        kwargs = _base_payload_kwargs()
        kwargs["nonce"] = "n"
        with pytest.raises(ValidationError):
            LicensePayload(**kwargs)

    def test_rejects_invalid_max_devices(self) -> None:
        kwargs = _base_payload_kwargs()
        kwargs["max_devices"] = 0
        with pytest.raises(ValidationError):
            LicensePayload(**kwargs)


class TestDeviceBinding:
    def test_enum_values(self) -> None:
        assert DeviceBindingMode.NONE == "none"
        assert DeviceBindingMode.HWID == "hwid"
        assert DeviceBindingMode.IP_CIDR == "ip_cidr"

    def test_default_is_none(self) -> None:
        p = LicensePayload(**_base_payload_kwargs())
        assert p.device_binding_mode == DeviceBindingMode.NONE

    def test_accepts_string_value(self) -> None:
        kwargs = _base_payload_kwargs()
        kwargs["device_binding_mode"] = "hwid"
        p = LicensePayload(**kwargs)
        assert p.device_binding_mode == DeviceBindingMode.HWID
