"""启动时预热本地模型和可复用的模型客户端。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.config import Settings
from app.ingest.embeddings import get_embedding_model
from app.models.llm import warmup_llm_clients
from app.rag.reranker import get_cross_encoder

logger = logging.getLogger(__name__)


@dataclass
class WarmupResult:
    llm_clients: list[str] = field(default_factory=list)
    embedding_ready: bool = False
    reranker_ready: bool = False
    errors: list[str] = field(default_factory=list)


def warmup_models(settings: Settings) -> WarmupResult:
    """预加载会被请求复用的客户端、Embedding 与 BGE 重排器。

    任一预热失败只记录错误，不阻止服务启动；真实请求仍会按原链路重试并返回明确错误。
    """
    result = WarmupResult()
    try:
        result.llm_clients = warmup_llm_clients(settings)
    except Exception as exc:
        logger.warning("LLM client warmup failed: %s", exc)
        result.errors.append(f"llm_clients:{type(exc).__name__}")

    try:
        get_embedding_model().encode_one("金融文档检索预热")
        result.embedding_ready = True
    except Exception as exc:
        logger.warning("embedding warmup failed: %s", exc)
        result.errors.append(f"embedding:{type(exc).__name__}")

    if settings.rag_rerank_enabled and settings.rag_rerank_backend == "bge":
        try:
            get_cross_encoder(settings.rag_rerank_model)
            result.reranker_ready = True
        except Exception as exc:
            logger.warning("reranker warmup failed: %s", exc)
            result.errors.append(f"reranker:{type(exc).__name__}")
    return result
