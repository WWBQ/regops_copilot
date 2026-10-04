from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.backends.local_shell import LocalShellBackend
from agent.core.workspace_context import load_workspace_context
from agent.core.settings import WORKSPACE_ROOT
from agent.prompt import get_system_prompt


def main() -> None:
    """验证静态工作区说明与 DeepAgents 原生 backend 目录保持一致。"""

    memory = load_workspace_context()
    required_terms = ["projects/", "runtimes/", "policies/", "reviews/", ".secrets"]
    for term in required_terms:
        if term not in memory:
            raise AssertionError(f"工作区说明缺少目录说明: {term}")

    prompt = get_system_prompt("coding")
    for term in ["工作区说明", "共享运行环境目录", "敏感凭据辅助目录", "/projects"]:
        if term not in prompt:
            raise AssertionError(f"系统提示词未注入工作区说明: {term}")

    backend = LocalShellBackend(WORKSPACE_ROOT)
    # LocalShellBackend 用相对路径 "." 表示受控工作区根目录；"/" 是宿主机根目录，必须拒绝。
    root_listing = backend.ls(".")
    if root_listing.error:
        raise AssertionError(f"工作区根目录应可列出，实际: {root_listing}")
    paths = {entry["path"].strip("/") for entry in root_listing.entries or []}
    for key in ["projects", "runtimes", "policies", "reviews", "logs", "tmp", "skills"]:
        if key not in paths:
            raise AssertionError(f"DeepAgents backend 根目录缺少: {key}")

    print("workspace context verification passed")


if __name__ == "__main__":
    main()
