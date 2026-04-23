"""Sign and verify Tenzo license tokens.

Tokens are PASETO v4.public (Ed25519). The footer is a small JSON object
containing the ``kid`` so verifiers can select the right public key during
key rotation. The footer is authenticated by the signature even though it is
not encrypted.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone

import pyseto

from .errors import (
    ExpiredLicenseError,
    InvalidSignatureError,
    MalformedTokenError,
    NotYetValidError,
    UnknownKeyIdError,
)
from .keys import PrivateKey, PublicKey
from .payload import LicensePayload

_DEFAULT_LEEWAY_SECONDS = 300


def sign_license(payload: LicensePayload, private_key: PrivateKey) -> str:
    footer_bytes = json.dumps(
        {"kid": private_key.kid}, separators=(",", ":")
    ).encode("utf-8")
    token_bytes = pyseto.encode(
        private_key.pyseto_key,
        payload=payload.to_json_bytes(),
        footer=footer_bytes,
    )
    return token_bytes.decode("utf-8")


def verify_license(
    token: str,
    public_keys: dict[str, PublicKey],
    *,
    now: datetime | None = None,
    leeway_seconds: int = _DEFAULT_LEEWAY_SECONDS,
) -> LicensePayload:
    if now is None:
        now = datetime.now(timezone.utc)

    try:
        kid = _extract_kid(token)
    except (ValueError, KeyError, json.JSONDecodeError) as e:
        raise MalformedTokenError(f"could not parse token footer: {e}") from e

    public_key = public_keys.get(kid)
    if public_key is None:
        raise UnknownKeyIdError(f"unknown kid: {kid!r}")

    try:
        decoded = pyseto.decode(public_key.pyseto_key, token.encode("utf-8"))
    except Exception as e:
        raise InvalidSignatureError(
            f"token verification failed: {type(e).__name__}: {e}"
        ) from e

    try:
        payload = LicensePayload.from_json_bytes(decoded.payload)
    except Exception as e:
        raise MalformedTokenError(f"invalid payload: {e}") from e

    _check_timing(payload, now=now, leeway_seconds=leeway_seconds)
    return payload


def _extract_kid(token: str) -> str:
    parts = token.split(".")
    if len(parts) != 4:
        raise ValueError(
            f"expected 4-segment token (v4.public.payload.footer), got {len(parts)}"
        )
    footer_b64 = parts[3]
    padded = footer_b64 + "=" * (-len(footer_b64) % 4)
    footer_json = base64.urlsafe_b64decode(padded)
    data = json.loads(footer_json)
    kid = data.get("kid")
    if not isinstance(kid, str) or not kid:
        raise ValueError("footer does not contain a non-empty string 'kid'")
    return kid


def _check_timing(
    payload: LicensePayload,
    *,
    now: datetime,
    leeway_seconds: int,
) -> None:
    leeway = timedelta(seconds=leeway_seconds)
    if payload.not_before - leeway > now:
        raise NotYetValidError(
            f"license not valid until {payload.not_before.isoformat()}"
        )
    if payload.expires_at + leeway < now:
        raise ExpiredLicenseError(
            f"license expired at {payload.expires_at.isoformat()}"
        )
