"""金融外部风险搜索的可切换供应商适配层。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urljoin, urlparse

import requests

from agent.env_utils import get_env, require_env
from agent.tools.web_search import _get_zhipu_client


class SearchProviderError(RuntimeError):
    """搜索供应商不可用或返回了无效响应。"""


@dataclass(frozen=True)
class SearchCandidate:
    """不同搜索供应商统一后的最小结果结构。"""

    title: str
    url: str
    snippet: str
    publisher: str = ""
    published_at: str = ""


def _configured_http_url(name: str) -> str:
    value = require_env(name).strip().rstrip("/") + "/"
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SearchProviderError(f"{name} 必须是有效的 HTTP(S) URL")
    if parsed.username or parsed.password:
        raise SearchProviderError(f"{name} 不能包含用户名或密码")
    return value


def _hostname(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def _string(value: Any) -> str:
    return str(value or "").strip()


def _zhipu_search(query: str, count: int, timeout_seconds: int) -> list[SearchCandidate]:
    response = _get_zhipu_client().web_search.web_search(
        search_engine="search_pro",
        search_query=query,
        count=count,
        search_recency_filter="noLimit",
        timeout=float(timeout_seconds),
    )
    output: list[SearchCandidate] = []
    for item in getattr(response, "search_result", None) or []:
        getter = item.get if isinstance(item, dict) else lambda key, default=None: getattr(item, key, default)
        url = _string(getter("link") or getter("url"))
        output.append(
            SearchCandidate(
                title=_string(getter("title") or getter("name")) or url,
                url=url,
                snippet=_string(getter("content") or getter("snippet") or getter("summary")),
                publisher=_string(getter("media") or getter("publisher") or getter("source")),
                published_at=_string(
                    getter("publish_date") or getter("published_at") or getter("publish_time") or getter("date")
                ),
            )
        )
    return output


def _searxng_search(query: str, count: int, timeout_seconds: int) -> list[SearchCandidate]:
    endpoint = urljoin(_configured_http_url("SEARXNG_BASE_URL"), "search")
    response = requests.get(
        endpoint,
        params={
            "q": query,
            "format": "json",
            "language": "zh-CN",
            "safesearch": 1,
            "categories": "general",
        },
        headers={"Accept": "application/json"},
        timeout=float(timeout_seconds),
    )
    response.raise_for_status()
    payload = response.json()
    raw_results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(raw_results, list):
        raise SearchProviderError("SearXNG 返回格式无效")
    output: list[SearchCandidate] = []
    for item in raw_results[:count]:
        if not isinstance(item, dict):
            continue
        url = _string(item.get("url"))
        output.append(
            SearchCandidate(
                title=_string(item.get("title")) or url,
                url=url,
                snippet=_string(item.get("content")),
                publisher=_string(item.get("publisher")) or _hostname(url),
                published_at=_string(item.get("publishedDate") or item.get("published_at")),
            )
        )
    return output


def _brave_search(query: str, count: int, timeout_seconds: int) -> list[SearchCandidate]:
    response = requests.get(
        "https://api.search.brave.com/res/v1/web/search",
        params={"q": query, "count": count, "safesearch": "moderate"},
        headers={
            "Accept": "application/json",
            "X-Subscription-Token": require_env("BRAVE_SEARCH_API_KEY"),
        },
        timeout=float(timeout_seconds),
    )
    response.raise_for_status()
    payload = response.json()
    web = payload.get("web") if isinstance(payload, dict) else None
    raw_results = web.get("results") if isinstance(web, dict) else None
    if not isinstance(raw_results, list):
        return []
    output: list[SearchCandidate] = []
    for item in raw_results[:count]:
        if not isinstance(item, dict):
            continue
        url = _string(item.get("url"))
        profile = item.get("profile")
        publisher = _string(profile.get("long_name")) if isinstance(profile, dict) else ""
        output.append(
            SearchCandidate(
                title=_string(item.get("title")) or url,
                url=url,
                snippet=_string(item.get("description")),
                publisher=publisher or _hostname(url),
                published_at=_string(item.get("page_age") or item.get("age")),
            )
        )
    return output


_PROVIDERS: dict[str, Callable[[str, int, int], list[SearchCandidate]]] = {
    "searxng": _searxng_search,
    "zhipu": _zhipu_search,
    "brave": _brave_search,
}


def _provider_order() -> tuple[str, ...]:
    primary = get_env("FIN_RISK_WEB_SEARCH_PROVIDER", "searxng").strip().lower()
    fallbacks = [item.strip().lower() for item in get_env("FIN_RISK_WEB_FALLBACK_PROVIDERS", "zhipu,brave").split(",")]
    names = [primary, *fallbacks]
    unknown = [name for name in names if name and name not in _PROVIDERS]
    if unknown:
        raise SearchProviderError(f"未知搜索供应商：{', '.join(dict.fromkeys(unknown))}")
    return tuple(dict.fromkeys(name for name in names if name))


def _official_query(query: str, official_domains: tuple[str, ...]) -> str:
    site_filter = " OR ".join(f"site:{domain}" for domain in official_domains)
    return f"{query} ({site_filter})" if site_filter else query


def search_with_fallback(
    query: str,
    *,
    count: int,
    timeout_seconds: int,
    official_domains: tuple[str, ...],
) -> tuple[list[SearchCandidate], dict[str, Any]]:
    """先查官方域名，不足时补通用检索；供应商失败后按配置降级。"""

    attempted: list[dict[str, str]] = []
    fetch_count = min(max(count * 3, 8), 20)
    official_query = _official_query(query, official_domains)
    last_error: Exception | None = None

    for provider_name in _provider_order():
        provider = _PROVIDERS[provider_name]
        try:
            official_results = provider(official_query, fetch_count, timeout_seconds)
            generic_results: list[SearchCandidate] = []
            official_urls = {item.url for item in official_results if item.url}
            if len(official_urls) < count:
                generic_results = provider(query, fetch_count, timeout_seconds)
            attempted.append({"provider": provider_name, "status": "ok"})
            return [*official_results, *generic_results], {
                "provider": provider_name,
                "attempted_providers": attempted,
                "official_query": official_query,
                "generic_query": query,
            }
        except Exception as exc:  # noqa: BLE001 - 单个供应商失败后继续备用供应商
            last_error = exc
            attempted.append({"provider": provider_name, "status": "unavailable"})

    if last_error is None:
        raise SearchProviderError("未配置可用的搜索供应商")
    raise SearchProviderError("所有搜索供应商均不可用") from last_error
