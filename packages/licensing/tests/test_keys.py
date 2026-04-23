from __future__ import annotations

from pathlib import Path

import pytest

from tenzo_licensing import (
    generate_keypair,
    load_private_key,
    load_public_key,
    load_public_key_from_file,
    sign_license,
    verify_license,
)


class TestKeyGeneration:
    def test_generates_pem_encoded_pair(self) -> None:
        priv_pem, pub_pem = generate_keypair()
        assert b"-----BEGIN PRIVATE KEY-----" in priv_pem
        assert b"-----END PRIVATE KEY-----" in priv_pem
        assert b"-----BEGIN PUBLIC KEY-----" in pub_pem
        assert b"-----END PUBLIC KEY-----" in pub_pem

    def test_pairs_are_unique_per_generation(self) -> None:
        priv1, pub1 = generate_keypair()
        priv2, pub2 = generate_keypair()
        assert priv1 != priv2
        assert pub1 != pub2


class TestKeyLoading:
    def test_load_preserves_kid(self) -> None:
        priv_pem, pub_pem = generate_keypair()
        priv = load_private_key("v1", priv_pem)
        pub = load_public_key("v1", pub_pem)
        assert priv.kid == "v1"
        assert pub.kid == "v1"

    def test_generated_pair_can_sign_and_verify(self, sample_payload) -> None:
        priv_pem, pub_pem = generate_keypair()
        priv = load_private_key("test", priv_pem)
        pub = load_public_key("test", pub_pem)
        token = sign_license(sample_payload, priv)
        restored = verify_license(token, {"test": pub})
        assert restored == sample_payload

    def test_rejects_invalid_pem(self) -> None:
        with pytest.raises(Exception):  # noqa: B017, BLE001 - pyseto error type varies
            load_public_key("bad", b"-----BEGIN GARBAGE-----\nxxx\n-----END GARBAGE-----\n")

    def test_load_public_key_from_file(self, tmp_path: Path) -> None:
        priv_pem, pub_pem = generate_keypair()
        pub_path = tmp_path / "signing_public_test.pem"
        pub_path.write_bytes(pub_pem)
        pub = load_public_key_from_file("test", pub_path)
        assert pub.kid == "test"
