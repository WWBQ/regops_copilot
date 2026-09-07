from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.review_draft_repository import ReviewDraftRow
from app.main import app
from app.schemas.tools import ToolContext
from app.tools import invoke_tool


def _row(*, dept: str = "research", thread_id: str = "research:t1", replayed: bool = False) -> ReviewDraftRow:
    return ReviewDraftRow(
        id=1,
        public_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        status="PENDING",
        dept=dept,
        company_code="002594",
        company_codes=["002594", "601633"],
        title="2024年净利润对比审查草稿",
        reason="人工确认后写入",
        conclusion="并列查数，未手算差额。",
        risk_level="低",
        clause_refs=["002594_2024#p20"],
        evidence_quotes=["净利润变动主要来自销量与产品结构。"],
        impact_scope="比亚迪、长城 · 2024 年合并 · 净利润",
        thread_id=thread_id,
        session_id=None,
        request_id="rid-1",
        idempotency_key=thread_id,
        created_at=datetime(2026, 9, 7, tzinfo=timezone.utc),
    )


@contextmanager
def _conn():
    class _C:
        def commit(self) -> None:
            return None

    yield _C()


def test_create_review_draft_persists_pending(monkeypatch):
    captured: dict = {}

    def fake_insert(conn, **kwargs):
        captured.update(kwargs)
        return _row(thread_id=kwargs.get("thread_id") or "research:t1"), False

    monkeypatch.setattr("app.tools.draft.get_connection", _conn)
    monkeypatch.setattr("app.tools.draft.insert_review_draft", fake_insert)
    out = invoke_tool(
        "create_review_draft",
        {
            "company_code": "002594",
            "title": "关联交易",
            "reason": "需复核",
            "conclusion": "需人工看影响范围",
            "clause_refs": ["002594_2024#p20"],
            "impact_scope": "比亚迪 2024 合并",
            "thread_id": "research:t1",
            "session_id": "",
            "dept": "research",
        },
        context=ToolContext(backend="live", request_id="rid-1"),
    )
    assert out.ok is True
    assert out.replayed is False
    assert out.result["status"] == "PENDING"
    assert out.result["draft_id"] == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    assert captured["session_id"] is None
    assert captured["request_id"] == "rid-1"
    assert captured["thread_id"] == "research:t1"
    assert "maker-checker" in out.result["message"]


def test_create_review_draft_same_thread_replays(monkeypatch):
    calls = {"n": 0}

    def fake_insert(conn, **kwargs):
        calls["n"] += 1
        return _row(thread_id=kwargs["thread_id"]), calls["n"] > 1

    monkeypatch.setattr("app.tools.draft.get_connection", _conn)
    monkeypatch.setattr("app.tools.draft.insert_review_draft", fake_insert)
    args = {
        "company_code": "002594",
        "title": "关联交易",
        "reason": "需复核",
        "thread_id": "research:t1",
        "dept": "research",
    }
    first = invoke_tool("create_review_draft", args, context=ToolContext(backend="live"))
    second = invoke_tool("create_review_draft", args, context=ToolContext(backend="live"))
    assert first.ok is True
    assert second.ok is True
    assert second.replayed is True
    assert first.result["draft_id"] == second.result["draft_id"]
    assert first.result["status"] == "PENDING"
    assert second.result["status"] == "PENDING"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.anyio
async def test_list_review_drafts_requires_dept(client: AsyncClient):
    missing = await client.get("/tools/review-drafts")
    assert missing.status_code == 400


@pytest.mark.anyio
async def test_list_and_get_review_drafts(client: AsyncClient, monkeypatch):
    row = _row()

    @contextmanager
    def fake_conn():
        yield object()

    monkeypatch.setattr("app.db.connection.get_connection", fake_conn)
    monkeypatch.setattr(
        "app.db.review_draft_repository.list_review_drafts",
        lambda conn, dept=None, limit=50, offset=0: ([row], 1),
    )
    monkeypatch.setattr("app.db.review_draft_repository.get_by_public_id", lambda conn, draft_id: row)
    listed = await client.get("/tools/review-drafts", headers={"X-Regops-Dept": "research"})
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == "PENDING"
    assert body["items"][0]["draft_id"] == row.public_id
    got = await client.get(f"/tools/review-drafts/{row.public_id}", headers={"X-Regops-Dept": "research"})
    assert got.status_code == 200
    assert got.json()["status"] == "PENDING"
    hidden = await client.get(f"/tools/review-drafts/{row.public_id}", headers={"X-Regops-Dept": "compliance"})
    assert hidden.status_code == 404
