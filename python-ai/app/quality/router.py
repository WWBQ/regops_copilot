"""质量门 G1/G2/G3 与 fin_metric 浏览。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.quality.service import fetch_fin_metrics, fetch_quality_gates, ingest_f10_to_fin_metric

router = APIRouter(prefix="/ops/quality", tags=["ops-quality"])


class QualityIngestRequest(BaseModel):
    codes: list[str] | None = None
    year: int = Field(default=2024, ge=2000, le=2100)
    dry_run: bool = False


@router.get("/gates")
def quality_gates_api() -> dict[str, Any]:
    return fetch_quality_gates()


@router.get("/facts")
def quality_facts_api(
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    company_code: str | None = Query(None),
    status: str | None = Query(None),
    statement: str | None = Query(None),
    concept: str | None = Query(None),
    doc_id: str | None = Query(None),
) -> dict[str, Any]:
    return fetch_fin_metrics(
        company_code=company_code,
        status=status,
        statement=statement,
        concept=concept,
        doc_id=doc_id,
        limit=limit,
        offset=offset,
    )


@router.post("/ingest")
def quality_ingest_api(body: QualityIngestRequest) -> dict[str, Any]:
    try:
        return ingest_f10_to_fin_metric(codes=body.codes, year=body.year, dry_run=body.dry_run)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
