"""AI Coding's runtime boundary, separate from financial evidence tools."""

from __future__ import annotations

from typing import Any
import re

from agent.core.runtime import RuntimeEventSink, run_agent_task
from agent.core.settings import PROJECTS_DIR

_PROJECT_PREFIX = re.compile(r"^目标项目：/projects/([^/\n\r]+)\n用户任务：")


def selected_project(prompt: str, known_project: str | None = None) -> str | None:
    match = _PROJECT_PREFIX.match(prompt)
    if not match:
        if prompt.startswith("目标项目："):
            raise ValueError("项目路径格式无效")
        return None
    name = match.group(1)
    if name not in available_projects() and name != known_project:
        raise ValueError("所选项目不在可用项目列表中")
    return name


def available_projects() -> list[str]:
    if not PROJECTS_DIR.is_dir():
        return []
    return sorted(
        item.name for item in PROJECTS_DIR.iterdir()
        if item.is_dir() and not item.is_symlink()
        and not item.name.startswith(".") and "\n" not in item.name and "\r" not in item.name
    )


def run_coding_task(
    *, prompt: str, thread_id: str, model_id: str,
    event_sink: RuntimeEventSink,
) -> dict[str, Any]:
    return run_agent_task(
        repo_url=None, prompt=prompt, thread_id=thread_id,
        forced_financial_audit=False, allow_financial_audit=False,
        model_id=model_id, event_sink=event_sink,
    )
