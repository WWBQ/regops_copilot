"""系统概览 API 测试。"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_system_overview():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ops/system/overview")
    assert response.status_code == 200
    body = response.json()
    assert "services" in body
    assert "corpus" in body
    assert body["services"]["python_ai"]["status"] == "ok"
    assert body["config"]["rag_rerank_backend"] in {"bge", "llm"}
    assert "rag_llm_rerank_api_key" not in body["config"]
