"""Ed25519 key generation and loading for Tenzo licensing.

Keys are wrapped in ``PrivateKey`` / ``PublicKey`` dataclasses that carry a
``kid`` (key ID) alongside the underlying pyseto key. The ``kid`` is what
lets verifiers pick the right key during rotation (v1 -> v2 -> ...).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pyseto
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

_PASETO_VERSION = 4
_PASETO_PURPOSE = "public"


@dataclass(frozen=True)
class PrivateKey:
    kid: str
    pyseto_key: pyseto.Key


@dataclass(frozen=True)
class PublicKey:
    kid: str
    pyseto_key: pyseto.Key


def generate_keypair() -> tuple[bytes, bytes]:
    """Generate a fresh Ed25519 keypair.

    Returns
    -------
    (private_pem, public_pem)
        Both PEM-encoded byte strings. ``private_pem`` is PKCS8 unencrypted;
        ``public_pem`` is SubjectPublicKeyInfo.
    """
    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


def load_private_key(kid: str, pem_bytes: bytes) -> PrivateKey:
    key = pyseto.Key.new(
        version=_PASETO_VERSION,
        purpose=_PASETO_PURPOSE,
        key=pem_bytes,
    )
    return PrivateKey(kid=kid, pyseto_key=key)


def load_public_key(kid: str, pem_bytes: bytes) -> PublicKey:
    key = pyseto.Key.new(
        version=_PASETO_VERSION,
        purpose=_PASETO_PURPOSE,
        key=pem_bytes,
    )
    return PublicKey(kid=kid, pyseto_key=key)


def load_public_key_from_file(kid: str, path: Path) -> PublicKey:
    return load_public_key(kid, path.read_bytes())
