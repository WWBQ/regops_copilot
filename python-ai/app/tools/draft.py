"""create_review_draft：确认后写入 PENDING 工单草稿，不提交 maker-checker。"""

from __future__ import annotations

from uuid import UUID

from app.db.connection import get_connection
from app.db.review_draft_repository import insert_review_draft
from app.schemas.tools import CreateReviewDraftArgs, CreateReviewDraftResult


def _optional_uuid(value: str | None) -> str | None:
    if not value or not str(value).strip():
        return None
    try:
        return str(UUID(str(value).strip()))
    except (ValueError, TypeError):
        return None


def run_create_review_draft(args: CreateReviewDraftArgs) -> CreateReviewDraftResult:
    codes = list(args.company_codes) or [args.company_code]
    if args.company_code not in codes:
        codes.insert(0, args.company_code)
    dept = (args.dept or "public").strip().lower() or "public"
    idempotency = (args.thread_id or "").strip() or None
    thread_id = idempotency
    try:
        with get_connection() as conn:
            row, replayed = insert_review_draft(
                conn,
                dept=dept,
                company_code=args.company_code,
                company_codes=codes,
                title=args.title,
                reason=args.reason,
                conclusion=args.conclusion,
                risk_level=args.risk_level,
                clause_refs=list(args.clause_refs),
                evidence_quotes=list(args.evidence_quotes),
                impact_scope=args.impact_scope,
                thread_id=thread_id,
                session_id=_optional_uuid(args.session_id),
                request_id=(args.request_id or "").strip() or None,
                idempotency_key=idempotency,
            )
            conn.commit()
    except RuntimeError as exc:
        return CreateReviewDraftResult(ok=False, stop=True, message=str(exc))
    except Exception as exc:
        return CreateReviewDraftResult(ok=False, stop=True, message=f"审查草稿写入失败：{exc}")
    action = "已存在" if replayed else "已写入"
    return CreateReviewDraftResult(
        ok=True,
        stop=False,
        draft_id=row.public_id,
        status=row.status,
        replayed=replayed,
        message=f"{action} PENDING 审查工单草稿 {row.public_id}，未提交 maker-checker。",
    )


def create_review_draft_description() -> str:
    return (
        "创建合规审查工单草稿，状态只能是 PENDING。"
        "须在人工确认之后调用；同一 thread_id 重复调用返回已有草稿，不建第二条。"
        "不提交复核、不改为 APPROVED。"
    )
