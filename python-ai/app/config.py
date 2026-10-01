# python-ai/app/config.py
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    deepseek_api_key: str | None = None
    qwen_api_key: str | None = None
    default_model: str = "deepseek-flash"
    deepseek_base_url: str = "https://api.deepseek.com"
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    deepseek_model_ids: str = "deepseek-flash,deepseek-v4-pro"
    qwen_model_ids: str = "qwen3.8-max,qwen3.8-flash,qwen3.7-plus"
    database_url: str = "postgresql://regops:regops123@localhost:5432/regops_db"
    llm_timeout_seconds: float = 120.0
    llm_max_output_tokens: int = Field(default=1400, ge=64, le=32768)
    startup_warmup_enabled: bool = True
    labeling_data_dir: str = str(ROOT_DIR / "data" / "labeling")
    object_store_root: str = str(ROOT_DIR / "data" / "objects")
    object_store_bucket: str = "regops-docs"
    api_public_base_url: str = "http://localhost:8000"
    object_store_presign_secret: str = "dev-presign-secret-change-me"
    object_store_presign_ttl_seconds: int = 300
    document_parser_backend: Literal["docling", "mineru"] = "docling"
    mineru_tier: Literal["flash", "basic", "standard", "advanced"] = "standard"
    mineru_ocr_mode: Literal["auto", "txt", "ocr"] = "auto"
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024
    embedding_batch_size: int = 16
    embedding_device: str = "auto"
    rag_min_score: float = 0.42
    rag_top_k: int = 12
    rag_vector_fetch_k: int = 80
    rag_keyword_top_k: int = 30
    rag_bm25_k1: float = 1.2
    rag_bm25_b: float = 0.75
    rag_rrf_k: int = 60
    rag_vector_rrf_weight: float = 2.0
    rag_keyword_rrf_weight: float = 1.0
    # 列举句式（「哪些 / 列举 / 分别是」）时用的关键词权重；<=0 表示不区分。
    # 默认关闭：product_enum 实测 nDCG 0.3295→0.2948、引用 17.0%→12.9%，是负收益。
    rag_enum_keyword_rrf_weight: float = 0.0
    # chunk 的 section_title 命中查询词时提前的名次；0 = 关闭
    rag_section_title_boost: int = 3
    rag_rerank_enabled: bool = True
    rag_rerank_backend: Literal["bge", "llm"] = "bge"
    rag_rerank_model: str = "BAAI/bge-reranker-v2-m3"
    rag_rerank_candidates: int = 12
    rag_llm_rerank_deployment: Literal["api", "local"] = "local"
    rag_llm_rerank_model: str | None = None
    rag_llm_rerank_base_url: str | None = None
    rag_llm_rerank_api_key: str | None = None
    rag_llm_rerank_candidates: int = 12
    rag_llm_rerank_max_chars: int = 800
    rag_llm_rerank_max_output_tokens: int = Field(default=800, ge=64, le=4096)
    # 同页最多留几条；0 = 不截断。2 是召回与同页细节的折中（见 docs/eval_rag_ablation.md §6.2）
    rag_max_chunks_per_page: int = 2
    # 多公司比较已按公司和年份缩小文档范围，无需沿用普通 RAG 的 80 条候选。
    rag_compare_rerank_candidates: int = 12
    rag_compare_top_k_per_company: int = 6
    rag_compare_min_hits_per_company: int = 1
    rag_trace_enabled: bool = True
    eval_chat_base_url: str = "http://127.0.0.1:8000"
    service_token: str = Field(
        default="",
        validation_alias=AliasChoices("REGOPS_SERVICE_TOKEN", "SERVICE_TOKEN"),
    )
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

    model_config = SettingsConfigDict(
        # 本地：有 .env 就读文件
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        # 环境变量优先于 .env（Docker 注入会走这里）
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
