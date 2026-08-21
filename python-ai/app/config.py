# python-ai/app/config.py
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    deepseek_api_key: str | None = None
    qwen_api_key: str | None = None
    default_model: str = "deepseek"
    database_url: str = "postgresql://regops:regops123@localhost:5432/regops_db"
    llm_timeout_seconds: float = 120.0
    labeling_data_dir: str = str(ROOT_DIR / "data" / "labeling")
    object_store_root: str = str(ROOT_DIR / "data" / "objects")
    object_store_bucket: str = "regops-docs"
    api_public_base_url: str = "http://localhost:8000"
    object_store_presign_secret: str = "dev-presign-secret-change-me"
    object_store_presign_ttl_seconds: int = 300
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024
    embedding_batch_size: int = 16
    embedding_device: str = "auto"
    rag_min_score: float = 0.42
    rag_top_k: int = 12
    rag_vector_fetch_k: int = 80
    rag_keyword_top_k: int = 30
    rag_rrf_k: int = 60
    rag_vector_rrf_weight: float = 2.0
    rag_keyword_rrf_weight: float = 1.0
    rag_rerank_enabled: bool = True
    rag_rerank_model: str = "BAAI/bge-reranker-v2-m3"
    rag_rerank_candidates: int = 80
    rag_max_chunks_per_page: int = 1
    rag_trace_enabled: bool = True
    eval_chat_base_url: str = "http://127.0.0.1:8000"

    model_config = SettingsConfigDict(
        # 本地：有 .env 就读文件
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        # 环境变量优先于 .env（Docker 注入会走这里）
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
