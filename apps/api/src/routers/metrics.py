"""Prometheus /metrics endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Response

router = APIRouter()

try:
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False
    CONTENT_TYPE_LATEST = "text/plain"
    def generate_latest(): return b"# prometheus_client not installed\n"  # type: ignore[misc]


@router.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
