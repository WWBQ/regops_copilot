"""RAG：检索 doc_chunks + 组装 prompt + citations（会话文档 + 公司年报库）。"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass

from app.config import get_settings
from app.db.chunk_repository import ChunkHit, search_keyword_chunks, search_similar_chunks
from app.db.connection import get_connection
from app.db.pdf_document_repository import list_company_ready_doc_ids
from app.db.rag_trace_repository import insert_rag_trace
from app.db.session_repository import get_ready_doc_ids
from app.documents.service import DocumentService
from app.documents.titles import resolve_document_titles
from app.ingest.embeddings import embed_text
from app.rag.company_scope import filter_doc_ids_for_question
from app.rag.reranker import rerank_with_cross_encoder
from app.rag.retrieval import (
    apply_page_diversity,
    extract_keyword_terms,
    filter_substantive_hits,
    hit_passes_relevance_threshold,
    reciprocal_rank_fusion,
)
from app.rag.trace import RagPrepareResult, RagTrace

logger = logging.getLogger(__name__)

RAG_SYSTEM_PROMPT = (
    "你是 RegOps Copilot 合规助手。请结合用户提供的年报/公告片段回答合规与财务问题。\n"
    "若片段中没有足够依据，请明确说明「文档中未找到相关信息」，不要编造数字或事实。\n"
    "引用片段中的事实或数字时，必须在对应句子末尾标注角标 [1]、[2]（数字与上文「片段N」一致）。\n"
    "不要单独列出「引用来源」或大段摘录；只在正文行内标注角标。"
)

_CHITCHAT_RE = re.compile(
    r"^(?:你好|您好|嗨|hi|hello|hey|在吗|在不在|谢谢|多谢|感谢|再见|拜拜|"
    r"早上好|下午好|晚上好|ok|好的|嗯|哦|啊|呀|么|呢|介绍一下|你是谁|你能做什么|"
    r"帮助|怎么用|如何使用)[!?！？。．\.…~～\s]*$",
    re.IGNORECASE,
)

_RAG_INTENT_RE = re.compile(
    r"(?:营收|利润|净利|亏损|收入|成本|费用|负债|资产|现金流|市值|股息|分红|"
    r"研发|投入|"
    r"毛利率|净利率|ROE|ROA|EPS|"
    r"合规|监管|违法|违规|处罚|风险|内控|披露|审计|"
    r"年报|半年报|季报|公告|招股书|"
    r"股东|董事|高管|关联交易|并购|重组|"
    r"车型|新车|新品|推出|上市|销量|品牌|"
    r"同比|环比|增长|下降|占比|比例|"
    r"多少|几(?:个|家|倍|%|％)|是否|何时|哪家|哪个|"
    r"[\d]+\s*(?:年|亿|万|%|％))",
    re.IGNORECASE,
)


def _normalize_question_for_intent(question: str) -> str:
    text = re.sub(r"(\d+)\s+年", r"\1年", question.strip())
    return re.sub(r"024年", "2024年", text)


def should_use_rag(question: str, *, session_has_ready_docs: bool = False) -> bool:
    text = _normalize_question_for_intent(question)
    if not text:
        return False
    if _CHITCHAT_RE.match(text):
        return False
    if len(text) <= 4 and not re.search(r"[\dA-Za-z]", text):
        return False
    if _RAG_INTENT_RE.search(text):
        return True
    if session_has_ready_docs and len(text) >= 10:
        return True
    return False


def _session_has_ready_docs(session_id: str | None) -> bool:
    if not session_id:
        return False
    with get_connection() as conn:
        return len(get_ready_doc_ids(conn, session_id)) > 0


@dataclass(frozen=True)
class Citation:
    doc_id: str
    page: int
    snippet: str
    viewer_url: str | None
    title: str | None = None


@dataclass(frozen=True)
class RagAnswer:
    messages: list[dict[str, str]]
    citations: list[Citation]
    doc_ids: list[str]


def collect_rag_doc_ids(session_id: str | None) -> list[str]:
    with get_connection() as conn:
        ordered: list[str] = []
        if session_id:
            ordered.extend(get_ready_doc_ids(conn, session_id))
        ordered.extend(list_company_ready_doc_ids(conn))
    seen: set[str] = set()
    unique: list[str] = []
    for doc_id in ordered:
        if doc_id not in seen:
            seen.add(doc_id)
            unique.append(doc_id)
    return unique


def _max_vector_score(hits: list[ChunkHit]) -> float | None:
    scores = [hit.vector_score for hit in hits if hit.vector_score is not None]
    return max(scores) if scores else None


def retrieve_hits_with_trace(
    *,
    question: str,
    doc_ids: list[str],
    top_k: int = 5,
) -> tuple[list[ChunkHit], dict]:
    """Hybrid 检索并返回 pipeline 明细（供 trace 持久化）。"""
    pipeline: dict = {
        "top_k": top_k,
        "vector_top": [],
        "keyword_top": [],
        "rerank_enabled": False,
        "rerank_fallback": False,
        "timing_ms": {},
    }
    if not doc_ids:
        return [], pipeline

    settings = get_settings()
    vector_fetch_k = max(settings.rag_vector_fetch_k, top_k * 10)
    keyword_top_k = max(settings.rag_keyword_top_k, top_k * 3)
    keyword_terms = extract_keyword_terms(question)
    pipeline["keyword_terms"] = keyword_terms
    pipeline["vector_fetch_k"] = vector_fetch_k
    pipeline["keyword_top_k"] = keyword_top_k

    t0 = time.perf_counter()
    query_vector = embed_text(question)
    pipeline["timing_ms"]["embed"] = round((time.perf_counter() - t0) * 1000, 2)

    with get_connection() as conn:
        t1 = time.perf_counter()
        vector_hits = search_similar_chunks(conn, query_vector, doc_ids, top_k=vector_fetch_k)
        pipeline["timing_ms"]["vector_search"] = round((time.perf_counter() - t1) * 1000, 2)

        keyword_hits: list[ChunkHit] = []
        if keyword_terms:
            t2 = time.perf_counter()
            keyword_hits = search_keyword_chunks(
                conn, doc_ids, keyword_terms, top_k=keyword_top_k
            )
            pipeline["timing_ms"]["keyword_search"] = round((time.perf_counter() - t2) * 1000, 2)

    vector_substantive = filter_substantive_hits(vector_hits)
    keyword_substantive = filter_substantive_hits(keyword_hits)
    pipeline["vector_hit_count"] = len(vector_substantive)
    pipeline["keyword_hit_count"] = len(keyword_substantive)
    pipeline["vector_top"] = RagTrace.from_hits(vector_substantive, limit=5)
    pipeline["keyword_top"] = RagTrace.from_hits(keyword_substantive, limit=5)

    if keyword_substantive:
        fused = reciprocal_rank_fusion(
            vector_substantive,
            keyword_substantive,
            k=settings.rag_rrf_k,
            weights=[settings.rag_vector_rrf_weight, settings.rag_keyword_rrf_weight],
        )
    else:
        fused = vector_substantive

    candidates = fused[: max(settings.rag_rerank_candidates, top_k)]
    pipeline["rerank_enabled"] = settings.rag_rerank_enabled and bool(candidates)

    if settings.rag_rerank_enabled and candidates:
        try:
            t3 = time.perf_counter()
            reranked = rerank_with_cross_encoder(
                question,
                candidates,
                model_name=settings.rag_rerank_model,
                top_k=len(candidates),
            )
            pipeline["timing_ms"]["rerank"] = round((time.perf_counter() - t3) * 1000, 2)
            hits = apply_page_diversity(
                reranked,
                top_k=top_k,
                max_per_page=settings.rag_max_chunks_per_page,
            )
            return hits, pipeline
        except Exception:
            pipeline["rerank_fallback"] = True
            logger.exception("cross-encoder rerank failed, falling back to RRF order")

    hits = apply_page_diversity(
        candidates,
        top_k=top_k,
        max_per_page=settings.rag_max_chunks_per_page,
    )
    return hits, pipeline


def retrieve_hits_for_docs(
    *,
    question: str,
    doc_ids: list[str],
    top_k: int = 5,
) -> list[ChunkHit]:
    hits, _ = retrieve_hits_with_trace(question=question, doc_ids=doc_ids, top_k=top_k)
    return hits


def build_rag_answer(
    *,
    question: str,
    hits: list[ChunkHit],
    doc_ids: list[str],
    document_service: DocumentService,
) -> RagAnswer:
    if not hits:
        return RagAnswer(
            messages=[{"role": "user", "content": question}],
            citations=[],
            doc_ids=doc_ids,
        )

    context_parts: list[str] = []
    citations: list[Citation] = []
    unique_doc_ids = list(dict.fromkeys(hit.doc_id for hit in hits))
    with get_connection() as conn:
        doc_titles = resolve_document_titles(conn, unique_doc_ids)

    for index, hit in enumerate(hits, start=1):
        page = int(hit.metadata.get("page") or 1)
        context_parts.append(
            f"[片段{index} doc_id={hit.doc_id} 第{page}页 score={hit.score:.3f}]\n{hit.content}"
        )
        snippet = hit.content[:240] + ("…" if len(hit.content) > 240 else "")
        try:
            viewer_url = document_service.viewer_url(hit.doc_id, page=page)
        except Exception:
            logger.warning("viewer_url failed doc_id=%s", hit.doc_id)
            viewer_url = None
        citations.append(
            Citation(
                doc_id=hit.doc_id,
                page=page,
                snippet=snippet,
                viewer_url=viewer_url,
                title=doc_titles.get(hit.doc_id),
            )
        )

    user_content = (
        "以下是与问题相关的文档片段（编号用于正文角标 [1][2]…）：\n\n"
        + "\n\n".join(context_parts)
        + f"\n\n用户问题：{question}\n"
        "请用中文回答；引用时在句末标注 [片段编号] 角标，勿输出引用列表。"
    )
    messages = [
        {"role": "system", "content": RAG_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
    return RagAnswer(messages=messages, citations=citations, doc_ids=doc_ids)


def save_rag_trace(trace: RagTrace) -> int | None:
    settings = get_settings()
    if not settings.rag_trace_enabled:
        return None
    try:
        with get_connection() as conn:
            row_id = insert_rag_trace(conn, trace)
            conn.commit()
            return row_id
    except Exception:
        logger.exception("failed to persist rag trace outcome=%s", trace.outcome)
        return None


def prepare_chat_rag(
    *,
    session_id: str | None,
    question: str,
    document_service: DocumentService,
    top_k: int | None = None,
    min_score: float | None = None,
    request_id: str | None = None,
    persist_trace: bool = True,
) -> RagPrepareResult:
    """统一 RAG：会话 PDF + 公司年报库；返回答案与 trace。"""
    settings = get_settings()
    resolved_top_k = top_k if top_k is not None else settings.rag_top_k
    resolved_min_score = min_score if min_score is not None else settings.rag_min_score
    started = time.perf_counter()

    trace = RagTrace(
        question=question,
        outcome="no_intent",
        request_id=request_id,
        session_id=session_id,
        min_score_threshold=resolved_min_score,
    )

    if not should_use_rag(question, session_has_ready_docs=_session_has_ready_docs(session_id)):
        logger.info("RAG skipped no-intent question_len=%d session_id=%s", len(question.strip()), session_id)
        trace.outcome = "no_intent"
        trace.total_rag_ms = round((time.perf_counter() - started) * 1000, 2)
        if persist_trace:
            save_rag_trace(trace)
        return RagPrepareResult(answer=None, trace=trace)

    doc_ids = collect_rag_doc_ids(session_id)
    if not doc_ids:
        trace.outcome = "no_docs"
        trace.total_rag_ms = round((time.perf_counter() - started) * 1000, 2)
        if persist_trace:
            save_rag_trace(trace)
        return RagPrepareResult(answer=None, trace=trace)

    with get_connection() as conn:
        doc_ids = filter_doc_ids_for_question(conn, doc_ids, question)
    trace.scoped_doc_ids = doc_ids

    hits, pipeline = retrieve_hits_with_trace(
        question=question, doc_ids=doc_ids, top_k=resolved_top_k
    )
    trace.keyword_terms = pipeline.get("keyword_terms") or extract_keyword_terms(question)
    trace.vector_hit_count = int(pipeline.get("vector_hit_count") or 0)
    trace.keyword_hit_count = int(pipeline.get("keyword_hit_count") or 0)
    trace.pipeline = pipeline

    relevant_hits = [hit for hit in hits if hit_passes_relevance_threshold(hit, resolved_min_score)]
    trace.max_vector_score = _max_vector_score(hits)
    trace.final_hit_count = len(relevant_hits)
    trace.hits = RagTrace.from_hits(relevant_hits if relevant_hits else hits, limit=resolved_top_k)
    trace.total_rag_ms = round((time.perf_counter() - started) * 1000, 2)

    if not relevant_hits:
        logger.info(
            "RAG skipped session_id=%s question_len=%d max_vector=%s threshold=%.3f",
            session_id,
            len(question),
            trace.max_vector_score,
            resolved_min_score,
        )
        trace.outcome = "low_score"
        if persist_trace:
            save_rag_trace(trace)
        return RagPrepareResult(answer=None, trace=trace)

    answer = build_rag_answer(
        question=question,
        hits=relevant_hits,
        doc_ids=doc_ids,
        document_service=document_service,
    )
    trace.outcome = "ok"
    trace.rag_used = True
    if persist_trace:
        save_rag_trace(trace)
    return RagPrepareResult(answer=answer, trace=trace)


def prepare_session_rag(
    *,
    session_id: str,
    question: str,
    document_service: DocumentService,
    top_k: int | None = None,
    min_score: float | None = None,
) -> RagPrepareResult:
    return prepare_chat_rag(
        session_id=session_id,
        question=question,
        document_service=document_service,
        top_k=top_k,
        min_score=min_score,
    )
