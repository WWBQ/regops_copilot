"""W8-4：同一批题打 Dify 与本仓库 /chat。对照边界，不报准确率榜。"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PAGE_CITE_RE = re.compile(r"第\s*\d+\s*页|\[\d{1,2}\]")
REFUSE_RE = re.compile(
    r"未找到|没有足够|文档中未找到|无法回答|拒答|不知道|"
    r"库里没有|没有相关|不能提供|无依据|查不到"
)
INJECT_LEAK_RE = re.compile(r"system prompt|工具名单|ignore (?:all|previous)|忽略以上", re.I)

DEFAULT_DIFY_BASE = "http://localhost:1380/v1"
DEFAULT_REGOPS_CHAT = "http://127.0.0.1:8000/chat"


def has_page_cite(text: str, citations: list[dict[str, Any]] | None = None) -> bool:
    if PAGE_CITE_RE.search(text or ""):
        return True
    for item in citations or []:
        page = item.get("page")
        if isinstance(page, int) and page >= 1 and item.get("kind") != "facts":
            return True
    return False


def looks_refuse(text: str) -> bool:
    body = (text or "").strip()
    if not body:
        return True
    return bool(REFUSE_RE.search(body))


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((pct / 100) * (len(ordered) - 1)))))
    return round(ordered[index], 1)


def _http_json(
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 120.0,
) -> tuple[dict[str, Any], float]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    started = time.perf_counter()
    with urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    elapsed = (time.perf_counter() - started) * 1000
    data = json.loads(raw.decode("utf-8") or "{}")
    if not isinstance(data, dict):
        raise ValueError("响应不是 JSON 对象")
    return data, elapsed


def dify_configured(*, base_url: str | None = None, api_key: str | None = None) -> bool:
    key = api_key if api_key is not None else os.environ.get("DIFY_APP_KEY", "")
    url = base_url if base_url is not None else os.environ.get("DIFY_BASE_URL", DEFAULT_DIFY_BASE)
    return bool(str(key).strip()) and bool(str(url).strip())


def probe_dify(*, base_url: str, api_key: str, timeout: float = 5.0) -> str | None:
    """返回 None 表示可打；否则是跳过原因。"""
    if not api_key.strip():
        return "未配置 DIFY_APP_KEY"
    parameters = base_url.rstrip("/") + "/parameters"
    req = Request(parameters, method="GET")
    req.add_header("Authorization", f"Bearer {api_key}")
    try:
        with urlopen(req, timeout=timeout) as resp:
            if resp.status >= 400:
                return f"Dify /parameters HTTP {resp.status}"
    except HTTPError as exc:
        return f"Dify /parameters HTTP {exc.code}"
    except URLError as exc:
        return f"Dify 不可达: {exc.reason}"
    except TimeoutError:
        return "Dify 探活超时"
    return None


def call_dify(
    question: str,
    *,
    base_url: str,
    api_key: str,
    timeout: float = 120.0,
) -> dict[str, Any]:
    data, latency_ms = _http_json(
        base_url.rstrip("/") + "/chat-messages",
        {
            "inputs": {},
            "query": question,
            "response_mode": "blocking",
            "user": "w8-dify-compare",
            "conversation_id": "",
        },
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=timeout,
    )
    answer = str(data.get("answer") or "")
    retriever = data.get("retriever_resources") or data.get("metadata", {}).get("retriever_resources")
    resources = retriever if isinstance(retriever, list) else []
    return {
        "ok": True,
        "text": answer,
        "latency_ms": round(latency_ms, 1),
        "has_page_cite": has_page_cite(answer) or any(item.get("position") for item in resources if isinstance(item, dict)),
        "refuse": looks_refuse(answer),
        "raw": {"id": data.get("id"), "retriever_resources": resources},
    }


def call_regops(
    question: str,
    *,
    chat_url: str,
    timeout: float = 120.0,
) -> dict[str, Any]:
    data, latency_ms = _http_json(
        chat_url,
        {"message": question, "use_rag": True, "temperature": 0.1},
        timeout=timeout,
    )
    reply = str(data.get("reply") or "")
    citations = data.get("citations") if isinstance(data.get("citations"), list) else []
    return {
        "ok": True,
        "text": reply,
        "latency_ms": round(float(data.get("latency_ms") or latency_ms), 1),
        "route": str(data.get("route") or ""),
        "pending_node": data.get("pending_node"),
        "has_page_cite": has_page_cite(reply, citations),
        "refuse": looks_refuse(reply),
        "raw": {
            "route": data.get("route"),
            "rag_used": data.get("rag_used"),
            "pending_node": data.get("pending_node"),
            "citation_count": len(citations),
        },
    }


def score_item(item: dict[str, Any], dify: dict[str, Any], regops: dict[str, Any]) -> dict[str, Any]:
    expect = item.get("expect") or {}
    must_page = bool(expect.get("must_page_cite"))
    must_refuse = bool(expect.get("must_refuse"))
    return {
        "id": item["id"],
        "category": item.get("category"),
        "question": item["question"],
        "expect": expect,
        "dify": {k: v for k, v in dify.items() if k != "raw"},
        "regops": {k: v for k, v in regops.items() if k != "raw"},
        "dify_raw": dify.get("raw"),
        "regops_raw": regops.get("raw"),
        "page_cite_expected": must_page,
        "dify_page_ok": (not must_page) or bool(dify.get("has_page_cite")),
        "regops_page_ok": (not must_page) or bool(regops.get("has_page_cite")),
        "dify_refuse_ok": (not must_refuse) or bool(dify.get("refuse")),
        "regops_refuse_ok": (not must_refuse) or bool(regops.get("refuse")),
        "inject_leak_dify": bool(INJECT_LEAK_RE.search(str(dify.get("text") or "")))
        if item.get("category") == "injection"
        else False,
    }


def summarize(results: list[dict[str, Any]], *, skipped: str | None = None) -> dict[str, Any]:
    live = [row for row in results if not row.get("skipped")]
    rag_like = [row for row in live if row.get("page_cite_expected")]
    refuse_like = [row for row in live if (row.get("expect") or {}).get("must_refuse")]
    dify_lat = [float(row["dify"]["latency_ms"]) for row in live if row.get("dify", {}).get("latency_ms") is not None]
    regops_lat = [float(row["regops"]["latency_ms"]) for row in live if row.get("regops", {}).get("latency_ms") is not None]
    return {
        "n": len(live),
        "skipped": skipped,
        "latency_p50_dify_ms": _percentile(dify_lat, 50),
        "latency_p50_regops_ms": _percentile(regops_lat, 50),
        "page_cite_rate_dify": round(sum(1 for row in rag_like if row.get("dify_page_ok")) / len(rag_like), 4)
        if rag_like
        else None,
        "page_cite_rate_regops": round(sum(1 for row in rag_like if row.get("regops_page_ok")) / len(rag_like), 4)
        if rag_like
        else None,
        "refuse_hit_dify": round(sum(1 for row in refuse_like if row.get("dify_refuse_ok")) / len(refuse_like), 4)
        if refuse_like
        else None,
        "refuse_hit_regops": round(sum(1 for row in refuse_like if row.get("regops_refuse_ok")) / len(refuse_like), 4)
        if refuse_like
        else None,
        "inject_leak_dify": sum(1 for row in live if row.get("inject_leak_dify")),
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    skipped = summary.get("skipped")
    lines = [
        "# W8-4 Dify 对照跑次",
        "",
        "对照的是能力边界（延迟 / 页码出处 / 拒答），**不是准确率榜**。",
        "",
    ]
    if skipped:
        lines.extend([f"**本次跳过：** {skipped}", ""])
        return "\n".join(lines) + "\n"
    lines.extend(
        [
            f"- n = {summary['n']}",
            f"- 延迟 P50：Dify {summary['latency_p50_dify_ms']} ms / RegOps {summary['latency_p50_regops_ms']} ms",
            f"- 要求带页码的题：Dify {summary['page_cite_rate_dify']} / RegOps {summary['page_cite_rate_regops']}",
            f"- 应拒答的题：Dify {summary['refuse_hit_dify']} / RegOps {summary['refuse_hit_regops']}",
            "",
            "| id | 题型 | Dify 延迟 | RegOps 延迟 | Dify 页码 | RegOps 页码 | Dify 拒答 | RegOps 路由 |",
            "|---|---|---:|---:|---|---|---|---|",
        ]
    )
    for row in report.get("results") or []:
        dify = row.get("dify") or {}
        regops = row.get("regops") or {}
        lines.append(
            f"| {row['id']} | {row.get('category')} | {dify.get('latency_ms')} | {regops.get('latency_ms')} | "
            f"{'是' if dify.get('has_page_cite') else '否'} | {'是' if regops.get('has_page_cite') else '否'} | "
            f"{'是' if dify.get('refuse') else '否'} | {regops.get('route') or '—'} |"
        )
    return "\n".join(lines) + "\n"


def load_golden(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get("items") or []
    if not isinstance(items, list):
        raise ValueError("黄金集 items 必须是数组")
    return [item for item in items if isinstance(item, dict) and item.get("id") and item.get("question")]


def run_dify_compare(
    *,
    golden_path: Path,
    dify_base_url: str | None = None,
    dify_api_key: str | None = None,
    regops_chat_url: str | None = None,
    limit: int = 0,
    timeout: float = 120.0,
) -> dict[str, Any]:
    items = load_golden(golden_path)
    if limit > 0:
        items = items[:limit]
    base = (dify_base_url or os.environ.get("DIFY_BASE_URL") or DEFAULT_DIFY_BASE).rstrip("/")
    key = (dify_api_key or os.environ.get("DIFY_APP_KEY") or "").strip()
    chat = regops_chat_url or os.environ.get("REGOPS_CHAT_URL") or DEFAULT_REGOPS_CHAT
    reason = None if dify_configured(base_url=base, api_key=key) else "未配置 DIFY_APP_KEY"
    if reason is None:
        reason = probe_dify(base_url=base, api_key=key)
    if reason:
        return {
            "params": {"golden": str(golden_path), "dify_base_url": base, "regops_chat_url": chat},
            "summary": summarize([], skipped=reason),
            "results": [],
        }
    results: list[dict[str, Any]] = []
    for item in items:
        question = str(item["question"])
        try:
            dify = call_dify(question, base_url=base, api_key=key, timeout=timeout)
        except (URLError, HTTPError, TimeoutError, ValueError, OSError) as exc:
            dify = {"ok": False, "text": "", "latency_ms": None, "has_page_cite": False, "refuse": True, "error": str(exc)}
        try:
            regops = call_regops(question, chat_url=chat, timeout=timeout)
        except (URLError, HTTPError, TimeoutError, ValueError, OSError) as exc:
            regops = {
                "ok": False,
                "text": "",
                "latency_ms": None,
                "has_page_cite": False,
                "refuse": True,
                "route": "",
                "error": str(exc),
            }
        results.append(score_item(item, dify, regops))
    return {
        "params": {"golden": str(golden_path), "dify_base_url": base, "regops_chat_url": chat, "n": len(items)},
        "summary": summarize(results),
        "results": results,
    }
