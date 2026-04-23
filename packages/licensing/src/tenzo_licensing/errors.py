"""License token exceptions.

All errors inherit from ``LicenseError`` so callers can catch any licensing
failure with a single except clause.
"""

from __future__ import annotations


class LicenseError(Exception):
    """Base class for all license-token errors."""


class MalformedTokenError(LicenseError):
    """Token structure is invalid (wrong segments, bad footer, bad JSON)."""


class InvalidSignatureError(LicenseError):
    """Signature verification failed — token was tampered with or signed with
    a different key than the one presented for verification."""


class ExpiredLicenseError(LicenseError):
    """Token's ``expires_at`` is in the past (beyond the allowed leeway)."""


class NotYetValidError(LicenseError):
    """Token's ``not_before`` is in the future (beyond the allowed leeway)."""


class UnknownKeyIdError(LicenseError):
    """Token's ``kid`` is not in the verifier's keyset — verifier cannot know
    if the signature is valid or not, so the token is rejected."""
