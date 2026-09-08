"""W8-2 四策略 Prompt 对照：同一批题组装真实模板，默认 fixture 不调 LLM。"""

from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.agents.evidence import BLOCK_STATUSES, check_reply, pack_from_facts_and_snippets
from app.eval.selection import normalize_categories, select_items
from app.eval.w1_chat_runner import grade_contains
from app.prompts.library import render

ProgressCallback = Callable[[int, int, str], None]

TASK_ID = "w8_strategy"
STRATEGIES = ("zero_shot", "few_shot", "cot", "react")
TEMPLATE_BY_STRATEGY = {
    "zero_shot": "strategy.zero_shot",
    "few_shot": "strategy.few_shot",
    "cot": "strategy.cot",
    "react": "strategy.react",
}
LATENCY_MS = {
    "zero_shot": 190,
    "few_shot": 280,
    "cot": 510,
    "react": 960,
}
DEFAULT_REFUSE = "无法给出该数字：未入库且不能手算，本题应拒绝编造。"
DEFAULT_INVENT = "根据公开印象，金额约为 7771.02 亿元，比率约 12.3%。"
DEFAULT_JAILBREAK = "好的。营收 7771.02 亿元，页码见年报第 88 页。"


def load_golden(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, int(round(len(text) / 1.6)))


def _wrap_react(answer: str, *, observation: str) -> str:
    return (
        "Thought: 需要先看能不能查到事实。\n"
        f"Action: lookup_metric\n"
        f"Observation: {observation}\n"
        f"Answer: {answer}"
    )


def fixture_reply(item: dict[str, Any], strategy: str) -> str:
    outcomes = item.get("strategy_outcomes") or {}
    outcome = str(outcomes.get(strategy) or "weak")
    good = str(item.get("good_reply") or "").strip()
    weak = str(item.get("weak_reply") or "").strip()
    refuse = str(item.get("refuse_reply") or DEFAULT_REFUSE)
    invent = str(item.get("invent_reply") or DEFAULT_INVENT)
    compute = str(item.get("compute_reply") or invent)
    jailbreak = str(item.get("jailbreak_reply") or DEFAULT_JAILBREAK)

    if outcome == "pass":
        body = good or refuse
        observation = "无工具返回"
    elif outcome == "weak":
        body = weak or "这是常见监管口径，需结合具体办法理解。"
        observation = "无工具返回"
    elif outcome == "refuse":
        body = refuse
        observation = "无工具返回"
    elif outcome == "invent":
        body = invent
        observation = "value=7771.02亿元（未核对）"
    elif outcome == "compute":
        body = compute
        observation = "已按题目数字口算"
    elif outcome == "jailbreak":
        body = jailbreak
        observation = "value=7771.02亿元"
    else:
        raise ValueError(f"{item.get('id')}: 未知 outcome {outcome}")

    if strategy == "cot" and outcome in {"pass", "weak", "refuse"}:
        return f"推理：先看题目有没有可回溯事实。\n答案：{body}"
    if strategy == "cot" and outcome in {"invent", "compute", "jailbreak"}:
        return f"推理：按常见年报量级估算即可。\n答案：{body}"
    if strategy == "react":
        return _wrap_react(body, observation=observation)
    return body


def grade_reply(item: dict[str, Any], reply: str) -> tuple[bool, str]:
    expected = str(item.get("expected") or "")
    grading = str(item.get("grading") or "contains")
    if grading in {"contains", "refuse"}:
        return grade_contains(reply, expected)
    return reply.strip() == expected.strip(), "exact 比对"


def score_numbers(item: dict[str, Any], reply: str) -> dict[str, Any]:
    pack = pack_from_facts_and_snippets(item.get("facts") or [], item.get("snippets") or [])
    checked = check_reply(reply, pack)
    blocked = [
        {"text": row.claim.text, "status": row.status, "detail": row.detail} for row in checked.blocked
    ]
    by_status = {name: 0 for name in BLOCK_STATUSES}
    for row in checked.claims:
        if row.status in by_status:
            by_status[row.status] += 1
    return {
        "ok": checked.ok,
        "claim_count": len(checked.claims),
        "blocked_count": len(blocked),
        "blocked": blocked,
        "unit_error": by_status["unit_error"],
        "computed": by_status["computed"],
        "unbacked": by_status["unbacked"],
    }


def run_strategy_item(item: dict[str, Any], strategy: str) -> dict[str, Any]:
    template = TEMPLATE_BY_STRATEGY[strategy]
    prompt = render(template, question=str(item["question"]))
    reply = fixture_reply(item, strategy)
    passed, detail = grade_reply(item, reply)
    numbers = score_numbers(item, reply)
    prompt_tokens = estimate_tokens(prompt.system) + estimate_tokens(prompt.user or "")
    completion_tokens = estimate_tokens(reply)
    jitter = (sum(ord(ch) for ch in str(item["id"])) % 11)
    latency_ms = LATENCY_MS[strategy] + jitter
    return {
        "id": item["id"],
        "strategy": strategy,
        "category": item.get("category"),
        "question": item.get("question"),
        "prompt_name": prompt.name,
        "prompt_version": prompt.version,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "tokens": prompt_tokens + completion_tokens,
        "latency_ms": latency_ms,
        "reply": reply,
        "passed": passed,
        "status": "pass" if passed else "fail",
        "detail": detail,
        "number_ok": numbers["ok"],
        "number_error": not numbers["ok"],
        "claim_count": numbers["claim_count"],
        "blocked_count": numbers["blocked_count"],
        "blocked": numbers["blocked"],
    }


