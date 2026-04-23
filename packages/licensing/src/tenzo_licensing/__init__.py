"""Tenzo licensing primitives — signing and verifying license tokens.

Public API:

    from tenzo_licensing import (
        LicensePayload, DeviceBindingMode,
        sign_license, verify_license,
        generate_keypair, load_private_key, load_public_key,
        PrivateKey, PublicKey,
        LicenseError, MalformedTokenError, InvalidSignatureError,
        ExpiredLicenseError, NotYetValidError, UnknownKeyIdError,
    )
"""

from .errors import (
    ExpiredLicenseError,
    InvalidSignatureError,
    LicenseError,
    MalformedTokenError,
    NotYetValidError,
    UnknownKeyIdError,
)
from .keys import (
    PrivateKey,
    PublicKey,
    generate_keypair,
    load_private_key,
    load_public_key,
    load_public_key_from_file,
)
from .payload import DeviceBindingMode, LicensePayload
from .signing import sign_license, verify_license

__all__ = [
    "DeviceBindingMode",
    "ExpiredLicenseError",
    "InvalidSignatureError",
    "LicenseError",
    "LicensePayload",
    "MalformedTokenError",
    "NotYetValidError",
    "PrivateKey",
    "PublicKey",
    "UnknownKeyIdError",
    "generate_keypair",
    "load_private_key",
    "load_public_key",
    "load_public_key_from_file",
    "sign_license",
    "verify_license",
]

__version__ = "0.1.0"
