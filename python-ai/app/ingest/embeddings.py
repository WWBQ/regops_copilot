"""本地 Embedding · BAAI/bge-m3（1024 维，对齐 doc_chunks.embedding）。"""

from __future__ import annotations

import logging
import threading
from functools import lru_cache
from typing import TYPE_CHECKING

from app.config import Settings, get_settings

if TYPE_CHECKING:
    import numpy as np
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "BAAI/bge-m3"
EMBEDDING_DIM = 1024


class EmbeddingError(Exception):
    """Embedding 推理失败。"""


class EmbeddingModel:
    """sentence-transformers 封装；模型懒加载，线程内复用。"""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        *,
        device: str = "auto",
        batch_size: int = 16,
        expected_dim: int = EMBEDDING_DIM,
        local_files_only: bool = True,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.batch_size = batch_size
        self.expected_dim = expected_dim
        self.local_files_only = local_files_only
        self._model: SentenceTransformer | None = None
        self._lock = threading.Lock()

    def _resolve_device(self) -> str:
        if self.device != "auto":
            return self.device
        import torch

        if torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            return "cuda"
        return "cpu"

    def _load(self) -> SentenceTransformer:
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is not None:
                return self._model
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise EmbeddingError(
                    "sentence-transformers 未安装；请执行: pip install sentence-transformers"
                ) from exc
            resolved = self._resolve_device()
            logger.info("loading embedding model=%s device=%s", self.model_name, resolved)
            self._model = SentenceTransformer(
                self.model_name, device=resolved, local_files_only=self.local_files_only,
            )
            return self._model

    def encode(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        cleaned = [text.strip() if text else "" for text in texts]
        if any(not text for text in cleaned):
            raise EmbeddingError("empty text is not embeddable")

        model = self._load()
        try:
            vectors: np.ndarray = model.encode(
                cleaned,
                batch_size=self.batch_size,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        except Exception as exc:
            logger.exception("embedding encode failed count=%d", len(cleaned))
            raise EmbeddingError(str(exc)) from exc

        if vectors.ndim != 2 or vectors.shape[1] != self.expected_dim:
            raise EmbeddingError(
                f"unexpected embedding shape {vectors.shape}, expected (*, {self.expected_dim})"
            )
        return [row.tolist() for row in vectors]

    def encode_one(self, text: str) -> list[float]:
        return self.encode([text])[0]


@lru_cache
def get_embedding_model() -> EmbeddingModel:
    settings = get_settings()
    return EmbeddingModel(
        settings.embedding_model,
        device=settings.embedding_device,
        batch_size=settings.embedding_batch_size,
        expected_dim=settings.embedding_dim,
        local_files_only=settings.embedding_local_files_only,
    )


def embed_texts(texts: list[str], *, model: EmbeddingModel | None = None) -> list[list[float]]:
    embedder = model or get_embedding_model()
    return embedder.encode(texts)


def embed_text(text: str, *, model: EmbeddingModel | None = None) -> list[float]:
    return embed_texts([text], model=model)[0]


def vector_to_pg_literal(values: list[float]) -> str:
    """PostgreSQL pgvector 字面量：'[0.1,0.2,...]'。"""
    return "[" + ",".join(f"{v:.8f}" for v in values) + "]"


def build_embedder_from_settings(settings: Settings) -> EmbeddingModel:
    return EmbeddingModel(
        settings.embedding_model,
        device=settings.embedding_device,
        batch_size=settings.embedding_batch_size,
        expected_dim=settings.embedding_dim,
        local_files_only=settings.embedding_local_files_only,
    )
