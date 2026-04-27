"""One-shot: mint a license for every existing tenant that doesn't have one.

Why
---
Phase 8 Day 1. We ship with ``LICENSING_MODE=off`` so nobody breaks. On
Day 2 we flip to ``warn`` and start logging denials. By Day 8 we flip to
``enforce``. If we flip to enforce without grandfathered licenses, every
pre-existing tenant gets 402'd. This script prevents that.

Behaviour
---------
* Finds every distinct ``tenant_id`` that has at least one user.
* For each tenant *without* an active license, mints a new license with
  configurable plan / expiry / max_devices.
* Skips tenants that already have ``status=active`` licenses.
* Writes one ``admin_audit_log`` row per mint, keyed by ``admin_subject=
  'grandfather-script'`` so this batch is traceable separately from UI
  admin actions.
* Emits a CSV of (tenant_id, plan, raw_key, expires_at, result) — the
  plaintext key appears once here and never again.

Run
---
    docker exec gem-tender-api \\
        python /app/scripts/grandfather_licenses.py --dry-run

    docker exec gem-tender-api \\
        python /app/scripts/grandfather_licenses.py \\
            --plan pro --expires-days 365 --max-devices 5 \\
            --output /tmp/grandfather-$(date +%F).csv

The CSV is the artifact you email to each tenant's billing contact.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import async_session
from db_models import (
    ACTION_LICENSE_CREATE,
    PLAN_BUSINESS,
    PLAN_ENTERPRISE,
    PLAN_FREE,
    PLAN_PRO,
    PLAN_STARTER,
    STATUS_ACTIVE,
    AdminAuditLog,
    License,
    User,
)
from services.license_keygen import (
    generate_fingerprint_salt,
    generate_license_key,
    hash_license_key,
    key_prefix as derive_key_prefix,
)

VALID_PLANS = {PLAN_FREE, PLAN_STARTER, PLAN_PRO, PLAN_BUSINESS, PLAN_ENTERPRISE}
DEFAULT_ADMIN_SUBJECT = "grandfather-script"


async def _find_tenants_needing_license(db: AsyncSession) -> list[str]:
    """Tenant IDs that have users but no active License row."""
    tenant_rows = await db.execute(
        select(distinct(User.tenant_id)).where(User.tenant_id.isnot(None))
    )
    all_tenants: set[str] = {row for (row,) in tenant_rows.all() if row}

    licensed_rows = await db.execute(
        select(distinct(License.tenant_id)).where(License.status == STATUS_ACTIVE)
    )
    licensed: set[str] = {row for (row,) in licensed_rows.all() if row}

    return sorted(all_tenants - licensed)


async def _mint_one(
    db: AsyncSession,
    tenant_id: str,
    plan: str,
    expires_at: datetime,
    max_devices: int,
    signing_kid: str,
    admin_subject: str,
    admin_email: Optional[str],
) -> tuple[int, str]:
    """Insert License + audit row; return (license_id, raw_key)."""
    raw_key = generate_license_key()
    lic = License(
        tenant_id=tenant_id,
        key_hash=hash_license_key(raw_key),
        key_prefix=derive_key_prefix(raw_key),
        plan=plan,
        status=STATUS_ACTIVE,
        signing_kid=signing_kid,
        not_before=datetime.now(tz=timezone.utc),
        expires_at=expires_at,
        max_devices=max_devices,
        features={},
        fingerprint_salt=generate_fingerprint_salt(),
    )
    db.add(lic)
    await db.flush()  # populate lic.id for the audit row

    audit = AdminAuditLog(
        admin_id=None,
        admin_subject=admin_subject,
        admin_email=admin_email,
        action=ACTION_LICENSE_CREATE,
        target_tenant_id=tenant_id,
        target_license_id=lic.id,
        payload={
            "grandfather_batch": True,
            "plan": plan,
            "expires_at": expires_at.isoformat(),
            "max_devices": max_devices,
        },
        ip=None,
    )
    db.add(audit)
    return lic.id, raw_key


async def run(args: argparse.Namespace) -> int:
    expires_at = datetime.now(tz=timezone.utc) + timedelta(days=args.expires_days)

    rows_to_write: list[dict] = []

    async with async_session() as db:
        needing = await _find_tenants_needing_license(db)
        print(f"Found {len(needing)} tenant(s) without an active license.", file=sys.stderr)
        if not needing:
            print("Nothing to do.", file=sys.stderr)
            return 0

        minted = 0
        for tenant_id in needing:
            if args.dry_run:
                rows_to_write.append({
                    "tenant_id": tenant_id,
                    "plan": args.plan,
                    "raw_key": "(dry-run — not minted)",
                    "expires_at": expires_at.isoformat(),
                    "result": "would-mint",
                })
                continue

            try:
                lic_id, raw_key = await _mint_one(
                    db,
                    tenant_id=tenant_id,
                    plan=args.plan,
                    expires_at=expires_at,
                    max_devices=args.max_devices,
                    signing_kid=args.signing_kid,
                    admin_subject=args.admin_subject,
                    admin_email=args.admin_email,
                )
                minted += 1
                rows_to_write.append({
                    "tenant_id": tenant_id,
                    "plan": args.plan,
                    "raw_key": raw_key,
                    "expires_at": expires_at.isoformat(),
                    "result": f"minted (id={lic_id})",
                })
            except Exception as exc:
                rows_to_write.append({
                    "tenant_id": tenant_id,
                    "plan": args.plan,
                    "raw_key": "",
                    "expires_at": expires_at.isoformat(),
                    "result": f"error: {exc}",
                })

        if not args.dry_run:
            await db.commit()

    # Write CSV (or stdout)
    fieldnames = ["tenant_id", "plan", "raw_key", "expires_at", "result"]
    out = Path(args.output) if args.output else None
    if out is not None:
        with out.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(rows_to_write)
        print(f"Wrote {len(rows_to_write)} row(s) to {out}", file=sys.stderr)
    else:
        w = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows_to_write)

    if args.dry_run:
        print(
            f"\nDRY RUN: {len(rows_to_write)} tenant(s) would have been minted. "
            f"Re-run without --dry-run to apply.",
            file=sys.stderr,
        )
    else:
        print(f"\nMinted {minted} license(s). Email the keys to each tenant.", file=sys.stderr)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description="Grandfather-mint a license for every existing tenant without one."
    )
    p.add_argument("--dry-run", action="store_true", help="Report what would be minted; write no rows.")
    p.add_argument("--plan", default=PLAN_PRO, choices=sorted(VALID_PLANS),
                   help=f"Plan for each grandfather license (default: {PLAN_PRO})")
    p.add_argument("--expires-days", type=int, default=365,
                   help="Days from now until expires_at (default: 365)")
    p.add_argument("--max-devices", type=int, default=5,
                   help="max_devices for each license (default: 5)")
    p.add_argument("--signing-kid", default="v1",
                   help="Kid stored on the License row (default: v1)")
    p.add_argument("--output", default=None,
                   help="CSV output path (default: stdout)")
    p.add_argument("--admin-subject", default=DEFAULT_ADMIN_SUBJECT,
                   help="admin_subject value in audit rows")
    p.add_argument("--admin-email", default=None,
                   help="admin_email value in audit rows (optional)")
    args = p.parse_args()

    if args.expires_days <= 0:
        print("ERROR: --expires-days must be positive", file=sys.stderr)
        return 2
    if args.max_devices <= 0:
        print("ERROR: --max-devices must be positive", file=sys.stderr)
        return 2

    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
