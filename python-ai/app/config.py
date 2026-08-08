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


if __name__ == "__main__":
    s = get_settings()
    print("ROOT:", ROOT_DIR)
    print(".env:", (ROOT_DIR / ".env").exists())
    print("deepseek ok:", bool(s.deepseek_api_key))