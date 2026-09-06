"""MCP 最小子集：JSON-RPC 2.0 + initialize / tools/list / tools/call。

这是协议层，不是 Agent。模型选工具仍是 Function Calling；本模块只负责发现与调用。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "regops-tools"
SERVER_VERSION = "0.5.3"

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


class JsonRpcError(BaseModel):
    code: int
    message: str
    data: Any | None = None


class JsonRpcRequest(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: int | str | None = None
    method: str
    params: dict[str, Any] | list[Any] | None = None


class JsonRpcResponse(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: int | str | None = None
    result: Any | None = None
    error: JsonRpcError | None = None
