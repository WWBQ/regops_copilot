"""POST /mcp ：JSON-RPC（initialize / tools/list / tools/call）。"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

from app.mcp.server import parse_and_handle
from app.security.service_identity import enforce_service_identity

router = APIRouter(tags=["mcp"])


@router.post("/mcp")
async def mcp_endpoint(
    request: Request,
    x_request_id: Annotated[str | None, Header(alias="X-Request-ID")] = None,
    x_regops_dept: Annotated[str | None, Header(alias="X-Regops-Dept")] = None,
    x_idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
    x_regops_tool_backend: Annotated[str | None, Header(alias="X-Regops-Tool-Backend")] = None,
) -> JSONResponse:
    enforce_service_identity(request)
    raw = await request.body()
    handled = parse_and_handle(
        raw,
        request_id=x_request_id,
        dept=x_regops_dept,
        idempotency_key=x_idempotency_key,
        backend=x_regops_tool_backend,
    )
    payload: dict[str, Any] = {"jsonrpc": handled.jsonrpc, "id": handled.id}
    if handled.error is not None:
        payload["error"] = handled.error.model_dump()
    else:
        payload["result"] = handled.result
    return JSONResponse(payload)
