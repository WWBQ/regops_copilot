"""Read-only financial Agent graph; no filesystem or Git tools are installed."""

from __future__ import annotations

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware, ToolCallLimitMiddleware
from langgraph.graph.state import RunnableConfig

from agent.core.checkpoint_history import _delta_messages_from_checkpoint
from agent.core.graph import get_checkpointer
from agent.core.middleware.run_limits import AgentRunLimits
from agent.core.model import make_main_model
from agent.financial.citations import ToolCitationIndexer, max_citation_id_from_messages
from agent.mcp.financial_client import load_financial_tools
from agent.prompt import get_system_prompt
from agent.tools.external_risk_search import create_external_risk_search_tool


def get_financial_agent(config: RunnableConfig):
    configurable = config.get("configurable") or {}
    thread_id = configurable["thread_id"]
    citation_indexer = ToolCitationIndexer(
        start_after=max_citation_id_from_messages(_delta_messages_from_checkpoint(thread_id))
    )
    tools = [
        *load_financial_tools(citation_indexer),
        create_external_risk_search_tool(citation_indexer),
    ]
    limits = AgentRunLimits.from_env("financial_audit")
    financial_config = {**config, "recursion_limit": 30}
    return create_agent(
        model=make_main_model(configurable.get("model_id")),
        tools=tools,
        system_prompt=get_system_prompt("financial_audit"),
        checkpointer=get_checkpointer(),
        middleware=[
            ModelCallLimitMiddleware(run_limit=8, exit_behavior="end"),
            ToolCallLimitMiddleware(run_limit=limits.max_tool_calls, exit_behavior="end"),
        ],
    ).with_config(financial_config)
