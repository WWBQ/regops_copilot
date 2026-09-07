"""OpenAI 兼容 chat.completions 解析（DeepSeek / Qwen）。"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.models.base import (
    ChatResult,
    ModelBadResponseError,
    ModelRateLimitError,
    ModelTimeoutError,
    StreamDelta,
    ToolCallRequest,
)

logger = logging.getLogger(__name__)


def parse_chat_completion(data: dict[str, Any], latency_ms: float) -> ChatResult:
    try:
        message = data["choices"][0]["message"]
        usage = data.get("usage") or {}
    except (KeyError, IndexError, TypeError) as exc:
        raise ModelBadResponseError("Invalid chat completion format") from exc

    raw_content = message.get("content")
    content = raw_content if isinstance(raw_content, str) else ""
    tool_calls: list[ToolCallRequest] = []
    for item in message.get("tool_calls") or []:
        if not isinstance(item, dict):
            continue
        function = item.get("function") or {}
        raw_args = function.get("arguments") or "{}"
        if isinstance(raw_args, str):
            try:
                arguments = json.loads(raw_args)
            except json.JSONDecodeError:
                arguments = {"_raw": raw_args}
        elif isinstance(raw_args, dict):
            arguments = raw_args
        else:
            arguments = {}
        if not isinstance(arguments, dict):
            arguments = {"_raw": raw_args}
        tool_calls.append(
            ToolCallRequest(
                id=str(item.get("id") or ""),
                name=str(function.get("name") or ""),
                arguments=arguments,
            )
        )
    return ChatResult(
        content=content,
        prompt_tokens=int(usage.get("prompt_tokens", 0) or 0),
        completion_tokens=int(usage.get("completion_tokens", 0) or 0),
        latency_ms=latency_ms,
        tool_calls=tool_calls,
    )


def parse_sse_data_line(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or stripped.startswith(":"):
        return None
    if not stripped.startswith("data:"):
        return None
    return stripped[5:].strip()


class OpenAIStreamAccumulator:
    def __init__(self) -> None:
        self._text: list[str] = []
        self._tools: dict[int, dict[str, str]] = {}
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def apply(self, payload: dict[str, Any]) -> str:
        usage = payload.get("usage") or {}
        if usage:
            self.prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
            self.completion_tokens = int(usage.get("completion_tokens", 0) or 0)
        choices = payload.get("choices") or []
        if not choices or not isinstance(choices[0], dict):
            return ""
        delta = choices[0].get("delta") or {}
        content = delta.get("content")
        text = content if isinstance(content, str) else ""
        if text:
            self._text.append(text)
        for item in delta.get("tool_calls") or []:
            if not isinstance(item, dict):
                continue
            index = int(item.get("index") or 0)
            slot = self._tools.setdefault(index, {"id": "", "name": "", "arguments": ""})
            if item.get("id"):
                slot["id"] = str(item["id"])
            function = item.get("function") or {}
            if function.get("name"):
                slot["name"] = str(function["name"])
            if function.get("arguments"):
                slot["arguments"] += str(function["arguments"])
        return text

    def result(self, latency_ms: float) -> ChatResult:
        tool_calls: list[ToolCallRequest] = []
        for index in sorted(self._tools):
            slot = self._tools[index]
            raw_args = slot["arguments"] or "{}"
            try:
                arguments = json.loads(raw_args)
            except json.JSONDecodeError:
                arguments = {"_raw": raw_args}
            if not isinstance(arguments, dict):
                arguments = {"_raw": raw_args}
            tool_calls.append(
                ToolCallRequest(id=slot["id"], name=slot["name"], arguments=arguments)
            )
        return ChatResult(
            content="".join(self._text),
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            latency_ms=latency_ms,
            tool_calls=tool_calls,
        )


async def stream_chat_completion(
    *,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: float,
    provider: str,
) -> AsyncIterator[StreamDelta]:
    body = {**payload, "stream": True, "stream_options": {"include_usage": True}}
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            for attempt in range(2):
                async with client.stream("POST", url, headers=headers, json=body) as response:
                    if response.status_code == 429 and attempt == 0:
                        logger.warning("%s rate limited, retrying once", provider)
                        await response.aread()
                        continue
                    if response.status_code == 429:
                        logger.error("%s rate limit exceeded after retry", provider)
                        raise ModelRateLimitError(f"{provider} rate limit exceeded")
                    if response.status_code >= 400:
                        raw = (await response.aread()).decode("utf-8", errors="replace")[:200]
                        logger.error(
                            "%s API error status=%s body=%s",
                            provider,
                            response.status_code,
                            raw,
                        )
                        raise ModelBadResponseError(
                            f"{provider} API error {response.status_code}: {raw}"
                        )
                    acc = OpenAIStreamAccumulator()
                    buffer = ""
                    finished = False
                    async for chunk in response.aiter_text():
                        buffer += chunk
                        while "\n" in buffer:
                            line, buffer = buffer.split("\n", 1)
                            event = parse_sse_data_line(line)
                            if event is None:
                                continue
                            if event == "[DONE]":
                                yield StreamDelta(
                                    done=True,
                                    result=acc.result((time.perf_counter() - started) * 1000),
                                )
                                finished = True
                                break
                            try:
                                payload_obj = json.loads(event)
                            except json.JSONDecodeError:
                                logger.warning("%s stream chunk is not JSON", provider)
                                continue
                            if not isinstance(payload_obj, dict):
                                continue
                            text = acc.apply(payload_obj)
                            if text:
                                yield StreamDelta(text=text)
                        if finished:
                            break
                    if not finished:
                        yield StreamDelta(
                            done=True,
                            result=acc.result((time.perf_counter() - started) * 1000),
                        )
                    return
    except httpx.TimeoutException as exc:
        logger.error("%s request timed out after %ss", provider, timeout)
        raise ModelTimeoutError(f"{provider} request timed out") from exc
    except httpx.HTTPError as exc:
        logger.error("%s HTTP error: %s", provider, exc)
        raise ModelBadResponseError(f"{provider} HTTP error: {exc}") from exc
