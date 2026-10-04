"""只发现并交付两项获准的金融 MCP 工具；连接失败时明确拒绝初筛。"""

from __future__ import annotations

import asyncio
import json
import logging
from urllib.parse import urlparse

from langchain_core.tools import BaseTool, StructuredTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from agent.env_utils import get_env
from agent.financial import TOOLS_UNAVAILABLE_MESSAGE
from agent.financial.citations import ToolCitationIndexer

logger = logging.getLogger(__name__)
_ALLOWED_TOOLS = frozenset({"lookup_financial_facts", "search_report_evidence"})


def _mcp_connection() -> dict:
    token = get_env("REGOPS_SERVICE_TOKEN").strip()
    url = get_env("REGOPS_MCP_URL", "http://127.0.0.1:8000/mcp/").strip()
    parsed = urlparse(url)
    if not token or parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path.rstrip("/") != "/mcp":
        raise RuntimeError(TOOLS_UNAVAILABLE_MESSAGE)
    return {
        "transport": "streamable_http",
        "url": url,
        "headers": {"X-Regops-Service-Token": token},
        "timeout": 150,
        "sse_read_timeout": 150,
    }


async def _discover_tools() -> list[BaseTool]:
    client = MultiServerMCPClient({"financial": _mcp_connection()})
    tools = await client.get_tools()
    by_name = {tool.name: tool for tool in tools}
    if not _ALLOWED_TOOLS.issubset(by_name):
        raise RuntimeError(TOOLS_UNAVAILABLE_MESSAGE)
    # 服务端后来增加任何工具，都不会自动进入金融 Agent 的权限集合。
    return [by_name[name] for name in sorted(_ALLOWED_TOOLS)]


def _sync_tool(
    mcp_tool: BaseTool,
    citation_indexer: ToolCitationIndexer | None = None,
) -> BaseTool:
    """现有 Agent 使用同步事件流；MCP 适配器工具只提供异步调用。"""

    def invoke(**kwargs):
        blocks = asyncio.run(mcp_tool.ainvoke(kwargs))
        if (
            not isinstance(blocks, list)
            or len(blocks) != 1
            or not isinstance(blocks[0], dict)
            or blocks[0].get("type") != "text"
            or not isinstance(blocks[0].get("text"), str)
        ):
            raise RuntimeError("财务 MCP 工具返回格式不正确")
        content = blocks[0]["text"]
        try:
            parsed = json.loads(content)
        except ValueError as exc:
            raise RuntimeError("财务 MCP 工具返回格式不正确") from exc
        if not isinstance(parsed, dict) or not isinstance(parsed.get("status"), str):
            raise RuntimeError("财务 MCP 工具返回格式不正确")
        if citation_indexer is not None:
            parsed = citation_indexer.annotate(mcp_tool.name, parsed)
        return json.dumps(parsed, ensure_ascii=False)

    return StructuredTool.from_function(
        func=invoke,
        name=mcp_tool.name,
        description=mcp_tool.description,
        args_schema=mcp_tool.args_schema,
    )


def load_financial_tools(
    citation_indexer: ToolCitationIndexer | None = None,
) -> list[BaseTool]:
    """同步运行线程中发现 MCP 工具，供 Agent 构图及 API 预检复用。"""
    try:
        citation_indexer = citation_indexer or ToolCitationIndexer()
        return [
            _sync_tool(tool, citation_indexer)
            for tool in asyncio.run(asyncio.wait_for(_discover_tools(), timeout=12))
        ]
    except Exception as exc:
        # MCP/HTTP 异常可能包含 URL 或认证头，不能原样写进前端/SSE。
        logger.warning("financial MCP unavailable: %s", type(exc).__name__)
        raise RuntimeError(TOOLS_UNAVAILABLE_MESSAGE) from exc
