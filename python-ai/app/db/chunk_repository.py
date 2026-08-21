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
    max_term_doc_frequency: int = 40,
) -> list[ChunkHit]:
    """关键词补检：ILIKE + 词频过滤（泛词降权），近似 BM25 的 IDF 效果。"""
    from app.rag.retrieval import is_low_value_chunk

    if not doc_ids or not terms:
        return []

    patterns = [f"%{term}%" for term in terms if term.strip()]
    if not patterns:
        return []

    specific_patterns = _filter_specific_patterns(
        conn,
        doc_ids,
        patterns,
        source_type=source_type,
        max_doc_frequency=max_term_doc_frequency,
    )
    if not specific_patterns:
        specific_patterns = patterns[:3]

    score_expr = " + ".join(
        f"CASE WHEN content ILIKE %s THEN {max(3 - idx, 1)} ELSE 0 END"
        for idx, _ in enumerate(specific_patterns)
    )
    where_clause = " OR ".join("content ILIKE %s" for _ in specific_patterns)
    params: list[Any] = [
        *specific_patterns,
        source_type,
        doc_ids,
        *specific_patterns,
        top_k,
    ]

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT doc_id, chunk_index, content, metadata,
                   ({score_expr})::float / {len(specific_patterns)} AS score
            FROM doc_chunks
            WHERE source_type = %s
              AND doc_id = ANY(%s)
              AND embedding IS NOT NULL
              AND ({where_clause})
            ORDER BY score DESC, chunk_index
            LIMIT %s
            """,
            params,
        )
        rows = cur.fetchall()

    hits: list[ChunkHit] = []
    for doc_id, chunk_index, content, metadata, score in rows:
        if is_low_value_chunk(content):
            continue
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


def _filter_specific_patterns(
    conn: psycopg.Connection,
    doc_ids: list[str],
    patterns: list[str],
    *,
    source_type: str,
    max_doc_frequency: int,
) -> list[str]:
    """去掉在语料中出现过多的泛词（通用 IDF 思想，非行业词表）。"""
    specific: list[str] = []
    with conn.cursor() as cur:
        for pattern in patterns:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM doc_chunks
                WHERE source_type = %s
                  AND doc_id = ANY(%s)
                  AND content ILIKE %s
                """,
                (source_type, doc_ids, pattern),
            )
            count = int(cur.fetchone()[0])
            if count <= max_doc_frequency:
                specific.append(pattern)
    return specific
