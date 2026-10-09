"""Read-only financial risk Agent boundary."""

from __future__ import annotations

from typing import Any

from agent.core.runtime import RuntimeEventSink, run_agent_task
from agent.mcp.financial_client import load_financial_tools


def require_financial_tools() -> None:
    load_financial_tools()


def run_risk_task(
    *, prompt: str, thread_id: str, model_id: str,
    event_sink: RuntimeEventSink,
) -> dict[str, Any]:
    return run_agent_task(
        repo_url=None, prompt=prompt, thread_id=thread_id,
        forced_financial_audit=True, model_id=model_id, event_sink=event_sink,
    )
