"""会话上传的切块和向量：落在本地目录，不写入公司检索表 doc_chunks。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.db.chunk_repository import ChunkHit
from app.ingest.chunker import TextChunk

logger = logging.getLogger(__name__)


def session_index_root() -> Path:
    settings = get_settings()
    return Path(settings.object_store_root) / "_session_index"


def _doc_path(session_id: str, doc_id: str) -> Path:
    return session_index_root() / session_id / f"{doc_id}.json"


def save_session_chunks(
    *,
    session_id: str,
    doc_id: str,
    chunks: list[TextChunk],
    vectors: list[list[float]],
) -> int:
    if len(chunks) != len(vectors):
        raise ValueError("chunks and vectors length mismatch")
    path = _doc_path(session_id, doc_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "session_id": session_id,
        "doc_id": doc_id,
        "chunks": [
            {
                "chunk_index": chunk.chunk_index,
                "content": chunk.content,
                "metadata": chunk.metadata,
                "embedding": vector,
            }
            for chunk, vector in zip(chunks, vectors, strict=True)
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
    logger.info("session index saved session_id=%s doc_id=%s chunks=%d", session_id, doc_id, len(chunks))
    return len(chunks)


def delete_session_chunks(*, session_id: str, doc_id: str) -> None:
    path = _doc_path(session_id, doc_id)
    path.unlink(missing_ok=True)


def _load_records(doc_ids: list[str]) -> list[dict[str, Any]]:
    if not doc_ids:
        return []
    wanted = set(doc_ids)
    root = session_index_root()
    if not root.is_dir():
        return []
    records: list[dict[str, Any]] = []
    for path in root.glob("*/*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("skip unreadable session index %s", path)
            continue
        if str(payload.get("doc_id") or "") not in wanted:
            continue
        for chunk in payload.get("chunks") or []:
            records.append(
                {
                    "doc_id": str(payload["doc_id"]),
                    "chunk_index": int(chunk["chunk_index"]),
                    "content": str(chunk.get("content") or ""),
                    "metadata": chunk.get("metadata") if isinstance(chunk.get("metadata"), dict) else {},
                    "embedding": chunk.get("embedding") or [],
                }
            )
    return records


def _cosine(query: list[float], vector: list[float]) -> float:
    if not query or not vector or len(query) != len(vector):
        return 0.0
    dot = 0.0
    qn = 0.0
    vn = 0.0
    for q, v in zip(query, vector, strict=True):
        dot += q * v
        qn += q * q
        vn += v * v
    if qn <= 0 or vn <= 0:
        return 0.0
    return dot / ((qn ** 0.5) * (vn ** 0.5))


def search_session_similar(
    query_vector: list[float],
    doc_ids: list[str],
    *,
    top_k: int,
) -> list[ChunkHit]:
    if not doc_ids or top_k <= 0:
        return []
    scored: list[ChunkHit] = []
    for rec in _load_records(doc_ids):
        embedding = rec["embedding"]
        if not isinstance(embedding, list) or not embedding:
            continue
        score = _cosine(query_vector, [float(x) for x in embedding])
        scored.append(
            ChunkHit(
                doc_id=rec["doc_id"],
                chunk_index=rec["chunk_index"],
                content=rec["content"],
                metadata=rec["metadata"],
                score=score,
                vector_score=score,
            )
        )
    scored.sort(key=lambda hit: hit.score, reverse=True)
    return scored[:top_k]


def search_session_keyword(
    doc_ids: list[str],
    terms: list[str],
    *,
    top_k: int,
    k1: float = 1.2,
    b: float = 0.75,
) -> list[ChunkHit]:
    from app.rag.bm25 import build_stats, score_text
    from app.rag.retrieval import is_low_value_chunk

    query_terms = list(dict.fromkeys(term.strip() for term in terms if term and term.strip()))
    if not doc_ids or not query_terms or top_k <= 0:
        return []
    corpus: list[tuple[str, int, str, dict[str, Any]]] = []
    for rec in _load_records(doc_ids):
        text = rec["content"]
        if is_low_value_chunk(text):
            continue
        corpus.append((rec["doc_id"], rec["chunk_index"], text, rec["metadata"]))
    if not corpus:
        return []
    stats = build_stats([text for _d, _i, text, _m in corpus], query_terms, k1=k1, b=b)
    ranked: list[tuple[float, tuple[str, int, str, dict[str, Any]]]] = []
    for row in corpus:
        ranked.append((score_text(row[2], query_terms, stats), row))
    ranked.sort(key=lambda item: item[0], reverse=True)
    hits: list[ChunkHit] = []
    for score, (doc_id, chunk_index, content, metadata) in ranked[:top_k]:
        if score <= 0:
            continue
        hits.append(
            ChunkHit(
                doc_id=doc_id,
                chunk_index=chunk_index,
                content=content,
                metadata=metadata,
                score=score,
                keyword_score=score,
            )
        )
    return hits
