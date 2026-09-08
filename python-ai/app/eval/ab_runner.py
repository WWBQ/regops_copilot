"""W8-3 Prompt A/B：同一批题、固定种子、随机顺序、Wilson / McNemar。"""

from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.eval.selection import normalize_categories, select_items
from app.eval.stats import assess_ab
from app.eval.strategy_runner import (
    DEFAULT_INVENT,
    DEFAULT_JAILBREAK,
    DEFAULT_REFUSE,
    estimate_tokens,
    grade_reply,
    score_numbers,
)
from app.prompts.library import render

ProgressCallback = Callable[[int, int, str], None]

TASK_ID = "w8_ab"
ARM_A = {"name": "strategy.zero_shot", "version": "1.0.0", "label": "A"}
ARM_B = {"name": "strategy.zero_shot", "version": "1.1.0", "label": "B"}


def load_golden(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _arm_reply(item: dict[str, Any], passed: bool) -> str:
    category = str(item.get("category") or "")
    if passed:
        if category in {"numeric_unbacked", "numeric_trap", "refuse"}:
            return str(item.get("refuse_reply") or DEFAULT_REFUSE)
        return str(item.get("good_reply") or "")
    if category in {"numeric_unbacked", "numeric_trap"}:
        return str(item.get("invent_reply") or DEFAULT_INVENT)
    if category == "refuse":
        return str(item.get("jailbreak_reply") or DEFAULT_JAILBREAK)
    return str(item.get("weak_reply") or "这是常见口径。")


def run_arm(item: dict[str, Any], arm: dict[str, str]) -> dict[str, Any]:
    flags = item.get("ab") or {}
    passed_flag = bool(flags.get(arm["label"]))
    prompt = render(arm["name"], version=arm["version"], question=str(item["question"]))
    reply = _arm_reply(item, passed_flag)
    graded, detail = grade_reply(item, reply)
    numbers = score_numbers(item, reply)
    prompt_tokens = estimate_tokens(prompt.system) + estimate_tokens(prompt.user or "")
    completion_tokens = estimate_tokens(reply)
    return {
        "prompt_name": prompt.name,
        "prompt_version": prompt.version,
        "reply": reply,
        "passed": graded,
        "detail": detail,
        "number_ok": numbers["ok"],
        "number_error": not numbers["ok"],
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "tokens": prompt_tokens + completion_tokens,
        "expected_pass": passed_flag,
    }


def run_ab_eval(
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

    results: list[dict[str, Any]] = []
    total = len(ordered)
    for index, item in enumerate(ordered, start=1):
        if on_progress:
            on_progress(index, total, item["id"])
        a = run_arm(item, ARM_A)
        b = run_arm(item, ARM_B)
        a_ok = bool(a["passed"])
        b_ok = bool(b["passed"])
        results.append(
            {
                "id": item["id"],
                "category": item.get("category"),
                "question": item.get("question"),
                "status": "pass" if b_ok else "fail",
                "passed": b_ok,
                "a_passed": a_ok,
                "b_passed": b_ok,
                "discordant": a_ok != b_ok,
                "detail": f"A={'通过' if a_ok else '未通过'} · B={'通过' if b_ok else '未通过'}",
                "A": a,
                "B": b,
            }
        )

    k_a = sum(1 for row in results if row["a_passed"])
    k_b = sum(1 for row in results if row["b_passed"])
    n01 = sum(1 for row in results if (not row["a_passed"]) and row["b_passed"])
    n10 = sum(1 for row in results if row["a_passed"] and (not row["b_passed"]))
    stats = assess_ab(n=len(results), k_a=k_a, k_b=k_b, n01=n01, n10=n10)
    stats["seed"] = seed
    stats["item_order"] = item_order
    stats["backend"] = "fixture"
    stats["arm_a"] = {"prompt": ARM_A["name"], "version": ARM_A["version"]}
    stats["arm_b"] = {"prompt": ARM_B["name"], "version": ARM_B["version"]}
    stats["accuracy"] = stats["accuracy_b"]
    tokens_a = [int(row["A"]["tokens"]) for row in results]
    tokens_b = [int(row["B"]["tokens"]) for row in results]
    stats["avg_tokens_a"] = round(sum(tokens_a) / len(tokens_a), 1) if tokens_a else 0.0
    stats["avg_tokens_b"] = round(sum(tokens_b) / len(tokens_b), 1) if tokens_b else 0.0
    by_category: dict[str, dict[str, int]] = {}
    for row in results:
        category = str(row.get("category") or "unknown")
        bucket = by_category.setdefault(category, {"total": 0, "passed": 0, "failed": 0})
        bucket["total"] += 1
        if row["b_passed"]:
            bucket["passed"] += 1
        else:
            bucket["failed"] += 1
    stats["by_category"] = by_category
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
        "summary": stats,
        "results": results,
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    return (
        "# W8-3 Prompt A/B\n\n"
        f"- 黄金集：{report['golden_file']}（{report.get('golden_version')}）\n"
        f"- 种子：{summary.get('seed')}，顺序已打乱，配对按题号\n"
        f"- A：`{summary['arm_a']['prompt']}@{summary['arm_a']['version']}` "
        f"准确率 {summary['accuracy_a']:.1%}（Wilson {summary['ci95_a'][0]:.1%}–{summary['ci95_a'][1]:.1%}）\n"
        f"- B：`{summary['arm_b']['prompt']}@{summary['arm_b']['version']}` "
        f"准确率 {summary['accuracy_b']:.1%}（Wilson {summary['ci95_b'][0]:.1%}–{summary['ci95_b'][1]:.1%}）\n"
        f"- Δ={summary['delta']:.1%}，95% 区间 "
        f"[{summary['ci95_delta'][0]:.1%}, {summary['ci95_delta'][1]:.1%}]\n"
        f"- McNemar n01={summary['n01']} n10={summary['n10']} p={summary['mcnemar_p']}\n"
        f"- credible={str(summary['credible']).lower()}\n\n"
        f"**结论：** {summary['verdict']}\n"
    )
