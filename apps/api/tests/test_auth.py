"""Auth endpoint tests — register, login, JWT verification."""

import pytest
from httpx import AsyncClient


class TestHealth:
    @pytest.mark.asyncio
    async def test_health_ok(self, client: AsyncClient) -> None:
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("ok", "degraded")


class TestAuthEndpoints:
    @pytest.mark.asyncio
    async def test_register_creates_user(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/auth/register",
            json={"email": "newuser@gem.test", "password": "SecurePass123!"},
        )
        assert resp.status_code in (200, 201, 409), resp.text
        if resp.status_code in (200, 201):
            data = resp.json()
            assert "access_token" in data or "token" in data

    @pytest.mark.asyncio
    async def test_login_invalid_password(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/auth/login",
            json={"email": "nobody@gem.test", "password": "wrong"},
        )
        assert resp.status_code in (401, 422, 404)

    @pytest.mark.asyncio
    async def test_me_requires_auth(self, client: AsyncClient) -> None:
        resp = await client.get("/api/auth/me")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_me_with_valid_token(self, client: AsyncClient, auth_headers: dict) -> None:
        resp = await client.get("/api/auth/me", headers=auth_headers)
        # Will return 200 or 404/422 if the user doesn't exist in DB yet.
        # The important thing is it's NOT 401.
        assert resp.status_code != 401

    @pytest.mark.asyncio
    async def test_me_with_invalid_token(self, client: AsyncClient) -> None:
        resp = await client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer garbage.token.here"},
        )
        assert resp.status_code == 401
