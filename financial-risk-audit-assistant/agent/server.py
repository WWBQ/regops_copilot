"""Agent factory dispatch. Financial and AI Coding graphs live in separate modules."""

from __future__ import annotations

from deepagents import create_deep_agent
from langgraph.graph.state import RunnableConfig

from agent.coding.factory import (
    DEFAULT_RECURSION_LIMIT,
    _task_kind_from_config,
    create_repo_backend,
    ensure_backend_for_thread,
    get_coding_agent,
    graph_loaded_for_execution,
)
from agent.financial.factory import get_financial_agent


def get_agent(config: RunnableConfig):
    config = dict(config or {})
    configurable = dict(config.get("configurable") or {})
    config["configurable"] = configurable
    config["recursion_limit"] = config.get("recursion_limit", DEFAULT_RECURSION_LIMIT)
    thread_id = configurable.get("thread_id")
    if not isinstance(thread_id, str) or not thread_id or not graph_loaded_for_execution(config):
        return create_deep_agent(system_prompt="", tools=[]).with_config(config)
    if _task_kind_from_config(configurable) == "financial_audit":
        return get_financial_agent(config)
    return get_coding_agent(config)
