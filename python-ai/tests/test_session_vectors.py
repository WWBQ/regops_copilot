from contextlib import contextmanager
from unittest.mock import MagicMock

from app.db.chunk_repository import ChunkHit
from app.rag.service import retrieve_hits_with_trace


def test_session_docs_query_shared_doc_chunks(monkeypatch):
    calls: list[tuple[str, list[str]]] = []
    session_hit = ChunkHit(
        "sess_demo_1",
        0,
        "本文件约定验收标准与交付清单，内容充实足以通过低价值过滤。",
        {"page": 1, "scope": "session"},
        0.9,
        vector_score=0.9,
    )

    @contextmanager
    def fake_conn():
        calls.append(("connection", []))
        yield MagicMock()

    def vector_search(_conn, _vector, doc_ids, **_kwargs):
        calls.append(("vector", doc_ids))
        return [session_hit]

    def keyword_search(_conn, doc_ids, _terms, **_kwargs):
        calls.append(("keyword", doc_ids))
        return []

    monkeypatch.setattr("app.rag.service.embed_text", lambda _q: [1.0, 0.0])
    monkeypatch.setattr("app.rag.service.get_connection", fake_conn)
    monkeypatch.setattr("app.rag.service.search_similar_chunks", vector_search)
    monkeypatch.setattr("app.rag.service.search_keyword_chunks", keyword_search)
    monkeypatch.setattr("app.rag.service.rerank_with_cross_encoder", lambda *_a, **_k: [session_hit])

    hits, pipeline = retrieve_hits_with_trace(
        question="这份验收标准怎么写",
        doc_ids=["sess_demo_1"],
        top_k=3,
        mode="hybrid",
    )

    assert ("vector", ["sess_demo_1"]) in calls
    assert hits[0].doc_id == "sess_demo_1"
    assert pipeline["session_doc_ids"] == ["sess_demo_1"]
    assert pipeline["corpus_doc_ids"] == []
