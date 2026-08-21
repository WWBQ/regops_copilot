"""运维：评测任务与报告。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.eval import job_service
from app.eval.registry import RUNNERS, list_golden_files

router = APIRouter(prefix="/ops/eval", tags=["ops-eval"])


class StartEvalRunRequest(BaseModel):
    task_id: str = Field(..., description="评测任务 ID")
    limit: int = Field(0, ge=0, le=500, description="只跑前 N 题，0 表示全量")
    category: str = Field("", description="RAG 评测可按题型过滤")
    top_k: int = Field(0, ge=0, le=50, description="RAG top_k 覆盖，0 用黄金集默认")


class CreateEvalTaskRequest(BaseModel):
    id: str = Field(..., description="任务 ID，如 my_rag_smoke")
    name: str = Field(..., min_length=1, max_length=80)
    description: str = Field("", max_length=500)
    golden_file: str = Field(..., description="eval/golden/ 下的 JSON 文件名")
    runner: str = Field(..., description="w1_chat 或 rag_retrieval")
    metrics: list[str] | None = Field(None, description="可选，默认按 runner 推断")


@router.get("/tasks")
def list_eval_tasks() -> dict[str, Any]:
    return {"items": job_service.list_tasks()}


@router.get("/golden-sets")
def list_eval_golden_sets() -> dict[str, Any]:
    return {"items": list_golden_files(), "runners": list(RUNNERS)}


class UploadGoldenSetRequest(BaseModel):
    filename: str = Field(..., description="保存到 eval/golden/ 的文件名，如 my_rag_20.json")
    content: dict[str, Any] = Field(..., description="黄金集 JSON 内容，须含 items 数组")
    runner: str | None = Field(None, description="可选：rag_retrieval 时校验 doc_id / gold_pages")


@router.post("/golden-sets/upload")
def upload_golden_set(body: UploadGoldenSetRequest) -> dict[str, Any]:
    from app.eval.registry import save_golden_set

    try:
        if body.runner and body.runner not in RUNNERS:
            raise ValueError(f"unsupported runner: {body.runner}")
        return save_golden_set(
            filename=body.filename.strip(),
            content=body.content,
            runner=body.runner,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/tasks")
def create_eval_task(body: CreateEvalTaskRequest) -> dict[str, Any]:
    try:
        return job_service.create_task(
            task_id=body.id.strip(),
            name=body.name,
            description=body.description,
            golden_file=body.golden_file.strip(),
            runner=body.runner.strip(),
            metrics=body.metrics,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/tasks/{task_id}")
def delete_eval_task(task_id: str) -> dict[str, str]:
    try:
        job_service.delete_task(task_id)
        return {"status": "deleted", "task_id": task_id}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/runs")
def list_eval_runs(
    task_id: str | None = Query(None),
    limit: int = Query(30, ge=1, le=100),
) -> dict[str, Any]:
    items = job_service.list_runs(task_id=task_id, limit=limit)
    return {"items": items, "total": len(items)}


@router.get("/runs/{run_id}")
def get_eval_run(run_id: str, include_report: bool = Query(True)) -> dict[str, Any]:
    row = job_service.get_run(run_id, include_report=include_report)
    if row is None:
        raise HTTPException(status_code=404, detail="eval run not found")
    return row


@router.delete("/runs/{run_id}")
def delete_eval_run(run_id: str) -> dict[str, str]:
    try:
        job_service.delete_run(run_id)
        return {"status": "deleted", "run_id": run_id}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/runs")
def start_eval_run(body: StartEvalRunRequest) -> dict[str, Any]:
    try:
        return job_service.start_run(
            task_id=body.task_id,
            limit=body.limit,
            category=body.category,
            top_k=body.top_k,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
