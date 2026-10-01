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

from app.rag.evidence import apply_checked_reply, pack_from_citations
from app.rag.comparison import prepare_multi_company_rag
from app.rag.comparison_output import (
    ComparisonContract,
    build_comparison_contract,
    validate_comparison_output,
)
from app.core.dependencies import get_document_service, get_settings_dep
from app.asknum import should_continue_pending, try_answer
from app.asknum.slots import looks_like_metric_question, parse_slots
from app.config import Settings
from app.db.connection import get_connection
from app.db.session_repository import list_session_documents, session_exists
from app.documents.service import DocumentService
from app.models.llm import LLMClient, ModelError, get_llm_client
from app.rag.service import collect_rag_doc_ids, prepare_chat_rag
from app.prompts.library import render_system
from app.chat.schemas import ChatRequest, ChatResponse, Citation, CompanyComparisonResult

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
    comparison_contract: ComparisonContract | None = None
    rag_performance: dict[str, Any] | None = None


def _elapsed_ms(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1000, 2)


def _rerank_input_count(pipeline: dict[str, Any]) -> int:
    return sum(
        int(value or 0)
        for key, value in pipeline.items()
        if key.endswith("_rerank_input_count")
    )


def _rag_performance(trace) -> dict[str, Any]:
    pipeline = trace.pipeline or {}
    return {
        "mode": "single",
        "outcome": trace.outcome,
        "total_ms": trace.total_rag_ms,
        "timing_ms": dict(pipeline.get("timing_ms") or {}),
        "rerank_backend": pipeline.get("rerank_backend"),
        "rerank_deployment": pipeline.get("rerank_deployment"),
        "rerank_model": pipeline.get("rerank_model"),
        "rerank_fallback": bool(pipeline.get("rerank_fallback")),
        "rerank_candidate_limit": pipeline.get("rerank_candidate_limit"),
        "rerank_input_count": _rerank_input_count(pipeline),
    }


def _finish_performance(
    performance: dict[str, Any],
    *,
    request_started: float,
    response: ChatResponse | None,
    stream: bool,
    session_id: str | None,
    model_name: str | None,
    status: str = "ok",
    error_type: str | None = None,
) -> ChatResponse | None:
    if performance.get("_recorded"):
        return response
    total_ms = _elapsed_ms(request_started)
    performance.setdefault("timing_ms", {})["total"] = total_ms
    if response is not None:
        response.total_latency_ms = total_ms
    try:
        from app.obs.performance import record_performance

        record_performance(
            {
                "status": status,
                "error_type": error_type,
                "stream": stream,
                "route": response.route if response is not None else performance.get("route"),
                "model": response.model if response is not None else model_name,
                "session_id": session_id,
                "rag_used": response.rag_used if response is not None else False,
                "timing_ms": dict(performance.get("timing_ms") or {}),
                "rag": performance.get("rag"),
                "prompt_tokens": response.prompt_tokens if response is not None else 0,
                "completion_tokens": response.completion_tokens if response is not None else 0,
                "total_tokens": response.total_tokens if response is not None else 0,
            }
        )
    except Exception:
        logger.debug("performance trace skipped", exc_info=True)
    performance["_recorded"] = True
    return response


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


def _client_for(body: ChatRequest, settings: Settings) -> LLMClient:
    try:
        return get_llm_client(settings, model=body.model or settings.default_model)
    except ValueError as exc:
        status = 503 if str(exc) == "no LLM model configured" else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc


def _try_asknum(
    body: ChatRequest,
    *,
    session_id: str | None,
    request_id: str | None,
    model_name: str,
    document_service: DocumentService,
    strict_failure: bool = False,
) -> ChatResponse | None:
    try:
        slots = parse_slots(body.message)
        asknum = try_answer(
            body.message,
            persist_trace=True,
            request_id=request_id,
            session_id=session_id,
            slots=slots,
        )
    except Exception:
        logger.exception("asknum failed")
        metric_candidate = strict_failure
        try:
            metric_candidate = metric_candidate or looks_like_metric_question(body.message)
        except Exception:
            logger.debug("asknum failure classification failed", exc_info=True)
        if metric_candidate:
            return ChatResponse(
                reply=(
                    "财务事实查询失败，本次未返回数字，也不会降级为 RAG 或让模型估算。"
                    "请稍后重试；若持续失败，请检查财务事实库和数据库连接。"
                ),
                model=model_name,
                session_id=session_id,
                rag_used=False,
                route="metric_error",
            )
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
        pending_request=asknum.pending_request,
    )


