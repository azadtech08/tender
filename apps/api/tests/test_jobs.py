"""Jobs API tests — CRUD, authorization, pagination, scheduling."""

import pytest
from httpx import AsyncClient

from conftest import make_token


class TestJobsCRUD:
    _job_id: int = 0

    @pytest.mark.asyncio
    async def test_create_job(self, client: AsyncClient, auth_headers: dict) -> None:
        resp = await client.post(
            "/api/jobs",
            json={"keywords": ["Server", "Laptop"], "cards_per_kw": 2},
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["status"] == "pending"
        assert set(data["keywords"]) == {"Server", "Laptop"}
        assert data["cards_per_kw"] == 2
        TestJobsCRUD._job_id = data["id"]

    @pytest.mark.asyncio
    async def test_list_jobs(self, client: AsyncClient, auth_headers: dict) -> None:
        resp = await client.get("/api/jobs", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        ids = [j["id"] for j in data["items"]]
        assert TestJobsCRUD._job_id in ids

    @pytest.mark.asyncio
    async def test_get_job(self, client: AsyncClient, auth_headers: dict) -> None:
        resp = await client.get(f"/api/jobs/{TestJobsCRUD._job_id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == TestJobsCRUD._job_id

    @pytest.mark.asyncio
    async def test_list_jobs_pagination(self, client: AsyncClient, auth_headers: dict) -> None:
        resp = await client.get("/api/jobs?page=1&per_page=1", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) <= 1
        assert data["per_page"] == 1

    @pytest.mark.asyncio
    async def test_list_jobs_status_filter(self, client: AsyncClient, auth_headers: dict) -> None:
        resp = await client.get("/api/jobs?status=pending", headers=auth_headers)
        assert resp.status_code == 200
        for job in resp.json()["items"]:
            assert job["status"] == "pending"

    @pytest.mark.asyncio
    async def test_other_user_cannot_see_job(self, client: AsyncClient) -> None:
        other_token = make_token(user_id=8888, email="stranger@gem.test")
        resp = await client.get(
            f"/api/jobs/{TestJobsCRUD._job_id}",
            headers={"Authorization": f"Bearer {other_token}"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_job(self, client: AsyncClient, auth_headers: dict) -> None:
        # Create a throwaway job to delete
        create_resp = await client.post(
            "/api/jobs",
            json={"keywords": ["DeleteMe"]},
            headers=auth_headers,
        )
        assert create_resp.status_code == 201
        jid = create_resp.json()["id"]

        del_resp = await client.delete(f"/api/jobs/{jid}", headers=auth_headers)
        assert del_resp.status_code == 204

        get_resp = await client.get(f"/api/jobs/{jid}", headers=auth_headers)
        assert get_resp.status_code == 404


class TestJobSchedule:
    @pytest.mark.asyncio
    async def test_upsert_schedule(self, client: AsyncClient, auth_headers: dict) -> None:
        job_id = TestJobsCRUD._job_id
        resp = await client.patch(
            f"/api/jobs/{job_id}/schedule",
            json={"cron_hour": 9, "cron_minute": 0, "is_active": True},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["cron_hour"] == 9
        assert data["is_active"] is True
        assert data["next_run_at"] is not None

    @pytest.mark.asyncio
    async def test_get_schedule(self, client: AsyncClient, auth_headers: dict) -> None:
        job_id = TestJobsCRUD._job_id
        resp = await client.get(f"/api/jobs/{job_id}/schedule", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["job_id"] == job_id

    @pytest.mark.asyncio
    async def test_disable_schedule(self, client: AsyncClient, auth_headers: dict) -> None:
        job_id = TestJobsCRUD._job_id
        resp = await client.patch(
            f"/api/jobs/{job_id}/schedule",
            json={"cron_hour": 9, "cron_minute": 0, "is_active": False},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

    @pytest.mark.asyncio
    async def test_delete_schedule(self, client: AsyncClient, auth_headers: dict) -> None:
        job_id = TestJobsCRUD._job_id
        resp = await client.delete(f"/api/jobs/{job_id}/schedule", headers=auth_headers)
        assert resp.status_code == 204
