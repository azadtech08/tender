"""Readiness check before any LICENSING_MODE flip.

Validates that the infrastructure required for enforcement is in place:

  1. Alembic at expected head (007_admin_audit_clerk_compat)
  2. All 5 licensing tables exist
  3. RLS enabled on 4 tenant-scoped tables
  4. Ed25519 keypair loadable + round-trip sign/verify works
  5. Redis reachable (SET/GET/DEL)
  6. Required env vars set (LICENSE_ACTIVE_KID, keys, LICENSING_MODE)
  7. /metrics endpoint responds
  8. Tenant coverage summary — how many tenants lack active licenses
     (they'd all 402 the moment you flip to enforce)

Exit code: 0 if all critical checks pass, 1 otherwise.

Run:
    docker exec gem-tender-api python /app/scripts/preflight_licensing.py
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
import redis.asyncio as redis_async
from sqlalchemy import distinct, func, select, text

from config import settings
from database import async_session
from db_models import STATUS_ACTIVE, License, User

EXPECTED_HEAD = "007_admin_audit_clerk_compat"
TENANT_TABLES = [
    "licenses",
    "license_devices",
    "license_activations",
    "license_usage_counters",
]
CROSS_TENANT_TABLES = ["admin_audit_log"]
ALL_LIC_TABLES = TENANT_TABLES + CROSS_TENANT_TABLES

_OK = "✓"
_FAIL = "✗"
_WARN = "⚠"


class Report:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.warnings: list[str] = []

    def ok(self, label: str, detail: str = "") -> None:
        print(f"  {_OK} {label}" + (f" — {detail}" if detail else ""))

    def warn(self, label: str, detail: str = "") -> None:
        msg = f"{label}" + (f" — {detail}" if detail else "")
        print(f"  {_WARN} {msg}")
        self.warnings.append(msg)

    def fail(self, label: str, detail: str = "") -> None:
        msg = f"{label}" + (f" — {detail}" if detail else "")
        print(f"  {_FAIL} {msg}")
        self.failures.append(msg)


async def check_alembic(report: Report) -> None:
    print("\n[1] Alembic migration state")
    async with async_session() as db:
        row = await db.execute(text("SELECT version_num FROM alembic_version"))
        current = row.scalar_one_or_none()
    if current == EXPECTED_HEAD:
        report.ok("alembic head", f"{current}")
    else:
        report.fail("alembic head mismatch", f"got {current}, want {EXPECTED_HEAD}")


async def check_tables(report: Report) -> None:
    print("\n[2] Licensing tables present")
    async with async_session() as db:
        rows = await db.execute(text("""
            SELECT tablename FROM pg_tables WHERE tablename = ANY(:names)
        """), {"names": ALL_LIC_TABLES})
        present = {r[0] for r in rows.all()}
    for t in ALL_LIC_TABLES:
        if t in present:
            report.ok(f"table {t}")
        else:
            report.fail(f"table {t} missing")


async def check_rls(report: Report) -> None:
    print("\n[3] RLS enabled on tenant-scoped tables")
    async with async_session() as db:
        rows = await db.execute(text("""
            SELECT tablename, rowsecurity FROM pg_tables
            WHERE tablename = ANY(:names)
        """), {"names": TENANT_TABLES + CROSS_TENANT_TABLES})
        rls_state = {r[0]: r[1] for r in rows.all()}
    for t in TENANT_TABLES:
        if rls_state.get(t):
            report.ok(f"RLS {t}", "enabled")
        else:
            report.fail(f"RLS {t}", "not enabled")
    if rls_state.get("admin_audit_log"):
        report.warn("admin_audit_log has RLS — by design it should NOT (admin cross-tenant)")
    else:
        report.ok("admin_audit_log", "RLS off (correct)")

    # Policies
    async with async_session() as db:
        rows = await db.execute(text("""
            SELECT tablename FROM pg_policies WHERE policyname='tenant_isolation'
              AND tablename = ANY(:names)
        """), {"names": TENANT_TABLES})
        with_policy = {r[0] for r in rows.all()}
    for t in TENANT_TABLES:
        if t in with_policy:
            report.ok(f"policy tenant_isolation on {t}")
        else:
            report.fail(f"policy tenant_isolation on {t}", "missing")


def check_keys(report: Report) -> None:
    print("\n[4] Ed25519 keypair loadable + round-trip sign/verify")
    private_path = Path(settings.license_private_key_path) if settings.license_private_key_path else None
    public_path = Path(settings.license_public_key_path)

    if not public_path.exists():
        report.fail("public key path", f"{public_path} does not exist")
        return
    report.ok("public key path", str(public_path))

    if private_path is None:
        report.warn("LICENSE_PRIVATE_KEY_PATH unset — will fall back to Secrets Manager in prod")
    elif not private_path.exists():
        report.fail("private key path", f"{private_path} does not exist")
        return
    else:
        report.ok("private key path", str(private_path))

    # Round-trip test
    try:
        import secrets
        from datetime import timedelta
        from tenzo_licensing import (
            DeviceBindingMode,
            LicensePayload,
            load_private_key,
            load_public_key,
            sign_license,
            verify_license,
        )

        if private_path is not None:
            priv = load_private_key(settings.license_active_kid, private_path.read_bytes())
        else:
            report.warn("round-trip test skipped (no local private key)")
            return
        pub = load_public_key(settings.license_active_kid, public_path.read_bytes())

        now = datetime.now(tz=timezone.utc)
        p = LicensePayload(
            lic_id="preflight",
            tenant_id="preflight",
            plan="pro",
            issued_at=now,
            not_before=now,
            expires_at=now + timedelta(days=1),
            device_binding_mode=DeviceBindingMode.HWID,
            fingerprint_salt=secrets.token_hex(16),
            nonce=secrets.token_hex(16),
        )
        tok = sign_license(p, priv)
        restored = verify_license(tok, {settings.license_active_kid: pub})
        if restored == p:
            report.ok("sign/verify round-trip", f"kid={settings.license_active_kid}")
        else:
            report.fail("sign/verify round-trip", "payload mismatch after round-trip")
    except Exception as exc:
        report.fail("sign/verify round-trip", f"{type(exc).__name__}: {exc}")


async def check_redis(report: Report) -> None:
    print("\n[5] Redis reachable")
    try:
        client = redis_async.from_url(settings.redis_url, decode_responses=True)
        probe_key = "preflight:licensing:probe"
        await client.set(probe_key, "ok", ex=10)
        got = await client.get(probe_key)
        await client.delete(probe_key)
        await client.close()
        if got == "ok":
            report.ok("redis SET/GET/DEL", settings.redis_url)
        else:
            report.fail("redis probe returned wrong value", f"got {got!r}")
    except Exception as exc:
        report.fail("redis unreachable", f"{type(exc).__name__}: {exc}")


def check_env(report: Report) -> None:
    print("\n[6] Env vars")
    if settings.licensing_mode in {"off", "warn", "enforce"}:
        report.ok("LICENSING_MODE", settings.licensing_mode)
    else:
        report.fail("LICENSING_MODE invalid", f"got {settings.licensing_mode!r}")

    if settings.license_active_kid:
        report.ok("LICENSE_ACTIVE_KID", settings.license_active_kid)
    else:
        report.fail("LICENSE_ACTIVE_KID unset")

    if settings.license_heartbeat_interval_seconds > 0:
        report.ok(
            "LICENSE_HEARTBEAT_INTERVAL_SECONDS",
            f"{settings.license_heartbeat_interval_seconds}s",
        )

    if settings.license_token_ttl_seconds > 0:
        report.ok(
            "LICENSE_TOKEN_TTL_SECONDS",
            f"{settings.license_token_ttl_seconds}s",
        )

    if not settings.local_admin_user_ids and settings.clerk_jwks_url is None:
        report.warn(
            "no admin identity configured — set CLERK_JWKS_URL or LOCAL_ADMIN_USER_IDS "
            "or admin endpoints will 403 every caller"
        )


async def check_metrics_endpoint(report: Report) -> None:
    print("\n[7] /metrics endpoint responds")
    # Assumes local uvicorn on 8000 from inside the container. In prod point
    # at localhost or use an internal health-check URL.
    url = "http://localhost:8000/metrics"
    try:
        async with httpx.AsyncClient(timeout=5) as http:
            r = await http.get(url)
        if r.status_code == 200 and "tenzo_license_activations_total" in r.text:
            report.ok("/metrics", f"{len(r.text.splitlines())} lines")
        else:
            report.warn(
                "/metrics responded but missing tenzo_ families",
                f"status={r.status_code}",
            )
    except Exception as exc:
        report.warn("/metrics unreachable", f"{type(exc).__name__}: {exc}")


async def check_tenant_coverage(report: Report) -> None:
    print("\n[8] Tenant coverage — tenants without an active license")
    async with async_session() as db:
        total_tenants = (await db.execute(
            select(func.count(distinct(User.tenant_id))).where(User.tenant_id.isnot(None))
        )).scalar_one()

        licensed_tenants = (await db.execute(
            select(func.count(distinct(License.tenant_id))).where(License.status == STATUS_ACTIVE)
        )).scalar_one()

        uncovered = total_tenants - licensed_tenants

    print(f"  total tenants:          {total_tenants}")
    print(f"  tenants with active lic:{licensed_tenants}")
    print(f"  uncovered tenants:      {uncovered}")
    if uncovered == 0:
        report.ok("all tenants have an active license")
    elif uncovered <= 5:
        report.warn(
            f"{uncovered} tenant(s) uncovered — run grandfather_licenses.py before flipping to enforce"
        )
    else:
        report.fail(
            f"{uncovered} tenant(s) uncovered — MUST run grandfather_licenses.py before flipping to enforce"
        )


async def main() -> int:
    print("=" * 70)
    print("Tenzo Licensing — Preflight readiness check")
    print(f"Time: {datetime.now(tz=timezone.utc).isoformat()}")
    print("=" * 70)

    report = Report()

    await check_alembic(report)
    await check_tables(report)
    await check_rls(report)
    check_keys(report)
    await check_redis(report)
    check_env(report)
    await check_metrics_endpoint(report)
    await check_tenant_coverage(report)

    print("\n" + "=" * 70)
    if report.failures:
        print(f"FAILED: {len(report.failures)} critical issue(s)")
        for f in report.failures:
            print(f"  {_FAIL} {f}")
        print("Do NOT flip to warn/enforce until these are resolved.")
        return 1
    if report.warnings:
        print(f"PASSED with {len(report.warnings)} warning(s):")
        for w in report.warnings:
            print(f"  {_WARN} {w}")
        print("Review warnings; flip to the next mode if acceptable.")
    else:
        print("PASSED — licensing infrastructure is ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
