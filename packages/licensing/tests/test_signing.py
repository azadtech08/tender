from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone

import pyseto
import pytest

from tenzo_licensing import (
    ExpiredLicenseError,
    InvalidSignatureError,
    LicensePayload,
    MalformedTokenError,
    NotYetValidError,
    PrivateKey,
    PublicKey,
    UnknownKeyIdError,
    sign_license,
    verify_license,
)


class TestRoundtrip:
    def test_valid_token_verifies(
        self,
        keypair_v1: tuple[PrivateKey, PublicKey],
        sample_payload: LicensePayload,
    ) -> None:
        priv, pub = keypair_v1
        token = sign_license(sample_payload, priv)
        restored = verify_license(token, {"v1": pub})
        assert restored == sample_payload

    def test_token_is_paseto_v4_public(
        self,
        keypair_v1: tuple[PrivateKey, PublicKey],
        sample_payload: LicensePayload,
    ) -> None:
        priv, _ = keypair_v1
        token = sign_license(sample_payload, priv)
        assert isinstance(token, str)
        assert token.startswith("v4.public.")
        assert token.count(".") == 3  # version.purpose.payload.footer


class TestExpiry:
    def _build_payload(
        self, issued: datetime, expires: datetime, sample_payload: LicensePayload
    ) -> LicensePayload:
        return sample_payload.model_copy(
            update={
                "issued_at": issued,
                "not_before": issued,
                "expires_at": expires,
            }
        )

    def test_expired_token_rejects(
        self,
        keypair_v1: tuple[PrivateKey, PublicKey],
        sample_payload: LicensePayload,
    ) -> None:
        priv, pub = keypair_v1
        long_ago = datetime(2020, 1, 1, tzinfo=timezone.utc)
        p = self._build_payload(long_ago, long_ago + timedelta(days=1), sample_payload)
        token = sign_license(p, priv)
        with pytest.raises(ExpiredLicenseError):
            verify_license(token, {"v1": pub})

    def test_not_yet_valid_rejects(
        self,
        keypair_v1: tuple[PrivateKey, PublicKey],
        sample_payload: LicensePayload,
    ) -> None:
        priv, pub = keypair_v1
        far_future = datetime.now(timezone.utc) + timedelta(days=365)
        p = self._build_payload(
            far_future, far_future + timedelta(days=30), sample_payload
        )
        token = sign_license(p, priv)
        with pytest.raises(NotYetValidError):
            verify_license(token, {"v1": pub})

    def test_clock_skew_leeway_allows_recent_expiry(
        self,
        keypair_v1: tuple[PrivateKey, PublicKey],
        sample_payload: LicensePayload,
    ) -> None:
        priv, pub = keypair_v1
        issued = datetime(2026, 1, 1, tzinfo=timezone.utc)
        expires = issued + timedelta(days=30)
        p = self._build_payload(issued, expires, sample_payload)
        token = sign_license(p, priv)

        # 2 min past expiry — default leeway (5 min) still accepts
        just_past = expires + timedelta(minutes=2)
        verify_license(token, {"v1": pub}, now=just_past)

        # 10 min past — beyond default leeway
        way_past = expires + timedelta(minutes=10)
        with pytest.raises(ExpiredLicenseError):
            verify_license(token, {"v1": pub}, now=way_past)

        # 2 min past with zero leeway
        with pytest.raises(ExpiredLicenseError):
            verify_license(token, {"v1": pub}, now=just_past, leeway_seconds=0)

    def test_injectable_now(
        self,
        keypair_v1: tuple[PrivateKey, PublicKey],
        sample_payload: LicensePayload,
    ) -> None:
        priv, pub = keypair_v1
        token = sign_license(sample_payload, priv)

        ok_time = sample_payload.issued_at + timedelta(days=1)
        verify_license(token, {"v1": pub}, now=ok_time)

        late_time = sample_payload.expires_at + timedelta(days=1)
        with pytest.raises(ExpiredLicenseError):
            verify_license(token, {"v1": pub}, now=late_time)


