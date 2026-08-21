#!/usr/bin/env python3
"""W1 /chat 黄金集评测脚本。用法见 docs/eval_w1_baseline.md"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GOLDEN = Path(__file__).resolve().parent / "golden" / "w1_chat_30.json"


def load_golden(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def extract_numbers(text: str) -> list[float]:
    matches = re.findall(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
    return [float(m) for m in matches]


def grade_contains(reply: str, expected: str) -> tuple[bool, str]:
    keywords = [k.strip() for k in re.split(r"[|，,]", expected) if k.strip()]
    if not keywords:
        return False, "expected 为空"
    # 至少命中 ceil(n/2) 个关键词，避免过于严格
    hit = [k for k in keywords if k.lower() in reply.lower()]
    need = max(1, (len(keywords) + 1) // 2)
    ok = len(hit) >= need
    detail = f"命中 {len(hit)}/{len(keywords)}：{hit}"
    return ok, detail


def grade_numeric(reply: str, expected: str, tolerance: float) -> tuple[bool, str]:
    exp_nums = extract_numbers(expected)
    rep_nums = extract_numbers(reply)
    if not exp_nums:
        return False, "expected 无数字"
    if not rep_nums:
        return False, "回复中未提取到数字"
    exp = exp_nums[0]
    # 取与 expected 最接近的回复数字
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


def write_report(
    out_dir: Path,
    golden: dict[str, Any],
    results: list[dict[str, Any]],
    summary: dict[str, Any],
    base_url: str,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "golden_version": golden.get("version"),
        "summary": summary,
        "results": results,
    }
    (out_dir / "report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    md = [
        "# W1 /chat 评测报告",
        "",
        f"- 运行时间（UTC）：{payload['run_at']}",
        f"- 接口：{base_url}/chat",
        f"- 黄金集：{golden.get('version')}",
        "",
        "## 汇总",
        "",
        f"| 指标 | 值 |",
        f"|------|-----|",
        f"| 总题数 | {summary['total']} |",
        f"| 正确 | {summary['passed']} |",
        f"| 错误 | {summary['failed']} |",
        f"| 拒答 | {summary['refused']} |",
        f"| 准确率 | {summary['accuracy']:.2%} |",
        f"| 数字错误率 | {summary['number_error_rate']:.2%} |",
        f"| P50 延迟 (ms) | {summary['latency_p50_ms']} |",
        f"| P95 延迟 (ms) | {summary['latency_p95_ms']} |",
        "",
        "## 错题",
        "",
    ]
    wrong = [r for r in results if r["status"] != "pass"]
    if not wrong:
        md.append("（无）")
    else:
        for r in wrong:
            md.extend(
                [
                    f"### {r['id']} · {r['status']}",
                    f"- 问：{r['question']}",
                    f"- 期望：{r['expected']}",
                    f"- 答：{r['reply'][:300]}",
                    f"- 说明：{r['detail']}",
                    "",
                ]
            )
    (out_dir / "report.md").write_text("\n".join(md), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run W1 chat golden set eval")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="python-ai 服务地址",
    )
    parser.add_argument(
        "--golden",
        type=Path,
        default=DEFAULT_GOLDEN,
        help="黄金集 JSON 路径",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="报告输出目录，默认 eval/reports/YYYYMMDD_HHMMSS",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="只跑前 N 题（调试用）",
    )
    args = parser.parse_args()

    golden = load_golden(args.golden)
    items = golden["items"]
    if args.limit > 0:
        items = items[: args.limit]

    temperature = golden.get("default_params", {}).get("temperature", 0.0)
    out_dir = args.out or (
        Path(__file__).resolve().parent
        / "reports"
        / datetime.now().strftime("%Y%m%d_%H%M%S")
    )

    results: list[dict[str, Any]] = []
    with httpx.Client(timeout=60.0) as client:
        for item in items:
            print(f"→ {item['id']} …", flush=True)
            try:
                results.append(run_item(client, args.base_url, item, temperature))
            except httpx.HTTPError as exc:
                print(f"  HTTP 错误: {exc}", file=sys.stderr)
                return 1

    summary = summarize(results)
    write_report(out_dir, golden, results, summary, args.base_url)

    print("\n=== W1 Eval Summary ===")
    for k, v in summary.items():
        print(f"{k}: {v}")
    print(f"\n报告已写入: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
