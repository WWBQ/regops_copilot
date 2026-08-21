"""RAG trace API 测试。"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


def _rag_log_ready() -> bool:
    try:
        from app.db.connection import get_connection

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT to_regclass('public.rag_query_log')")
                return cur.fetchone()[0] is not None
    except Exception:
        return False


requires_rag_log = pytest.mark.skipif(not _rag_log_ready(), reason="rag_query_log table missing")


@pytest.fixture
def anyio_backend():
    return "asyncio"


@requires_rag_log
@pytest.mark.anyio
async def test_list_rag_traces_empty_ok():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ops/rag-traces?limit=5")
    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert "total" in body
    assert isinstance(body["items"], list)
