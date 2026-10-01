"""多公司叙述性比较：按公司隔离检索，证据门通过后再交给模型综合。"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from app.asknum.aliases import company_aliases
from app.asknum.slots import AsknumSlots, company_display_name
from app.config import get_settings
from app.db.chunk_repository import ChunkHit
from app.db.connection import get_connection
from app.documents.service import DocumentService
from app.documents.titles import resolve_document_titles
from app.prompts.library import render_system
from app.rag.company_scope import (
    company_code_from_doc_id,
    is_session_doc,
    report_year_from_doc_id,
)
from app.rag.dept_scope import filter_doc_ids_for_dept
from app.rag.service import (
    Citation,
    RagAnswer,
    collect_rag_doc_ids,
    context_content_for_hit,
    retrieve_relevant_hits_for_docs,
)

logger = logging.getLogger(__name__)

_COMPARE_WORDS_RE = re.compile(
    r"(?:谁的|哪家的|谁|哪家|哪个|更高|更低|更好|更差|更多|更少|"
    r"更严重|更突出|比较|对比|相比|分别)",
    re.IGNORECASE,
)
_JOINERS_RE = re.compile(r"^[\s、，,和与及或]+|[\s、，,和与及或]+$")


@dataclass(frozen=True)
class CompanyEvidence:
    company_code: str
    company_name: str
    doc_ids: tuple[str, ...]
    hits: tuple[ChunkHit, ...] = ()
    status: str = "ok"
    reason: str | None = None
    pipeline: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ComparisonPrepareResult:
    answer: RagAnswer | None
    blocked_reply: str | None
    citations: tuple[Citation, ...]
    selected_years: tuple[int, ...]
    evidences: tuple[CompanyEvidence, ...]


@dataclass(frozen=True)
class ComparisonScopePlan:
    """多公司比较的确定性检索范围；不依赖向量库和大模型。"""

    selected_years: tuple[int, ...]
    company_doc_ids: dict[str, tuple[str, ...]]
    missing: dict[str, str]


def _search_dimension(question: str, company_codes: tuple[str, ...]) -> str:
    text = question
    try:
        aliases = company_aliases()
    except Exception:
        aliases = {}
    candidates = [
        alias
        for alias, code in aliases.items()
        if code in company_codes
    ] + list(company_codes)
    for token in sorted(set(candidates), key=len, reverse=True):
        text = re.sub(re.escape(token), " ", text, flags=re.IGNORECASE)
    text = _COMPARE_WORDS_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = _JOINERS_RE.sub("", text).strip("？?。 ")
    return text or question.strip()


def _document_matrix(
    doc_ids: list[str],
    company_codes: tuple[str, ...],
) -> dict[str, dict[int, list[str]]]:
    matrix: dict[str, dict[int, list[str]]] = {code: {} for code in company_codes}
    for doc_id in doc_ids:
        if is_session_doc(doc_id):
            continue
        code = company_code_from_doc_id(doc_id)
        year = report_year_from_doc_id(doc_id)
        if code not in matrix or year is None:
            continue
        matrix[code].setdefault(year, []).append(doc_id)
    return matrix


def _select_years(
    matrix: dict[str, dict[int, list[str]]],
    slots: AsknumSlots,
) -> tuple[tuple[int, ...], dict[str, str]]:
    if not slots.year_defaulted:
        selected = tuple(sorted(set(slots.years)))
        missing: dict[str, str] = {}
        for code in slots.company_codes:
            absent = [year for year in selected if year not in matrix.get(code, {})]
            if absent:
                shown = "、".join(str(year) for year in absent)
                missing[code] = f"当前可访问资料中缺少 {shown} 年对应报告"
        return selected, missing

    available_sets = [set(matrix.get(code, {})) for code in slots.company_codes]
    common = set.intersection(*available_sets) if available_sets else set()
    if common:
        return (max(common),), {}
    return (), {
        code: "当前可访问资料中没有所有公司共同覆盖的报告年度"
        for code in slots.company_codes
    }


def plan_comparison_scope(
    *,
    slots: AsknumSlots,
    all_doc_ids: list[str],
    dept: str | None,
) -> ComparisonScopePlan:
    """先做 ACL 和共同期间校验，再为每家公司生成完全隔离的文档集合。"""
    accessible = filter_doc_ids_for_dept(all_doc_ids, dept)
    matrix = _document_matrix(accessible, slots.company_codes)
    selected_years, missing = _select_years(matrix, slots)
    company_doc_ids = {
        code: tuple(
            doc_id
            for year in selected_years
            for doc_id in matrix.get(code, {}).get(year, [])
        )
        for code in slots.company_codes
    }
    for code, doc_ids in company_doc_ids.items():
        if not doc_ids and code not in missing:
            missing[code] = "当前可访问资料中没有同期间报告"
    return ComparisonScopePlan(
        selected_years=selected_years,
        company_doc_ids=company_doc_ids,
        missing=missing,
    )


def _blocked_reply(
    evidences: list[CompanyEvidence],
    selected_years: tuple[int, ...],
) -> str:
    period = "、".join(str(year) for year in selected_years)
    head = "无法直接比较"
    if period:
        head += f"（比较期间：{period} 年）"
    lines = [f"{head}："]
    for evidence in evidences:
        if evidence.status == "ok":
            detail = f"已找到 {len(evidence.hits)} 条有效证据"
        else:
            detail = evidence.reason or "证据不足"
        lines.append(f"- {evidence.company_name}：{detail}。")
    lines.append("任意一家公司证据不足或期间不一致时，系统不会让模型补全，也不输出高低排序。")
    return "\n".join(lines)


def _context_and_citations(
    evidences: list[CompanyEvidence],
    *,
    document_service: DocumentService,
) -> tuple[str, list[Citation]]:
    all_doc_ids = list(
        dict.fromkeys(
            hit.doc_id
            for evidence in evidences
            for hit in evidence.hits
        )
    )
    try:
        with get_connection() as conn:
            titles = resolve_document_titles(conn, all_doc_ids)
    except Exception:
        logger.warning("resolve comparison document titles failed", exc_info=True)
        titles = {doc_id: doc_id for doc_id in all_doc_ids}

    citations: list[Citation] = []
    company_blocks: list[str] = []
    for evidence in evidences:
        rows: list[str] = []
        for hit in evidence.hits:
            index = len(citations) + 1
            page = int(hit.metadata.get("page") or 1)
            rows.append(
                f"[片段{index} doc_id={hit.doc_id} 第{page}页 score={hit.score:.3f}]\n"
                f"{context_content_for_hit(hit)}"
            )
            try:
                viewer_url = document_service.viewer_url(hit.doc_id, page=page)
            except Exception:
                logger.warning("comparison viewer_url failed doc_id=%s", hit.doc_id)
                viewer_url = None
            snippet = hit.content[:240] + ("…" if len(hit.content) > 240 else "")
            citations.append(
                Citation(
                    doc_id=hit.doc_id,
                    page=page,
                    snippet=snippet,
                    viewer_url=viewer_url,
                    title=titles.get(hit.doc_id, hit.doc_id),
                )
            )
        company_blocks.append(
            f"【{evidence.company_name}（{evidence.company_code}）证据】\n"
            + "\n\n".join(rows)
        )
    return "\n\n==========\n\n".join(company_blocks), citations


def prepare_multi_company_rag(
    *,
    question: str,
    slots: AsknumSlots,
    document_service: DocumentService,
    dept: str | None,
) -> ComparisonPrepareResult:
    """对每家公司独立检索；全部通过证据门后，只调用一次模型综合。"""
    if len(slots.company_codes) < 2:
        raise ValueError("multi-company RAG requires at least two companies")

    settings = get_settings()
    all_doc_ids = collect_rag_doc_ids(None)
    plan = plan_comparison_scope(
        slots=slots,
        all_doc_ids=all_doc_ids,
        dept=dept,
    )
    selected_years = plan.selected_years

    evidences: list[CompanyEvidence] = []
    for code in slots.company_codes:
        doc_ids = plan.company_doc_ids[code]
        if code in plan.missing:
            evidences.append(
                CompanyEvidence(
                    company_code=code,
                    company_name=company_display_name(code),
                    doc_ids=doc_ids,
                    status="no_docs",
                    reason=plan.missing[code],
                )
            )
        else:
            evidences.append(
                CompanyEvidence(
                    company_code=code,
                    company_name=company_display_name(code),
                    doc_ids=doc_ids,
                    status="scope_ready",
                    reason="同期间报告可用；因其他公司范围不完整，本次未进入检索",
                )
            )
    if plan.missing:
        return ComparisonPrepareResult(
            answer=None,
            blocked_reply=_blocked_reply(evidences, selected_years),
            citations=(),
            selected_years=selected_years,
            evidences=tuple(evidences),
        )

    dimension = _search_dimension(question, slots.company_codes)
    period = "、".join(str(year) for year in selected_years)
    evidences = []
    for code in slots.company_codes:
        company_name = company_display_name(code)
        doc_ids = plan.company_doc_ids[code]
        query = f"{company_name} {period}年 {dimension}".strip()
        try:
            hits, pipeline = retrieve_relevant_hits_for_docs(
                question=query,
                doc_ids=list(doc_ids),
                top_k=settings.rag_compare_top_k_per_company,
                min_score=settings.rag_min_score,
                rerank_candidates=settings.rag_compare_rerank_candidates,
            )
        except Exception:
            logger.exception("company comparison retrieval failed company=%s", code)
            evidences.append(
                CompanyEvidence(
                    company_code=code,
                    company_name=company_name,
                    doc_ids=doc_ids,
                    status="retrieval_error",
                    reason="检索失败",
                )
            )
            continue
        status = "ok" if len(hits) >= settings.rag_compare_min_hits_per_company else "low_score"
        reason = None if status == "ok" else "没有达到相关性阈值的直接证据"
        evidences.append(
            CompanyEvidence(
                company_code=code,
                company_name=company_name,
                doc_ids=doc_ids,
                hits=tuple(hits),
                status=status,
                reason=reason,
                pipeline=pipeline,
            )
        )

    context, citations = _context_and_citations(
        evidences,
        document_service=document_service,
    )
    if any(item.status != "ok" for item in evidences):
        return ComparisonPrepareResult(
            answer=None,
            blocked_reply=_blocked_reply(evidences, selected_years),
            citations=tuple(citations),
            selected_years=selected_years,
            evidences=tuple(evidences),
        )

    user_content = (
        f"比较期间：{period} 年。以下证据已按公司隔离：\n\n{context}\n\n"
        f"原始问题：{question}\n"
        "请分别陈述每家公司的证据，再基于同一比较维度给出结论；引用使用片段角标。"
    )
    answer = RagAnswer(
        messages=[
            {"role": "system", "content": render_system("rag.compare")},
            {"role": "user", "content": user_content},
        ],
        citations=citations,
        doc_ids=list(dict.fromkeys(doc_id for item in evidences for doc_id in item.doc_ids)),
    )
    return ComparisonPrepareResult(
        answer=answer,
        blocked_reply=None,
        citations=tuple(citations),
        selected_years=selected_years,
        evidences=tuple(evidences),
    )