def _try_pending_asknum(
    body: ChatRequest,
    *,
    session_id: str | None,
    request_id: str | None,
    model_name: str,
    document_service: DocumentService,
) -> ChatResponse | None:
    if not session_id or not should_continue_pending(body.message, session_id):
        return None
    return _try_asknum(
        body,
        session_id=session_id,
        request_id=request_id,
        model_name=model_name,
        document_service=document_service,
        strict_failure=True,
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
    model_name: str,
    document_service: DocumentService,
    request_id: str | None,
    dept: str | None = None,
    performance: dict[str, Any] | None = None,
) -> ChatResponse | LlmTurn:
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
        dept=dept,
    )
    rag = rag_result.answer
    rag_metrics = _rag_performance(rag_result.trace)
    if performance is not None:
        performance["rag"] = rag_metrics
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
            rag_performance=rag_metrics,
        )
    if rag_result.trace.outcome in {"no_docs", "low_score"}:
        return ChatResponse(
            reply=(
                "当前可访问的知识库中没有检索到足够可靠的证据，本次不生成推测性答案。"
                "请确认公司、年份和相关文档已入库后重试。"
            ),
            model=model_name,
            session_id=session_id,
            rag_used=False,
            route="rag_blocked",
        )
    route = "chitchat" if rag_result.trace.outcome == "no_intent" else "general"
    return LlmTurn(
        messages=[
            {"role": "system", "content": _general_chat_system()},
            {"role": "user", "content": body.message},
        ],
        route=route,
        rag_performance=rag_metrics,
    )


def _try_multi_company_rag(
    body: ChatRequest,
    *,
    model_name: str,
    document_service: DocumentService,
    dept: str | None,
    session_id: str | None,
    performance: dict[str, Any],
) -> ChatResponse | LlmTurn | None:
    slots = parse_slots(body.message)
    if len(slots.company_codes) < 2:
        return None
    try:
        prepared = prepare_multi_company_rag(
            question=body.message,
            slots=slots,
            document_service=document_service,
            dept=dept,
        )
    except Exception:
        performance["rag"] = {
            "mode": "comparison",
            "outcome": "retrieval_error",
            "companies": {},
        }
        logger.exception("multi-company RAG preparation failed")
        return ChatResponse(
            reply=(
                "多公司证据检索失败，本次拒绝直接比较，也不会让模型补全。"
                "请稍后重试或检查文档索引与数据库连接。"
            ),
            model=model_name,
            session_id=session_id,
            rag_used=False,
            route="rag_compare_blocked",
        )
    performance["rag"] = {
        "mode": "comparison",
        "outcome": "ok" if prepared.blocked_reply is None else "blocked",
        "selected_years": list(prepared.selected_years),
        "companies": {
            evidence.company_code: {
                "status": evidence.status,
                "timing_ms": dict((evidence.pipeline or {}).get("timing_ms") or {}),
                "rerank_backend": (evidence.pipeline or {}).get("rerank_backend"),
                "rerank_deployment": (evidence.pipeline or {}).get("rerank_deployment"),
                "rerank_model": (evidence.pipeline or {}).get("rerank_model"),
                "rerank_fallback": bool((evidence.pipeline or {}).get("rerank_fallback")),
                "rerank_candidate_limit": (evidence.pipeline or {}).get(
                    "rerank_candidate_limit"
                ),
                "rerank_input_count": _rerank_input_count(evidence.pipeline or {}),
            }
            for evidence in prepared.evidences
        },
    }
    citations = [
        Citation(
            doc_id=item.doc_id,
            page=item.page,
            snippet=item.snippet,
            viewer_url=item.viewer_url,
            title=item.title,
        )
        for item in prepared.citations
    ]
    if prepared.blocked_reply is not None:
        return ChatResponse(
            reply=prepared.blocked_reply,
            model=model_name,
            citations=citations,
            session_id=session_id,
            rag_used=bool(citations),
            route="rag_compare_blocked",
        )
    if prepared.answer is None:
        return None
    return LlmTurn(
        messages=prepared.answer.messages,
        citations=citations,
        rag_used=True,
        route="rag_compare",
        status="正在综合多家公司证据…",
        comparison_contract=build_comparison_contract(
            companies=[
                (evidence.company_code, evidence.company_name)
                for evidence in prepared.evidences
            ],
            periods=prepared.selected_years,
            citations=citations,
        ),
        rag_performance=performance["rag"],
    )


