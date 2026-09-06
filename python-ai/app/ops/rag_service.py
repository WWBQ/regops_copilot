"""RAG 运维统计：trace 汇总与拒答率。"""

from __future__ import annotations

from typing import Any

from app.db.connection import get_connection

# 证据不足或无文档库 → 未带引用回答（相对 no_intent 寒暄跳过）
REFUSAL_OUTCOMES = frozenset({"low_score", "no_docs"})


def _table_exists(conn, table: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", (f"public.{table}",))
        return cur.fetchone()[0] is not None


def fetch_rag_overview() -> dict[str, Any]:
    """全库 RAG trace 汇总；拒答率 = 拒答次数 / 有意图检索次数。"""
    overview: dict[str, Any] = {
        "total": 0,
        "ok_count": 0,
        "refusal_count": 0,
        "no_intent_count": 0,
        "refusal_rate": 0.0,
        "avg_rag_ms": 0.0,
        "by_outcome": {},
    }
    with get_connection() as conn:
        if not _table_exists(conn, "rag_query_log"):
            return overview

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT outcome, COUNT(*)::int, COALESCE(AVG(total_rag_ms), 0)
                FROM rag_query_log
                GROUP BY outcome
                """
            )
            rows = cur.fetchall()

        by_outcome: dict[str, int] = {}
        total_ms = 0.0
        total = 0
        for outcome, count, avg_ms in rows:
            outcome_str = str(outcome)
            count_int = int(count)
            by_outcome[outcome_str] = count_int
            total += count_int
            total_ms += float(avg_ms) * count_int

        ok_count = by_outcome.get("ok", 0)
        no_intent_count = by_outcome.get("no_intent", 0)
        refusal_count = sum(by_outcome.get(o, 0) for o in REFUSAL_OUTCOMES)
        rag_intent_total = total - no_intent_count
        refusal_rate = (refusal_count / rag_intent_total) if rag_intent_total > 0 else 0.0

        overview.update(
            {
                "total": total,
                "ok_count": ok_count,
                "refusal_count": refusal_count,
                "no_intent_count": no_intent_count,
                "refusal_rate": round(refusal_rate, 4),
                "avg_rag_ms": round(total_ms / total, 2) if total > 0 else 0.0,
                "by_outcome": by_outcome,
            }
        )
    return overview
