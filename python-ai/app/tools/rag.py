"""rag_search：复用 prepare_chat_rag，低分拒答，引用必须有 doc_id+页。"""

from __future__ import annotations

from app.api.deps import get_document_service
from app.config import get_settings
from app.documents.service import DocumentService
from app.rag.service import prepare_chat_rag
from app.schemas.tools import RagSearchArgs, RagSearchHit, RagSearchResult

_OUTCOME_MSG = {
    "ok": "检索到可引用片段。",
    "no_intent": "问题不像叙述检索，未查年报。",
    "no_docs": "没有可检索文档。",
    "low_score": "检索分低于阈值，拒答，不得用模型补出处。",
    "pending_docs": "文档尚未就绪。",
}


def run_rag_search(
    args: RagSearchArgs,
    *,
    document_service: DocumentService | None = None,
    persist_trace: bool = False,
) -> RagSearchResult:
    service = document_service or get_document_service(get_settings())
    prepared = prepare_chat_rag(
        session_id=args.session_id,
        question=args.question,
        document_service=service,
        persist_trace=persist_trace,
    )
    outcome = prepared.trace.outcome
    citations: list[RagSearchHit] = []
    if prepared.answer is not None:
        for cite in prepared.answer.citations:
            if not cite.doc_id or cite.page < 1:
                continue
            citations.append(
                RagSearchHit(
                    doc_id=cite.doc_id,
                    page=cite.page,
                    snippet=cite.snippet,
                    title=cite.title,
                    viewer_url=cite.viewer_url,
                )
            )
    ok = outcome == "ok" and bool(citations)
    if outcome == "ok" and not citations:
        outcome = "low_score"
    return RagSearchResult(
        ok=ok,
        stop=not ok,
        outcome=outcome,
        citations=citations,
        message=_OUTCOME_MSG.get(outcome, "检索未完成。"),
    )


def rag_search_description() -> str:
    return (
        "对年报或会话 PDF 做叙述检索，返回带 doc_id 和页码的引用。"
        "低分、无文档或没有页码时 ok=false 且 stop=true，不得编造出处。"
        "不要用它查精确财务数字，数字走 lookup_metric。"
    )
