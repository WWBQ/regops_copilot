"""AI Coding's runtime boundary, separate from financial evidence tools."""

from __future__ import annotations

from typing import Any

from agent.backends.open_sandbox import execution_backend
from agent.core.runtime import RuntimeEventSink, run_agent_task


def run_coding_task(
    *, prompt: str, thread_id: str, model_id: str,
    event_sink: RuntimeEventSink,
) -> dict[str, Any]:
    execution_backend()  # Fail closed before any runtime or host-workspace path.
    return run_agent_task(
        repo_url=None, prompt=prompt, thread_id=thread_id,
        forced_financial_audit=False, allow_financial_audit=False,
        model_id=model_id, event_sink=event_sink,
    )
