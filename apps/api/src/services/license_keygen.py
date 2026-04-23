"""License key generation and validation.

Format (Phase 0 §3.5 LOCKED):
    TNZO-XXXXX-XXXXX-XXXXX-XXXXX

  - Static product prefix `TNZO-`
  - Three random groups (5 chars each = 75 bits of entropy)
  - One checksum group (CRC-16 of the body, base32-encoded into 5 chars)
  - Crockford base32 alphabet (excludes I, L, O, U)
  - Case-insensitive on input; ambiguous chars (I->1, L->1, O->0) normalized
  - Stored uppercase

The CRC catches typos client-side before any server round-trip. Real security
is the Ed25519 signature on the license token, NOT this string.
"""

from __future__ import annotations

import hashlib
import re
import secrets

PRODUCT_PREFIX = "TNZO"
CROCKFORD_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

_CROCKFORD_DECODE = {ch: i for i, ch in enumerate(CROCKFORD_ALPHABET)}
# Crockford normalization: I/L -> 1, O -> 0. U is excluded but we accept it
# defensively as V to avoid frustrating support tickets.
_CROCKFORD_NORMALIZE = {"I": "1", "L": "1", "O": "0", "U": "V"}

_GROUP_LEN = 5
_NUM_RANDOM_GROUPS = 3
_KEY_RE = re.compile(r"^TNZO(-[0-9A-Z]{5}){4}$")


def _crc16_ccitt(data: bytes) -> int:
    """CRC-16/CCITT-FALSE — poly 0x1021, init 0xFFFF."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if (crc & 0x8000) else (crc << 1) & 0xFFFF
    return crc


def _encode_base32(value: int, width: int) -> str:
    chars = []
    for _ in range(width):
        chars.append(CROCKFORD_ALPHABET[value & 0x1F])
        value >>= 5
    return "".join(reversed(chars))


def _normalize(raw: str) -> str:
    """Strip whitespace, uppercase, and translate ambiguous Crockford chars.

    The literal product prefix ``TNZO-`` is preserved verbatim — its trailing
    ``O`` would otherwise be translated to ``0`` and break the CRC check.
    A user-typed ``TNZ0-`` is corrected back to ``TNZO-`` for typo tolerance.
    """
    cleaned = raw.strip().upper().replace(" ", "")
    if cleaned.startswith("TNZ0-"):
        cleaned = PRODUCT_PREFIX + "-" + cleaned[len(PRODUCT_PREFIX) + 1 :]
    if cleaned.startswith(PRODUCT_PREFIX + "-"):
        body = cleaned[len(PRODUCT_PREFIX) + 1 :]
        body_norm = "".join(_CROCKFORD_NORMALIZE.get(ch, ch) for ch in body)
        return f"{PRODUCT_PREFIX}-{body_norm}"
    return "".join(_CROCKFORD_NORMALIZE.get(ch, ch) for ch in cleaned)


def generate_license_key() -> str:
    """Generate a fresh license key.

    Returns
    -------
    str
        Key in canonical form ``TNZO-XXXXX-XXXXX-XXXXX-CCCCC``.
    """
    rand_value = secrets.randbits(_NUM_RANDOM_GROUPS * _GROUP_LEN * 5)
    rand_chars = _encode_base32(rand_value, _NUM_RANDOM_GROUPS * _GROUP_LEN)
    body = f"{PRODUCT_PREFIX}-{rand_chars[:5]}-{rand_chars[5:10]}-{rand_chars[10:15]}"

    crc = _crc16_ccitt(body.replace("-", "").encode("ascii"))
    # CRC is 16 bits; encode into 5 chars (25 bits) by left-padding with 9 zero bits.
    checksum = _encode_base32(crc << 9, _GROUP_LEN)
    return f"{body}-{checksum}"


def validate_license_key_format(key: str) -> bool:
    """Validate the structural format and CRC of a license key.

    Returns ``True`` only if the key is well-formed AND the CRC matches.
    Does not check the database — that is the caller's job.
    """
    normalized = _normalize(key)
    if not _KEY_RE.match(normalized):
        return False

    parts = normalized.split("-")
    body = "".join(parts[:-1])  # TNZO + 3 random groups, no hyphens
    expected_checksum = _encode_base32(_crc16_ccitt(body.encode("ascii")) << 9, _GROUP_LEN)
    return parts[-1] == expected_checksum


def normalize_license_key(key: str) -> str:
    """Return canonical form (uppercase, hyphenated) or raise ValueError."""
    normalized = _normalize(key)
    if not _KEY_RE.match(normalized):
        msg = "key does not match TNZO-XXXXX-XXXXX-XXXXX-XXXXX format"
        raise ValueError(msg)
    return normalized


def hash_license_key(key: str) -> str:
    """SHA-256 hex digest of the canonical-form key. Stored in licenses.key_hash."""
    return hashlib.sha256(normalize_license_key(key).encode("ascii")).hexdigest()


def key_prefix(key: str) -> str:
    """First two groups (`TNZO-XXXXX`, 10 chars) — safe to display in UI."""
    normalized = normalize_license_key(key)
    return normalized[: len(PRODUCT_PREFIX) + 1 + _GROUP_LEN]


def generate_fingerprint_salt() -> str:
    """Random 32-hex-char salt embedded in each license payload."""
    return secrets.token_hex(16)
