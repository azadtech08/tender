"""Multi-tenancy integration test.

Asserts that Tenant A cannot see Tenant B's jobs, tenders, or billing data,
even when both tenants exist in the same Postgres database with RLS enabled.

These tests hit a REAL Postgres database (running in Docker Compose).
They do NOT mock the database — that was a deliberate design choice to catch
RLS policy bugs that mocks would hide.

Run with:
    docker compose up -d postgres
    pytest apps/api/tests/test_multi_tenancy.py -v
"""

import asyncio
import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Override settings before importing the app
import os
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://gem:devpass@localhost:5432/gem_tender",
)
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("DEBUG", "false")

from main import app  # noqa: E402 — must come after env overrides
from auth import create_access_token  # noqa: E402
from database import async_session  # noqa: E402


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_token(user_id: int, tenant_id: str, email: str) -> str:
    """Mint a local HS256 JWT for a fake test user."""
    return create_access_token(
        {"sub": str(user_id), "tenant_id": tenant_id, "email": email}
    )


async def _set_tenant(session: AsyncSession, tenant_id: str) -> None:
    await session.execute(text(f"SET LOCAL app.tenant_id = '{tenant_id}'"))


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="module")
async def http_client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


@pytest.fixture(scope="module")
def tenant_a() -> str:
    return str(uuid.uuid4())


@pytest.fixture(scope="module")
def tenant_b() -> str:
    return str(uuid.uuid4())


@pytest.fixture(scope="module")
def token_a(tenant_a: str) -> str:
    return _make_token(1001, tenant_a, "alice@test.com")


@pytest.fixture(scope="module")
def token_b(tenant_b: str) -> str:
    return _make_token(1002, tenant_b, "bob@test.com")


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestJobIsolation:
    """Jobs created by tenant A must not be visible to tenant B."""

    @pytest.mark.asyncio
    async def test_tenant_a_creates_job(
        self,
        http_client: AsyncClient,
        token_a: str,
        tenant_a: str,
    ) -> None:
        resp = await http_client.post(
            "/api/jobs",
            json={"keywords": ["Laptop"], "cards_per_kw": 3},
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["tenant_id"] == tenant_a
        # Stash job id on the class for later tests.
        TestJobIsolation._job_id_a = data["id"]

    @pytest.mark.asyncio
    async def test_tenant_b_cannot_list_tenant_a_jobs(
        self,
        http_client: AsyncClient,
        token_b: str,
    ) -> None:
        resp = await http_client.get(
            "/api/jobs",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        job_ids = [j["id"] for j in items]
        assert TestJobIsolation._job_id_a not in job_ids, (
            "Tenant B can see Tenant A's job — RLS is broken!"
        )

    @pytest.mark.asyncio
    async def test_tenant_b_cannot_fetch_tenant_a_job_by_id(
        self,
        http_client: AsyncClient,
        token_b: str,
    ) -> None:
        job_id = TestJobIsolation._job_id_a
        resp = await http_client.get(
            f"/api/jobs/{job_id}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        # Should be 404 (RLS makes the row invisible) not 403.
        assert resp.status_code == 404, (
            f"Expected 404 but got {resp.status_code} — "
            "Tenant B should not see Tenant A's job"
        )


class TestBillingIsolation:
    """Subscription rows must not leak across tenants."""

    @pytest.mark.asyncio
    async def test_each_tenant_gets_own_plan(
        self,
        http_client: AsyncClient,
        token_a: str,
        token_b: str,
        tenant_a: str,
        tenant_b: str,
    ) -> None:
        resp_a = await http_client.get(
            "/api/billing/plan",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        resp_b = await http_client.get(
            "/api/billing/plan",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp_a.status_code == 200, resp_a.text
        assert resp_b.status_code == 200, resp_b.text

        plan_a = resp_a.json()
        plan_b = resp_b.json()

        assert plan_a["tenant_id"] == tenant_a
        assert plan_b["tenant_id"] == tenant_b
        # Both new tenants start on free plan.
        assert plan_a["plan"] == "free"
        assert plan_b["plan"] == "free"


class TestRlsDirectly:
    """Direct DB-level check: SET LOCAL app.tenant_id scopes SELECT correctly."""

    @pytest.mark.asyncio
    async def test_raw_rls_scoping(
        self,
        tenant_a: str,
        tenant_b: str,
    ) -> None:
        """Verify that setting app.tenant_id to A hides rows from B."""
        async with async_session() as session:
            async with session.begin():
                # Insert a row for tenant_a directly.
                await session.execute(
                    text(
                        "INSERT INTO subscriptions (tenant_id, plan, status) "
                        "VALUES (:tid, 'free', 'active') "
                        "ON CONFLICT (tenant_id) DO NOTHING"
                    ),
                    {"tid": tenant_a},
                )

            # Now activate RLS for tenant_b and try to read tenant_a's row.
            async with session.begin():
                await _set_tenant(session, tenant_b)
                result = await session.execute(
                    text(
                        "SELECT id FROM subscriptions WHERE tenant_id = :tid"
                    ),
                    {"tid": tenant_a},
                )
                rows = result.fetchall()
                assert rows == [], (
                    "RLS leak: tenant_b session can see tenant_a's subscription row"
                )
