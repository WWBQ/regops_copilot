"""RAG 检索 trace：单次问答检索链路的结构化指标。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


def _hit_snapshot(
    hit: Any,
    *,
    rank: int,
    snippet_len: int = 160,
) -> dict[str, Any]:
    page = int(hit.metadata.get("page") or 0) if hit.metadata else 0
    content = hit.content or ""
    snippet = content[:snippet_len] + ("…" if len(content) > snippet_len else "")
    return {
        "rank": rank,
        "doc_id": hit.doc_id,
        "chunk_index": hit.chunk_index,
        "page": page,
        "score": round(float(hit.score), 4),
        "vector_score": round(float(hit.vector_score), 4) if hit.vector_score is not None else None,
        "keyword_score": round(float(hit.keyword_score), 4) if hit.keyword_score is not None else None,
        "snippet": snippet,
    }


@dataclass
class RagTrace:
    """一次 RAG 准备阶段的完整 trace（可持久化 / 展示）。"""

    question: str
    outcome: str  # ok | no_intent | no_docs | low_score | pending_docs
    rag_used: bool = False
    request_id: str | None = None
    session_id: str | None = None
    user_id: str | None = None
    keyword_terms: list[str] = field(default_factory=list)
    scoped_doc_ids: list[str] = field(default_factory=list)
    vector_hit_count: int = 0
    keyword_hit_count: int = 0
    final_hit_count: int = 0
    max_vector_score: float | None = None
    min_score_threshold: float | None = None
    total_rag_ms: float = 0.0
    hits: list[dict[str, Any]] = field(default_factory=list)
    pipeline: dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_hits(
        hits: list[Any],
        *,
        limit: int = 12,
    ) -> list[dict[str, Any]]:
        return [_hit_snapshot(hit, rank=i) for i, hit in enumerate(hits[:limit], start=1)]


@dataclass
class RagPrepareResult:
    """prepare_chat_rag 返回值：答案 + trace。"""

    answer: Any | None
    trace: RagTrace
