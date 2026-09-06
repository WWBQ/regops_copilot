"""emit_conclusion：只做合规 DTO 校验，不落库、不提交复核。"""

from __future__ import annotations

from app.schemas.tools import EmitConclusionArgs, EmitConclusionResult


def run_emit_conclusion(args: EmitConclusionArgs) -> EmitConclusionResult:
    return EmitConclusionResult(
        ok=True,
        stop=False,
        conclusion=args,
        message="结论已通过 Schema 校验，尚未提交 maker-checker（W7）。",
    )


def emit_conclusion_description() -> str:
    return (
        "输出结构化合规结论：conclusion、risk_level（低/中/高）、"
        "clause_refs（至少一条）、可选 evidence_quotes、confidence。"
        "高风险结论 confidence 不得超过 0.95。本工具只校验，不自动出具对外意见。"
    )
