"""Cross-Encoder 精排：Hybrid 召回后的第二阶段 rerank（企业 RAG 标准架构）。"""

from __future__ import annotations

import logging
from functools import lru_cache

from app.db.chunk_repository import ChunkHit

logger = logging.getLogger(__name__)


@lru_cache
def _get_cross_encoder(model_name: str):
    from sentence_transformers import CrossEncoder

    logger.info("loading cross-encoder reranker model=%s", model_name)
    return CrossEncoder(model_name)


def rerank_with_cross_encoder(
    question: str,
    hits: list[ChunkHit],
    *,
    model_name: str,
    top_k: int,
) -> list[ChunkHit]:
    if not hits:
        return hits

    model = _get_cross_encoder(model_name)
    pairs = [[question, hit.content[:2000]] for hit in hits]
    scores = model.predict(pairs)

    reranked: list[ChunkHit] = []
    for hit, rerank_score in sorted(
        zip(hits, scores, strict=True),
        key=lambda item: float(item[1]),
        reverse=True,
    ):
        reranked.append(
            ChunkHit(
                doc_id=hit.doc_id,
                chunk_index=hit.chunk_index,
                content=hit.content,
                metadata=hit.metadata,
                score=float(rerank_score),
                vector_score=hit.vector_score,
                keyword_score=hit.keyword_score,
            )
        )
    return reranked[:top_k]
