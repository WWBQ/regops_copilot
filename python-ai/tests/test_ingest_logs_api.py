"""解析监控 API 测试。"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.ops import ingest_service


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_ingest_overview(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        ingest_service,
        "fetch_ingest_overview",
        lambda: {"corpus": {}, "jobs": {}, "session_uploads": {}},
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ops/ingest/overview")
    assert response.status_code == 200
    body = response.json()
    assert "corpus" in body
    assert "jobs" in body
    assert "session_uploads" in body


@pytest.mark.anyio
async def test_ingest_jobs_list(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        ingest_service,
        "list_ingest_jobs",
        lambda **kwargs: {"items": [], "limit": kwargs["limit"]},
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ops/ingest/jobs", params={"limit": 5})
    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert body["limit"] == 5


@pytest.mark.anyio
async def test_removed_log_events_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ops/logs/events", params={"limit": 10})
    assert response.status_code == 404
