"""RAG trace API 测试。"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

USER_ID = "00000000-0000-0000-0000-000000000001"
USER_HEADERS = {"X-Regops-User": USER_ID}


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
async def test_rag_overview_ok():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ops/rag/overview", headers=USER_HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert "refusal_rate" in body
    assert "refusal_count" in body
    assert "ok_count" in body
    assert isinstance(body["by_outcome"], dict)


def _asknum_log_ready() -> bool:
    try:
        from app.db.connection import get_connection

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT to_regclass('public.asknum_query_log')")
                return cur.fetchone()[0] is not None
    except Exception:
        return False


requires_asknum_log = pytest.mark.skipif(
    not _asknum_log_ready(), reason="asknum_query_log table missing"
)


@requires_rag_log
@pytest.mark.anyio
async def test_list_rag_traces_empty_ok():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ops/rag-traces?limit=5", headers=USER_HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert "total" in body
    assert "summary" in body
    assert "refusal_rate" in body["summary"]
    assert isinstance(body["items"], list)


@requires_asknum_log
@pytest.mark.anyio
async def test_list_asknum_traces_ok():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ops/asknum-traces?limit=5", headers=USER_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert "total" in body
    assert "summary" in body
    assert "by_route" in body["summary"]
    assert isinstance(body["items"], list)


@pytest.mark.anyio
async def test_monitor_requires_user_identity():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for path in (
            "/ops/rag/overview", "/ops/rag-traces", "/ops/rag-traces/1",
            "/ops/asknum-traces", "/ops/asknum-traces/1",
        ):
            response = await client.get(path)
            assert response.status_code == 401, path
