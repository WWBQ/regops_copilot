"""Java → Python 服务身份。不认用户 Authorization。"""

from __future__ import annotations

from fastapi import HTTPException, Request

from app.config import get_settings


def enforce_service_identity(request: Request) -> None:
    expected = get_settings().service_token.strip()
    if not expected:
        return
    if not request.headers.get("X-Regops-Service"):
        return
    presented = request.headers.get("X-Regops-Service-Token", "")
    if presented != expected:
        raise HTTPException(status_code=401, detail="invalid service token")