class TestTampering:
    def test_tampered_payload_segment_rejects(
        self,
        keypair_v1: tuple[PrivateKey, PublicKey],
        sample_payload: LicensePayload,
    ) -> None:
        priv, pub = keypair_v1
        token = sign_license(sample_payload, priv)
        parts = token.split(".")
        payload_seg = parts[2]
        flipped = "B" if payload_seg[10] != "B" else "C"
        tampered = ".".join(
            [parts[0], parts[1], payload_seg[:10] + flipped + payload_seg[11:], parts[3]]
        )
        with pytest.raises(InvalidSignatureError):
            verify_license(tampered, {"v1": pub})

    def test_tampered_footer_rejects(
        self,
        keypair_v1: tuple[PrivateKey, PublicKey],
        sample_payload: LicensePayload,
    ) -> None:
        priv, pub = keypair_v1
        token = sign_license(sample_payload, priv)
        parts = token.split(".")
        new_footer_json = json.dumps({"kid": "v1", "extra": "injected"}).encode("utf-8")
        new_footer_b64 = (
            base64.urlsafe_b64encode(new_footer_json).rstrip(b"=").decode("ascii")
        )
        tampered = ".".join([parts[0], parts[1], parts[2], new_footer_b64])
        with pytest.raises(InvalidSignatureError):
            verify_license(tampered, {"v1": pub})


class TestWrongKey:
    def test_wrong_key_under_same_kid_rejects(
        self,
        keypair_v1: tuple[PrivateKey, PublicKey],
        keypair_v2: tuple[PrivateKey, PublicKey],
        sample_payload: LicensePayload,
    ) -> None:
        priv1, _ = keypair_v1
        _, pub2 = keypair_v2
        token = sign_license(sample_payload, priv1)
        # Verifier has v2's public key mapped to v1's kid
        with pytest.raises(InvalidSignatureError):
            verify_license(token, {"v1": pub2})

    def test_unknown_kid_rejects(
        self,
        keypair_v1: tuple[PrivateKey, PublicKey],
        sample_payload: LicensePayload,
    ) -> None:
        priv, pub = keypair_v1
        token = sign_license(sample_payload, priv)
        with pytest.raises(UnknownKeyIdError):
            verify_license(token, {"v99": pub})


class TestKeyRotation:
    def test_verifier_handles_multiple_kids(
        self,
        keypair_v1: tuple[PrivateKey, PublicKey],
        keypair_v2: tuple[PrivateKey, PublicKey],
        sample_payload: LicensePayload,
    ) -> None:
        priv1, pub1 = keypair_v1
        priv2, pub2 = keypair_v2
        keyset = {"v1": pub1, "v2": pub2}

        token_v1 = sign_license(sample_payload, priv1)
        token_v2 = sign_license(sample_payload, priv2)

        assert verify_license(token_v1, keyset) == sample_payload
        assert verify_license(token_v2, keyset) == sample_payload


class TestMalformed:
    def test_garbage_rejects(
        self,
        keypair_v1: tuple[PrivateKey, PublicKey],
    ) -> None:
        _, pub = keypair_v1
        with pytest.raises(MalformedTokenError):
            verify_license("not-a-token", {"v1": pub})

    def test_wrong_segment_count_rejects(
        self,
        keypair_v1: tuple[PrivateKey, PublicKey],
    ) -> None:
        _, pub = keypair_v1
        with pytest.raises(MalformedTokenError):
            verify_license("v4.public.aaaaaa", {"v1": pub})

    def test_footer_without_kid_rejects(
        self,
        keypair_v1: tuple[PrivateKey, PublicKey],
        sample_payload: LicensePayload,
    ) -> None:
        priv, pub = keypair_v1
        # Sign directly with pyseto, bypassing sign_license, to produce a footer
        # that lacks the 'kid' claim.
        token_bytes = pyseto.encode(
            priv.pyseto_key,
            payload=sample_payload.to_json_bytes(),
            footer=b'{"other":"field"}',
        )
        token = token_bytes.decode("utf-8") if isinstance(token_bytes, bytes) else token_bytes
        with pytest.raises(MalformedTokenError):
            verify_license(token, {"v1": pub})

    def test_footer_with_non_string_kid_rejects(
        self,
        keypair_v1: tuple[PrivateKey, PublicKey],
        sample_payload: LicensePayload,
    ) -> None:
        priv, pub = keypair_v1
        token_bytes = pyseto.encode(
            priv.pyseto_key,
            payload=sample_payload.to_json_bytes(),
            footer=b'{"kid": 123}',
        )
        token = token_bytes.decode("utf-8") if isinstance(token_bytes, bytes) else token_bytes
        with pytest.raises(MalformedTokenError):
            verify_license(token, {"v1": pub})

    def test_malformed_payload_json_rejects(
        self,
        keypair_v1: tuple[PrivateKey, PublicKey],
    ) -> None:
        priv, pub = keypair_v1
        # Sign a payload that isn't a valid LicensePayload
        token_bytes = pyseto.encode(
            priv.pyseto_key,
            payload=b'{"not": "a license"}',
            footer=b'{"kid":"v1"}',
        )
        token = token_bytes.decode("utf-8") if isinstance(token_bytes, bytes) else token_bytes
        with pytest.raises(MalformedTokenError):
            verify_license(token, {"v1": pub})
