#!/usr/bin/env python3
"""W9-1 双栈冒烟：经 Java BFF（:8080）验证健康、RAG 与问数。

用法（项目根目录，Java 与 Postgres 需已启动；Python 可选）：
  python-ai/.venv/bin/python eval/run_w9_e2e.py
  python-ai/.venv/bin/python eval/run_w9_e2e.py --base http://localhost:8080
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class ChainResult:
    name: str
    status: str
    detail: str
    request_id: str | None = None
    extra: dict[str, Any] | None = None


def _headers(
    *,
    token: str | None = None,
    request_id: str | None = None,
    extra: dict[str, str] | None = None,
    json_body: bool = False,
) -> dict[str, str]:
    headers = {"Accept": "application/json", "X-Request-ID": request_id or str(uuid.uuid4())}
    if json_body:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if extra:
        headers.update(extra)
    return headers


def _call(
    base: str,
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    token: str | None = None,
    extra_headers: dict[str, str] | None = None,
    timeout: float = 30.0,
    request_id: str | None = None,
) -> tuple[int, dict[str, Any] | list[Any] | str, str | None]:
    rid = request_id or str(uuid.uuid4())
    payload = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = Request(
        base.rstrip("/") + path,
        data=payload,
        method=method,
        headers=_headers(
            token=token,
            request_id=rid,
            extra=extra_headers,
            json_body=body is not None,
        ),
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            echoed = resp.headers.get("X-Request-ID") or rid
            if not raw:
                return resp.status, {}, echoed
            try:
                return resp.status, json.loads(raw), echoed
            except json.JSONDecodeError:
                return resp.status, raw, echoed
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        echoed = exc.headers.get("X-Request-ID") if exc.headers else rid
        try:
            parsed: dict[str, Any] | list[Any] | str = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = raw
        return exc.code, parsed, echoed or rid
    except URLError as exc:
        raise ConnectionError(str(exc.reason or exc)) from exc


def _detail_text(payload: dict[str, Any] | list[Any] | str) -> str:
    if isinstance(payload, dict):
        extra = payload.get("extra") if isinstance(payload.get("extra"), dict) else {}
        code = extra.get("error_code") if extra else None
        detail = payload.get("detail")
        if code and detail:
            return f"{code}: {detail}"
        if detail is not None:
            return str(detail)
        return json.dumps(payload, ensure_ascii=False)[:240]
    return str(payload)[:240]


def chain_health(base: str) -> tuple[ChainResult, dict[str, Any]]:
    status, payload, rid = _call(base, "GET", "/api/health", timeout=8.0, request_id="w9-health")
    if status != 200 or not isinstance(payload, dict) or payload.get("status") != "ok":
        return (
            ChainResult("health", "fail", f"Java 探活失败 HTTP {status} {_detail_text(payload)}", rid),
            {},
        )
    if rid != "w9-health":
        return ChainResult("health", "fail", f"X-Request-ID 未回写，得到 {rid}", rid), payload
    python = payload.get("pythonAi") if isinstance(payload.get("pythonAi"), dict) else {}
    py_status = str(python.get("status") or "unknown")
    detail = f"java=ok python={py_status}"
    if py_status != "ok":
        detail += f" ({python.get('error_code') or python.get('error') or 'down'})"
    return ChainResult("health", "pass", detail, rid), payload


def chain_asknum(base: str, python_up: bool) -> ChainResult:
    if not python_up:
        return ChainResult("asknum", "skip", "python-ai down，问数链路跳过")
    status, payload, rid = _call(
        base,
        "POST",
        "/api/chat",
        body={"message": "比亚迪2024年营业收入是多少", "use_rag": True},
        timeout=60.0,
        request_id="w9-asknum",
    )
    if status != 200 or not isinstance(payload, dict):
        return ChainResult("asknum", "fail", f"HTTP {status} {_detail_text(payload)}", rid)
    route = str(payload.get("route") or "")
    tokens = payload.get("total_tokens")
    if not route.startswith("metric"):
        return ChainResult("asknum", "fail", f"期望 metric*，实际 route={route}", rid, {"route": route})
    return ChainResult("asknum", "pass", f"route={route} tokens={tokens}", rid, {"route": route})


def chain_rag(base: str, python_up: bool) -> ChainResult:
    if not python_up:
        return ChainResult("rag", "skip", "python-ai down，问答链路跳过")
    status, payload, rid = _call(
        base,
        "POST",
        "/api/chat",
        body={"message": "比亚迪年报风险因素主要写了什么", "use_rag": True},
        timeout=90.0,
        request_id="w9-rag",
    )
    if status == 503:
        return ChainResult("rag", "skip", "未配置可用模型，RAG 问答跳过", rid)
    if status != 200 or not isinstance(payload, dict):
        return ChainResult("rag", "fail", f"HTTP {status} {_detail_text(payload)}", rid)
    route = str(payload.get("route") or "")
    if route.startswith("metric"):
        return ChainResult("rag", "fail", f"叙述题不应走进问数 route={route}", rid)
    return ChainResult(
        "rag",
        "pass",
        f"route={route} rag_used={payload.get('rag_used')} citations={len(payload.get('citations') or [])}",
        rid,
        {"route": route},
    )


def render_markdown(results: list[ChainResult], python_up: bool) -> str:
    lines = [
        "# W9-1 健康、RAG 与问数冒烟",
        "",
        f"- 时间：{datetime.now().isoformat(timespec='seconds')}",
        f"- python-ai：{'ok' if python_up else 'down（问答与问数跳过）'}",
        "",
        "| 链路 | 结果 | 关联 ID | 说明 |",
        "|---|---|---|---|",
    ]
    labels = {
        "health": "探活 + Correlation ID",
        "rag": "问答 RAG",
        "asknum": "问数",
    }
    for item in results:
        rid = item.request_id or "—"
        lines.append(f"| {labels.get(item.name, item.name)} | {item.status} | `{rid}` | {item.detail} |")
    lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run W9-1 dual-stack e2e smoke via Java BFF")
    parser.add_argument("--base", default="http://localhost:8080")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    try:
        health, health_body = chain_health(args.base)
    except ConnectionError as exc:
        print(json.dumps({"ok": False, "error": f"连不上 Java BFF: {exc}"}, ensure_ascii=False, indent=2))
        return 1

    python = health_body.get("pythonAi") if isinstance(health_body.get("pythonAi"), dict) else {}
    python_up = str(python.get("status") or "") == "ok"
    results = [
        health,
        chain_rag(args.base, python_up),
        chain_asknum(args.base, python_up),
    ]
    markdown = render_markdown(results, python_up)
    out_dir = args.out or (ROOT / "eval" / "reports" / "w9_e2e" / datetime.now().strftime("%Y%m%d_%H%M%S"))
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "python_up": python_up,
        "results": [asdict(item) for item in results],
        "ok": all(item.status != "fail" for item in results),
    }
    (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "report.md").write_text(markdown, encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"Report: {out_dir / 'report.md'}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
