"""W5：工具目录与受控调用。只读，不经 Java 再包一层 RAG。"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Request

from app.config import get_settings
from app.schemas.tools import ToolContext, ToolInvokeRequest, ToolInvokeResponse
from app.security.service_identity import enforce_service_identity
from app.tools.capabilities import tool_capabilities, tool_schema
from app.tools.registry import invoke_tool, openai_tool_schemas

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("")
def list_tools_api() -> dict[str, Any]:
    return {
        "transport": "function_calling",
        "backend": get_settings().tool_backend,
        "mcp": {
            "endpoint": "/mcp",
            "methods": ["initialize", "tools/list", "tools/call"],
            "protocol": "jsonrpc-2.0",
        },
        "wired_to_chat": False,
        "introspection": {
            "capabilities": "/tools/capabilities",
            "schema": "/tools/schema/{name}",
        },
        "tools": [item["function"] for item in openai_tool_schemas()],
    }


@router.get("/capabilities")
def tools_capabilities_api() -> dict[str, Any]:
    return tool_capabilities()


@router.get("/schema/{name}")
def tool_schema_api(name: str) -> dict[str, Any]:
    schema = tool_schema(name)
    if schema is None:
        raise HTTPException(status_code=404, detail=f"unknown tool: {name}")
    return schema


@router.post("/invoke", response_model=ToolInvokeResponse)
def invoke_tool_api(
    request: Request,
    body: ToolInvokeRequest,
    x_request_id: Annotated[str | None, Header(alias="X-Request-ID")] = None,
    x_regops_dept: Annotated[str | None, Header(alias="X-Regops-Dept")] = None,
) -> ToolInvokeResponse:
    enforce_service_identity(request)
    context = ToolContext(
        dept=body.dept or x_regops_dept,
        actor=body.actor,
        idempotency_key=body.idempotency_key,
        inject=body.inject,
        backend=body.backend,
        request_id=x_request_id,
    )
    return invoke_tool(body.name, body.arguments, context=context)
