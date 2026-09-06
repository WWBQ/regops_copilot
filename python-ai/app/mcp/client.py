"""MCP Client：对 /mcp 做 initialize → tools/list → tools/call。"""

from __future__ import annotations

from typing import Any

import httpx

from app.mcp.protocol import PROTOCOL_VERSION
from app.schemas.tools import ToolInvokeResponse


class McpClientError(RuntimeError):
    def __init__(self, message: str, *, code: int | None = None, data: Any = None):
        super().__init__(message)
        self.code = code
        self.data = data


class McpHttpClient:
    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        path: str = "/mcp",
        request_id: str | None = None,
        dept: str | None = None,
        backend: str | None = None,
    ) -> None:
        self._http = http
        self._path = path
        self._request_id = request_id
        self._dept = dept
        self._backend = backend
        self._next_id = 1
        self.initialized = False
        self.server_info: dict[str, Any] = {}

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._request_id:
            headers["X-Request-ID"] = self._request_id
        if self._dept:
            headers["X-Regops-Dept"] = self._dept
        if self._backend:
            headers["X-Regops-Tool-Backend"] = self._backend
        return headers

    async def _rpc(self, method: str, params: dict[str, Any] | None = None) -> Any:
        rpc_id = self._next_id
        self._next_id += 1
        body: dict[str, Any] = {"jsonrpc": "2.0", "id": rpc_id, "method": method}
        if params is not None:
            body["params"] = params
        response = await self._http.post(self._path, json=body, headers=self._headers())
        payload = response.json()
        if "error" in payload and payload["error"]:
            err = payload["error"]
            raise McpClientError(err.get("message") or "mcp error", code=err.get("code"), data=err.get("data"))
        return payload.get("result")

    async def initialize(self) -> dict[str, Any]:
        result = await self._rpc(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "regops-mcp-client", "version": "0.5.3"},
            },
        )
        self.initialized = True
        self.server_info = result or {}
        await self._http.post(
            self._path,
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            headers=self._headers(),
        )
        return self.server_info

    async def list_tools(self) -> list[dict[str, Any]]:
        result = await self._rpc("tools/list")
        return list((result or {}).get("tools") or [])

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        *,
        meta: dict[str, Any] | None = None,
    ) -> ToolInvokeResponse:
        params: dict[str, Any] = {"name": name, "arguments": arguments or {}}
        extra = dict(meta or {})
        if self._dept and "dept" not in extra:
            extra["dept"] = self._dept
        if self._backend and "backend" not in extra:
            extra["backend"] = self._backend
        if self._request_id and "request_id" not in extra:
            extra["request_id"] = self._request_id
        if extra:
            params["_meta"] = extra
        result = await self._rpc("tools/call", params)
        structured = (result or {}).get("structuredContent")
        if structured:
            return ToolInvokeResponse.model_validate(structured)
        raise McpClientError("tools/call 没有 structuredContent")
