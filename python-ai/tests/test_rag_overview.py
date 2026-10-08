"""RAG overview 统计测试。"""

from __future__ import annotations

from app.ops.rag_service import REFUSAL_OUTCOMES, fetch_rag_overview


def test_refusal_outcomes_defined():
    assert REFUSAL_OUTCOMES == frozenset({"low_score", "no_docs"})


def test_fetch_rag_overview_empty_when_no_table(monkeypatch):
    def fake_get_connection():
        class FakeConn:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def cursor(self):
                return self

            def execute(self, *args, **kwargs):
                pass

            def fetchone(self):
                return (None,)

        return FakeConn()

    monkeypatch.setattr("app.ops.rag_service.get_connection", fake_get_connection)
    monkeypatch.setattr("app.ops.rag_service._table_exists", lambda *_: False)

    overview = fetch_rag_overview(user_id="00000000-0000-0000-0000-000000000001")
    assert overview["total"] == 0
    assert overview["refusal_rate"] == 0.0
