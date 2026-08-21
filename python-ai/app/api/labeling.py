from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Annotated

import httpx
import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse

from app.api.deps import get_label_store
from app.labeling.items import ALLOWED_UPLOAD_EXTS, ALLOWED_URL_TYPES, build_template_bytes
from app.labeling.options import normalize_label_options, task_label_options
from app.labeling.pdf import download_pdf, is_http_url, pdf_filename_for
from app.labeling.store import LabelStore, LabelStoreError
from app.schemas.labeling import (
    LabelItem,
    LabelItemList,
    LabelTask,
    SaveLabelRequest,
    SaveLabelResponse,
)

router = APIRouter(prefix="/labeling", tags=["labeling"])
logger = logging.getLogger(__name__)

StoreDep = Annotated[LabelStore, Depends(get_label_store)]


def _task_or_404(store: LabelStore, task_id: str) -> dict:
    try:
        task = store.get_task(task_id)
    except LabelStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.get("/tasks", response_model=list[LabelTask])
def list_tasks(store: StoreDep) -> list[LabelTask]:
    try:
        tasks = store.list_tasks()
    except LabelStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return [LabelTask.model_validate(store.with_progress(t)) for t in tasks]


@router.get("/template")
def download_template() -> StreamingResponse:
    buf = io.BytesIO(build_template_bytes())
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="labeling_template.xlsx"'},
    )


@router.post("/tasks", response_model=LabelTask)
async def create_task(
    store: StoreDep,
    name: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    desc: Annotated[str, Form()] = "",
    url_type: Annotated[str, Form()] = "pdf",
    label_options: Annotated[str, Form()] = "",
) -> LabelTask:
    name = name.strip()
    desc = desc.strip()
    url_type = url_type.strip().lower()
    if not name:
        raise HTTPException(status_code=400, detail="任务名称不能为空")
    if url_type not in ALLOWED_URL_TYPES:
        raise HTTPException(status_code=400, detail="url 类型必须是 pdf / html / text")
    try:
        options = normalize_label_options(label_options)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    filename = file.filename or ""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXTS:
        raise HTTPException(status_code=400, detail="只接受标准模板 .xlsx，请先下载模板")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="请上传数据文件")
    try:
        task = store.create_task(
            name=name,
            desc=desc,
            url_type=url_type,
            filename=filename,
            content=content,
            label_options=options,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info("created labeling task %s count=%s", task["id"], task["count"])
    return LabelTask.model_validate(task)


@router.get("/tasks/{task_id}", response_model=LabelItemList)
def get_task(task_id: str, store: StoreDep) -> LabelItemList:
    task = _task_or_404(store, task_id)
    items = store.list_items(task)
    return LabelItemList(
        task=LabelTask.model_validate(store.with_progress(task)),
        items=[LabelItem.model_validate(item) for item in items],
    )


@router.get("/tasks/{task_id}/items/{idx}", response_model=LabelItem)
async def get_item(task_id: str, idx: int, store: StoreDep) -> LabelItem:
    task = _task_or_404(store, task_id)
    try:
        item = store.get_item(task, idx)
    except IndexError as exc:
        raise HTTPException(status_code=404, detail="Index out of range") from exc

    url_type = task.get("url_type", "pdf")
    if url_type == "pdf" and item.get("url"):
        filename = pdf_filename_for(item["url"], idx)
        dest = store.pdf_path(task_id, filename)
        if not dest.exists():
            ok, err = await download_pdf(item["url"], dest)
            if ok:
                item["pdf_filename"] = filename
            else:
                item["download_msg"] = f"下载失败: {err}"
        else:
            item["pdf_filename"] = filename
    return LabelItem.model_validate(item)


@router.post("/tasks/{task_id}/items/{idx}", response_model=SaveLabelResponse)
def save_item(
    task_id: str,
    idx: int,
    body: SaveLabelRequest,
    store: StoreDep,
) -> SaveLabelResponse:
    task = _task_or_404(store, task_id)
    try:
        store.get_item(task, idx)
    except IndexError as exc:
        raise HTTPException(status_code=404, detail="Index out of range") from exc
    status = (body.status or "").strip()
    allowed = task_label_options(task)
    if status and status not in allowed:
        raise HTTPException(status_code=400, detail="标注选项不在本任务配置中")
    payload = body.model_dump()
    payload["status"] = status
    saved = store.save_item(task, idx, payload)
    return SaveLabelResponse(saved=saved, progress=store.compute_progress(task))


@router.get("/tasks/{task_id}/export")
def export_task(task_id: str, store: StoreDep) -> StreamingResponse:
    task = _task_or_404(store, task_id)
    rows = store.export_rows(task)
    if not rows:
        raise HTTPException(status_code=404, detail="本任务尚无标记结果")
    buf = io.BytesIO()
    pd.DataFrame(rows).to_excel(buf, index=False)
    buf.seek(0)
    filename = f"{task.get('name') or task_id}_report.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/tasks/{task_id}/pdf/{filename}")
def serve_pdf(task_id: str, filename: str, store: StoreDep) -> FileResponse:
    if not store.valid_task_id(task_id):
        raise HTTPException(status_code=404, detail="任务不存在")
    path = store.pdf_path(task_id, Path(filename).name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="PDF 不存在")
    return FileResponse(path, media_type="application/pdf", filename=path.name)


@router.get("/tasks/{task_id}/html/{idx}")
async def proxy_html(task_id: str, idx: int, store: StoreDep) -> Response:
    task = _task_or_404(store, task_id)
    try:
        item = store.get_item(task, idx)
    except IndexError as exc:
        raise HTTPException(status_code=404, detail="Index out of range") from exc
    url = item.get("url") or ""
    if not is_http_url(url):
        raise HTTPException(status_code=400, detail="URL 必须是 http/https")
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"获取 HTML 失败: {exc}") from exc
    return Response(content=resp.content, media_type="text/html; charset=utf-8")
