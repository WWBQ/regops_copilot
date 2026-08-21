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


def run_item(
    client: httpx.Client,
    base_url: str,
    item: dict[str, Any],
    temperature: float,
) -> dict[str, Any]:
    started = time.perf_counter()
    resp = client.post(
        f"{base_url.rstrip('/')}/chat",
        json={"message": item["question"], "temperature": temperature},
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
    number_items = [r for r in results if r["category"] == "number"]
    number_failed = sum(1 for r in number_items if r["status"] != "pass")
    number_error_rate = round(number_failed / len(number_items), 4) if number_items else 0.0

    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "refused": refused,
        "accuracy": round(passed / total, 4) if total else 0.0,
        "number_error_rate": number_error_rate,
        "latency_p50_ms": round(statistics.median(latencies), 1) if latencies else 0,
        "latency_p95_ms": round(
            sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)], 1
        )
        if latencies
        else 0,
    }


def run_w1_chat_eval(
    *,
    golden_path: Path,
    base_url: str,
    limit: int = 0,
    on_progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    golden = load_golden(golden_path)
    items = golden["items"]
    if limit > 0:
        items = items[:limit]
    temperature = golden.get("default_params", {}).get("temperature", 0.0)

    results: list[dict[str, Any]] = []
    total = len(items)
    with httpx.Client(timeout=120.0) as client:
        for index, item in enumerate(items, start=1):
            if on_progress:
                on_progress(index, total, item["id"])
            results.append(run_item(client, base_url, item, temperature))

    summary = summarize(results)
    return {
        "task_id": "w1_chat",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "golden_version": golden.get("version"),
        "golden_file": golden_path.name,
        "params": {"limit": limit},
        "summary": summary,
        "results": results,
    }
