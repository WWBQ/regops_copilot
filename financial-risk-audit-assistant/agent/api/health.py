from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from agent.core import settings
from agent.env_utils import get_env

health_router = APIRouter()


@health_router.get("/health")
def health() -> dict[str, Any]:
    """后端健康检查。

    这个接口用于确认 FastAPI/Uvicorn 服务是否正常运行，
    同时展示当前实现最关键的运行目录和持久化类型。
    注意这里只返回密钥是否存在，不返回真实 API Key 或 Token。
    """

    return {
        "ok": True,
        "project_root": str(settings.PROJECT_ROOT),
        "workspace_root": str(settings.WORKSPACE_ROOT),
        "checkpoint_db": "postgresql",
        "store_db": "postgresql (agent schema)",
        "log_dir": str(settings.LOG_DIR),
        "backend_log": str(settings.backend_log_path()),
        "agent_log": str(settings.agent_log_path()),
        "has_deepseek_key": bool(get_env("DEEPSEEK_API_KEY")),
        "deepseek_base_url": get_env("DEEPSEEK_BASE_URL"),
        "main_model": get_env("MAIN_MODEL", "deepseek-v4-pro"),
        "has_gitee_token": bool(get_env("GITEE_TOKEN")),
    }
