from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import pytest

from tenzo_licensing import (
    DeviceBindingMode,
    LicensePayload,
    PrivateKey,
    PublicKey,
    generate_keypair,
    load_private_key,
    load_public_key,
)


@pytest.fixture
def keypair_v1() -> tuple[PrivateKey, PublicKey]:
    priv_pem, pub_pem = generate_keypair()
    return load_private_key("v1", priv_pem), load_public_key("v1", pub_pem)


@pytest.fixture
def keypair_v2() -> tuple[PrivateKey, PublicKey]:
    priv_pem, pub_pem = generate_keypair()
    return load_private_key("v2", priv_pem), load_public_key("v2", pub_pem)


@pytest.fixture
def sample_payload() -> LicensePayload:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return LicensePayload(
        lic_id="lic_01JABCXYZ",
        tenant_id="tenant-abc-123",
        plan="pro",
        issued_at=now,
        not_before=now,
        expires_at=now + timedelta(days=30),
        features={"max_jobs_per_day": 500, "export_xlsx": True},
        device_binding_mode=DeviceBindingMode.HWID,
        bound_fingerprints=[],
        max_devices=2,
        fingerprint_salt=secrets.token_hex(16),
        nonce=secrets.token_hex(16),
    )
