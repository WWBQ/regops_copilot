from unittest.mock import MagicMock

from app.db.chunk_repository import ChunkHit
from app.rag.service import prepare_chat_rag, should_use_rag


def test_should_use_rag_skips_greetings():
    assert should_use_rag("你好") is False
    assert should_use_rag("您好！") is False
    assert should_use_rag("谢谢") is False
    assert should_use_rag("hi") is False
    assert should_use_rag("介绍一下") is False


def test_should_use_rag_keeps_substantive_questions():
    assert should_use_rag("美的营收是多少") is True
    assert should_use_rag("比亚迪净利润") is True
    assert should_use_rag("2024年合规风险有哪些") is True
    assert should_use_rag("2024 年长城新推出的车型") is True
    assert should_use_rag("024 年长城新推出的车型") is True


def test_should_use_rag_session_upload_long_question():
    assert should_use_rag("请总结这份文档的主要结论", session_has_ready_docs=True) is True
    assert should_use_rag("你好", session_has_ready_docs=True) is False


def test_prepare_chat_rag_skips_greeting_without_retrieve(monkeypatch):
    retrieve = MagicMock()
    monkeypatch.setattr("app.rag.service.collect_rag_doc_ids", lambda _: ["000333_2024"])
    monkeypatch.setattr("app.rag.service.retrieve_hits_for_docs", retrieve)
    result = prepare_chat_rag(
        session_id=None,
        question="你好",
        document_service=MagicMock(),
    )
    assert result is None
    retrieve.assert_not_called()


def test_prepare_chat_rag_skips_low_score_hits(monkeypatch):
    low_hit = ChunkHit(
        doc_id="000333_2024",
        chunk_index=0,
        content="无关片段",
        metadata={"page": 1},
        score=0.2,
    )

    monkeypatch.setattr("app.rag.service.collect_rag_doc_ids", lambda _: ["000333_2024"])
    monkeypatch.setattr("app.rag.service.retrieve_hits_for_docs", lambda **_: [low_hit])
    result = prepare_chat_rag(
        session_id=None,
        question="美的营收是多少",
        document_service=MagicMock(),
        min_score=0.42,
    )
    assert result is None


def test_prepare_chat_rag_keeps_relevant_hits(monkeypatch):
    high_hit = ChunkHit(
        doc_id="000333_2024",
        chunk_index=0,
        content="营业收入 100 亿元",
        metadata={"page": 12},
        score=0.78,
    )
    mock_service = MagicMock()
    mock_service.viewer_url.return_value = "http://test#page=12"

    monkeypatch.setattr("app.rag.service.collect_rag_doc_ids", lambda _: ["000333_2024"])
    monkeypatch.setattr("app.rag.service.retrieve_hits_for_docs", lambda **_: [high_hit])
    monkeypatch.setattr(
        "app.rag.service.resolve_document_titles",
        lambda _conn, _ids: {"000333_2024": "美的集团2024年年度报告"},
    )
    result = prepare_chat_rag(
        session_id=None,
        question="美的营收是多少",
        document_service=mock_service,
        min_score=0.42,
    )
    assert result is not None
    assert len(result.citations) == 1
    assert result.citations[0].page == 12
    assert result.citations[0].title == "美的集团2024年年度报告"
