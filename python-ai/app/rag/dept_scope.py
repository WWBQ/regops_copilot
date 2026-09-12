"""部门数据域：与 Java DeptAcl / Python mock 对齐。会话 PDF 不受部门裁剪。"""

from __future__ import annotations

from app.rag.company_scope import (
    company_code_from_doc_id,
    filter_doc_ids_by_question,
    is_session_doc,
)

DEPT_COMPANY_ALLOW: dict[str, frozenset[str]] = {
    "research": frozenset({"002594", "601633"}),
    "rm": frozenset({"000333", "000651"}),
    "compliance": frozenset(
        {"002594", "601633", "000333", "000651", "600031", "300750", "600519"}
    ),
}

DEFAULT_CORPUS_DOC_IDS: tuple[str, ...] = (
    "002594_2024",
    "002594_2023",
    "601633_2024",
    "601633_2023",
    "000333_2024",
    "000333_2023",
    "000651_2024",
    "000651_2023",
    "600031_2024",
    "600031_2023",
    "300750_2024",
    "600519_2024",
)


def normalize_dept(dept: str | None) -> str | None:
    if dept is None:
        return None
    text = dept.strip().lower()
    return text or None


def depts_for_company(company_code: str | None) -> list[str]:
    if not company_code:
        return []
    return sorted(dept for dept, allow in DEPT_COMPANY_ALLOW.items() if company_code in allow)


def filter_doc_ids_for_dept(doc_ids: list[str], dept: str | None) -> list[str]:
    """未登录（dept 为空）不裁剪；未知部门只保留会话文档。"""
    resolved = normalize_dept(dept)
    if not resolved:
        return list(doc_ids)
    allow = DEPT_COMPANY_ALLOW.get(resolved)
    kept: list[str] = []
    for doc_id in doc_ids:
        if is_session_doc(doc_id):
            kept.append(doc_id)
            continue
        if allow is None:
            continue
        code = company_code_from_doc_id(doc_id)
        if code is not None and code in allow:
            kept.append(doc_id)
    return kept


def apply_retrieval_scope(
    doc_ids: list[str],
    question: str,
    dept: str | None = None,
) -> list[str]:
    """先部门、再问题里的公司/年份。不连库，doc_id 形如 002594_2024。"""
    narrowed = filter_doc_ids_for_dept(doc_ids, dept)
    return filter_doc_ids_by_question(narrowed, question)
