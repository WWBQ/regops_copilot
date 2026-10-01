"""校验 Java BFF 调用 Python AI 服务时携带的服务令牌。"""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from app.config import Settings
from app.core.dependencies import get_settings_dep


def require_service_token(
    settings: Annotated[Settings, Depends(get_settings_dep)],
    token: Annotated[
        str | None,
        Header(alias="X-Regops-Service-Token"),
    ] = None,
) -> None:
    """只允许持有共享服务令牌的上游访问受保护 API。"""
    expected = settings.service_token.strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="service authentication is not configured",
        )
    if token is None or not secrets.compare_digest(token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid service credentials",
        )
