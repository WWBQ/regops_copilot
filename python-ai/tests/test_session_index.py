from pathlib import Path

from app.db.chunk_repository import ChunkHit
from app.ingest.chunker import TextChunk
from app.rag.session_index import (
    save_session_chunks,
    search_session_keyword,
    search_session_similar,
)


def _chunk(doc_id: str, index: int, text: str) -> TextChunk:
    return TextChunk(
        doc_id=doc_id,
        chunk_index=index,
        content=text,
        metadata={"page": index, "session_id": "sid", "scope": "session"},
    )


def test_session_index_vector_and_keyword_stay_off_corpus(tmp_path, monkeypatch):
    monkeypatch.setattr("app.rag.session_index.session_index_root", lambda: tmp_path)
    doc_id = "sess_demo_1"
    save_session_chunks(
        session_id="sid",
        doc_id=doc_id,
        chunks=[
            _chunk(doc_id, 0, "本文件约定验收标准与交付清单"),
            _chunk(doc_id, 1, "无关页眉年度报告全文"),
        ],
        vectors=[[1.0, 0.0], [0.0, 1.0]],
    )
    assert (tmp_path / "sid" / f"{doc_id}.json").is_file()

    vector_hits = search_session_similar([1.0, 0.0], [doc_id], top_k=2)
    assert vector_hits[0].chunk_index == 0
    assert vector_hits[0].vector_score is not None

    keyword_hits = search_session_keyword([doc_id], ["验收标准"], top_k=5)
    assert keyword_hits
    assert keyword_hits[0].chunk_index == 0
    assert isinstance(keyword_hits[0], ChunkHit)


def test_session_docs_do_not_query_company_table(monkeypatch):
    from contextlib import contextmanager
    from unittest.mock import MagicMock

    from app.db.chunk_repository import ChunkHit
    from app.rag.service import retrieve_hits_with_trace

    corpus_calls: list[str] = []
    session_hit = ChunkHit(
        "sess_demo_1",
        0,
        "本文件约定验收标准与交付清单，内容充实足以通过低价值过滤。",
        {"page": 1},
        0.9,
        vector_score=0.9,
    )

    @contextmanager
    def fake_conn():
        corpus_calls.append("conn")
        yield MagicMock()

    monkeypatch.setattr("app.rag.service.embed_text", lambda _q: [1.0, 0.0])
    monkeypatch.setattr("app.rag.service.get_connection", fake_conn)
    monkeypatch.setattr(
        "app.rag.service.search_similar_chunks",
        lambda *_a, **_k: corpus_calls.append("search") or [],
    )
    monkeypatch.setattr("app.rag.service.search_session_similar", lambda *_a, **_k: [session_hit])
    monkeypatch.setattr("app.rag.service.search_session_keyword", lambda *_a, **_k: [])
    monkeypatch.setattr("app.rag.service.rerank_with_cross_encoder", lambda *_a, **_k: [session_hit])

    hits, pipeline = retrieve_hits_with_trace(
        question="这份验收标准怎么写",
        doc_ids=["sess_demo_1"],
        top_k=3,
        mode="hybrid",
    )
    assert corpus_calls == []
    assert hits[0].doc_id == "sess_demo_1"
    assert pipeline["session_doc_ids"] == ["sess_demo_1"]
    assert pipeline["corpus_doc_ids"] == []
