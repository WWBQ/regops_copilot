from app.config import Settings
from app.core.warmup import warmup_models


class _Embedder:
    def __init__(self):
        self.inputs = []

    def encode_one(self, text: str):
        self.inputs.append(text)
        return [0.1]


def test_warmup_loads_configured_clients_embedding_and_bge(monkeypatch):
    embedder = _Embedder()
    rerank_models = []
    monkeypatch.setattr(
        "app.core.warmup.warmup_llm_clients",
        lambda _settings: ["deepseek-flash"],
    )
    monkeypatch.setattr("app.core.warmup.get_embedding_model", lambda: embedder)
    monkeypatch.setattr(
        "app.core.warmup.get_cross_encoder",
        lambda model: rerank_models.append(model) or object(),
    )
    settings = Settings(
        rag_rerank_enabled=True,
        rag_rerank_backend="bge",
        _env_file=None,
    )

    result = warmup_models(settings)

    assert result.llm_clients == ["deepseek-flash"]
    assert result.embedding_ready is True
    assert result.reranker_ready is True
    assert result.errors == []
    assert embedder.inputs == ["金融文档检索预热"]
    assert rerank_models == [settings.rag_rerank_model]


def test_warmup_failure_does_not_abort_startup(monkeypatch):
    monkeypatch.setattr(
        "app.core.warmup.warmup_llm_clients",
        lambda _settings: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(
        "app.core.warmup.get_embedding_model",
        lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    settings = Settings(rag_rerank_enabled=False, _env_file=None)

    result = warmup_models(settings)

    assert "llm_clients:RuntimeError" in result.errors
    assert "embedding:RuntimeError" in result.errors
