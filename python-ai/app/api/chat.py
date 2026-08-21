import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_document_service, get_settings_dep
from app.config import Settings
from app.db.connection import get_connection
from app.db.session_repository import list_session_documents, session_exists
from app.documents.service import DocumentService
from app.models.base import ModelError
from app.models.factory import get_llm_client, list_available_models
from app.rag.service import collect_rag_doc_ids, prepare_chat_rag
from app.schemas.chat import ChatRequest, ChatResponse, Citation

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)

GENERAL_CHAT_SYSTEM = (
    "你是 RegOps Copilot 合规助手。"
    "对寒暄请用一两句话简短回复，不要引用文档、不要罗列引用来源、不要主动展开长篇说明。"
    "若用户尚未提出具体问题，可简要说明可协助查询合规、监管或年报财务信息。"
)


def _valid_session_id(session_id: str | None) -> str | None:
    if not session_id:
        return None
    try:
        return str(UUID(session_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid session_id") from exc


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


@router.post("", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    settings: Annotated[Settings, Depends(get_settings_dep)],
    document_service: Annotated[DocumentService, Depends(get_document_service)],
) -> ChatResponse:
    session_id = _valid_session_id(body.session_id)
    model_name = _resolve_model(body, settings)
    client = get_llm_client(settings, model=model_name)

    citations: list[Citation] = []
    rag_used = False
    messages: list[dict[str, str]]

    if body.use_rag:
        pending: list = []
        if session_id:
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
            )

        rag = prepare_chat_rag(
            session_id=session_id,
            question=body.message,
            document_service=document_service,
        )
        if rag is not None:
            messages = rag.messages
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
        else:
            messages = [
                {"role": "system", "content": GENERAL_CHAT_SYSTEM},
                {"role": "user", "content": body.message},
            ]
    else:
        messages = [
            {"role": "system", "content": GENERAL_CHAT_SYSTEM},
            {"role": "user", "content": body.message},
        ]

    try:
        result = await client.chat_with_usage(messages, temperature=body.temperature)
    except ModelError as exc:
        logger.warning("POST /chat model error: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        logger.error("POST /chat config error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    logger.info(
        "POST /chat ok model=%s session_id=%s rag_used=%s citations=%d tokens=%d latency_ms=%.0f",
        model_name,
        session_id,
        rag_used,
        len(citations),
        result.total_tokens,
        result.latency_ms,
    )
    return ChatResponse(
        reply=result.content,
        model=model_name,
        citations=citations,
        session_id=session_id,
        rag_used=rag_used,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        total_tokens=result.total_tokens,
        latency_ms=result.latency_ms,
    )
