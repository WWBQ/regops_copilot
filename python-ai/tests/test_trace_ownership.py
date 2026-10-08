"""监控读写都绑定登录用户；历史无归属记录不能落入任一用户查询。"""

from __future__ import annotations

from contextlib import contextmanager
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.asknum_trace_repository import (
    count_asknum_traces, get_asknum_trace, list_asknum_traces, summarize_asknum_traces,
)
from app.db.rag_trace_repository import count_rag_traces, get_rag_trace, list_rag_traces
from app.main import app

ALICE = "00000000-0000-0000-0000-000000000001"
BOB = "00000000-0000-0000-0000-000000000002"


class Cursor:
    def __init__(self):
        self.calls = []
        self.result = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def execute(self, sql, params=()):
        self.calls.append((sql, params))

    def fetchone(self):
        return self.result

    def fetchall(self):
        return []


class Connection:
    def __init__(self):
        self.cur = Cursor()

    def cursor(self):
        return self.cur


def test_repository_queries_always_filter_user():
    for user in (ALICE, BOB):
        conn = Connection()
        list_rag_traces(conn, user_id=user)
        conn.cur.result = (0,)
        count_rag_traces(conn, user_id=user)
        conn.cur.result = None
        get_rag_trace(conn, 42, user_id=user)
        list_asknum_traces(conn, user_id=user)
        conn.cur.result = (0,)
        count_asknum_traces(conn, user_id=user)
        conn.cur.result = None
        get_asknum_trace(conn, 42, user_id=user)
        summarize_asknum_traces(conn, user_id=user)
        assert len(conn.cur.calls) == 7
        for sql, params in conn.cur.calls:
            assert "user_id = %s::uuid" in sql
            assert user in params


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_trace_details_do_not_expose_other_users(monkeypatch):
    @contextmanager
    def connection():
        yield Connection()

    def rag_get(_conn, _trace_id, *, user_id):
        assert user_id == BOB
        return None

    def asknum_get(_conn, _trace_id, *, user_id):
        assert user_id == BOB
        return None

    monkeypatch.setattr("app.ops.router.get_connection", connection)
    monkeypatch.setattr("app.ops.router.get_rag_trace", rag_get)
    monkeypatch.setattr("app.ops.router.get_asknum_trace", asknum_get)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for path in ("/ops/rag-traces/42", "/ops/asknum-traces/42"):
            response = await client.get(path, headers={"X-Regops-User": BOB})
            assert response.status_code == 404
            invalid = await client.get(path, headers={"X-Regops-User": "not-a-uuid"})
            assert invalid.status_code == 401


def test_user_ids_are_canonical_uuids():
    assert str(UUID(ALICE)) == ALICE


def test_postgres_monitor_isolation():
    """同一数据库中 Alice/Bob/无归属三类 trace 不得串读；事务结束自动回滚。"""
    from app.db.connection import get_connection

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT user_id FROM rag_query_log LIMIT 0")
                cur.execute("SELECT user_id FROM asknum_query_log LIMIT 0")
    except Exception:
        pytest.skip("trace ownership migration or PostgreSQL unavailable")

    alice, bob = str(uuid4()), str(uuid4())
    with get_connection() as conn:
        with conn.cursor() as cur:
            for user in (alice, bob, None):
                cur.execute(
                    "INSERT INTO rag_query_log (user_id, question, outcome) "
                    "VALUES (%s::uuid, %s, 'ok') RETURNING id",
                    (user, "ownership-test"),
                )
                rag_id = cur.fetchone()[0]
                if user == alice:
                    alice_rag_id = rag_id
                cur.execute(
                    "INSERT INTO asknum_query_log (user_id, question, route) "
                    "VALUES (%s::uuid, %s, 'metric') RETURNING id",
                    (user, "ownership-test"),
                )
                asknum_id = cur.fetchone()[0]
                if user == alice:
                    alice_asknum_id = asknum_id
        assert count_rag_traces(conn, user_id=alice) == 1
        assert count_asknum_traces(conn, user_id=alice) == 1
        assert count_rag_traces(conn, user_id=bob) == 1
        assert count_asknum_traces(conn, user_id=bob) == 1
        assert len(list_rag_traces(conn, user_id=bob)) == 1
        assert len(list_asknum_traces(conn, user_id=bob)) == 1
        assert get_rag_trace(conn, alice_rag_id, user_id=bob) is None
        assert get_asknum_trace(conn, alice_asknum_id, user_id=bob) is None
        assert summarize_asknum_traces(conn, user_id=alice)["total"] == 1
        conn.rollback()
