from __future__ import annotations

from pathlib import Path

import pytest

from tenzo_licensing import load_private_key, load_public_key, sign_license, verify_license
from tenzo_licensing.scripts.generate_keypair import main


class TestGenerateKeypairScript:
    def test_generates_files_at_target_paths(self, tmp_path: Path) -> None:
        rc = main(["--kid", "v1", "--out-dir", str(tmp_path)])
        assert rc == 0
        priv_path = tmp_path / "signing_private_v1.pem"
        pub_path = tmp_path / "signing_public_v1.pem"
        assert priv_path.exists()
        assert pub_path.exists()

    def test_generated_files_are_usable_for_sign_verify(
        self, tmp_path: Path, sample_payload
    ) -> None:
        rc = main(["--kid", "v1", "--out-dir", str(tmp_path)])
        assert rc == 0
        priv = load_private_key(
            "v1", (tmp_path / "signing_private_v1.pem").read_bytes()
        )
        pub = load_public_key(
            "v1", (tmp_path / "signing_public_v1.pem").read_bytes()
        )
        token = sign_license(sample_payload, priv)
        assert verify_license(token, {"v1": pub}) == sample_payload

    def test_refuses_to_overwrite_without_force(self, tmp_path: Path) -> None:
        assert main(["--kid", "v1", "--out-dir", str(tmp_path)]) == 0
        # Second call without --force should fail
        assert main(["--kid", "v1", "--out-dir", str(tmp_path)]) == 1

    def test_overwrites_with_force(self, tmp_path: Path) -> None:
        assert main(["--kid", "v1", "--out-dir", str(tmp_path)]) == 0
        original = (tmp_path / "signing_private_v1.pem").read_bytes()
        assert main(["--kid", "v1", "--out-dir", str(tmp_path), "--force"]) == 0
        after = (tmp_path / "signing_private_v1.pem").read_bytes()
        assert original != after

    def test_missing_kid_exits_nonzero(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit):
            main(["--out-dir", str(tmp_path)])
