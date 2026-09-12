"""检索消融档位：只改变融合路径，不改 embedding / top_k / 页多样性。"""

from __future__ import annotations

from typing import Literal

RetrievalMode = Literal["baseline", "hybrid", "rerank"]

ABLATION_MODES: tuple[RetrievalMode, ...] = ("baseline", "hybrid", "rerank")

MODE_DESCRIPTIONS: dict[RetrievalMode, str] = {
    "baseline": "向量检索 only：无关键词、无 RRF、无 Cross-Encoder",
    "hybrid": "向量 + BM25 + RRF，关闭 Cross-Encoder",
    "rerank": "hybrid 候选 + bge-reranker-v2-m3，当前生产路径",
}


def parse_retrieval_mode(value: str | None) -> RetrievalMode | None:
    if value is None:
        return None
    text = value.strip().lower()
    if not text or text in {"production", "default"}:
        return None
    if text not in ABLATION_MODES:
        raise ValueError(f"unknown retrieval mode: {value!r}（允许 baseline / hybrid / rerank）")
    return text  # type: ignore[return-value]


def resolve_retrieval_flags(
    mode: RetrievalMode | None,
    *,
    rerank_enabled: bool,
) -> tuple[bool, bool]:
    """返回 (use_keyword, use_rerank)。mode=None 表示生产配置。"""
    if mode is None:
        return True, bool(rerank_enabled)
    if mode == "baseline":
        return False, False
    if mode == "hybrid":
        return True, False
    if mode == "rerank":
        return True, True
    raise ValueError(f"unknown retrieval mode: {mode!r}")
