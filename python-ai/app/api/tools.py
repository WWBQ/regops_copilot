"""W5/W6：工具目录与受控调用。写工具只落 PENDING 草稿；RAG 不经 Java 再包一层。"""

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
        "wired_to_chat": True,
        "chat_entry": "intent",
        "wired_to_graph": True,
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


@router.get("/review-drafts")
def list_review_drafts_api(
    x_regops_dept: Annotated[str | None, Header(alias="X-Regops-Dept")] = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    from app.db.connection import get_connection
    from app.db.review_draft_repository import list_review_drafts

    if not x_regops_dept:
        raise HTTPException(status_code=400, detail="X-Regops-Dept required")
    capped = max(1, min(limit, 100))
    start = max(0, offset)
    try:
        with get_connection() as conn:
            rows, total = list_review_drafts(conn, dept=x_regops_dept, limit=capped, offset=start)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "items": [row.to_dict() for row in rows],
        "total": total,
        "limit": capped,
        "offset": start,
        "dept": x_regops_dept,
    }


@router.get("/review-drafts/{draft_id}")
def get_review_draft_api(
    draft_id: str,
    x_regops_dept: Annotated[str | None, Header(alias="X-Regops-Dept")] = None,
) -> dict[str, Any]:
    from app.db.connection import get_connection
    from app.db.review_draft_repository import get_by_public_id

    if not x_regops_dept:
        raise HTTPException(status_code=400, detail="X-Regops-Dept required")
    try:
        with get_connection() as conn:
            row = get_by_public_id(conn, draft_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if row is None or row.dept != x_regops_dept:
        raise HTTPException(status_code=404, detail="review draft not found")
    return row.to_dict()
