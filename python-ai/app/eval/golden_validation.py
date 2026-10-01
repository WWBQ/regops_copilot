"""RAG 检索黄金集的结构、语料页码与证据关键词校验。"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from app.db.connection import get_connection

REQUIRED_ITEM_FIELDS = frozenset(
    {
        "id",
        "category",
        "question",
        "doc_id",
        "company_code",
        "report_year",
        "gold_pages",
        "probe_keywords",
    }
)


def _match_text(value: str) -> str:
    """忽略 PDF 表格抽取插入的空白，避免把“净 额”误判为不匹配。"""
    return re.sub(r"\s+", "", value.casefold())


def load_json_without_duplicate_keys(path: Path) -> tuple[dict[str, Any], list[str]]:
    duplicates: list[str] = []

    def build_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                duplicates.append(key)
            result[key] = value
        return result

    payload = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=build_object)
    if not isinstance(payload, dict):
        raise ValueError("golden root must be an object")
    return payload, duplicates


def _corpus_pages(doc_ids: list[str]) -> dict[str, dict[int, str]]:
    pages: dict[str, dict[int, list[str]]] = defaultdict(lambda: defaultdict(list))
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT doc_id, (metadata->>'page')::int AS page, content
                FROM doc_chunks
                WHERE doc_id = ANY(%s)
                  AND NULLIF(metadata->>'page', '') IS NOT NULL
                ORDER BY doc_id, page, chunk_index
                """,
                (doc_ids,),
            )
            for doc_id, page, content in cur.fetchall():
                if page is not None:
                    pages[str(doc_id)][int(page)].append(str(content or ""))
    return {
        doc_id: {page: "\n".join(chunks) for page, chunks in doc_pages.items()}
        for doc_id, doc_pages in pages.items()
    }


def validate_rag_retrieval_golden(
    path: Path,
    *,
    expected_count: int = 100,
    check_corpus: bool = True,
) -> dict[str, Any]:
    payload, duplicate_json_keys = load_json_without_duplicate_keys(path)
    items = list(payload.get("items") or [])
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    if duplicate_json_keys:
        errors.append({"code": "duplicate_json_key", "keys": duplicate_json_keys})
    if len(items) != expected_count:
        errors.append(
            {"code": "unexpected_item_count", "expected": expected_count, "actual": len(items)}
        )

    ids = [str(item.get("id") or "") for item in items]
    duplicate_ids = sorted(item_id for item_id, count in Counter(ids).items() if count > 1)
    if duplicate_ids:
        errors.append({"code": "duplicate_item_id", "ids": duplicate_ids})

    category_counts: Counter[str] = Counter()
    valid_items: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        item_id = str(item.get("id") or f"index-{index}")
        missing = sorted(REQUIRED_ITEM_FIELDS - set(item))
        if missing:
            errors.append({"code": "missing_fields", "id": item_id, "fields": missing})
            continue
        category_counts[str(item["category"])] += 1
        expected_doc_id = f"{item['company_code']}_{item['report_year']}"
        if item["doc_id"] != expected_doc_id:
            errors.append(
                {
                    "code": "doc_scope_mismatch",
                    "id": item_id,
                    "expected": expected_doc_id,
                    "actual": item["doc_id"],
                }
            )
        pages = item.get("gold_pages") or []
        if not pages or any(not isinstance(page, int) or page <= 0 for page in pages):
            errors.append({"code": "invalid_gold_pages", "id": item_id, "pages": pages})
        if len(pages) != len(set(pages)):
            errors.append({"code": "duplicate_gold_page", "id": item_id, "pages": pages})
        keywords = [str(value).strip() for value in item.get("probe_keywords") or []]
        if not any(keywords):
            errors.append({"code": "missing_probe_keywords", "id": item_id})
        valid_items.append(item)

    declared_counts = payload.get("category_counts") or {}
    if dict(category_counts) != declared_counts:
        errors.append(
            {
                "code": "category_count_mismatch",
                "declared": declared_counts,
                "actual": dict(category_counts),
            }
        )

    corpus_checked = False
    doc_stats: dict[str, dict[str, int]] = {}
    if check_corpus and valid_items:
        corpus_checked = True
        doc_ids = sorted({str(item["doc_id"]) for item in valid_items})
        corpus = _corpus_pages(doc_ids)
        for doc_id in doc_ids:
            doc_stats[doc_id] = {"page_count": len(corpus.get(doc_id) or {})}
            if not corpus.get(doc_id):
                errors.append({"code": "document_not_indexed", "doc_id": doc_id})

        for item in valid_items:
            item_id = str(item["id"])
            page_text = corpus.get(str(item["doc_id"])) or {}
            gold_pages = [int(page) for page in item["gold_pages"]]
            missing_pages = [page for page in gold_pages if page not in page_text]
            if missing_pages:
                errors.append(
                    {"code": "gold_page_not_indexed", "id": item_id, "pages": missing_pages}
                )
            keywords = [_match_text(str(value)) for value in item["probe_keywords"] if str(value)]
            supported_pages = [
                page
                for page in gold_pages
                if any(keyword in _match_text(page_text.get(page, "")) for keyword in keywords)
            ]
            if not supported_pages:
                errors.append(
                    {
                        "code": "no_keyword_evidence_on_gold_pages",
                        "id": item_id,
                        "pages": gold_pages,
                    }
                )
            unsupported = [page for page in gold_pages if page not in supported_pages and page in page_text]
            if unsupported:
                warnings.append(
                    {
                        "code": "gold_page_needs_manual_review",
                        "id": item_id,
                        "pages": unsupported,
                    }
                )

    return {
        "status": "passed" if not errors else "failed",
        "file": str(path),
        "item_count": len(items),
        "category_counts": dict(category_counts),
        "corpus_checked": corpus_checked,
        "documents": doc_stats,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
    }
