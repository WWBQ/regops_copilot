"""create_review_draft：只声明合同，W5 不落库。"""

from __future__ import annotations

from app.schemas.tools import CreateReviewDraftArgs, CreateReviewDraftResult


def run_create_review_draft(_args: CreateReviewDraftArgs) -> CreateReviewDraftResult:
    return CreateReviewDraftResult(
        ok=False,
        stop=True,
        message="审查工单草稿是写操作，W5 只读工具不落库；W7 maker-checker 再接。",
    )


def create_review_draft_description() -> str:
    return (
        "创建合规审查工单草稿（PENDING）。当前周只暴露合同、不写库。"
        "调用后 ok=false 且 stop=true。"
    )
