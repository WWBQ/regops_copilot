"""RAG：检索 doc_chunks + 组装 prompt + citations（会话文档 + 公司年报库）。"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.db.chunk_repository import ChunkHit, search_keyword_chunks, search_similar_chunks
from app.db.connection import get_connection
from app.db.pdf_document_repository import list_company_ready_doc_ids
from app.db.session_repository import get_ready_doc_ids
from app.documents.service import DocumentService
from app.documents.titles import resolve_document_titles
from app.config import get_settings
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

logger = logging.getLogger(__name__)

RAG_SYSTEM_PROMPT = (
    "你是 RegOps Copilot 合规助手。请结合用户提供的年报/公告片段回答合规与财务问题。\n"
    "若片段中没有足够依据，请明确说明「文档中未找到相关信息」，不要编造数字或事实。\n"
    "引用片段中的事实或数字时，必须在对应句子末尾标注角标 [1]、[2]（数字与上文「片段N」一致）。\n"
    "不要单独列出「引用来源」或大段摘录；只在正文行内标注角标。"
)

# 寒暄/无实质问题时跳过 RAG，避免无关引用
_CHITCHAT_RE = re.compile(
    r"^(?:你好|您好|嗨|hi|hello|hey|在吗|在不在|谢谢|多谢|感谢|再见|拜拜|"
    r"早上好|下午好|晚上好|ok|好的|嗯|哦|啊|呀|么|呢|介绍一下|你是谁|你能做什么|"
    r"帮助|怎么用|如何使用)[!?！？。．\.…~～\s]*$",
    re.IGNORECASE,
)

# 明显需要查文档/财务时才走 RAG（公司语料库）
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
    """归一化空格/常见年份笔误，避免「2024 年」漏触发 RAG。"""
    text = re.sub(r"(\d+)\s+年", r"\1年", question.strip())
    text = re.sub(r"024年", "2024年", text)
    return text


def should_use_rag(question: str, *, session_has_ready_docs: bool = False) -> bool:
    """仅在有文档检索意图，或会话内已上传 PDF 且问题足够具体时走 RAG。"""
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
    """会话上传 PDF 优先，再叠加公司年报库（pdf_document ready）。"""
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


def retrieve_hits_for_docs(
    *,
    question: str,
    doc_ids: list[str],
    top_k: int = 5,
) -> list[ChunkHit]:
    """Hybrid 检索：向量语义召回 + 问题词关键词召回，RRF 融合后取 top_k。"""
    if not doc_ids:
        return []
    settings = get_settings()
    vector_fetch_k = max(settings.rag_vector_fetch_k, top_k * 10)
    keyword_top_k = max(settings.rag_keyword_top_k, top_k * 3)

    query_vector = embed_text(question)
    keyword_terms = extract_keyword_terms(question)
    with get_connection() as conn:
        vector_hits = search_similar_chunks(conn, query_vector, doc_ids, top_k=vector_fetch_k)
        keyword_hits = (
            search_keyword_chunks(conn, doc_ids, keyword_terms, top_k=keyword_top_k)
            if keyword_terms
            else []
        )

    vector_substantive = filter_substantive_hits(vector_hits)
    keyword_substantive = filter_substantive_hits(keyword_hits)

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
    if settings.rag_rerank_enabled and candidates:
        try:
            reranked = rerank_with_cross_encoder(
                question,
                candidates,
                model_name=settings.rag_rerank_model,
                top_k=len(candidates),
            )
            return apply_page_diversity(
                reranked,
                top_k=top_k,
                max_per_page=settings.rag_max_chunks_per_page,
            )
        except Exception:
            logger.exception("cross-encoder rerank failed, falling back to RRF order")
    return apply_page_diversity(
        candidates,
        top_k=top_k,
        max_per_page=settings.rag_max_chunks_per_page,
    )


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


def prepare_chat_rag(
    *,
    session_id: str | None,
    question: str,
    document_service: DocumentService,
    top_k: int | None = None,
    min_score: float | None = None,
) -> RagAnswer | None:
    """统一 RAG：会话 PDF + 公司年报库；分数不达标则走普通对话。"""
    from app.config import get_settings

    if not should_use_rag(question, session_has_ready_docs=_session_has_ready_docs(session_id)):
        logger.info("RAG skipped no-intent question_len=%d session_id=%s", len(question.strip()), session_id)
        return None

    settings = get_settings()
    resolved_top_k = top_k if top_k is not None else settings.rag_top_k
    resolved_min_score = min_score if min_score is not None else settings.rag_min_score

    doc_ids = collect_rag_doc_ids(session_id)
    if not doc_ids:
        return None

    with get_connection() as conn:
        doc_ids = filter_doc_ids_for_question(conn, doc_ids, question)

    hits = retrieve_hits_for_docs(question=question, doc_ids=doc_ids, top_k=resolved_top_k)
    relevant_hits = [hit for hit in hits if hit_passes_relevance_threshold(hit, resolved_min_score)]
    if not relevant_hits:
        logger.info(
            "RAG skipped session_id=%s question_len=%d max_score=%.3f threshold=%.3f",
            session_id,
            len(question),
            hits[0].score if hits else 0.0,
            resolved_min_score,
        )
        return None

    return build_rag_answer(
        question=question,
        hits=relevant_hits,
        doc_ids=doc_ids,
        document_service=document_service,
    )


# 兼容旧名
def prepare_session_rag(
    *,
    session_id: str,
    question: str,
    document_service: DocumentService,
    top_k: int | None = None,
    min_score: float | None = None,
) -> RagAnswer | None:
    return prepare_chat_rag(
        session_id=session_id,
        question=question,
        document_service=document_service,
        top_k=top_k,
        min_score=min_score,
    )
