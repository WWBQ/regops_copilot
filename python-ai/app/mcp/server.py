"""MCP Server：发现并调用 app.tools，不另写一套检索。"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import ValidationError

from app.mcp.protocol import (
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    PROTOCOL_VERSION,
    SERVER_NAME,
    SERVER_VERSION,
    JsonRpcError,
    JsonRpcRequest,
    JsonRpcResponse,
)
from app.schemas.tools import ToolContext
from app.tools.registry import invoke_tool, mcp_tool_schemas

logger = logging.getLogger(__name__)


def _error(rpc_id: int | str | None, code: int, message: str, data: Any | None = None) -> JsonRpcResponse:
    return JsonRpcResponse(id=rpc_id, error=JsonRpcError(code=code, message=message, data=data))


def _ok(rpc_id: int | str | None, result: Any) -> JsonRpcResponse:
    return JsonRpcResponse(id=rpc_id, result=result)


def _context_from_meta(params: dict[str, Any], request_id: str | None) -> ToolContext:
    meta = params.get("_meta") if isinstance(params.get("_meta"), dict) else {}
    raw = {
        "dept": meta.get("dept"),
        "actor": meta.get("actor"),
        "idempotency_key": meta.get("idempotency_key"),
        "inject": meta.get("inject"),
        "backend": meta.get("backend"),
        "request_id": request_id or meta.get("request_id"),
    }
    try:
        return ToolContext.model_validate(raw)
    except ValidationError:
        return ToolContext(request_id=request_id)


def handle_mcp(
    payload: Any,
    *,
    request_id: str | None = None,
    dept: str | None = None,
    idempotency_key: str | None = None,
    backend: str | None = None,
) -> JsonRpcResponse | None:
    """处理一条 JSON-RPC。notification（无 id）返回 None。"""
    if not isinstance(payload, dict):
        return _error(None, INVALID_REQUEST, "请求必须是 JSON 对象")
    try:
        req = JsonRpcRequest.model_validate(payload)
    except ValidationError:
        if payload.get("jsonrpc") != "2.0":
            return _error(payload.get("id"), INVALID_REQUEST, "jsonrpc 必须是 2.0")
        return _error(payload.get("id"), INVALID_REQUEST, "非法 JSON-RPC 请求")

    is_notification = req.id is None and req.method.startswith("notifications/")
    params = req.params if isinstance(req.params, dict) else {}

    logger.info(
        "mcp method=%s id=%s request_id=%s",
        req.method,
        req.id,
        request_id,
    )

    if req.method == "notifications/initialized":
        return None if is_notification else _ok(req.id, {})

    if req.method == "initialize":
        return _ok(
            req.id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        )

    if req.method == "ping":
        return _ok(req.id, {})

    if req.method == "tools/list":
        return _ok(req.id, {"tools": mcp_tool_schemas()})

    if req.method == "tools/call":
        name = params.get("name")
        if not isinstance(name, str) or not name:
            return _error(req.id, INVALID_PARAMS, "tools/call 需要 name")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            return _error(req.id, INVALID_PARAMS, "arguments 必须是对象")
        ctx = _context_from_meta(params, request_id)
        if dept and not ctx.dept:
            ctx = ctx.model_copy(update={"dept": dept})
        if idempotency_key and not ctx.idempotency_key:
            ctx = ctx.model_copy(update={"idempotency_key": idempotency_key})
        if backend and not ctx.backend:
            ctx = ctx.model_copy(update={"backend": backend})
        invoked = invoke_tool(name, arguments, context=ctx)
        text = json.dumps(invoked.model_dump(), ensure_ascii=False)
        return _ok(
            req.id,
            {
                "content": [{"type": "text", "text": text}],
                "isError": not invoked.ok,
                "structuredContent": invoked.model_dump(),
            },
        )

    if is_notification:
        return None
    return _error(req.id, METHOD_NOT_FOUND, f"未实现方法：{req.method}")


def parse_and_handle(
    raw: str | bytes,
    *,
    request_id: str | None = None,
    dept: str | None = None,
    idempotency_key: str | None = None,
    backend: str | None = None,
) -> JsonRpcResponse:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return _error(None, PARSE_ERROR, "JSON 解析失败")
    handled = handle_mcp(
        payload,
        request_id=request_id,
        dept=dept,
        idempotency_key=idempotency_key,
        backend=backend,
    )
    if handled is None:
        return _ok(None, {"ok": True})
    return handled
