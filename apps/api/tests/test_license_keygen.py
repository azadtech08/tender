"""Tests for the license key generation utility."""

from __future__ import annotations

import re

import pytest

from services.license_keygen import (
    PRODUCT_PREFIX,
    generate_fingerprint_salt,
    generate_license_key,
    hash_license_key,
    key_prefix,
    normalize_license_key,
    validate_license_key_format,
)

KEY_PATTERN = re.compile(r"^TNZO-[0-9A-Z]{5}-[0-9A-Z]{5}-[0-9A-Z]{5}-[0-9A-Z]{5}$")


class TestGenerate:
    def test_format_matches_spec(self) -> None:
        for _ in range(20):
            key = generate_license_key()
            assert KEY_PATTERN.match(key), f"bad format: {key!r}"
            assert key.startswith(PRODUCT_PREFIX + "-")

    def test_keys_are_unique(self) -> None:
        keys = {generate_license_key() for _ in range(100)}
        assert len(keys) == 100

    def test_no_ambiguous_chars_in_random_body(self) -> None:
        # Crockford excludes I, L, O, U from the random body and checksum.
        # The literal prefix "TNZO-" is exempt — its O is unambiguous in context.
        for _ in range(50):
            key = generate_license_key()
            body = key[len(PRODUCT_PREFIX) + 1 :]  # everything after "TNZO-"
            assert not (set(body) & set("ILOU"))


class TestValidate:
    def test_freshly_generated_key_validates(self) -> None:
        for _ in range(20):
            assert validate_license_key_format(generate_license_key())

    def test_typo_detected(self) -> None:
        key = generate_license_key()
        # Flip one character of the random body (not the checksum group)
        parts = key.split("-")
        original = parts[1][2]
        replacement = "X" if original != "X" else "Y"
        parts[1] = parts[1][:2] + replacement + parts[1][3:]
        tampered = "-".join(parts)
        assert not validate_license_key_format(tampered)

    def test_typo_in_checksum_detected(self) -> None:
        key = generate_license_key()
        parts = key.split("-")
        original = parts[4][0]
        replacement = "Y" if original != "Y" else "Z"
        parts[4] = replacement + parts[4][1:]
        tampered = "-".join(parts)
        assert not validate_license_key_format(tampered)

    def test_empty_string(self) -> None:
        assert not validate_license_key_format("")

    def test_wrong_prefix(self) -> None:
        # Build a key with wrong prefix, real-looking body
        good = generate_license_key()
        assert not validate_license_key_format("ACME" + good[4:])

    def test_wrong_segment_count(self) -> None:
        assert not validate_license_key_format("TNZO-AAAAA-BBBBB")


class TestNormalization:
    def test_lowercase_input_normalized(self) -> None:
        key = generate_license_key()
        assert validate_license_key_format(key.lower())

    def test_whitespace_stripped(self) -> None:
        key = generate_license_key()
        assert validate_license_key_format(f"  {key}  ")

    def test_ambiguous_chars_translated(self) -> None:
        # Synthesize a "user typed" version with I/L/O substituted for 1/0
        key = generate_license_key()
        # Only reverse-substitute *if* the original key had the canonical chars
        substituted = key.replace("1", "I", 1).replace("0", "O", 1)
        # Should still validate after normalization
        assert validate_license_key_format(substituted)

    def test_normalize_returns_canonical(self) -> None:
        key = generate_license_key()
        assert normalize_license_key(f" {key.lower()} ") == key

    def test_normalize_raises_on_garbage(self) -> None:
        with pytest.raises(ValueError):
            normalize_license_key("not a key")


class TestHashing:
    def test_hash_is_64_hex_chars(self) -> None:
        key = generate_license_key()
        h = hash_license_key(key)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_hash_stable_across_input_styles(self) -> None:
        key = generate_license_key()
        assert hash_license_key(key) == hash_license_key(key.lower())
        assert hash_license_key(key) == hash_license_key(f"  {key}  ")

    def test_different_keys_different_hashes(self) -> None:
        a = hash_license_key(generate_license_key())
        b = hash_license_key(generate_license_key())
        assert a != b


class TestKeyPrefix:
    def test_prefix_shape(self) -> None:
        key = generate_license_key()
        prefix = key_prefix(key)
        assert prefix.startswith("TNZO-")
        assert len(prefix) == len("TNZO-XXXXX")
        # Must be the literal first two groups of the key
        assert key.startswith(prefix)


class TestFingerprintSalt:
    def test_salt_is_32_hex_chars(self) -> None:
        salt = generate_fingerprint_salt()
        assert len(salt) == 32
        assert all(c in "0123456789abcdef" for c in salt)

    def test_salts_are_unique(self) -> None:
        salts = {generate_fingerprint_salt() for _ in range(100)}
        assert len(salts) == 100
