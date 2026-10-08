from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from app.ingest.embeddings import (
    EMBEDDING_DIM,
    EmbeddingModel,
    build_embedder_from_settings,
    embed_text,
    vector_to_pg_literal,
)


def _mock_model(vectors: np.ndarray) -> MagicMock:
    mock_model = MagicMock()
    mock_model.encode.return_value = vectors
    return mock_model


def test_embed_texts_shape():
    vectors = np.array([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]], dtype=np.float32)
    model = EmbeddingModel("BAAI/bge-m3", device="cpu", expected_dim=3)
    model._model = _mock_model(vectors)

    out = model.encode(["hello", "world"])
    assert len(out) == 2
    assert len(out[0]) == 3
    model._model.encode.assert_called_once()


def test_embed_texts_rejects_empty():
    model = EmbeddingModel("BAAI/bge-m3", device="cpu")
    with pytest.raises(Exception, match="empty"):
        model.encode(["ok", "   "])


def test_embed_text_helper():
    vectors = np.array([[0.1, 0.2, 0.3]], dtype=np.float32)
    model = EmbeddingModel("BAAI/bge-m3", device="cpu", expected_dim=3)
    model._model = _mock_model(vectors)

    vec = embed_text("hello", model=model)
    assert vec == pytest.approx([0.1, 0.2, 0.3])


def test_vector_to_pg_literal():
    literal = vector_to_pg_literal([0.1, -0.2, 0.3])
    assert literal.startswith("[")
    assert "0.10000000" in literal


def test_default_dim_constant():
    assert EMBEDDING_DIM == 1024


@pytest.mark.parametrize("local_files_only", [True, False])
def test_embedding_load_respects_local_files_only(monkeypatch, local_files_only):
    from types import SimpleNamespace
    import sentence_transformers

    calls = []
    fake_model = MagicMock()

    def fake_constructor(model_name, **kwargs):
        calls.append((model_name, kwargs))
        return fake_model

    monkeypatch.setattr(sentence_transformers, "SentenceTransformer", fake_constructor)
    settings = SimpleNamespace(
        embedding_model="BAAI/bge-m3", embedding_device="cpu",
        embedding_batch_size=16, embedding_dim=1024,
        embedding_local_files_only=local_files_only,
    )
    model = build_embedder_from_settings(settings)

    assert model._load() is fake_model
    assert calls == [("BAAI/bge-m3", {"device": "cpu", "local_files_only": local_files_only})]
