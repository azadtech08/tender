"""Lazy-loaded singleton signer for license tokens.

Loads the Ed25519 private key from one of two sources, in this order:

1. ``LICENSE_PRIVATE_KEY_PATH`` — local file (used in dev/CI)
2. AWS Secrets Manager secret named ``LICENSE_SIGNING_KEY_SECRET_ID`` (prod)

Caches the loaded key in process memory so subsequent activate/heartbeat
requests don't re-read the file or call AWS on every request.

Usage:
    signer = get_signer()
    token = signer.mint_token(license_row, fingerprint="abc...", ttl_seconds=...)
"""

from __future__ import annotations

import secrets as _secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Union

import structlog
try:
    from tenzo_licensing import (
        DeviceBindingMode,
        LicensePayload,
        PrivateKey,
        load_private_key,
        sign_license,
    )
    _TENZO_AVAILABLE = True
except ImportError:
    _TENZO_AVAILABLE = False
    class DeviceBindingMode: FINGERPRINT = "fingerprint"  # type: ignore[misc]
    class LicensePayload: pass  # type: ignore[misc]
    class PrivateKey: pass  # type: ignore[misc]
    def load_private_key(*a, **k): return None  # type: ignore[misc]
    def sign_license(*a, **k): raise RuntimeError("tenzo_licensing not installed")  # type: ignore[misc]

from config import settings
from db_models import License

logger = structlog.get_logger()

_signer_singleton: Optional[Union["LicenseSigner", "_JwtFallbackSigner"]] = None


class LicenseSigner:
    """Holds the active private key and mints signed PASETO license tokens."""

    def __init__(self, private_key: PrivateKey) -> None:
        self._private_key = private_key

    @property
    def kid(self) -> str:
        return self._private_key.kid

    def mint_token(
        self,
        license_row: License,
        *,
        fingerprint: str,
        ttl_seconds: Optional[int] = None,
    ) -> tuple[str, datetime]:
        now = datetime.now(tz=timezone.utc)
        ttl = ttl_seconds or settings.license_token_ttl_seconds
        base_exp = now + timedelta(seconds=ttl)
        token_exp = (
            min(base_exp, license_row.expires_at)
            if license_row.expires_at is not None
            else base_exp
        )

        binding_mode = (
            DeviceBindingMode.HWID if license_row.max_devices > 0 else DeviceBindingMode.NONE
        )

        payload = LicensePayload(
            lic_id=str(license_row.id),
            tenant_id=license_row.tenant_id,
            plan=license_row.plan,
            issued_at=now,
            not_before=license_row.not_before,
            expires_at=token_exp,
            features=dict(license_row.features or {}),
            device_binding_mode=binding_mode,
            bound_fingerprints=[fingerprint] if binding_mode != DeviceBindingMode.NONE else [],
            max_devices=license_row.max_devices,
            fingerprint_salt=license_row.fingerprint_salt,
            nonce=_secrets.token_hex(16),
        )
        token = sign_license(payload, self._private_key)
        return token, token_exp


class _JwtFallbackSigner:
    """HS256 JWT fallback used in dev when tenzo_licensing or key files are absent.

    NOT suitable for production — the token is signed with the JWT_SECRET_KEY
    env var rather than an Ed25519 key pair.
    """

    @property
    def kid(self) -> str:
        return "jwt-dev-fallback"

    def mint_token(
        self,
        license_row: License,
        *,
        fingerprint: str,
        ttl_seconds: Optional[int] = None,
    ) -> tuple[str, datetime]:
        from jose import jwt  # python-jose is a declared dependency

        now = datetime.now(tz=timezone.utc)
        ttl = ttl_seconds or settings.license_token_ttl_seconds
        base_exp = now + timedelta(seconds=ttl)
        token_exp = (
            min(base_exp, license_row.expires_at)
            if license_row.expires_at is not None
            else base_exp
        )

        claims = {
            "lic_id": str(license_row.id),
            "tenant_id": license_row.tenant_id,
            "plan": license_row.plan,
            "iat": int(now.timestamp()),
            "exp": int(token_exp.timestamp()),
            "fingerprint": fingerprint,
            "nonce": _secrets.token_hex(16),
        }
        token = jwt.encode(claims, settings.jwt_secret_key, algorithm="HS256")
        return token, token_exp


def _load_private_key_from_disk(path: str, kid: str) -> PrivateKey:
    pem = Path(path).read_bytes()
    return load_private_key(kid, pem)


def _load_private_key_from_secrets_manager(secret_id: str, kid: str) -> PrivateKey:
    import boto3  # local import — only needed in prod path

    client = boto3.client("secretsmanager")
    resp = client.get_secret_value(SecretId=secret_id)
    pem = resp.get("SecretBinary") or resp["SecretString"].encode("utf-8")
    return load_private_key(kid, pem)


def _build_signer() -> Union[LicenseSigner, _JwtFallbackSigner]:
    kid = settings.license_active_kid

    if not _TENZO_AVAILABLE:
        logger.warning(
            "license_signer.tenzo_unavailable_jwt_fallback",
            note="Install tenzo_licensing for PASETO tokens in production",
        )
        return _JwtFallbackSigner()

    if settings.license_private_key_path:
        key_path = Path(settings.license_private_key_path)
        if not key_path.exists():
            logger.warning(
                "license_signer.key_file_missing_jwt_fallback",
                path=str(key_path),
                note="Create the key file for PASETO tokens in production",
            )
            return _JwtFallbackSigner()
        logger.info(
            "license_signer.load_from_disk",
            path=str(key_path),
            kid=kid,
        )
        return LicenseSigner(_load_private_key_from_disk(str(key_path), kid))

    logger.info(
        "license_signer.load_from_secrets_manager",
        secret_id=settings.license_signing_key_secret_id,
        kid=kid,
    )
    return LicenseSigner(
        _load_private_key_from_secrets_manager(
            settings.license_signing_key_secret_id, kid
        )
    )


def get_signer() -> Union[LicenseSigner, _JwtFallbackSigner]:
    """Return the process-wide signer, building it on first use."""
    global _signer_singleton
    if _signer_singleton is None:
        _signer_singleton = _build_signer()
    return _signer_singleton


def reset_signer_for_tests() -> None:
    """Test hook — drop the cached signer so the next get_signer() re-builds."""
    global _signer_singleton
    _signer_singleton = None
