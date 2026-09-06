"""W1 /chat 黄金集评测 runner。"""

from __future__ import annotations

import json
import re
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import httpx

from app.eval.selection import select_items

ProgressCallback = Callable[[int, int, str], None]


def load_golden(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def extract_numbers(text: str) -> list[float]:
    matches = re.findall(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
    return [float(m) for m in matches]


def grade_contains(reply: str, expected: str) -> tuple[bool, str]:
    keywords = [k.strip() for k in re.split(r"[|，,]", expected) if k.strip()]
    if not keywords:
        return False, "expected 为空"
    hit = [k for k in keywords if k.lower() in reply.lower()]
    need = max(1, (len(keywords) + 1) // 2)
    ok = len(hit) >= need
    return ok, f"命中 {len(hit)}/{len(keywords)}：{hit}"


def grade_numeric(reply: str, expected: str, tolerance: float) -> tuple[bool, str]:
    exp_nums = extract_numbers(expected)
    rep_nums = extract_numbers(reply)
    if not exp_nums:
        return False, "expected 无数字"
    if not rep_nums:
        return False, "回复中未提取到数字"
    exp = exp_nums[0]
    closest = min(rep_nums, key=lambda x: abs(x - exp))
    ok = abs(closest - exp) <= tolerance
    return ok, f"期望 {exp}，解析 {closest}，容差 ±{tolerance}"


def is_refusal(reply: str) -> bool:
    markers = ("无法", "不能", "无法提供", "没有足够", "无法确定", "抱歉", "无法回答")
    return any(m in reply for m in markers) and len(reply) < 200


def resolve_eval_chat_model(
    requested: str | None,
    *,
    available: list[str],
    default_model: str,
) -> str:
    """把评测请求里的 model 收成 /chat 能接受的值。空则用默认，不在列表里就报错。"""
    if not available:
        raise ValueError("no LLM model configured")
    chosen = (requested or "").strip().lower()
    if chosen:
        if chosen not in available:
            raise ValueError(
                f"unsupported model: {chosen}; available: {', '.join(available)}"
            )
        return chosen
    fallback = (default_model or "").strip().lower()
    if fallback in available:
        return fallback
    return available[0]


def run_item(
    client: httpx.Client,
    base_url: str,
    item: dict[str, Any],
    temperature: float,
    model: str | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    payload: dict[str, Any] = {
        "message": item["question"],
        "temperature": temperature,
        "use_rag": False,
    }
    if model:
        payload["model"] = model
    resp = client.post(
        f"{base_url.rstrip('/')}/chat",
        json=payload,
    )
    latency_ms = (time.perf_counter() - started) * 1000
    resp.raise_for_status()
    body = resp.json()
    reply = body.get("reply", "")

    if is_refusal(reply):
        passed, detail = False, "判为拒答"
        status = "refuse"
    elif item["grading"] == "contains":
        passed, detail = grade_contains(reply, item["expected"])
        status = "pass" if passed else "fail"
    elif item["grading"] == "numeric_tolerance":
        tol = float(item.get("numeric_tolerance", 0.1))
        passed, detail = grade_numeric(reply, item["expected"], tol)
        status = "pass" if passed else "fail"
    else:
        passed, detail = reply.strip() == item["expected"].strip(), "exact 比对"
        status = "pass" if passed else "fail"

    return {
        "id": item["id"],
        "category": item["category"],
        "question": item["question"],
        "expected": item["expected"],
        "reply": reply,
        "model": body.get("model"),
        "status": status,
        "passed": passed if status != "refuse" else False,
        "detail": detail,
        "latency_ms": round(latency_ms, 1),
    }


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for r in results if r["status"] == "pass")
    failed = sum(1 for r in results if r["status"] == "fail")
    refused = sum(1 for r in results if r["status"] == "refuse")
    latencies = [r["latency_ms"] for r in results]
    by_category: dict[str, dict[str, Any]] = {}
    for row in results:
        bucket = by_category.setdefault(
            row["category"], {"total": 0, "passed": 0, "refused": 0}
        )
        bucket["total"] += 1
        if row["status"] == "pass":
            bucket["passed"] += 1
        if row["status"] == "refuse":
            bucket["refused"] += 1
    for bucket in by_category.values():
        total_cat = bucket["total"]
        bucket["accuracy"] = round(bucket["passed"] / total_cat, 4) if total_cat else 0.0

    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "refused": refused,
        "accuracy": round(passed / total, 4) if total else 0.0,
        "refuse_rate": round(refused / total, 4) if total else 0.0,
        "latency_p50_ms": round(statistics.median(latencies), 1) if latencies else 0,
        "latency_p95_ms": round(
            sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)], 1
        )
        if latencies
        else 0,
        "by_category": by_category,
    }


def run_w1_chat_eval(
    *,
    golden_path: Path,
    base_url: str,
    limit: int = 0,
    model: str | None = None,
    categories: list[str] | None = None,
    item_ids: list[str] | None = None,
    temperature: float | None = None,
    on_progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    golden = load_golden(golden_path)
    items = select_items(
        golden["items"],
        categories=categories,
        item_ids=item_ids,
        limit=limit,
    )
    if not items:
        raise ValueError("没有匹配的评测题，请检查题型或题号")
    resolved_temperature = (
        temperature
        if temperature is not None
        else float(golden.get("default_params", {}).get("temperature", 0.0))
    )

    results: list[dict[str, Any]] = []
    total = len(items)
    with httpx.Client(timeout=120.0) as client:
        for index, item in enumerate(items, start=1):
            if on_progress:
                on_progress(index, total, item["id"])
            results.append(
                run_item(client, base_url, item, resolved_temperature, model=model)
            )

    summary = summarize(results)
    if model:
        summary["model"] = model
    return {
        "task_id": "w1_chat",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "golden_version": golden.get("version"),
        "golden_file": golden_path.name,
        "params": {
            "limit": limit,
            "use_rag": False,
            "model": model,
            "categories": categories or None,
            "item_ids": item_ids or None,
            "temperature": resolved_temperature,
        },
        "summary": summary,
        "results": results,
    }
