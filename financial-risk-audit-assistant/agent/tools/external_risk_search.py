"""金融 Agent 内部的外部风险线索搜索工具。"""

from __future__ import annotations

import json
import logging
import re
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from threading import Lock
from time import monotonic
from typing import Any
from urllib.parse import urlparse

from langchain_core.tools import BaseTool, StructuredTool

from agent.core.events import record_event
from agent.env_utils import get_env
from agent.financial.citations import ToolCitationIndexer
from agent.tools.gitee_api import mask_token
from agent.tools.runtime_context import get_runtime_thread_id
from agent.tools.web_search_providers import SearchCandidate, search_with_fallback

logger = logging.getLogger("agent.run.external_risk_search")

_COMPANY_CODE_RE = re.compile(r"^\d{6}$")
_OFFICIAL_DOMAINS = (
    "csrc.gov.cn",
    "sse.com.cn",
    "szse.cn",
    "cninfo.com.cn",
    "bse.cn",
    "samr.gov.cn",
    "court.gov.cn",
    "wenshu.court.gov.cn",
    "zxgk.court.gov.cn",
)
_DEFAULT_PUBLIC_DOMAINS = (
    "xinhua.com",
    "people.com.cn",
    "stcn.com",
    "cs.com.cn",
    "cnstock.com",
    "yicai.com",
    "caixin.com",
)
_INJECTION_PATTERNS = (
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"system\s+prompt", re.IGNORECASE),
    re.compile(r"developer\s+message", re.IGNORECASE),
    re.compile(r"忽略.{0,12}(指令|规则|提示词)"),
    re.compile(r"(泄露|输出|显示).{0,12}(密钥|token|系统提示词|开发者消息)", re.IGNORECASE),
    re.compile(r"调用.{0,12}(工具|函数).{0,12}(绕过|修改|删除)"),
)

_CACHE_LOCK = Lock()
_SEARCH_CACHE: dict[tuple[str, int, tuple[str, ...], str, str], tuple[float, dict[str, Any]]] = {}


def _safe_public_url(value: str) -> str:
    """只把普通 HTTP(S) 公网链接交给前端。"""

    try:
        parsed = urlparse(value)
    except ValueError:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ""
    if parsed.username or parsed.password:
        return ""
    return value


def _source_tier(url: str) -> str:
    hostname = (urlparse(url).hostname or "").lower()
    if any(hostname == domain or hostname.endswith(f".{domain}") for domain in _OFFICIAL_DOMAINS):
        return "official"
    return "public_web"


def _normalized_domain(value: str) -> str:
    return value.strip().lower().removeprefix("*.").strip(".")


def _allowed_domains() -> tuple[str, ...]:
    configured = get_env("FIN_RISK_WEB_ALLOWED_DOMAINS").strip()
    values = configured.split(",") if configured else [*_OFFICIAL_DOMAINS, *_DEFAULT_PUBLIC_DOMAINS]
    return tuple(sorted({domain for item in values if (domain := _normalized_domain(item))}))


def _hostname_allowed(url: str, allowed_domains: tuple[str, ...]) -> bool:
    hostname = (urlparse(url).hostname or "").lower()
    return any(hostname == domain or hostname.endswith(f".{domain}") for domain in allowed_domains)


