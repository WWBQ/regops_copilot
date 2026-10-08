"""金融 MCP 工具必须直接读已入库 PDF，不经聊天模型或跨公司检索。"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.db.chunk_repository import ChunkHit
from app.mcp import financial_server


def _f10_fact(**changes):
    row = {
        "company_code": "002594", "concept": "revenue", "period": "2024-12-31",
        "scope": "consolidated", "status": "auto_accepted", "currency": "CNY",
        "value_yuan": "123.45", "doc_id": "002594_2024", "page_no": None,
        "fact_key": "revenue_2024", "source_type": "web",
        "parser": "eastmoney_f10", "content_hash": "sha256:" + "a" * 64,
    }
    return {**row, **changes}


def test_f10_fact_accepts_hash_without_pdf_page():
    result = financial_server._accepted_fact(
        [_f10_fact()], company_code="002594", concept="revenue", year=2024,
    )

    assert result["outcome"] == "ok"
    assert result["value_yuan"] == "123.45"
    assert result["sources"] == [{
        "doc_id": "002594_2024", "source_type": "web", "parser": "eastmoney_f10",
        "content_hash": "sha256:" + "a" * 64, "fact_key": "revenue_2024",
    }]
    assert "page" not in result["sources"][0]


def test_manually_accepted_fact_is_available_to_agent():
    result = financial_server._accepted_fact(
        [_f10_fact(status="manually_accepted", value_yuan="456.78")],
        company_code="002594", concept="revenue", year=2024,
    )
    assert result["outcome"] == "ok"
    assert result["value_yuan"] == "456.78"


def test_rejected_fact_is_not_available_to_agent():
    result = financial_server._accepted_fact(
        [_f10_fact(status="rejected")],
        company_code="002594", concept="revenue", year=2024,
    )
    assert result["outcome"] != "ok"


def test_f10_fact_rejects_invalid_or_mismatched_provenance():
    for row in (
        _f10_fact(content_hash="sha256:short"),
        _f10_fact(doc_id="000333_2024"),
        _f10_fact(status="human_review"),
    ):
        result = financial_server._accepted_fact(
            [row], company_code="002594", concept="revenue", year=2024,
        )
        assert result["outcome"] != "ok"


def test_f10_fact_does_not_mix_pdf_facts_or_conflicting_bundles():
    pdf_only = financial_server._accepted_fact(
        [_f10_fact(source_type="pdf", page_no=12)],
        company_code="002594", concept="revenue", year=2024,
    )
    assert pdf_only["outcome"] == "missing"

    different_bundles = financial_server._accepted_fact(
        [_f10_fact(), _f10_fact(content_hash="sha256:" + "b" * 64)],
        company_code="002594", concept="revenue", year=2024,
    )
    assert different_bundles["outcome"] == "conflict"


def _ready_connection(monkeypatch, *, ready: bool = True):
    conn = MagicMock()
    conn.__enter__.return_value = conn
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = (1,) if ready else None
    monkeypatch.setattr(financial_server, "get_connection", lambda: conn)
    return cursor


def test_evidence_search_scopes_pdf_before_retrieval_and_skips_chat(monkeypatch):
    cursor = _ready_connection(monkeypatch)
    monkeypatch.setattr(
        financial_server, "get_settings",
        lambda: SimpleNamespace(rag_rerank_enabled=True, rag_rerank_backend="bge", rag_min_score=0.42),
    )
    retrieve = MagicMock(return_value=([
        ChunkHit("002594_2024", 1, "有效原文", {"page": 138}, 0.9),
        ChunkHit("002594_2023", 2, "跨年原文", {"page": 100}, 0.9),
        ChunkHit("002594_2024", 3, "无页码原文", {}, 0.9),
    ], {}))
    monkeypatch.setattr(financial_server, "retrieve_relevant_hits_for_docs", retrieve)
    monkeypatch.setattr(financial_server, "_request_json", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not call /chat")))

    result = financial_server.search_report_evidence("002594", 2024, "应收账款减值风险")

    assert result["status"] == "ok"
    assert result["citations"] == [{"doc_id": "002594_2024", "page": 138, "snippet": "有效原文"}]
    assert cursor.execute.call_args.args[1] == ("002594_2024", "002594", 2024)
    assert retrieve.call_args.kwargs == {
        "question": "应收账款减值风险", "doc_ids": ["002594_2024"],
        "top_k": 8, "min_score": 0.42, "mode": "rerank",
    }


def test_evidence_search_does_not_retrieve_without_ready_report(monkeypatch):
    _ready_connection(monkeypatch, ready=False)
    retrieve = MagicMock()
    monkeypatch.setattr(financial_server, "retrieve_relevant_hits_for_docs", retrieve)

    result = financial_server.search_report_evidence("002594", 2025, "风险在哪里")

    assert result["status"] == "insufficient_evidence"
    retrieve.assert_not_called()


def test_evidence_search_disables_llm_rerank(monkeypatch):
    _ready_connection(monkeypatch)
    monkeypatch.setattr(
        financial_server, "get_settings",
        lambda: SimpleNamespace(rag_rerank_enabled=True, rag_rerank_backend="llm", rag_min_score=0.42),
    )
    retrieve = MagicMock(return_value=([], {}))
    monkeypatch.setattr(financial_server, "retrieve_relevant_hits_for_docs", retrieve)

    result = financial_server.search_report_evidence("002594", 2024, "风险在哪里")

    assert result["status"] == "insufficient_evidence"
    assert retrieve.call_args.kwargs["mode"] == "hybrid"


def test_evidence_search_reports_backend_failure_without_leaking_details(monkeypatch):
    _ready_connection(monkeypatch)
    monkeypatch.setattr(
        financial_server, "get_settings",
        lambda: SimpleNamespace(rag_rerank_enabled=False, rag_rerank_backend="bge", rag_min_score=0.42),
    )
    monkeypatch.setattr(
        financial_server, "retrieve_relevant_hits_for_docs",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("private database URL")),
    )

    result = financial_server.search_report_evidence("002594", 2024, "风险在哪里")

    assert result == {"status": "unavailable", "reason": "年报检索服务不可用"}
