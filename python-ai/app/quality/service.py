"""质量门与财务事实查询服务。"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.db.connection import get_connection
from app.db.fin_metric_repository import (
    count_fin_metrics,
    list_all_for_gates,
    list_fin_metrics,
    serialize_metric,
    upsert_fin_metrics,
)
from app.db.ingest_job_repository import create_job, update_job_status
from app.documents.titles import COMPANY_DISPLAY_NAMES
from app.ingest.facts import FinancialFact
from app.ingest.financial import (
    DEFAULT_F10_ROOT,
    GOLDEN_CODES,
    GateReport,
    discover_f10_dirs,
    extract_and_gate,
    format_yuan,
)
from app.ingest.reconciliation import run_reconciliation
from app.ingest.validation import CRITICAL_CONCEPTS, validate_fact_evidence


def _table_exists(conn, table_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", (f"public.{table_name}",))
        return cur.fetchone()[0] is not None


def _company_name(code: str | None) -> str:
    if not code:
        return "—"
    return COMPANY_DISPLAY_NAMES.get(code, code)


def report_from_rows(rows) -> dict[str, Any]:
    grouped: dict[tuple[str, str, str], list] = defaultdict(list)
    for row in rows:
        period = row.period.isoformat() if hasattr(row.period, "isoformat") else str(row.period)
        grouped[(row.company_code or "", period, row.scope)].append(row)

    companies: list[dict[str, Any]] = []
    for (company_code, period, scope), items in grouped.items():
        facts = [
            FinancialFact(
                company_code=item.company_code or company_code,
                doc_id=item.doc_id,
                concept=item.concept,
                period=period,
                scope=item.scope,
                statement=item.statement,
                value=item.value_yuan,
                raw_name=item.raw_name or item.concept,
                raw_value=item.raw_value or "",
                source_type=item.source_type,
                currency=item.currency,
                unit_raw=item.unit_raw or "元",
                page_no=item.page_no,
                bbox=item.bbox_json if isinstance(item.bbox_json, list) else None,
                parser=item.parser or "eastmoney_f10",
                status=item.status,
                review_reason=item.review_reason,
                xbrl_tag=item.xbrl_tag,
                content_hash=item.content_hash,
            )
            for item in items
        ]
        values = {fact.concept: fact.value for fact in facts}
        g2 = run_reconciliation(values)
        g3_failed = []
        for fact in facts:
            ok, reason = validate_fact_evidence(fact.to_gate_dict())
            if not ok:
                g3_failed.append({"fact_key": fact.fact_key_id, "reason": reason})
        present = {fact.concept for fact in facts}
        status_counts: dict[str, int] = defaultdict(int)
        for fact in facts:
            status_counts[fact.status] += 1
        companies.append(
            {
                "company_code": company_code,
                "company_name": _company_name(company_code),
                "doc_id": facts[0].doc_id,
                "period": period,
                "scope": scope,
                "fact_count": len(facts),
                "auto_accepted": status_counts.get("auto_accepted", 0),
                "human_review": status_counts.get("human_review", 0),
                "rejected": status_counts.get("rejected", 0),
                "missing_critical": sorted(CRITICAL_CONCEPTS - present),
                "g1": {
                    "passed": all("amount_mismatch" not in (fact.review_reason or "") for fact in facts),
                    "conflicts": [
                        {"fact_key": fact.fact_key_id, "reason": fact.review_reason}
                        for fact in facts
                        if fact.review_reason and "amount_mismatch" in fact.review_reason
                    ],
                },
                "g2": {"passed": all(item.passed for item in g2), "rules": [item.to_dict() for item in g2]},
                "g3": {
                    "passed": not g3_failed,
                    "policy": "web_content_hash"
                    if all(fact.source_type == "web" for fact in facts)
                    else "pdf_bbox",
                    "failed": g3_failed,
                },
            }
        )

    companies.sort(key=lambda item: item["company_code"])
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "source": "fin_metric",
        "summary": {
            "companies": len(companies),
            "facts": sum(item["fact_count"] for item in companies),
            "auto_accepted": sum(item["auto_accepted"] for item in companies),
            "human_review": sum(item["human_review"] for item in companies),
            "g2_all_passed": all(item["g2"]["passed"] for item in companies) if companies else False,
            "g3_all_passed": all(item["g3"]["passed"] for item in companies) if companies else False,
            "missing_critical_companies": sum(1 for item in companies if item["missing_critical"]),
        },
        "companies": companies,
    }


def fetch_quality_gates() -> dict[str, Any]:
    empty = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "source": "fin_metric",
        "summary": {
            "companies": 0,
            "facts": 0,
            "auto_accepted": 0,
            "human_review": 0,
            "g2_all_passed": False,
            "g3_all_passed": False,
            "missing_critical_companies": 0,
        },
        "companies": [],
        "f10_ready": DEFAULT_F10_ROOT.is_dir(),
        "f10_root": str(DEFAULT_F10_ROOT),
    }
    with get_connection() as conn:
        if not _table_exists(conn, "fin_metric"):
            empty["error"] = "fin_metric table missing"
            return empty
        payload = report_from_rows(list_all_for_gates(conn))
    payload["f10_ready"] = DEFAULT_F10_ROOT.is_dir()
    payload["f10_root"] = str(DEFAULT_F10_ROOT)
    return payload


def fetch_fin_metrics(
    *,
    company_code: str | None = None,
    status: str | None = None,
    statement: str | None = None,
    concept: str | None = None,
    doc_id: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    with get_connection() as conn:
        if not _table_exists(conn, "fin_metric"):
            return {"total": 0, "limit": limit, "offset": offset, "items": []}
        rows = list_fin_metrics(
            conn,
            company_code=company_code,
            status=status,
            statement=statement,
            concept=concept,
            doc_id=doc_id,
            limit=limit,
            offset=offset,
        )
        total = count_fin_metrics(
            conn,
            company_code=company_code,
            status=status,
            statement=statement,
            concept=concept,
            doc_id=doc_id,
        )
    items = []
    for row in rows:
        item = serialize_metric(row)
        item["company_name"] = _company_name(row.company_code)
        item["value_display"] = format_yuan(row.value_yuan)
        items.append(item)
    return {"total": total, "limit": limit, "offset": offset, "items": items}


def ingest_f10_to_fin_metric(
    *,
    codes: list[str] | None = None,
    year: int = 2024,
    root: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    directories = discover_f10_dirs(root, codes=codes, year=year)
    wanted = list(codes or GOLDEN_CODES)
    missing_dirs = [code for code in wanted if not any(path.name.startswith(code) for path in directories)]
    if not directories:
        raise FileNotFoundError(
            f"F10 JSON not found under {root or DEFAULT_F10_ROOT}. "
            "Run: python python-ai/scripts/download_xbrl.py"
        )

    reports: list[GateReport] = []
    written = 0
    for directory in directories:
        reports.append(extract_and_gate(directory))
    if dry_run:
        return _ingest_payload(reports, written=0, missing_dirs=missing_dirs, root=root, dry_run=True)

    with get_connection() as conn:
        for report in reports:
            job_id = create_job(
                conn,
                target_type="web",
                target_doc_id=report.doc_id,
                status="EXTRACTING",
            )
            conn.commit()
            try:
                written += upsert_fin_metrics(conn, report.facts)
                update_job_status(conn, job_id=job_id, status="DONE")
                conn.commit()
            except Exception as exc:
                conn.rollback()
                update_job_status(conn, job_id=job_id, status="FAILED", error_message=str(exc)[:500])
                conn.commit()
                raise
    return _ingest_payload(reports, written=written, missing_dirs=missing_dirs, root=root, dry_run=False)


def _ingest_payload(
    reports: list[GateReport],
    *,
    written: int,
    missing_dirs: list[str],
    root: Path | None,
    dry_run: bool,
) -> dict[str, Any]:
    return {
        "dry_run": dry_run,
        "written": written,
        "missing_dirs": missing_dirs,
        "root": str((root or DEFAULT_F10_ROOT).resolve()),
        "companies": [report.to_dict() for report in reports],
        "summary": {
            "companies": len(reports),
            "facts": sum(len(report.facts) for report in reports),
            "auto_accepted": sum(report.auto_accepted for report in reports),
            "human_review": sum(report.human_review for report in reports),
            "g2_all_passed": all(report.g2_passed for report in reports),
            "g3_all_passed": all(report.g3_passed for report in reports),
        },
    }
