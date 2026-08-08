from app.config import ROOT_DIR, get_settings


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