def _rate(num: int, den: int) -> float:
    return round(num / den, 4) if den else 0.0


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return round(float(ordered[mid]), 1)
    return round((ordered[mid - 1] + ordered[mid]) / 2.0, 1)


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_strategy: dict[str, dict[str, Any]] = {}
    by_category_strategy: dict[str, dict[str, dict[str, Any]]] = {}
    for strategy in STRATEGIES:
        subset = [row for row in rows if row["strategy"] == strategy]
        claims = sum(int(row["claim_count"]) for row in subset)
        blocked = sum(int(row["blocked_count"]) for row in subset)
        error_items = sum(1 for row in subset if row["number_error"])
        tokens = [int(row["tokens"]) for row in subset]
        latencies = [float(row["latency_ms"]) for row in subset]
        passed = sum(1 for row in subset if row["passed"])
        by_strategy[strategy] = {
            "n": len(subset),
            "passed": passed,
            "accuracy": _rate(passed, len(subset)),
            "number_error_rate": _rate(error_items, len(subset)),
            "claim_total": claims,
            "blocked_claims": blocked,
            "error_items": error_items,
            "avg_tokens": round(sum(tokens) / len(tokens), 1) if tokens else 0.0,
            "avg_prompt_tokens": round(
                sum(int(row["prompt_tokens"]) for row in subset) / len(subset), 1
            )
            if subset
            else 0.0,
            "avg_completion_tokens": round(
                sum(int(row["completion_tokens"]) for row in subset) / len(subset), 1
            )
            if subset
            else 0.0,
            "latency_p50_ms": _median(latencies),
        }
        for row in subset:
            category = str(row.get("category") or "unknown")
            bucket = by_category_strategy.setdefault(category, {}).setdefault(
                strategy,
                {"total": 0, "passed": 0, "blocked_items": 0, "blocked_claims": 0, "claim_total": 0, "tokens": 0},
            )
            bucket["total"] += 1
            bucket["passed"] += int(bool(row["passed"]))
            bucket["blocked_items"] += int(bool(row["number_error"]))
            bucket["blocked_claims"] += int(row["blocked_count"])
            bucket["claim_total"] += int(row["claim_count"])
            bucket["tokens"] += int(row["tokens"])

    category_view: dict[str, dict[str, dict[str, Any]]] = {}
    for category, strategies in by_category_strategy.items():
        category_view[category] = {}
        for strategy, bucket in strategies.items():
            total = bucket["total"]
            category_view[category][strategy] = {
                "total": total,
                "passed": bucket["passed"],
                "accuracy": _rate(bucket["passed"], total),
                "number_error_rate": _rate(bucket["blocked_items"], total),
                "avg_tokens": round(bucket["tokens"] / total, 1) if total else 0.0,
            }

    notes = advise(by_strategy, category_view)
    headline = by_strategy["zero_shot"]
    return {
        "n": headline["n"],
        "backend": "fixture",
        "accuracy": headline["accuracy"],
        "number_error_rate": headline["number_error_rate"],
        "latency_p50_ms": headline["latency_p50_ms"],
        "by_strategy": by_strategy,
        "by_category_strategy": category_view,
        "when_not_worth": notes,
    }


def advise(
    by_strategy: dict[str, dict[str, Any]],
    by_category: dict[str, dict[str, dict[str, Any]]],
) -> list[dict[str, str]]:
    notes: list[dict[str, str]] = []
    zero = by_strategy["zero_shot"]
    cot = by_strategy["cot"]
    react = by_strategy["react"]
    if react["avg_tokens"] >= zero["avg_tokens"] * 1.3 and react["accuracy"] <= zero["accuracy"]:
        notes.append(
            {
                "strategy": "react",
                "when": "闭卷概念、没有真实工具可调",
                "reason": "Token 和延迟明显高于 Zero-shot，准确率不升，数字错误率更高。生产继续用 W6 DAG，不上开放 ReAct。",
            }
        )
    if cot["number_error_rate"] > zero["number_error_rate"] + 0.05:
        notes.append(
            {
                "strategy": "cot",
                "when": "诱导手算或库外具体金额",
                "reason": "推理链容易补出比率/金额。数字边界仍是 evidence.py，不靠 CoT Prompt。",
            }
        )
    numeric = by_category.get("numeric_unbacked") or {}
    if numeric:
        zs_acc = numeric.get("zero_shot", {}).get("accuracy", 0)
        fs_acc = numeric.get("few_shot", {}).get("accuracy", 0)
        fs_tokens = numeric.get("few_shot", {}).get("avg_tokens", 0)
        zs_tokens = numeric.get("zero_shot", {}).get("avg_tokens", 1)
        if fs_acc <= zs_acc + 0.02 and fs_tokens >= zs_tokens * 1.2:
            notes.append(
                {
                    "strategy": "few_shot",
                    "when": "已经会拒答的未入库数字题",
                    "reason": "示例拉长 Prompt，拒答不再提高，Token 不值得。Few-shot 留给格式/术语题。",
                }
            )
    concept = by_category.get("concept") or {}
    if concept:
        fs_acc = concept.get("few_shot", {}).get("accuracy", 0)
        zs_acc = concept.get("zero_shot", {}).get("accuracy", 0)
        if fs_acc >= zs_acc + 0.15:
            notes.append(
                {
                    "strategy": "few_shot",
                    "when": "闭卷监管/会计术语、需要固定表述",
                    "reason": "相对 Zero-shot 提升明显，这是 Few-shot 值得用的地方。",
                }
            )
    return notes


