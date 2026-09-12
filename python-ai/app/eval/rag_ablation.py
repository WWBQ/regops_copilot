"""W3-5 检索消融：baseline / hybrid / rerank 三档对照。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.eval.rag_retrieval_runner import run_rag_retrieval_eval
from app.rag.modes import ABLATION_MODES, MODE_DESCRIPTIONS, RetrievalMode

ProgressCallback = Callable[[str, int, int, str], None]

ADJACENT_PAIRS: tuple[tuple[RetrievalMode, RetrievalMode], ...] = (
    ("baseline", "hybrid"),
    ("hybrid", "rerank"),
)


def _flip_rows(left: dict[str, Any], right: dict[str, Any]) -> tuple[list[dict], list[dict]]:
    left_map = {row["id"]: row for row in left.get("results") or []}
    right_map = {row["id"]: row for row in right.get("results") or []}
    improvements: list[dict] = []
    regressions: list[dict] = []
    for item_id in sorted(set(left_map) & set(right_map)):
        a = left_map[item_id]
        b = right_map[item_id]
        a_hit = bool(a.get("page_hit_at_k"))
        b_hit = bool(b.get("page_hit_at_k"))
        payload = {
            "id": item_id,
            "category": b.get("category"),
            "question": b.get("question"),
            "gold_pages": b.get("gold_pages"),
            "from_pages": a.get("retrieved_pages"),
            "to_pages": b.get("retrieved_pages"),
            "from_mrr": a.get("reciprocal_rank"),
            "to_mrr": b.get("reciprocal_rank"),
        }
        if not a_hit and b_hit:
            improvements.append(payload)
        elif a_hit and not b_hit:
            regressions.append(payload)
    return improvements, regressions


def _mode_headline(report: dict[str, Any]) -> dict[str, Any]:
    summary = report.get("summary") or {}
    return {
        "recall_at_k": summary.get("recall_at_k"),
        "mrr": summary.get("mrr"),
        "ndcg_at_k": summary.get("ndcg_at_k"),
        "citation_accuracy": summary.get("citation_accuracy"),
        "count": summary.get("count"),
        "latency_p50_ms": summary.get("latency_p50_ms"),
        "latency_p95_ms": summary.get("latency_p95_ms"),
        "latency_mean_ms": summary.get("latency_mean_ms"),
        "by_category": summary.get("by_category") or {},
        "rerank_fallback_count": sum(
            1 for row in report.get("results") or [] if row.get("rerank_fallback")
        ),
    }


def compare_ablation_reports(reports: dict[str, dict[str, Any]]) -> dict[str, Any]:
    missing = [mode for mode in ABLATION_MODES if mode not in reports]
    if missing:
        raise ValueError(f"消融对照缺少档位: {missing}")

    by_mode = {mode: _mode_headline(reports[mode]) for mode in ABLATION_MODES}
    adjacent: list[dict[str, Any]] = []
    for left, right in ADJACENT_PAIRS:
        improvements, regressions = _flip_rows(reports[left], reports[right])
        left_sum = reports[left].get("summary") or {}
        right_sum = reports[right].get("summary") or {}
        category_delta: dict[str, dict[str, Any]] = {}
        cats = set((left_sum.get("by_category") or {})) | set((right_sum.get("by_category") or {}))
        for cat in sorted(cats):
            a_cat = (left_sum.get("by_category") or {}).get(cat) or {}
            b_cat = (right_sum.get("by_category") or {}).get(cat) or {}
            category_delta[cat] = {
                "recall_at_k_delta": round(
                    float(b_cat.get("recall_at_k") or 0) - float(a_cat.get("recall_at_k") or 0),
                    4,
                ),
                "mrr_delta": round(float(b_cat.get("mrr") or 0) - float(a_cat.get("mrr") or 0), 4),
                "ndcg_at_k_delta": round(
                    float(b_cat.get("ndcg_at_k") or 0) - float(a_cat.get("ndcg_at_k") or 0),
                    4,
                ),
                "citation_accuracy_delta": round(
                    float(b_cat.get("citation_accuracy") or 0)
                    - float(a_cat.get("citation_accuracy") or 0),
                    4,
                ),
                "from_recall": a_cat.get("recall_at_k"),
                "to_recall": b_cat.get("recall_at_k"),
            }
        adjacent.append(
            {
                "from": left,
                "to": right,
                "recall_at_k_delta": round(
                    float(right_sum.get("recall_at_k") or 0) - float(left_sum.get("recall_at_k") or 0),
                    4,
                ),
                "mrr_delta": round(
                    float(right_sum.get("mrr") or 0) - float(left_sum.get("mrr") or 0),
                    4,
                ),
                "ndcg_at_k_delta": round(
                    float(right_sum.get("ndcg_at_k") or 0) - float(left_sum.get("ndcg_at_k") or 0),
                    4,
                ),
                "citation_accuracy_delta": round(
                    float(right_sum.get("citation_accuracy") or 0)
                    - float(left_sum.get("citation_accuracy") or 0),
                    4,
                ),
                "latency_p50_ms_delta": round(
                    float(right_sum.get("latency_p50_ms") or 0)
                    - float(left_sum.get("latency_p50_ms") or 0),
                    1,
                ),
                "improvements": improvements,
                "regressions": regressions,
                "by_category": category_delta,
            }
        )
    return {"by_mode": by_mode, "adjacent": adjacent}


def _pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{float(value) * 100:.1f}%"


def _ms(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{float(value):.0f}"


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") or {}
    by_mode = summary.get("by_mode") or {}
    adjacent = summary.get("adjacent") or []
    params = report.get("params") or {}
    generated = str(report.get("generated_at") or "")[:19].replace("T", " ")
    golden = report.get("golden_file") or "rag_retrieval_100.json"
    n = params.get("count") or next(
        (row.get("count") for row in by_mode.values() if row.get("count")), 0
    )

    lines = [
        "# RAG 检索消融（baseline / hybrid / rerank）",
        "",
        f"- 时间：{generated}",
        f"- 黄金集：`{golden}`（n={n}，top_k={params.get('top_k', 12)}）",
        "- 指标：page Recall@k（命中任一 gold 页即成功）+ MRR + nDCG@k（gold 页同等相关）+ citation_accuracy（top-k 去重页中 gold 页占比）；延迟为端到端检索，含 embed",
        "- 关键词路是 Okapi BM25（问题短语 TF + Lucene IDF + 长度归一）；精排失败会回退 RRF",
        "",
        "| 档位 | 路径 | Recall@k | MRR | nDCG@k | CiteAcc | P50 | P95 | 均值 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for mode in ABLATION_MODES:
        row = by_mode.get(mode) or {}
        lines.append(
            f"| {mode} | {MODE_DESCRIPTIONS[mode]} | {_pct(row.get('recall_at_k'))} | "
            f"{float(row.get('mrr') or 0):.4f} | {float(row.get('ndcg_at_k') or 0):.4f} | "
            f"{_pct(row.get('citation_accuracy'))} | "
            f"{_ms(row.get('latency_p50_ms'))} ms | "
            f"{_ms(row.get('latency_p95_ms'))} ms | {_ms(row.get('latency_mean_ms'))} ms |"
        )

    lines.extend(["", "## 相邻 Δ", ""])
    for pair in adjacent:
        lines.append(
            f"- **{pair['from']} → {pair['to']}**：Recall Δ {pair['recall_at_k_delta']:+.4f}，"
            f" MRR Δ {pair['mrr_delta']:+.4f}，nDCG Δ {pair.get('ndcg_at_k_delta', 0):+.4f}，"
            f" CiteAcc Δ {pair.get('citation_accuracy_delta', 0):+.4f}，"
            f" P50 Δ {pair['latency_p50_ms_delta']:+.0f} ms；"
            f" 提升 {len(pair.get('improvements') or [])} 题，回归 {len(pair.get('regressions') or [])} 题"
        )

    lines.extend(["", "## 分题型 Recall@k", "", "| 题型 | baseline | hybrid | rerank | hybrid−baseline | rerank−hybrid |", "|---|---:|---:|---:|---:|---:|"])
    cats: set[str] = set()
    for row in by_mode.values():
        cats.update((row.get("by_category") or {}).keys())
    hybrid_delta = next((p.get("by_category") or {} for p in adjacent if p.get("from") == "baseline"), {})
    rerank_delta = next((p.get("by_category") or {} for p in adjacent if p.get("from") == "hybrid"), {})
    for cat in sorted(cats):
        cells = []
        for mode in ABLATION_MODES:
            rec = ((by_mode.get(mode) or {}).get("by_category") or {}).get(cat) or {}
            cells.append(_pct(rec.get("recall_at_k")))
        h = hybrid_delta.get(cat) or {}
        r = rerank_delta.get(cat) or {}
        lines.append(
            f"| {cat} | {cells[0]} | {cells[1]} | {cells[2]} | "
            f"{h.get('recall_at_k_delta', 0):+.4f} | {r.get('recall_at_k_delta', 0):+.4f} |"
        )

    lines.extend(["", "## 分题型 MRR", "", "| 题型 | baseline | hybrid | rerank | hybrid−baseline | rerank−hybrid |", "|---|---:|---:|---:|---:|---:|"])
    for cat in sorted(cats):
        cells = []
        for mode in ABLATION_MODES:
            rec = ((by_mode.get(mode) or {}).get("by_category") or {}).get(cat) or {}
            mrr = rec.get("mrr")
            cells.append("—" if mrr is None else f"{float(mrr):.4f}")
        h = hybrid_delta.get(cat) or {}
        r = rerank_delta.get(cat) or {}
        lines.append(
            f"| {cat} | {cells[0]} | {cells[1]} | {cells[2]} | "
            f"{h.get('mrr_delta', 0):+.4f} | {r.get('mrr_delta', 0):+.4f} |"
        )

    lines.extend(
        [
            "",
            "## 分题型 nDCG@k",
            "",
            "| 题型 | baseline | hybrid | rerank | hybrid−baseline | rerank−hybrid |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for cat in sorted(cats):
        cells = []
        for mode in ABLATION_MODES:
            rec = ((by_mode.get(mode) or {}).get("by_category") or {}).get(cat) or {}
            ndcg = rec.get("ndcg_at_k")
            cells.append("—" if ndcg is None else f"{float(ndcg):.4f}")
        h = hybrid_delta.get(cat) or {}
        r = rerank_delta.get(cat) or {}
        lines.append(
            f"| {cat} | {cells[0]} | {cells[1]} | {cells[2]} | "
            f"{h.get('ndcg_at_k_delta', 0):+.4f} | {r.get('ndcg_at_k_delta', 0):+.4f} |"
        )

    lines.extend(
        [
            "",
            "## 分题型 citation_accuracy",
            "",
            "| 题型 | baseline | hybrid | rerank | hybrid−baseline | rerank−hybrid |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for cat in sorted(cats):
        cells = []
        for mode in ABLATION_MODES:
            rec = ((by_mode.get(mode) or {}).get("by_category") or {}).get(cat) or {}
            cite = rec.get("citation_accuracy")
            cells.append("—" if cite is None else _pct(cite))
        h = hybrid_delta.get(cat) or {}
        r = rerank_delta.get(cat) or {}
        lines.append(
            f"| {cat} | {cells[0]} | {cells[1]} | {cells[2]} | "
            f"{h.get('citation_accuracy_delta', 0):+.4f} | {r.get('citation_accuracy_delta', 0):+.4f} |"
        )

    lines.extend(["", "## 相邻翻转（未命中↔命中）", ""])
    for pair in adjacent:
        lines.append(f"### {pair['from']} → {pair['to']}")
        lines.append("")
        improvements = pair.get("improvements") or []
        regressions = pair.get("regressions") or []
        if improvements:
            lines.append("提升：")
            for row in improvements[:12]:
                lines.append(f"- `{row['id']}` · {row.get('category')} · {row.get('question')}")
            if len(improvements) > 12:
                lines.append(f"- … 另 {len(improvements) - 12} 题")
        else:
            lines.append("提升：无")
        lines.append("")
        if regressions:
            lines.append("回归：")
            for row in regressions[:12]:
                lines.append(f"- `{row['id']}` · {row.get('category')} · {row.get('question')}")
            if len(regressions) > 12:
                lines.append(f"- … 另 {len(regressions) - 12} 题")
        else:
            lines.append("回归：无")
        lines.append("")

    lines.extend(
        [
            "## 怎么读",
            "",
            "- 三档**不必单调上升**。关键词可能把枚举题拉上来，也可能把数字题噪声打进 top-k。",
            "- Cross-Encoder 主要改 **位次（MRR / nDCG）**，对 Recall@12 的边际可能很小，但延迟通常明显增加。",
            "- `numeric_financial` 弱、`product_enum` 强时，数字题应分流问数/Text2SQL，而不是继续堆 rerank。",
            "- Recall@k 是题级 page_hit（任一 gold 页即成功）；nDCG@k 奖励全部 gold 页的排序；citation_accuracy 是 top-k 去重页里 gold 页的比例（检索很吵时 recall 仍可能为 1）。",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def run_rag_ablation_eval(
    *,
    golden_path: Path,
    limit: int = 0,
    category: str = "",
    categories: list[str] | None = None,
    item_ids: list[str] | None = None,
    top_k: int = 0,
    label: str = "",
    on_progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    reports: dict[str, dict[str, Any]] = {}
    for mode in ABLATION_MODES:
        def _progress(done: int, total: int, item_id: str, *, _mode: RetrievalMode = mode) -> None:
            if on_progress:
                on_progress(_mode, done, total, item_id)

        reports[mode] = run_rag_retrieval_eval(
            golden_path=golden_path,
            limit=limit,
            category=category,
            categories=categories,
            item_ids=item_ids,
            top_k=top_k,
            label=f"{label} {mode}".strip() if label else mode,
            mode=mode,
            warmup=True,
            on_progress=_progress,
        )

    comparison = compare_ablation_reports(reports)
    first = reports[ABLATION_MODES[0]]
    params = dict(first.get("params") or {})
    params["modes"] = list(ABLATION_MODES)
    params["count"] = (first.get("summary") or {}).get("count")
    return {
        "task_id": "rag_ablation",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "golden_version": first.get("golden_version"),
        "golden_file": first.get("golden_file"),
        "params": params,
        "provenance": first.get("provenance"),
        "summary": comparison,
        "reports": reports,
    }
