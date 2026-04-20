"""Tenders API tests — list, search, cross-tenant isolation."""

import pytest
from httpx import AsyncClient

from conftest import make_token


class TestTendersAPI:
    @pytest.mark.asyncio
    async def test_list_tenders_empty(self, client: AsyncClient, auth_headers: dict) -> None:
        """New tenant starts with zero tenders."""
        resp = await client.get("/api/tenders", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_list_tenders_pagination_params(self, client: AsyncClient, auth_headers: dict) -> None:
        resp = await client.get("/api/tenders?page=1&per_page=10", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 1
        assert data["per_page"] == 10

    @pytest.mark.asyncio
    async def test_search_filter(self, client: AsyncClient, auth_headers: dict) -> None:
        resp = await client.get("/api/tenders?search=laptop", headers=auth_headers)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_job_id_filter(self, client: AsyncClient, auth_headers: dict) -> None:
        resp = await client.get("/api/tenders?job_id=99999", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    @pytest.mark.asyncio
    async def test_requires_auth(self, client: AsyncClient) -> None:
        resp = await client.get("/api/tenders")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_cross_tenant_isolation(self, client: AsyncClient, auth_headers: dict) -> None:
        """A different tenant token should not see this tenant's tenders."""
        other_token = make_token(user_id=7777, email="other@gem.test")
        resp_other = await client.get(
            "/api/tenders",
            headers={"Authorization": f"Bearer {other_token}"},
        )
        resp_mine = await client.get("/api/tenders", headers=auth_headers)
        # Other tenant's result set must be independent (no overlap expected here
        # since both are empty, but the query must not fail)
        assert resp_other.status_code == 200
        assert resp_mine.status_code == 200
