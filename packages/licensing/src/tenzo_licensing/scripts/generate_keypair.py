"""Generate an Ed25519 keypair for Tenzo license signing.

Usage:
    python -m tenzo_licensing.scripts.generate_keypair --kid v1 --out-dir ./keys

Produces:
    <out-dir>/signing_private_<kid>.pem  -> mode 600, upload to Secrets Manager, then delete locally
    <out-dir>/signing_public_<kid>.pem   -> mode 644, commit to the repo
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tenzo_licensing import generate_keypair


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate an Ed25519 keypair for Tenzo licensing.",
    )
    parser.add_argument("--kid", required=True, help="Key ID (e.g. v1, v2)")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("./keys"),
        help="Output directory (default: ./keys)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files at the target paths",
    )
    args = parser.parse_args(argv)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    private_path = args.out_dir / f"signing_private_{args.kid}.pem"
    public_path = args.out_dir / f"signing_public_{args.kid}.pem"

    if (private_path.exists() or public_path.exists()) and not args.force:
        print(  # noqa: T201
            f"ERROR: {private_path} or {public_path} already exists. "
            f"Pass --force to overwrite.",
            file=sys.stderr,
        )
        return 1

    private_pem, public_pem = generate_keypair()
    private_path.write_bytes(private_pem)
    public_path.write_bytes(public_pem)
    try:
        private_path.chmod(0o600)
        public_path.chmod(0o644)
    except OSError:
        # chmod is a no-op on Windows; permissions are fine as-is.
        pass

    print(f"Private key: {private_path}  (KEEP SECRET)")  # noqa: T201
    print(f"Public  key: {public_path}  (commit to repo)")  # noqa: T201
    print()  # noqa: T201
    print("Next steps:")  # noqa: T201
    print(  # noqa: T201
        f"  1. Upload {private_path.name} to AWS Secrets Manager:\n"
        f"     aws secretsmanager create-secret \\\n"
        f"       --name tenzo/licensing/signing_key_{args.kid} \\\n"
        f"       --secret-binary fileb://{private_path}"
    )
    print(f"  2. Commit {public_path.name} under packages/licensing/keys/")  # noqa: T201
    print(f"  3. Securely delete the local copy of {private_path.name}")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