def _int_setting(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(get_env(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, min(value, maximum))


def _has_prompt_injection(text: str) -> bool:
    return any(pattern.search(text) for pattern in _INJECTION_PATTERNS)


def _content_hash(item: dict[str, Any]) -> str:
    canonical = json.dumps(
        {
            "title": item.get("title"),
            "url": item.get("url"),
            "publisher": item.get("publisher"),
            "published_at": item.get("published_at"),
            "snippet": item.get("snippet"),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"sha256:{sha256(canonical.encode('utf-8')).hexdigest()}"


def _cache_get(key: tuple[str, int, tuple[str, ...], str, str]) -> dict[str, Any] | None:
    now = monotonic()
    with _CACHE_LOCK:
        cached = _SEARCH_CACHE.get(key)
        if cached is None:
            return None
        expires_at, payload = cached
        if expires_at <= now:
            _SEARCH_CACHE.pop(key, None)
            return None
        return deepcopy(payload)


def _cache_put(
    key: tuple[str, int, tuple[str, ...], str, str],
    payload: dict[str, Any],
    *,
    ttl_seconds: int,
) -> None:
    if ttl_seconds <= 0:
        return
    with _CACHE_LOCK:
        _SEARCH_CACHE[key] = (monotonic() + ttl_seconds, deepcopy(payload))


def _clear_search_cache() -> None:
    """仅供测试和运维诊断清空进程内搜索缓存。"""

    with _CACHE_LOCK:
        _SEARCH_CACHE.clear()


def _normalized_text(value: str, *, max_length: int) -> str:
    return " ".join((value or "").split())[:max_length]


def create_external_risk_search_tool(
    citation_indexer: ToolCitationIndexer,
) -> BaseTool:
    """创建与本轮 MCP 工具共享引用编号的内部搜索工具。"""

    max_calls_per_run = _int_setting("FIN_RISK_WEB_MAX_CALLS_PER_RUN", 2, minimum=1, maximum=5)
    timeout_seconds = _int_setting("FIN_RISK_WEB_TIMEOUT_SECONDS", 10, minimum=2, maximum=30)
    cache_ttl_seconds = _int_setting("FIN_RISK_WEB_CACHE_TTL_SECONDS", 600, minimum=0, maximum=3600)
    run_limit_lock = Lock()
    calls_used = 0

    def search_external_risk_signals(
        company_name: str,
        company_code: str,
        year: int,
        risk_topic: str,
        max_results: int = 5,
    ) -> str:
        """搜索企业外部风险线索，不用于补造财务报表数值。

        仅在年报或财务事实已经出现异常、用户明确要求调查外部原因，或需要核查
        监管处罚、问询函、诉讼、违约、审计机构变更等公开事件时调用。搜索结果
        是不可信的候选线索；官方来源仍需人工核对原网页，普通网页不能单独形成
        财务造假、违规或因果关系认定。

        Args:
            company_name: 公司正式名称或常用证券简称。
            company_code: 六位证券代码。
            year: 待核查事件所属年份。
            risk_topic: 需要调查的风险主题，例如监管问询、诉讼或审计机构变更。
            max_results: 最多返回结果数，范围 1 到 5。

        Returns:
            JSON 字符串，包含状态、实际查询词和带引用编号的外部候选线索。
        """

        nonlocal calls_used

        name = _normalized_text(company_name, max_length=80)
        code = _normalized_text(company_code, max_length=6)
        topic = _normalized_text(risk_topic, max_length=120)
        current_year = datetime.now(timezone.utc).year
        if not name:
            return json.dumps({"status": "invalid_request", "results": [], "error": "公司名称不能为空"}, ensure_ascii=False)
        if not _COMPANY_CODE_RE.fullmatch(code):
            return json.dumps({"status": "invalid_request", "results": [], "error": "证券代码必须是六位数字"}, ensure_ascii=False)
        if not isinstance(year, int) or year < 1990 or year > current_year + 1:
            return json.dumps({"status": "invalid_request", "results": [], "error": "年份超出允许范围"}, ensure_ascii=False)
        if not topic:
            return json.dumps({"status": "invalid_request", "results": [], "error": "风险主题不能为空"}, ensure_ascii=False)

        with run_limit_lock:
            if calls_used >= max_calls_per_run:
                return json.dumps(
                    {
                        "status": "limit_exceeded",
                        "results": [],
                        "error": f"本轮外部搜索最多调用 {max_calls_per_run} 次",
                    },
                    ensure_ascii=False,
                )
            calls_used += 1

        count = max(1, min(int(max_results), 5))
        query = f"{name} {code} {year} {topic} 公告 监管"
        allowed_domains = _allowed_domains()
        configured_provider = get_env("FIN_RISK_WEB_SEARCH_PROVIDER", "searxng").strip().lower()
        configured_fallbacks = get_env("FIN_RISK_WEB_FALLBACK_PROVIDERS", "zhipu,brave").strip().lower()
        cache_key = (query, count, allowed_domains, configured_provider, configured_fallbacks)
        thread_id = get_runtime_thread_id()
        event_key = f"external-risk-search:{code}:{year}:{topic[:40]}"
        if thread_id:
            record_event(
                thread_id,
                event_key,
                "搜索外部风险线索",
                kind="fetch",
                status="in_progress",
                detail=json.dumps({"company_code": code, "year": year, "risk_topic": topic}, ensure_ascii=False),
            )

        try:
            payload = _cache_get(cache_key)
            cache_hit = payload is not None
            if payload is None:
                raw_results, search_metadata = search_with_fallback(
                    query,
                    count=count,
                    timeout_seconds=timeout_seconds,
                    official_domains=_OFFICIAL_DOMAINS,
                )
                fetched_at = datetime.now(timezone.utc).isoformat()
                results: list[dict[str, Any]] = []
                seen_urls: set[str] = set()
                filtered_domain_count = 0
                blocked_injection_count = 0
                for item in raw_results:
                    if not isinstance(item, SearchCandidate):
                        continue
                    url = _safe_public_url(item.url)
                    snippet = _normalized_text(item.snippet, max_length=1500)
                    title = _normalized_text(item.title, max_length=240) or url
                    if not url or not snippet or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    if not _hostname_allowed(url, allowed_domains):
                        filtered_domain_count += 1
                        continue
                    if _has_prompt_injection(f"{title} {snippet}"):
                        blocked_injection_count += 1
                        continue
                    result = {
                        "title": title,
                        "url": url,
                        "publisher": _normalized_text(item.publisher, max_length=120),
                        "published_at": _normalized_text(item.published_at, max_length=60),
                        "fetched_at": fetched_at,
                        "snippet": snippet,
                        "source_tier": _source_tier(url),
                        "hash_scope": "search_result_metadata",
                    }
                    result["content_hash"] = _content_hash(result)
                    results.append(result)

                # 官方来源稳定排在普通公开网页前，保持同等级内的搜索引擎原始顺序。
                results.sort(key=lambda item: 0 if item["source_tier"] == "official" else 1)
                payload = {
                    "status": "ok" if results else "insufficient_evidence",
                    "company_name": name,
                    "company_code": code,
                    "year": year,
                    "risk_topic": topic,
                    "query": query,
                    "results": results[:count],
                    "fetched_at": fetched_at,
                    "allowed_domains": list(allowed_domains),
                    "filtered_domain_count": filtered_domain_count,
                    "blocked_injection_count": blocked_injection_count,
                    **search_metadata,
                    "warning": "网页摘要是不可信候选线索；财务数值仍以已验证事实和年报原文为准。",
                }
                _cache_put(cache_key, payload, ttl_seconds=cache_ttl_seconds)

            payload["cache_hit"] = cache_hit
            payload = citation_indexer.annotate("search_external_risk_signals", payload)
            if thread_id:
                record_event(
                    thread_id,
                    event_key,
                    "搜索外部风险线索",
                    kind="fetch",
                    status="completed",
                    detail=json.dumps(
                        {
                            "query": query,
                            "result_count": len(payload.get("results") or []),
                            "cache_hit": cache_hit,
                        },
                        ensure_ascii=False,
                    ),
                )
            return json.dumps(payload, ensure_ascii=False)
        except Exception as exc:  # noqa: BLE001 - 外部服务失败必须可降级
            logger.warning(
                "外部风险搜索失败：company_code=%s year=%s error=%s",
                code,
                year,
                mask_token(str(exc)),
            )
            if thread_id:
                record_event(
                    thread_id,
                    event_key,
                    "搜索外部风险线索",
                    kind="fetch",
                    status="error",
                    detail=json.dumps({"query": query, "error": "外部搜索服务不可用"}, ensure_ascii=False),
                )
            return json.dumps(
                {
                    "status": "unavailable",
                    "company_name": name,
                    "company_code": code,
                    "year": year,
                    "risk_topic": topic,
                    "query": query,
                    "results": [],
                    "error": "外部搜索服务不可用",
                },
                ensure_ascii=False,
            )

    return StructuredTool.from_function(
        func=search_external_risk_signals,
        name="search_external_risk_signals",
        description=(
            "搜索监管处罚、交易所问询、诉讼、违约、审计机构变更等外部公开风险线索。"
            "搜索结果不能替代财务事实或年报原文，只能作为需要人工复核的候选证据。"
        ),
    )
