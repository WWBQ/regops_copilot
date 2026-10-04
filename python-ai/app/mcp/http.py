"""仅允许内部服务令牌访问金融 MCP HTTP 端点。"""

from __future__ import annotations

import secrets

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import get_settings


class MCPServiceTokenGuard:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        expected = get_settings().service_token.strip()
        supplied = dict(scope.get("headers", [])).get(b"x-regops-service-token", b"").decode("utf-8", "ignore")
        if not expected:
            response = JSONResponse({"detail": "service authentication is not configured"}, status_code=503)
        elif not supplied or not secrets.compare_digest(supplied, expected):
            response = JSONResponse({"detail": "invalid service credentials"}, status_code=401)
        else:
            await self.app(scope, receive, send)
            return
        await response(scope, receive, send)
