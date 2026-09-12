import pytest

from app.db.chunk_repository import ChunkHit
from app.rag.service import prepare_chat_rag
from app.rag.trace import RagPrepareResult


@pytest.fixture(autouse=True)
def _disable_rag_trace_persist(monkeypatch):
    monkeypatch.setattr("app.rag.service.save_rag_trace", lambda _trace: None)


def test_should_use_rag_skips_greetings():
    from app.rag.service import should_use_rag

    assert should_use_rag("你好") is False
    assert should_use_rag("您好！") is False
    assert should_use_rag("谢谢") is False
    assert should_use_rag("hi") is False
    assert should_use_rag("介绍一下") is False


def test_should_use_rag_keeps_substantive_questions():
    from app.rag.service import should_use_rag

    assert should_use_rag("美的营收是多少") is True
    assert should_use_rag("比亚迪净利润") is True
    assert should_use_rag("2024年合规风险有哪些") is True
    assert should_use_rag("2024 年长城新推出的车型") is True
    assert should_use_rag("024 年长城新推出的车型") is True


def test_should_use_rag_session_upload_long_question():
    from app.rag.service import should_use_rag

    assert should_use_rag("请总结这份文档的主要结论", session_has_ready_docs=True) is True
    assert should_use_rag("你好", session_has_ready_docs=True) is False


def test_prepare_chat_rag_skips_greeting_without_retrieve(monkeypatch):
    from unittest.mock import MagicMock

    retrieve = MagicMock()
    monkeypatch.setattr("app.rag.service.collect_rag_doc_ids", lambda _: ["000333_2024"])
    monkeypatch.setattr("app.rag.service.retrieve_hits_with_trace", retrieve)
    result = prepare_chat_rag(
        session_id=None,
        question="你好",
        document_service=MagicMock(),
        persist_trace=False,
    )
    assert isinstance(result, RagPrepareResult)
    assert result.answer is None
    assert result.trace.outcome == "no_intent"
    retrieve.assert_not_called()


def test_prepare_chat_rag_skips_low_score_hits(monkeypatch):
    from unittest.mock import MagicMock

    low_hit = ChunkHit(
        doc_id="000333_2024",
        chunk_index=0,
        content="无关片段",
        metadata={"page": 1},
        score=0.2,
    )

    monkeypatch.setattr("app.rag.service.collect_rag_doc_ids", lambda _: ["000333_2024"])
    monkeypatch.setattr(
        "app.rag.service.retrieve_hits_with_trace",
        lambda **_: ([low_hit], {"keyword_terms": [], "vector_top": [], "keyword_top": []}),
    )
    result = prepare_chat_rag(
        session_id=None,
        question="美的营收是多少",
        document_service=MagicMock(),
        min_score=0.42,
        persist_trace=False,
    )
    assert result.answer is None
    assert result.trace.outcome == "low_score"


def test_prepare_chat_rag_keeps_relevant_hits(monkeypatch):
    from contextlib import contextmanager
    from unittest.mock import MagicMock

    high_hit = ChunkHit(
        doc_id="000333_2024",
        chunk_index=0,
        content="营业收入 100 亿元",
        metadata={"page": 12},
        score=0.78,
        vector_score=0.78,
    )
    mock_service = MagicMock()
    mock_service.viewer_url.return_value = "http://test#page=12"

    @contextmanager
    def fake_conn():
        yield MagicMock()

    monkeypatch.setattr("app.rag.service.get_connection", fake_conn)
    monkeypatch.setattr("app.rag.service.collect_rag_doc_ids", lambda _: ["000333_2024"])
    monkeypatch.setattr(
        "app.rag.service.retrieve_hits_with_trace",
        lambda **_: ([high_hit], {"keyword_terms": ["营收"], "vector_top": [], "keyword_top": []}),
    )
    monkeypatch.setattr(
        "app.rag.service.resolve_document_titles",
        lambda _conn, _ids: {"000333_2024": "美的集团2024年年度报告"},
    )
    result = prepare_chat_rag(
        session_id=None,
        question="美的营收是多少",
        document_service=mock_service,
        min_score=0.42,
        persist_trace=False,
    )
    assert result.answer is not None
    assert len(result.answer.citations) == 1
    assert result.answer.citations[0].page == 12
    assert result.answer.citations[0].title == "美的集团2024年年度报告"
    assert result.trace.outcome == "ok"
    assert result.trace.rag_used is True


def test_prepare_chat_rag_acl_deny_skips_retrieve(monkeypatch):
    from unittest.mock import MagicMock

    retrieve = MagicMock()
    monkeypatch.setattr(
        "app.rag.service.collect_rag_doc_ids",
        lambda _: ["002594_2024", "601633_2024", "000333_2024", "000651_2024", "600031_2024"],
    )
    monkeypatch.setattr("app.rag.service.retrieve_hits_with_trace", retrieve)
    result = prepare_chat_rag(
        session_id=None,
        question="美的集团2024年营业收入是多少",
        document_service=MagicMock(),
        persist_trace=False,
        dept="research",
    )
    assert result.answer is None
    assert result.trace.outcome == "no_docs"
    assert result.trace.scoped_doc_ids == []
    retrieve.assert_not_called()


def test_prepare_chat_rag_missing_year_is_no_docs(monkeypatch):
    from unittest.mock import MagicMock

    retrieve = MagicMock()
    monkeypatch.setattr("app.rag.service.collect_rag_doc_ids", lambda _: ["002594_2024"])
    monkeypatch.setattr("app.rag.service.retrieve_hits_with_trace", retrieve)
    result = prepare_chat_rag(
        session_id=None,
        question="比亚迪2099年营业收入是多少",
        document_service=MagicMock(),
        persist_trace=False,
    )
    assert result.trace.outcome == "no_docs"
    retrieve.assert_not_called()
