"""AI Coding HTTP/SSE API, isolated from the financial risk conversation API.

Both products reuse the persistence and event-stream runtime, but coding threads
have their own identifier namespace and always use the DeepAgents task path.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from starlette.concurrency import run_in_threadpool
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from agent.api.auth import require_regops_user
from agent.core.checkpoint_history import visible_checkpoint_messages
from agent.core.model import available_agent_models, default_agent_model_id, require_agent_model_id
from agent.core.runtime import delete_task, get_task, initialize_task_record, list_tasks
from agent.core.graph import get_store
from agent.coding.service import run_coding_task
from agent.backends.coding_upload import UploadRejected, upload_to_workspace
from agent.backends.open_sandbox import (
    SandboxExpiredError,
    delete_saved_export,
    destroy_sandbox_for_thread,
    consume_workspace_notice,
    execution_backend,
    export_project_zip,
    ensure_sandbox_for_thread,
    save_export_snapshot,
)
from agent.backends.coding_snapshot_memory import recall_snapshot

coding_agent_router = APIRouter(prefix="/regops/coding-agent")
logger = logging.getLogger(__name__)


class CodingMessageRequest(BaseModel):
    content: str
    model_id: str | None = None


def _owned_thread_id(user_id: str, thread_id: str) -> str:
    prefix = f"{user_id}_coding_"
    if not thread_id.startswith(prefix):
        raise HTTPException(status_code=404, detail="thread not found")
    try:
        uuid.UUID(thread_id[len(prefix):])
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="thread not found") from exc
    return thread_id


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def _thread_meta(thread: dict[str, Any]) -> dict[str, Any]:
    def timestamp(value: str | None) -> int:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000) if value else int(datetime.now().timestamp() * 1000)

    status = thread.get("latest_run_status")
    return {
        "id": thread["thread_id"],
        "title": thread.get("title") or "AI Coding 任务",
        "status": "running" if status in {"running", "pending"} else "error" if status == "failed" else "idle" if status == "idle" else "finished",
        "createdAt": timestamp(thread.get("created_at")),
        "updatedAt": timestamp(thread.get("updated_at")),
        "sandboxReady": bool(thread.get("sandbox_id")),
    }


def _thread_payload(thread: dict[str, Any], *, include_snapshot: bool = False) -> dict[str, Any]:
    messages = []
    for index, item in enumerate(visible_checkpoint_messages(str(thread["thread_id"]))):
        content = str(item.get("content") or "").strip()
        if not content or item.get("author") not in {"user", "agent"}:
            continue
        messages.append({
            "id": item.get("message_id") or f"{thread['thread_id']}-history-{index}",
            "author": item["author"],
            "timestamp": item.get("created_at") or thread.get("created_at"),
            "chunks": [{"kind": "text", "text": content}],
        })
    payload = {**_thread_meta(thread), "messages": messages}
    if include_snapshot:
        payload["snapshotReady"] = recall_snapshot(str(thread["thread_id"])) is not None
    return payload


@coding_agent_router.get("/options")
def options(_user_id: str = Depends(require_regops_user)) -> dict[str, Any]:
    try:
        backend = execution_backend()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    models = available_agent_models()
    return {
        "models": [{"id": model_id, "label": model_id} for model_id in models],
        "default_agent_model": default_agent_model_id(models),
        "execution_backend": backend,
    }


@coding_agent_router.get("/threads")
def threads(limit: int = 50, user_id: str = Depends(require_regops_user)) -> list[dict[str, Any]]:
    prefix = f"{user_id}_coding_"
    return [_thread_payload(item) for item in list_tasks(limit=max(1, min(limit, 100)), owner_prefix=prefix)]


@coding_agent_router.get("/threads/{thread_id}")
def thread_detail(thread_id: str, user_id: str = Depends(require_regops_user)) -> dict[str, Any]:
    task = get_task(_owned_thread_id(user_id, thread_id))
    if task is None:
        raise HTTPException(status_code=404, detail="thread not found")
    return _thread_payload(task, include_snapshot=True)


def _prepare_sandbox(thread_id: str) -> dict[str, Any]:
    task = get_task(thread_id)
    if task is None:
        raise HTTPException(status_code=404, detail="thread not found")
    if task.get("latest_run_status") in {"running", "pending"}:
        raise HTTPException(status_code=409, detail="任务执行中，不能重建沙箱")
    try:
        execution_backend()
        backend = ensure_sandbox_for_thread(thread_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    notice = consume_workspace_notice(thread_id)
    current = get_task(thread_id) or task
    return {
        "thread": _thread_meta(current),
        "sandbox_created": str(task.get("sandbox_id") or "") != backend.id,
        "workspace_notice": notice,
    }


@coding_agent_router.post("/threads/sandbox")
def create_thread_sandbox(user_id: str = Depends(require_regops_user)) -> dict[str, Any]:
    thread_id = f"{user_id}_coding_{uuid.uuid4()}"
    get_store().upsert_thread(thread_id=thread_id, title="AI Coding 会话", latest_run_status="idle")
    try:
        return _prepare_sandbox(thread_id)
    except Exception:
        delete_task(thread_id)
        raise


@coding_agent_router.post("/threads/{thread_id}/sandbox")
def prepare_thread_sandbox(thread_id: str, user_id: str = Depends(require_regops_user)) -> dict[str, Any]:
    return _prepare_sandbox(_owned_thread_id(user_id, thread_id))


@coding_agent_router.post("/threads/{thread_id}/files")
async def upload_code_file(
    thread_id: str, request: Request,
    filename: str = Query(..., min_length=1, max_length=512),
    user_id: str = Depends(require_regops_user),
) -> dict[str, Any]:
    owned_id = _owned_thread_id(user_id, thread_id)
    task = get_task(owned_id)
    if task is None:
        raise HTTPException(status_code=404, detail="thread not found")
    if task.get("latest_run_status") in {"running", "pending"}:
        raise HTTPException(status_code=409, detail="任务执行中，不能上传代码")
    if int(request.headers.get("content-length") or 0) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="上传文件超过 20 MiB")
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > 20 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="上传文件超过 20 MiB")
        chunks.append(chunk)
    try:
        result = await run_in_threadpool(upload_to_workspace, owned_id, filename, b"".join(chunks))
    except UploadRejected as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"thread": _thread_meta(get_task(owned_id) or task), **result}


@coding_agent_router.get("/threads/{thread_id}/export")
def export_thread_project(thread_id: str, user_id: str = Depends(require_regops_user)) -> Response:
    owned_id = _owned_thread_id(user_id, thread_id)
    task = get_task(owned_id)
    if task is None:
        raise HTTPException(status_code=404, detail="thread not found")
    if task.get("latest_run_status") in {"running", "pending"}:
        raise HTTPException(status_code=409, detail="任务执行中，请完成后再导出")
    try:
        _project, archive = export_project_zip(owned_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except SandboxExpiredError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return Response(
        content=archive,
        media_type="application/zip",
        headers={
            "Content-Disposition": "attachment; filename=ai-coding-sandbox.zip",
            "Cache-Control": "no-store",
        },
    )


def _stream_response(thread_id: str, content: str, model_id: str | None) -> StreamingResponse:
    if not content.strip() or len(content) > 20_000:
        raise HTTPException(status_code=422, detail="content must contain 1–20000 characters")
    try:
        selected_model = require_agent_model_id(model_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        execution_backend()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    initialize_task_record(repo_url=None, prompt=content, thread_id=thread_id)
    initial = get_task(thread_id)
    if initial is None:
        raise HTTPException(status_code=500, detail="task was not persisted")

    async def events():
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()

        def emit(event: str, data: dict[str, Any]) -> None:
            payload = {**data, "thread_id": thread_id}
            loop.call_soon_threadsafe(queue.put_nowait, (event, payload))

        def sink(event: str, data: dict[str, Any]) -> None:
            if event == "text_delta" and not str(data.get("content") or "").strip():
                return
            emit(event, data)

        def worker() -> None:
            run_completed = False
            snapshot_saved = False
            try:
                result = run_coding_task(prompt=content, thread_id=thread_id,
                                         model_id=selected_model, event_sink=sink)
                run_completed = True
                answer = result.get("final_answer")
                if isinstance(answer, str) and answer.strip():
                    emit("final_answer", {"content": answer})
            except Exception as exc:
                emit("error", {"message": str(exc), "detail": str(exc)})
            finally:
                notice = consume_workspace_notice(thread_id)
                if notice:
                    emit("workspace_notice", {"message": notice})
                if run_completed and (get_task(thread_id) or {}).get("sandbox_id"):
                    try:
                        snapshot_saved = save_export_snapshot(thread_id)
                    except Exception:
                        logger.exception("AI Coding 导出快照保存失败：thread_id=%s", thread_id)
                        emit("export_warning", {"message": "自动保存导出快照失败，请在沙箱过期前手动导出"})
                emit("thread_done", {**_thread_meta(get_task(thread_id) or initial), "snapshotReady": snapshot_saved})
                emit("done", {})

        yield _sse("thread_snapshot", _thread_meta(initial))
        yield _sse("user_message", {
            "thread_id": thread_id, "message_id": f"{thread_id}-user-{uuid.uuid4()}",
            "author": "user", "content": content,
        })
        threading.Thread(target=worker, name=f"regops-coding-{thread_id}", daemon=True).start()
        while True:
            event, data = await queue.get()
            yield _sse(event, data)
            if event == "done":
                break

    return StreamingResponse(events(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no",
    })


@coding_agent_router.post("/threads/stream-message")
def stream_new(body: CodingMessageRequest, user_id: str = Depends(require_regops_user)) -> StreamingResponse:
    return _stream_response(f"{user_id}_coding_{uuid.uuid4()}", body.content, body.model_id)


@coding_agent_router.post("/threads/{thread_id}/stream-message")
def stream_existing(
    thread_id: str, body: CodingMessageRequest,
    user_id: str = Depends(require_regops_user),
) -> StreamingResponse:
    _owned_thread_id(user_id, thread_id)
    task = get_task(thread_id)
    if task is None:
        raise HTTPException(status_code=404, detail="thread not found")
    return _stream_response(thread_id, body.content, body.model_id)


@coding_agent_router.delete("/threads/{thread_id}", status_code=204)
def delete_thread(thread_id: str, user_id: str = Depends(require_regops_user)) -> None:
    owned_id = _owned_thread_id(user_id, thread_id)
    existing = get_task(owned_id)
    if existing and existing.get("sandbox_id"):
        destroy_sandbox_for_thread(owned_id)
    delete_saved_export(owned_id)
    if not delete_task(owned_id):
        raise HTTPException(status_code=404, detail="thread not found")
