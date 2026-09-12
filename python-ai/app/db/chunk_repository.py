"""doc_chunks 写入 pgvector。"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import psycopg

from app.ingest.chunker import TextChunk
from app.ingest.embeddings import vector_to_pg_literal

logger = logging.getLogger(__name__)


def delete_chunks(conn: psycopg.Connection, *, doc_id: str, source_type: str = "pdf") -> int:
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM doc_chunks WHERE source_type = %s AND doc_id = %s",
            (source_type, doc_id),
        )
        return cur.rowcount


def insert_chunks(
    conn: psycopg.Connection,
    chunks: list[TextChunk],
    vectors: list[list[float]],
    *,
    source_type: str = "pdf",
) -> int:
    if len(chunks) != len(vectors):
        raise ValueError("chunks and vectors length mismatch")
    if not chunks:
        return 0

    rows: list[tuple[Any, ...]] = []
    for chunk, vector in zip(chunks, vectors, strict=True):
        rows.append(
            (
                source_type,
                chunk.doc_id,
                chunk.chunk_index,
                chunk.content,
                json.dumps(chunk.metadata, ensure_ascii=False),
                vector_to_pg_literal(vector),
            )
        )

    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO doc_chunks (source_type, doc_id, chunk_index, content, metadata, embedding)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s::vector)
            """,
            rows,
        )
    logger.info("inserted %d chunks for doc_id=%s", len(rows), chunks[0].doc_id)
    return len(rows)


@dataclass(frozen=True)
class ChunkHit:
    doc_id: str
    chunk_index: int
    content: str
    metadata: dict[str, Any]
    score: float
    vector_score: float | None = None
    keyword_score: float | None = None


def search_similar_chunks(
    conn: psycopg.Connection,
    query_vector: list[float],
    doc_ids: list[str],
    *,
    source_type: str = "pdf",
    top_k: int = 5,
) -> list[ChunkHit]:
    if not doc_ids:
        return []
    literal = vector_to_pg_literal(query_vector)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT doc_id, chunk_index, content, metadata,
                   1 - (embedding <=> %s::vector) AS score
            FROM doc_chunks
            WHERE source_type = %s
              AND doc_id = ANY(%s)
              AND embedding IS NOT NULL
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (literal, source_type, doc_ids, literal, top_k),
        )
        rows = cur.fetchall()
    hits: list[ChunkHit] = []
    for doc_id, chunk_index, content, metadata, score in rows:
        meta = metadata if isinstance(metadata, dict) else json.loads(metadata or "{}")
        hits.append(
            ChunkHit(
                doc_id=doc_id,
                chunk_index=int(chunk_index),
                content=content,
                metadata=meta,
                score=float(score),
            )
        )
    return hits


def search_keyword_chunks(
    conn: psycopg.Connection,
    doc_ids: list[str],
    terms: list[str],
    *,
    source_type: str = "pdf",
    top_k: int = 5,
    k1: float = 1.2,
    b: float = 0.75,
) -> list[ChunkHit]:
    """关键词补检：在已裁剪的 doc_id 语料上跑 Okapi BM25，取 top_k。"""
    from app.rag.bm25 import build_stats, score_text
    from app.rag.retrieval import is_low_value_chunk

    query_terms = [term.strip() for term in terms if term and term.strip()]
    query_terms = list(dict.fromkeys(query_terms))
    if not doc_ids or not query_terms or top_k <= 0:
        return []

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT doc_id, chunk_index, content, metadata
            FROM doc_chunks
            WHERE source_type = %s
              AND doc_id = ANY(%s)
              AND embedding IS NOT NULL
            """,
            (source_type, doc_ids),
        )
        rows = cur.fetchall()

    corpus: list[tuple[str, int, str, dict[str, Any]]] = []
    for doc_id, chunk_index, content, metadata in rows:
        text = content or ""
        if is_low_value_chunk(text):
            continue
        meta = metadata if isinstance(metadata, dict) else json.loads(metadata or "{}")
        corpus.append((str(doc_id), int(chunk_index), text, meta))

    if not corpus:
        return []

    stats = build_stats([text for _doc_id, _idx, text, _meta in corpus], query_terms, k1=k1, b=b)
    ranked: list[tuple[float, tuple[str, int, str, dict[str, Any]]]] = []
    for row in corpus:
        score = score_text(row[2], query_terms, stats)
        if score > 0:
            ranked.append((score, row))
    ranked.sort(key=lambda item: (-item[0], item[1][1]))

    hits: list[ChunkHit] = []
    for score, (doc_id, chunk_index, text, meta) in ranked[:top_k]:
        hits.append(
            ChunkHit(
                doc_id=doc_id,
                chunk_index=chunk_index,
                content=text,
                metadata=meta,
                score=round(float(score), 6),
                keyword_score=round(float(score), 6),
            )
        )
    return hits
