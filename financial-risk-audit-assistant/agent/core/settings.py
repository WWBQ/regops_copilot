from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from agent.env_utils import get_env

# 项目根目录固定为当前项目目录。Windows 开发环境通常是
# 本地项目目录，Linux/Docker 部署时可使用 /opt/financial-risk-audit-assistant/app。
# 后续所有本项目自己的数据文件、日志文件都默认放在这个目录下面，
# 避免 LangGraph dev 或第三方工具把文件散落到隐藏目录中。
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Agent 与 RegOps 共用 PostgreSQL 实例。Compose 中单独覆盖为 db 主机名。
# 旧 SQLite 路径仅供一次性迁移脚本读取，不再作为运行时写入目标。
AGENT_DATABASE_URL = get_env(
    "AGENT_DATABASE_URL",
    get_env("DATABASE_URL", "postgresql://regops:regops123@localhost:5432/regops_db"),
)

# SQLite 数据目录：默认使用项目内 data/。
# 用户仍然可以通过 .env 覆盖，但默认推荐显式落在项目目录中，
# 方便直接打开 SQLite 文件观察 checkpoint 和业务 Store 的区别。
DATA_DIR = Path(get_env("FIN_RISK_AUDIT_DATA_DIR", get_env("AI_CODING_DATA_DIR", str(PROJECT_ROOT / "data")))).resolve()
CHECKPOINT_DB_PATH = Path(
    get_env("CHECKPOINT_DB_PATH", str(DATA_DIR / "checkpoints.sqlite"))
).resolve()
STORE_DB_PATH = Path(get_env("STORE_DB_PATH", str(DATA_DIR / "store.sqlite"))).resolve()
LANGGRAPH_STORE_DB_PATH = Path(
    get_env("LANGGRAPH_STORE_DB_PATH", str(DATA_DIR / "langgraph_store.sqlite"))
).resolve()

# 日志目录：所有后端日志和 Agent 运行日志都写入项目内 logs/。
# 这样既能在控制台实时看，也能在课后通过日志文件复盘 Agent 做了什么。
LOG_DIR = Path(get_env("FIN_RISK_AUDIT_LOG_DIR", get_env("AI_CODING_LOG_DIR", str(PROJECT_ROOT / "logs")))).resolve()
LOG_LEVEL = get_env("FIN_RISK_AUDIT_LOG_LEVEL", get_env("AI_CODING_LOG_LEVEL", "INFO")).upper()
LOG_ROTATION_WHEN = get_env("FIN_RISK_AUDIT_LOG_WHEN", get_env("AI_CODING_LOG_WHEN", "midnight"))
LOG_ROTATION_INTERVAL = int(get_env("FIN_RISK_AUDIT_LOG_INTERVAL", get_env("AI_CODING_LOG_INTERVAL", "1")))
LOG_RETENTION_DAYS = int(get_env("FIN_RISK_AUDIT_LOG_RETENTION_DAYS", get_env("AI_CODING_LOG_RETENTION_DAYS", "14")))


def log_date_text(target_date: date | None = None) -> str:
    """返回历史日志文件使用的日期文本。

    TimedRotatingFileHandler 当前写入固定文件名，例如 backend.log；
    历史文件默认追加 YYYY-MM-DD 后缀，例如 backend.log.2026-07-10。
    这个函数保留给日志 API 读取历史日期时使用。
    """

    return (target_date or date.today()).isoformat()


def backend_log_path(target_date: date | None = None) -> Path:
    """返回后端日志路径。

    不传日期时返回当前正在写入的固定文件名；传日期时返回标准轮转后的
    历史文件名。
    """

    if target_date is None:
        return LOG_DIR / "backend.log"
    return LOG_DIR / f"backend.log.{log_date_text(target_date)}"


def agent_log_path(target_date: date | None = None) -> Path:
    """返回 Agent 运行日志路径。"""

    if target_date is None:
        return LOG_DIR / "agent-runs.log"
    return LOG_DIR / f"agent-runs.log.{log_date_text(target_date)}"


BACKEND_LOG_PATH = backend_log_path()
AGENT_LOG_PATH = agent_log_path()

def _default_workspace_root() -> str:
    """返回跨平台默认 Agent 工作区。

    生产部署应优先通过 AI_WORKSPACE_ROOT 显式配置，例如：
    - Linux/Docker: /opt/financial-risk-audit-assistant/workspace
    - Windows: E:\ai_workspace

    默认值只用于本地开发兜底，避免代码里写死某一个操作系统路径。
    """

    if os.name == "nt":
        return r"E:\ai_workspace"
    return str(PROJECT_ROOT / "workspace")


# Agent 操作真实代码仓库时使用的工作区。它和项目源码目录分离，
# 避免 Agent 在执行用户任务时误改本项目自身。
WORKSPACE_ROOT = Path(get_env("AI_WORKSPACE_ROOT", _default_workspace_root())).expanduser().resolve()
PROJECTS_DIR = WORKSPACE_ROOT / "projects"

# DeepAgents skills 目录。当前实现统一放在 WORKSPACE_ROOT/skills，
# 这样可以通过 DeepAgents 原生 backend route 暴露为 `/skills/`。
SKILLS_DIR = WORKSPACE_ROOT / "skills"
