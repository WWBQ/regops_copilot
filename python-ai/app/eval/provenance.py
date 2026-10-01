"""评测报告溯源：便于日后对比不同代码/配置下的评测结果。"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any

from app.config import get_settings


def _git_field(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        if result.returncode != 0:
            return None
        value = (result.stdout or "").strip()
        return value or None
    except Exception:
        return None


def file_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def rag_config_snapshot() -> dict[str, Any]:
    settings = get_settings()
    return {
        "rag_top_k": settings.rag_top_k,
        "rag_min_score": settings.rag_min_score,
        "rag_vector_fetch_k": settings.rag_vector_fetch_k,
        "rag_keyword_top_k": settings.rag_keyword_top_k,
        "rag_bm25_k1": settings.rag_bm25_k1,
        "rag_bm25_b": settings.rag_bm25_b,
        "rag_rrf_k": settings.rag_rrf_k,
        "rag_vector_rrf_weight": settings.rag_vector_rrf_weight,
        "rag_keyword_rrf_weight": settings.rag_keyword_rrf_weight,
        "rag_rerank_enabled": settings.rag_rerank_enabled,
        "rag_rerank_backend": settings.rag_rerank_backend,
        "rag_rerank_model": settings.rag_rerank_model,
        "rag_rerank_candidates": settings.rag_rerank_candidates,
        "rag_llm_rerank_deployment": settings.rag_llm_rerank_deployment,
        "rag_llm_rerank_model": settings.rag_llm_rerank_model,
        "rag_llm_rerank_base_url": settings.rag_llm_rerank_base_url,
        "rag_llm_rerank_candidates": settings.rag_llm_rerank_candidates,
        "rag_llm_rerank_max_chars": settings.rag_llm_rerank_max_chars,
        "rag_max_chunks_per_page": settings.rag_max_chunks_per_page,
        "embedding_model": settings.embedding_model,
    }


def build_provenance(
    *,
    golden_path: Path,
    label: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    provenance: dict[str, Any] = {
        "label": (label or "").strip() or None,
        "git": {
            "commit": _git_field("rev-parse", "HEAD"),
            "branch": _git_field("rev-parse", "--abbrev-ref", "HEAD"),
            "describe": _git_field("describe", "--tags", "--always", "--dirty"),
            "dirty": bool(_git_field("status", "--porcelain")),
        },
        "golden": {
            "file": golden_path.name,
            "path": str(golden_path.resolve()),
            "sha256": file_sha256(golden_path),
        },
        "rag_config": rag_config_snapshot(),
    }
    if extra:
        provenance.update(extra)
    return provenance
