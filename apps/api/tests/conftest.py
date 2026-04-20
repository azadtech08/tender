"""Pytest configuration and shared fixtures for API tests."""

import os
import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# Override env before importing the app
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://gem:devpass@localhost:5432/gem_tender",
)
os.environ.setdefault("SYNC_DATABASE_URL", "postgresql://gem:devpass@localhost:5432/gem_tender")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("DEBUG", "false")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key")


def pytest_configure(config):
    config.addinivalue_line("markers", "asyncio: mark test as async")


# ── App + client ──────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="session")
async def client() -> AsyncGenerator[AsyncClient, None]:
    from main import app
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c


# ── Auth helpers ──────────────────────────────────────────────────────────────

def make_token(user_id: int = 1, tenant_id: str | None = None, email: str = "test@example.com") -> str:
    from auth import create_access_token
    tid = tenant_id or str(uuid.uuid4())
    return create_access_token({"sub": str(user_id), "tenant_id": tid, "email": email})


@pytest.fixture(scope="session")
def tenant_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture(scope="session")
def auth_headers(tenant_id: str) -> dict:
    token = make_token(user_id=999, tenant_id=tenant_id, email="testuser@gem.test")
    return {"Authorization": f"Bearer {token}"}
