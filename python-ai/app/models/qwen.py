import logging
import time

import httpx

from app.models.base import (
    ChatResult,
    LLMClient,
    ModelBadResponseError,
    ModelRateLimitError,
    ModelTimeoutError,
)

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = "qwen-plus"


class QwenClient(LLMClient):
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = 120.0,
    ) -> None:
        if not api_key:
            raise ValueError("Qwen API key is required")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.1,
    ) -> str:
        result = await self.chat_with_usage(messages, temperature=temperature)
        return result.content

    async def chat_with_usage(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.1,
    ) -> ChatResult:
        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self._base_url}/chat/completions"

        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await self._post_with_retry(client, url, headers, payload)
        except httpx.TimeoutException as exc:
            logger.error("Qwen request timed out after %ss", self._timeout)
            raise ModelTimeoutError("Qwen request timed out") from exc
        except httpx.HTTPError as exc:
            logger.error("Qwen HTTP error: %s", exc)
            raise ModelBadResponseError(f"Qwen HTTP error: {exc}") from exc

        latency_ms = (time.perf_counter() - started) * 1000
        result = self._parse_response(response, latency_ms)
        logger.info(
            "Qwen chat ok latency_ms=%.0f prompt_tokens=%d completion_tokens=%d",
            result.latency_ms,
            result.prompt_tokens,
            result.completion_tokens,
        )
        return result

    async def _post_with_retry(
        self,
        client: httpx.AsyncClient,
        url: str,
        headers: dict[str, str],
        payload: dict,
    ) -> httpx.Response:
        response = await client.post(url, headers=headers, json=payload)
        if response.status_code == 429:
            logger.warning("Qwen rate limited, retrying once")
            response = await client.post(url, headers=headers, json=payload)
        if response.status_code == 429:
            logger.error("Qwen rate limit exceeded after retry")
            raise ModelRateLimitError("Qwen rate limit exceeded")
        if response.status_code >= 400:
            logger.error(
                "Qwen API error status=%s body=%s",
                response.status_code,
                response.text[:200],
            )
            raise ModelBadResponseError(
                f"Qwen API error {response.status_code}: {response.text[:200]}"
            )
        return response

    def _parse_response(self, response: httpx.Response, latency_ms: float) -> ChatResult:
        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
        except (KeyError, IndexError, ValueError) as exc:
            logger.error("Invalid Qwen response format: %s", exc)
            raise ModelBadResponseError("Invalid Qwen response format") from exc

        return ChatResult(
            content=content,
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            latency_ms=latency_ms,
        )