def _route_request(
    body: ChatRequest,
    *,
    session_id: str | None,
    request_id: str | None,
    model_name: str,
    document_service: DocumentService,
    dept: str | None,
    performance: dict[str, Any],
) -> ChatResponse | LlmTurn:
    """普通与流式接口共用的 AskNum / 待入库 / RAG 路由。"""
    if body.use_rag:
        asknum_started = time.perf_counter()
        direct = _try_pending_asknum(
            body,
            session_id=session_id,
            request_id=request_id,
            model_name=model_name,
            document_service=document_service,
        )
        if direct is None:
            direct = _try_asknum(
                body,
                session_id=session_id,
                request_id=request_id,
                model_name=model_name,
                document_service=document_service,
            )
        performance["timing_ms"]["asknum"] = _elapsed_ms(asknum_started)
        if direct is None:
            pending_started = time.perf_counter()
            direct = _pending_docs_response(session_id=session_id, model_name=model_name)
            performance["timing_ms"]["pending_docs"] = _elapsed_ms(pending_started)
        if direct is not None:
            performance["route"] = direct.route
            return direct
        comparison_started = time.perf_counter()
        comparison = _try_multi_company_rag(
            body,
            model_name=model_name,
            document_service=document_service,
            dept=dept,
            session_id=session_id,
            performance=performance,
        )
        performance["timing_ms"]["rag_compare"] = _elapsed_ms(comparison_started)
        if comparison is not None:
            performance["route"] = comparison.route
            return comparison
    rag_started = time.perf_counter()
    turn = _prepare_llm_turn(
        body,
        session_id=session_id,
        model_name=model_name,
        document_service=document_service,
        request_id=request_id,
        dept=dept,
        performance=performance,
    )
    performance["timing_ms"]["rag" if body.use_rag else "prepare_turn"] = _elapsed_ms(
        rag_started
    )
    performance["route"] = turn.route
    if isinstance(turn, LlmTurn) and turn.rag_performance is not None:
        performance["rag"] = turn.rag_performance
    return turn


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


def _finalize_reply(
    turn: LlmTurn,
    raw_reply: str,
) -> tuple[str, str, list[dict[str, Any]], CompanyComparisonResult | None]:
    reply = raw_reply
    route = turn.route
    validation_trace: list[dict[str, Any]] = []
    comparison: CompanyComparisonResult | None = None

    if turn.route == "rag_compare":
        if turn.comparison_contract is None:
            return (
                "【比较结果校验拦截】缺少比较输出契约，本次不展示比较结论。",
                "rag_compare_blocked",
                [
                    {
                        "name": "comparison_schema",
                        "node": "comparison_schema",
                        "ok": False,
                        "stop": True,
                        "errors": ["missing comparison contract"],
                    }
                ],
                None,
            )
        structured = validate_comparison_output(raw_reply, turn.comparison_contract)
        validation_trace.append(structured.to_trace())
        reply = structured.reply
        comparison = structured.comparison
        if structured.blocked:
            route = "rag_compare_blocked"
        if not structured.ok:
            return reply, route, validation_trace, None

    if turn.route in {"rag", "rag_compare"}:
        reply, checked_route, checked = apply_checked_reply(
            reply,
            pack_from_citations(turn.citations),
            route=turn.route,
        )
        validation_trace.append(checked.to_trace())
        if not checked.ok:
            route = checked_route
            comparison = None
    return reply, route, validation_trace, comparison


