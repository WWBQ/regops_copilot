from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from app.ingest.embeddings import (
    EMBEDDING_DIM,
    EmbeddingModel,
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
