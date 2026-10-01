import pytest

from app.config import Settings
from app.db.chunk_repository import ChunkHit
from app.models.llm import ChatResult
from app.rag.llm_reranker import _configured_client, rerank_with_llm


def _settings(**overrides) -> Settings:
    values = {
        "rag_rerank_backend": "llm",
        "rag_llm_rerank_deployment": "local",
        "rag_llm_rerank_model": "qwen3:8b",
        "rag_llm_rerank_base_url": "http://127.0.0.1:11434/v1",
        "rag_llm_rerank_api_key": "local",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _hit(index: int, page: int) -> ChunkHit:
    return ChunkHit(
        doc_id="000333_2024",
        chunk_index=index,
        content=f"候选片段 {index} 的财务与战略内容",
        metadata={"page": page, "company_code": "000333", "year": 2024},
        score=0.03 + index / 1000,
        vector_score=0.7 + index / 100,
    )


class _FakeClient:
    def __init__(self, content: str):
        self.content = content
        self.messages = None

    def chat_with_usage_sync(self, messages, *, temperature=0.1):
        self.messages = messages
        return ChatResult(content=self.content, latency_ms=25.0)


def test_llm_reranker_reorders_without_overwriting_retrieval_scores(monkeypatch):
    fake = _FakeClient(
        '{"supports_answer":true,"ranked":['
        '{"id":"c2","score":97},{"id":"c1","score":81}]}'
    )
    monkeypatch.setattr(
        "app.rag.llm_reranker._configured_client",
        lambda _settings: (fake, "local"),
    )
    hits = [_hit(1, 10), _hit(2, 20)]

    result = rerank_with_llm("两项战略有什么不同", hits, settings=_settings())

    assert [hit.chunk_index for hit in result.hits] == [2, 1]
    assert result.hits[0].score == hits[1].score
    assert result.hits[0].vector_score == hits[1].vector_score
    assert result.ranking[0]["score"] == 97
    assert result.latency_ms == 25.0
    assert "候选片段 1" in fake.messages[1]["content"]


def test_llm_reranker_accepts_explicit_no_evidence(monkeypatch):
    fake = _FakeClient('{"supports_answer":false,"ranked":[]}')
    monkeypatch.setattr(
        "app.rag.llm_reranker._configured_client",
        lambda _settings: (fake, "local"),
    )

    result = rerank_with_llm("没有依据的问题", [_hit(1, 10)], settings=_settings())

    assert result.supports_answer is False
    assert result.hits == []


def test_llm_reranker_rejects_unknown_candidate_id(monkeypatch):
    fake = _FakeClient(
        '{"supports_answer":true,"ranked":[{"id":"c99","score":90}]}'
    )
    monkeypatch.setattr(
        "app.rag.llm_reranker._configured_client",
        lambda _settings: (fake, "local"),
    )

    with pytest.raises(ValueError, match="unknown candidate ID"):
        rerank_with_llm("问题", [_hit(1, 10)], settings=_settings())


def test_api_deployment_requires_independent_api_key():
    settings = _settings(
        rag_llm_rerank_deployment="api",
        rag_llm_rerank_base_url="https://example.com/v1",
        rag_llm_rerank_api_key="",
    )

    with pytest.raises(ValueError, match="RAG_LLM_RERANK_API_KEY"):
        _configured_client(settings)