async def _complete_llm(
    client: LLMClient,
    turn: LlmTurn,
    *,
    body: ChatRequest,
    model_name: str,
    session_id: str | None,
    performance: dict[str, Any],
) -> ChatResponse:
    model_started = time.perf_counter()
    try:
        result = await client.chat_with_usage(turn.messages, temperature=body.temperature)
    finally:
        performance["timing_ms"]["answer_model"] = _elapsed_ms(model_started)
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
    validation_started = time.perf_counter()
    reply, route, validation_trace, comparison = _finalize_reply(turn, result.content)
    performance["timing_ms"]["validation"] = _elapsed_ms(validation_started)
    performance["route"] = route
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
        validation_trace=validation_trace,
        comparison=comparison,
    )
    return response


@router.post("", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    settings: Annotated[Settings, Depends(get_settings_dep)],
    document_service: Annotated[DocumentService, Depends(get_document_service)],
    x_request_id: Annotated[str | None, Header(alias="X-Request-ID")] = None,
    x_regops_dept: Annotated[str | None, Header(alias="X-Regops-Dept")] = None,
) -> ChatResponse:
    request_started = time.perf_counter()
    performance: dict[str, Any] = {"timing_ms": {}}
    session_id: str | None = None
    model_name: str | None = None
    try:
        session_id = _valid_session_id(body.session_id)
        client = _client_for(body, settings)
        model_name = client.model_id
        routing_started = time.perf_counter()
        routed = await asyncio.to_thread(
            _route_request,
            body,
            session_id=session_id,
            document_service=document_service,
            request_id=x_request_id,
            model_name=model_name,
            dept=x_regops_dept,
            performance=performance,
        )
        performance["timing_ms"]["routing"] = _elapsed_ms(routing_started)
        if isinstance(routed, ChatResponse):
            response = routed
        else:
            response = await _complete_llm(
                client,
                routed,
                body=body,
                model_name=model_name,
                session_id=session_id,
                performance=performance,
            )
        _finish_performance(
            performance,
            request_started=request_started,
            response=response,
            stream=False,
            session_id=session_id,
            model_name=model_name,
        )
        return _observe(response, message=body.message)
    except HTTPException as exc:
        _finish_performance(
            performance,
            request_started=request_started,
            response=None,
            stream=False,
            session_id=session_id,
            model_name=model_name,
            status="error",
            error_type=f"HTTP_{exc.status_code}",
        )
        raise
    except ModelError as exc:
        _finish_performance(
            performance,
            request_started=request_started,
            response=None,
            stream=False,
            session_id=session_id,
            model_name=model_name,
            status="error",
            error_type=type(exc).__name__,
        )
        logger.warning("POST /chat model error: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        _finish_performance(
            performance,
            request_started=request_started,
            response=None,
            stream=False,
            session_id=session_id,
            model_name=model_name,
            status="error",
            error_type=type(exc).__name__,
        )
        logger.error("POST /chat config error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        _finish_performance(
            performance,
            request_started=request_started,
            response=None,
            stream=False,
            session_id=session_id,
            model_name=model_name,
            status="error",
            error_type=type(exc).__name__,
        )
        raise


