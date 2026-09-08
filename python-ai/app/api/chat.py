import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse

from app.agents import (
    checkpoint_command,
    run_review_workflow,
    run_tool_loop,
    tool_loop_reason,
    wants_review_graph,
    wants_tool_loop,
)
from app.agents.evidence import apply_checked_reply, pack_from_citations
from app.agents.graph import WorkflowResult
from app.agents.tool_loop import ToolLoopResult
from app.api.deps import get_document_service, get_settings_dep
from app.asknum import try_answer
from app.config import Settings
from app.db.connection import get_connection
from app.db.session_repository import list_session_documents, session_exists
from app.documents.service import DocumentService
from app.models.base import LLMClient, ModelError
from app.models.factory import get_llm_client, list_available_models
from app.rag.service import collect_rag_doc_ids, prepare_chat_rag
from app.prompts.library import render_system
from app.schemas.chat import ChatRequest, ChatResponse, Citation

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)

def _general_chat_system() -> str:
    return render_system("chat.general")


SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


@dataclass
class LlmTurn:
    messages: list[dict[str, Any]]
    citations: list[Citation] = field(default_factory=list)
    rag_used: bool = False
    route: str = "general"
    status: str = "正在生成回答…"


def _valid_session_id(session_id: str | None) -> str | None:
    if not session_id:
        return None
    try:
        return str(UUID(session_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid session_id") from exc


def _asknum_citations(asknum, document_service: DocumentService) -> list[Citation]:
    citations: list[Citation] = []
    for item in asknum.citations:
        viewer_url = None
        if item.kind == "document" and item.doc_id:
            try:
                viewer_url = document_service.viewer_url(item.doc_id, page=item.page)
            except Exception:
                logger.warning("asknum viewer_url failed doc_id=%s", item.doc_id)
        citations.append(
            Citation(
                doc_id=item.doc_id,
                page=item.page,
                snippet=item.snippet,
                viewer_url=viewer_url,
                title=item.title,
                href=item.href,
                kind=item.kind,
            )
        )
    return citations


def _resolve_model(body: ChatRequest, settings: Settings) -> str:
    available = list_available_models(settings)
    if not available:
        raise HTTPException(status_code=503, detail="no LLM model configured")
    requested = (body.model or settings.default_model).lower()
    if requested not in available:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported model: {requested}; available: {', '.join(available)}",
        )
    return requested


def _from_workflow(workflow: WorkflowResult, model_name: str, session_id: str | None) -> ChatResponse:
    return ChatResponse(
        reply=workflow.reply,
        model=model_name,
        citations=workflow.citations,
        session_id=session_id,
        rag_used=workflow.rag_used,
        route=workflow.route,
        thread_id=workflow.thread_id,
        pending_node=workflow.pending_node,
    )


def _maybe_review_workflow(
    body: ChatRequest,
    *,
    session_id: str | None,
    request_id: str | None,
    dept: str | None,
) -> WorkflowResult | None:
    if not body.use_rag:
        return None
    command = checkpoint_command(body.message)
    if body.thread_id and command:
        return run_review_workflow(
            body.message,
            session_id=session_id,
            request_id=request_id,
            thread_id=body.thread_id,
            dept=dept,
            action=command,
        )
    if wants_review_graph(body.message):
        return run_review_workflow(
            body.message,
            session_id=session_id,
            request_id=request_id,
            dept=dept,
            action="start",
        )
    return None


def _from_tool_loop(loop: ToolLoopResult, model_name: str, session_id: str | None) -> ChatResponse:
    return ChatResponse(
        reply=loop.reply,
        model=model_name,
        citations=loop.citations,
        session_id=session_id,
        rag_used=loop.rag_used,
        route=loop.route,
        prompt_tokens=loop.prompt_tokens,
        completion_tokens=loop.completion_tokens,
        total_tokens=loop.prompt_tokens + loop.completion_tokens,
        latency_ms=loop.latency_ms,
        tool_trace=loop.trace,
    )


def _try_asknum(
    body: ChatRequest,
    *,
    session_id: str | None,
    request_id: str | None,
    model_name: str,
    document_service: DocumentService,
) -> ChatResponse | None:
    try:
        asknum = try_answer(
            body.message,
            persist_trace=True,
            request_id=request_id,
            session_id=session_id,
        )
    except Exception:
        logger.exception("asknum failed, falling through to RAG")
        return None
    if asknum is None:
        return None
    citations = _asknum_citations(asknum, document_service)
    logger.info(
        "POST /chat asknum route=%s model=%s session_id=%s citations=%d",
        asknum.route,
        model_name,
        session_id,
        len(citations),
    )
    return ChatResponse(
        reply=asknum.reply,
        model=model_name,
        citations=citations,
        session_id=session_id,
        rag_used=False,
        route=asknum.route,
    )


def _pending_docs_response(
    *,
    session_id: str | None,
    model_name: str,
) -> ChatResponse | None:
    if not session_id:
        return None
    with get_connection() as conn:
        if not session_exists(conn, session_id):
            raise HTTPException(status_code=404, detail="session not found")
        pending = [
            row
            for row in list_session_documents(conn, session_id)
            if row.status in ("PENDING", "PROCESSING")
        ]
    if pending and not collect_rag_doc_ids(session_id):
        names = "、".join(doc.source_filename for doc in pending)
        return ChatResponse(
            reply=(
                f"您上传的文档（{names}）仍在解析入库中，请稍候 1～5 分钟后再提问。"
                "解析完成后我会基于文档内容回答。"
            ),
            model=model_name,
            session_id=session_id,
            rag_used=False,
            route="general",
        )
    return None


def _prepare_llm_turn(
    body: ChatRequest,
    *,
    session_id: str | None,
    document_service: DocumentService,
    request_id: str | None,
) -> LlmTurn:
    if not body.use_rag:
        return LlmTurn(
            messages=[
                {"role": "system", "content": _general_chat_system()},
                {"role": "user", "content": body.message},
            ],
            route="general",
        )
    rag_result = prepare_chat_rag(
        session_id=session_id,
        question=body.message,
        document_service=document_service,
        request_id=request_id,
    )
    rag = rag_result.answer
    if rag is not None:
        citations = [
            Citation(
                doc_id=item.doc_id,
                page=item.page,
                snippet=item.snippet,
                viewer_url=item.viewer_url,
                title=item.title,
            )
            for item in rag.citations
        ]
        rag_used = bool(citations)
        return LlmTurn(
            messages=rag.messages,
            citations=citations,
            rag_used=rag_used,
            route="rag" if rag_used else "general",
        )
    route = "chitchat" if rag_result.trace.outcome == "no_intent" else "general"
    return LlmTurn(
        messages=[
            {"role": "system", "content": _general_chat_system()},
            {"role": "user", "content": body.message},
        ],
        route=route,
    )


def _sse(event: str, data: dict[str, Any]) -> bytes:
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {payload}\n\n".encode("utf-8")


def _error_detail(detail: Any) -> str:
    if isinstance(detail, str):
        return detail
    return json.dumps(detail, ensure_ascii=False, default=str)


def _observe(
    response: ChatResponse,
    *,
    message: str,
    stream: bool = False,
    ttft_ms: float | None = None,
) -> ChatResponse:
    try:
        from app.obs.generations import record_from_chat

        record_from_chat(response, message=message, stream=stream, ttft_ms=ttft_ms)
    except Exception:
        logger.debug("obs skipped", exc_info=True)
    return response


async def _complete_llm(
    client: LLMClient,
    turn: LlmTurn,
    *,
    body: ChatRequest,
    model_name: str,
    session_id: str | None,
) -> ChatResponse:
    result = await client.chat_with_usage(turn.messages, temperature=body.temperature)
    logger.info(
        "POST /chat ok model=%s session_id=%s route=%s rag_used=%s citations=%d tokens=%d latency_ms=%.0f",
        model_name,
        session_id,
        turn.route,
        turn.rag_used,
        len(turn.citations),
        result.total_tokens,
        result.latency_ms,
    )
    reply = result.content
    route = turn.route
    tool_trace: list[dict[str, Any]] = []
    if turn.route == "rag":
        reply, route, checked = apply_checked_reply(
            reply,
            pack_from_citations(turn.citations),
            route=turn.route,
        )
        tool_trace.append(checked.to_trace())
    response = ChatResponse(
        reply=reply,
        model=model_name,
        citations=turn.citations,
        session_id=session_id,
        rag_used=turn.rag_used,
        route=route,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        total_tokens=result.total_tokens,
        latency_ms=result.latency_ms,
        tool_trace=tool_trace,
    )
    return _observe(response, message=body.message)


async def _stream_tool_loop(
    body: ChatRequest,
    client: LLMClient,
    *,
    session_id: str | None,
    request_id: str | None,
    model_name: str,
) -> AsyncIterator[bytes]:
    queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

    async def on_event(kind: str, payload: dict[str, Any]) -> None:
        await queue.put((kind, payload))

    async def runner() -> None:
        try:
            result = await run_tool_loop(
                body.message,
                client,
                session_id=session_id,
                request_id=request_id,
                temperature=body.temperature,
                on_event=on_event,
            )
            await queue.put(("__done__", result))
        except Exception as exc:
            await queue.put(("__error__", exc))

    task = asyncio.create_task(runner())
    yield _sse("meta", {"route": "tools", "model": model_name, "session_id": session_id})
    await asyncio.sleep(0)
    try:
        while True:
            kind, payload = await queue.get()
            if kind == "__done__":
                loop = payload
                response = _observe(_from_tool_loop(loop, model_name, session_id), message=body.message, stream=True)
                logger.info(
                    "POST /chat/stream tools route=%s reason=%s steps=%d tokens=%d",
                    loop.route,
                    tool_loop_reason(body.message),
                    len(loop.trace),
                    loop.prompt_tokens + loop.completion_tokens,
                )
                yield _sse("delta", {"text": response.reply})
                yield _sse("done", response.model_dump())
                return
            if kind == "__error__":
                raise payload
            yield _sse(kind, payload)
            await asyncio.sleep(0)
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


@router.post("", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    settings: Annotated[Settings, Depends(get_settings_dep)],
    document_service: Annotated[DocumentService, Depends(get_document_service)],
    x_request_id: Annotated[str | None, Header(alias="X-Request-ID")] = None,
    x_regops_dept: Annotated[str | None, Header(alias="X-Regops-Dept")] = None,
) -> ChatResponse:
    session_id = _valid_session_id(body.session_id)
    model_name = _resolve_model(body, settings)
    client = get_llm_client(settings, model=model_name)

    workflow = _maybe_review_workflow(
        body,
        session_id=session_id,
        request_id=x_request_id,
        dept=x_regops_dept,
    )
    if workflow is not None:
        logger.info(
            "POST /chat agent route=%s steps=%d stop=%s thread=%s pending=%s",
            workflow.route,
            len(workflow.trace),
            workflow.stop_reason,
            workflow.thread_id,
            workflow.pending_node,
        )
        return _observe(_from_workflow(workflow, model_name, session_id), message=body.message)
    if body.use_rag and wants_tool_loop(body.message):
        loop = await run_tool_loop(
            body.message,
            client,
            session_id=session_id,
            request_id=x_request_id,
            temperature=body.temperature,
        )
        logger.info(
            "POST /chat tools route=%s reason=%s steps=%d tokens=%d",
            loop.route,
            tool_loop_reason(body.message),
            len(loop.trace),
            loop.prompt_tokens + loop.completion_tokens,
        )
        return _observe(_from_tool_loop(loop, model_name, session_id), message=body.message)
    if body.use_rag:
        asknum = _try_asknum(
            body,
            session_id=session_id,
            request_id=x_request_id,
            model_name=model_name,
            document_service=document_service,
        )
        if asknum is not None:
            return _observe(asknum, message=body.message)
        pending = _pending_docs_response(session_id=session_id, model_name=model_name)
        if pending is not None:
            return _observe(pending, message=body.message)

    turn = _prepare_llm_turn(
        body,
        session_id=session_id,
        document_service=document_service,
        request_id=x_request_id,
    )
    try:
        return await _complete_llm(
            client,
            turn,
            body=body,
            model_name=model_name,
            session_id=session_id,
        )
    except ModelError as exc:
        logger.warning("POST /chat model error: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        logger.error("POST /chat config error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/stream")
async def chat_stream(
    body: ChatRequest,
    settings: Annotated[Settings, Depends(get_settings_dep)],
    document_service: Annotated[DocumentService, Depends(get_document_service)],
    x_request_id: Annotated[str | None, Header(alias="X-Request-ID")] = None,
    x_regops_dept: Annotated[str | None, Header(alias="X-Regops-Dept")] = None,
) -> StreamingResponse:
    session_id = _valid_session_id(body.session_id)
    model_name = _resolve_model(body, settings)
    client = get_llm_client(settings, model=model_name)

    async def events() -> AsyncIterator[bytes]:
        try:
            yield _sse("meta", {"model": model_name, "session_id": session_id})
            workflow = _maybe_review_workflow(
                body,
                session_id=session_id,
                request_id=x_request_id,
                dept=x_regops_dept,
            )
            if workflow is not None:
                status = (
                    "正在恢复审查检查点…"
                    if checkpoint_command(body.message)
                    else "正在运行审查对比工作流…"
                )
                yield _sse("status", {"text": status})
                logger.info(
                    "POST /chat/stream agent route=%s steps=%d stop=%s thread=%s pending=%s",
                    workflow.route,
                    len(workflow.trace),
                    workflow.stop_reason,
                    workflow.thread_id,
                    workflow.pending_node,
                )
                response = _observe(_from_workflow(workflow, model_name, session_id), message=body.message, stream=True)
                yield _sse("meta", {"route": response.route, "thread_id": response.thread_id})
                yield _sse("delta", {"text": response.reply})
                yield _sse("done", response.model_dump())
                return
            if body.use_rag and wants_tool_loop(body.message):
                async for chunk in _stream_tool_loop(
                    body,
                    client,
                    session_id=session_id,
                    request_id=x_request_id,
                    model_name=model_name,
                ):
                    yield chunk
                return
            if body.use_rag:
                asknum = _try_asknum(
                    body,
                    session_id=session_id,
                    request_id=x_request_id,
                    model_name=model_name,
                    document_service=document_service,
                )
                if asknum is not None:
                    yield _sse("meta", {"route": asknum.route})
                    yield _sse("delta", {"text": asknum.reply})
                    yield _sse("done", _observe(asknum, message=body.message, stream=True).model_dump())
                    return
                yield _sse("status", {"text": "正在检索相关文档…"})
                pending = _pending_docs_response(session_id=session_id, model_name=model_name)
                if pending is not None:
                    yield _sse("delta", {"text": pending.reply})
                    yield _sse("done", _observe(pending, message=body.message, stream=True).model_dump())
                    return
            turn = _prepare_llm_turn(
                body,
                session_id=session_id,
                document_service=document_service,
                request_id=x_request_id,
            )
            yield _sse("status", {"text": turn.status})
            yield _sse("meta", {"route": turn.route, "model": model_name})
            pieces: list[str] = []
            result = None
            started = time.perf_counter()
            ttft_ms: float | None = None
            async for delta in client.chat_stream(turn.messages, temperature=body.temperature):
                if delta.text:
                    if ttft_ms is None:
                        ttft_ms = (time.perf_counter() - started) * 1000
                    pieces.append(delta.text)
                    yield _sse("delta", {"text": delta.text})
                    await asyncio.sleep(0)
                if delta.done:
                    result = delta.result
            if result is None:
                raise ModelError("empty stream")
            reply = "".join(pieces) or result.content
            route = turn.route
            tool_trace: list[dict[str, Any]] = []
            if turn.route == "rag":
                reply, route, checked = apply_checked_reply(
                    reply,
                    pack_from_citations(turn.citations),
                    route=turn.route,
                )
                tool_trace.append(checked.to_trace())
            response = _observe(
                ChatResponse(
                    reply=reply,
                    model=model_name,
                    citations=turn.citations,
                    session_id=session_id,
                    rag_used=turn.rag_used,
                    route=route,
                    prompt_tokens=result.prompt_tokens,
                    completion_tokens=result.completion_tokens,
                    total_tokens=result.total_tokens,
                    latency_ms=result.latency_ms,
                    tool_trace=tool_trace,
                ),
                message=body.message,
                stream=True,
                ttft_ms=ttft_ms,
            )
            logger.info(
                "POST /chat/stream ok model=%s session_id=%s route=%s rag_used=%s citations=%d tokens=%d latency_ms=%.0f",
                model_name,
                session_id,
                route,
                turn.rag_used,
                len(turn.citations),
                result.total_tokens,
                result.latency_ms,
            )
            yield _sse("done", response.model_dump())
        except HTTPException as exc:
            yield _sse("error", {"detail": _error_detail(exc.detail), "status": exc.status_code})
        except ModelError as exc:
            logger.warning("POST /chat/stream model error: %s", exc)
            yield _sse("error", {"detail": str(exc), "status": 502})
        except ValueError as exc:
            logger.error("POST /chat/stream config error: %s", exc)
            yield _sse("error", {"detail": str(exc), "status": 500})
        except Exception:
            logger.exception("POST /chat/stream failed")
            yield _sse("error", {"detail": "stream failed", "status": 500})

    return StreamingResponse(events(), media_type="text/event-stream", headers=SSE_HEADERS)
