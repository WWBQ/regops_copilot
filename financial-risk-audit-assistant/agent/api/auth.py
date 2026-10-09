"""Only the authenticated RegOps BFF may identify a user to Agent APIs."""

import secrets
import uuid

from fastapi import HTTPException, Request

from agent.env_utils import get_env


def require_regops_user(request: Request) -> str:
    expected = get_env("REGOPS_SERVICE_TOKEN").strip()
    supplied = request.headers.get("X-Regops-Service-Token", "")
    if not expected or not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Agent service authentication required")
    try:
        return str(uuid.UUID(request.headers.get("X-Regops-User", "")))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=401, detail="RegOps user identity required") from exc