@router.post("/stream")
async def chat_stream(
    body: ChatRequest,
    settings: Annotated[Settings, Depends(get_settings_dep)],
    document_service: Annotated[DocumentService, Depends(get_document_service)],
    x_request_id: Annotated[str | None, Header(alias="X-Request-ID")] = None,
    x_regops_dept: Annotated[str | None, Header(alias="X-Regops-Dept")] = None,
) -> StreamingResponse:
    request_started = time.perf_counter()
    performance: dict[str, Any] = {"timing_ms": {}}
    try:
        session_id = _valid_session_id(body.session_id)
        client = _client_for(body, settings)
        model_name = client.model_id
    except Exception as exc:
        _finish_performance(
            performance,
            request_started=request_started,
            response=None,
            stream=True,
            session_id=body.session_id,
            model_name=body.model,
            status="error",
            error_type=type(exc).__name__,
        )
        raise

    async def events() -> AsyncIterator[bytes]:
        try:
            yield _sse("meta", {"model": model_name, "session_id": session_id})
            if body.use_rag:
                yield _sse("status", {"text": "正在分析问题并检索相关数据…"})
            routing_started = time.perf_counter()
            routed = await asyncio.to_thread(
                _route_request,
                body,
                session_id=session_id,
                document_service=document_service,
                request_id=x_request_id,
                model_name=model_name,
                dept=x_regops_dept,
                performance=performance,
            )
            performance["timing_ms"]["routing"] = _elapsed_ms(routing_started)
            if isinstance(routed, ChatResponse):
                _finish_performance(
                    performance,
                    request_started=request_started,
                    response=routed,
                    stream=True,
                    session_id=session_id,
                    model_name=model_name,
                )
                yield _sse("meta", {"route": routed.route})
                yield _sse("delta", {"text": routed.reply})
                yield _sse(
                    "done",
                    _observe(routed, message=body.message, stream=True).model_dump(),
                )
                return
            turn = routed
            yield _sse("status", {"text": turn.status})
            yield _sse("meta", {"route": turn.route, "model": model_name})
            pieces: list[str] = []
            result = None
            model_started = time.perf_counter()
            ttft_ms: float | None = None
            try:
                async for delta in client.chat_stream(turn.messages, temperature=body.temperature):
                    if delta.text:
                        if turn.route != "rag_compare" and ttft_ms is None:
                            ttft_ms = _elapsed_ms(model_started)
                            performance["timing_ms"]["model_ttft"] = ttft_ms
                            performance["timing_ms"]["end_to_end_ttft"] = _elapsed_ms(
                                request_started
                            )
                        pieces.append(delta.text)
                        if turn.route != "rag_compare":
                            yield _sse("delta", {"text": delta.text})
                            await asyncio.sleep(0)
                    if delta.done:
                        result = delta.result
            finally:
                performance["timing_ms"]["answer_model"] = _elapsed_ms(model_started)
            if result is None:
                raise ModelError("empty stream")
            raw_reply = "".join(pieces) or result.content
            validation_started = time.perf_counter()
            reply, route, validation_trace, comparison = _finalize_reply(
                turn,
                raw_reply,
            )
            performance["timing_ms"]["validation"] = _elapsed_ms(validation_started)
            performance["route"] = route
            if turn.route == "rag_compare" and reply:
                if ttft_ms is None:
                    ttft_ms = _elapsed_ms(model_started)
                    performance["timing_ms"]["model_ttft"] = ttft_ms
                    performance["timing_ms"]["end_to_end_ttft"] = _elapsed_ms(
                        request_started
                    )
                yield _sse("delta", {"text": reply})
                await asyncio.sleep(0)
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
                validation_trace=validation_trace,
                comparison=comparison,
            )
            _finish_performance(
                performance,
                request_started=request_started,
                response=response,
                stream=True,
                session_id=session_id,
                model_name=model_name,
            )
            response = _observe(
                response,
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
            _finish_performance(
                performance,
                request_started=request_started,
                response=None,
                stream=True,
                session_id=session_id,
                model_name=model_name,
                status="error",
                error_type=f"HTTP_{exc.status_code}",
            )
            yield _sse("error", {"detail": _error_detail(exc.detail), "status": exc.status_code})
        except ModelError as exc:
            _finish_performance(
                performance,
                request_started=request_started,
                response=None,
                stream=True,
                session_id=session_id,
                model_name=model_name,
                status="error",
                error_type=type(exc).__name__,
            )
            logger.warning("POST /chat/stream model error: %s", exc)
            yield _sse("error", {"detail": str(exc), "status": 502})
        except ValueError as exc:
            _finish_performance(
                performance,
                request_started=request_started,
                response=None,
                stream=True,
                session_id=session_id,
                model_name=model_name,
                status="error",
                error_type=type(exc).__name__,
            )
            logger.error("POST /chat/stream config error: %s", exc)
            yield _sse("error", {"detail": str(exc), "status": 500})
        except Exception as exc:
            _finish_performance(
                performance,
                request_started=request_started,
                response=None,
                stream=True,
                session_id=session_id,
                model_name=model_name,
                status="error",
                error_type=type(exc).__name__,
            )
            logger.exception("POST /chat/stream failed")
            yield _sse("error", {"detail": "stream failed", "status": 500})

    return StreamingResponse(events(), media_type="text/event-stream", headers=SSE_HEADERS)