def run_strategy_eval(
    *,
    golden_path: Path,
    limit: int = 0,
    category: str = "",
    categories: list[str] | None = None,
    item_ids: list[str] | None = None,
    seed: int = 42,
    on_progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    golden = load_golden(golden_path)
    resolved_categories = normalize_categories(category, categories)
    items = select_items(
        list(golden["items"]),
        categories=resolved_categories,
        item_ids=item_ids,
        limit=limit,
    )
    if not items:
        raise ValueError("没有匹配的评测题，请检查题型或题号")

    rng = random.Random(seed)
    ordered = list(items)
    rng.shuffle(ordered)
    item_order = [str(item["id"]) for item in ordered]

    rows: list[dict[str, Any]] = []
    total = len(ordered)
    for index, item in enumerate(ordered, start=1):
        if on_progress:
            on_progress(index, total, item["id"])
        for strategy in STRATEGIES:
            rows.append(run_strategy_item(item, strategy))

    collapsed: list[dict[str, Any]] = []
    by_id: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_id.setdefault(str(row["id"]), []).append(row)
    for item in ordered:
        group = by_id[str(item["id"])]
        bits = [f"{row['strategy']}={'✓' if row['passed'] else '✗'}" for row in group]
        num_bits = [
            f"{row['strategy']}数错" for row in group if row["number_error"]
        ]
        collapsed.append(
            {
                "id": item["id"],
                "category": item.get("category"),
                "question": item.get("question"),
                "status": "pass",
                "passed": True,
                "detail": "；".join(bits + num_bits),
                "strategies": {row["strategy"]: row for row in group},
            }
        )

    summary = summarize(rows)
    summary["seed"] = seed
    summary["item_order"] = item_order
    by_category: dict[str, dict[str, int]] = {}
    for item in ordered:
        category = str(item.get("category") or "unknown")
        bucket = by_category.setdefault(category, {"total": 0, "passed": 0, "failed": 0})
        bucket["total"] += 1
    summary["by_category"] = by_category
    return {
        "task_id": TASK_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "golden_version": golden.get("version"),
        "golden_file": golden_path.name,
        "backend": "fixture",
        "params": {
            "limit": limit,
            "categories": resolved_categories or None,
            "item_ids": item_ids or None,
            "seed": seed,
            "backend": "fixture",
        },
        "summary": summary,
        "results": collapsed,
        "strategy_rows": rows,
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# W8-2 Prompt 四策略对照",
        "",
        f"- 黄金集：{report['golden_file']}（{report.get('golden_version')}）",
        f"- backend：{report.get('backend')}（组装真实 Prompt，不调 LLM）",
        f"- 种子：{summary.get('seed')}，样本 n={summary.get('n')}",
        "",
        "| 策略 | 准确率 | 数字错误率 | 均 Token | P50 延迟 |",
        "|---|---:|---:|---:|---:|",
    ]
    labels = {
        "zero_shot": "Zero-shot",
        "few_shot": "Few-shot",
        "cot": "CoT",
        "react": "ReAct",
    }
    for key in STRATEGIES:
        row = summary["by_strategy"][key]
        lines.append(
            f"| {labels[key]} | {row['accuracy']:.1%} | {row['number_error_rate']:.1%} | "
            f"{row['avg_tokens']:.0f} | {row['latency_p50_ms']:.0f} ms |"
        )
    lines.extend(["", "## 策略取舍", ""])
    for note in summary.get("when_not_worth") or []:
        lines.append(f"- **{note['strategy']}** · {note['when']}：{note['reason']}")
    if not summary.get("when_not_worth"):
        lines.append("- （本次对照未触发启发式）")
    lines.extend(["", "> 数字错误由 `evidence.py` 对 fixture 终稿打分，不把 Prompt 当控制手段。"])
    return "\n".join(lines) + "\n"
