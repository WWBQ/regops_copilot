"""质量门 / fin_metric API。"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_quality_gates_ok():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ops/quality/gates")
    assert response.status_code == 200
    body = response.json()
    assert "summary" in body
    assert "companies" in body
    assert "facts" in body["summary"]


@pytest.mark.anyio
async def test_quality_facts_ok():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ops/quality/facts", params={"limit": 5})
    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert body["limit"] == 5
    assert "total" in body
