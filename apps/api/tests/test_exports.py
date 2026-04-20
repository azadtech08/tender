"""Export tests — XLSX download, 23-column contract verification."""

import io

import openpyxl
import pytest
from httpx import AsyncClient


# The exact 23 columns the golden file specifies — order matters.
EXPECTED_COLUMNS = [
    "S.No", "Keyword", "Tender Reference No", "Tender Type",
    "Published Date", "Bid Submission End Date", "Title", "Description",
    "Cleaned BOQ", "Organisation", "Ministry", "Tender Value", "EMD",
    "State", "Pincode", "Delivery Period", "Product Type", "Exemption",
    "Email", "IT Relevant", "Quantity", "Link", "Scraped Date",
]


class TestXlsxContract:
    @pytest.mark.asyncio
    async def test_export_requires_auth(self, client: AsyncClient) -> None:
        resp = await client.get("/api/exports/1.xlsx")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_export_nonexistent_job_404(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        resp = await client.get("/api/exports/99999.xlsx", headers=auth_headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_export_column_contract(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """Create an empty job, export its XLSX, verify exactly 23 column headers."""
        # Create job
        create_resp = await client.post(
            "/api/jobs",
            json={"keywords": ["XlsxTest"], "cards_per_kw": 1},
            headers=auth_headers,
        )
        assert create_resp.status_code == 201
        job_id = create_resp.json()["id"]

        # Export (job is empty — we're just verifying schema)
        export_resp = await client.get(
            f"/api/exports/{job_id}.xlsx",
            headers=auth_headers,
        )
        assert export_resp.status_code == 200

        content_type = export_resp.headers.get("content-type", "")
        assert "spreadsheetml" in content_type, f"Wrong content type: {content_type}"

        # Parse XLSX
        wb = openpyxl.load_workbook(io.BytesIO(export_resp.content))
        ws = wb.active
        headers = [cell.value for cell in ws[1]]

        assert headers == EXPECTED_COLUMNS, (
            f"Column mismatch.\n"
            f"Expected: {EXPECTED_COLUMNS}\n"
            f"Got:      {headers}"
        )

    @pytest.mark.asyncio
    async def test_export_content_disposition(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """Response must have Content-Disposition: attachment."""
        create_resp = await client.post(
            "/api/jobs",
            json={"keywords": ["DispoTest"], "cards_per_kw": 1},
            headers=auth_headers,
        )
        assert create_resp.status_code == 201
        job_id = create_resp.json()["id"]

        resp = await client.get(f"/api/exports/{job_id}.xlsx", headers=auth_headers)
        assert resp.status_code == 200
        disposition = resp.headers.get("content-disposition", "")
        assert "attachment" in disposition
        assert ".xlsx" in disposition
