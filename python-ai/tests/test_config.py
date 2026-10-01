from app.config import ROOT_DIR, Settings, get_settings


def test_root_dir_points_to_monorepo_root():
    assert ROOT_DIR.name == "regops_copilot"
    assert (ROOT_DIR / "compose.yaml").exists()


def test_env_file_exists():
    assert (ROOT_DIR / ".env").exists()


def test_settings_loads_database_url():
    s = get_settings()
    assert s.database_url.startswith("postgresql://")


def test_at_least_one_llm_key_when_env_configured():
    s = get_settings()
    assert s.deepseek_api_key or s.qwen_api_key


def test_rag_and_latency_defaults_are_consistent():
    settings = Settings(_env_file=None)
    assert settings.rag_rerank_candidates == 12
    assert settings.rag_compare_rerank_candidates == 12
    assert settings.rag_compare_top_k_per_company == 6
    assert settings.llm_max_output_tokens == 1400
    assert settings.rag_llm_rerank_max_output_tokens == 800
    assert settings.startup_warmup_enabled is True


def test_service_token_accepts_java_environment_alias(monkeypatch):
    monkeypatch.setenv("REGOPS_SERVICE_TOKEN", "from-java")
    settings = Settings(_env_file=None)
    assert settings.service_token == "from-java"


def test_env_example_matches_production_candidate_defaults():
    example = (ROOT_DIR / ".env.example").read_text(encoding="utf-8")
    assert "RAG_RERANK_CANDIDATES=12" in example
    assert "RAG_COMPARE_RERANK_CANDIDATES=12" in example
    assert "RAG_COMPARE_TOP_K_PER_COMPANY=6" in example
    assert "LLM_MAX_OUTPUT_TOKENS=1400" in example
    assert "STARTUP_WARMUP_ENABLED=true" in example
