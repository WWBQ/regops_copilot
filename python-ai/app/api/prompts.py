"""运维：Prompt 模板列表与回滚钉扎。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.prompts.library import PromptLibraryError, changelog, list_templates, rollback

router = APIRouter(prefix="/ops/prompts", tags=["ops-prompts"])


class RollbackRequest(BaseModel):
    version: str = Field(..., min_length=5, max_length=16, description="要回滚到的 x.y.z")


@router.get("")
def list_prompt_templates() -> dict[str, Any]:
    return {"items": list_templates()}


@router.get("/{name}")
def get_prompt_template(name: str) -> dict[str, Any]:
    try:
        items = [row for row in list_templates() if row["id"] == name]
        if not items:
            raise PromptLibraryError(f"未知 Prompt 模板: {name}")
        row = dict(items[0])
        row["changelog"] = changelog(name)
        return row
    except PromptLibraryError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{name}/rollback")
def rollback_prompt(name: str, body: RollbackRequest) -> dict[str, Any]:
    try:
        rollback(name, body.version)
        items = [row for row in list_templates() if row["id"] == name]
        return {"ok": True, "item": items[0] if items else None}
    except PromptLibraryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
