from __future__ import annotations

import logging

from agent.core.settings import PROJECT_ROOT

logger = logging.getLogger("agent.workspace_context")

WORKSPACE_CONTEXT_PATH = PROJECT_ROOT / "agent" / "prompts" / "workspace_context.md"


def load_workspace_context() -> str:
    """读取编程模式使用的静态工作区说明，不读取会话记忆。

    这份记忆只描述 `AI_WORKSPACE_ROOT` 下各个固定目录的客观用途，例如
    `projects/` 是仓库目录、`runtimes/` 是运行环境目录、`.secrets/` 是敏感目录。

    它不负责表达强制行为规则。文件读写边界、命令执行方式、是否允许修改代码等约束
    仍然放在系统提示词和后端权限控制中，避免同一条规则在多个地方重复维护。
    """

    try:
        return WORKSPACE_CONTEXT_PATH.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        logger.warning("工作区说明文件不存在：%s", WORKSPACE_CONTEXT_PATH)
        return ""
