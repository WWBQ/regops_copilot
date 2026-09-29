"""RegOps 模型调用：LangChain 客户端、模型配置与业务返回类型。"""

import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from time import perf_counter
from typing import Any

import httpx
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, AIMessageChunk, convert_to_messages
from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


@dataclass
class ChatResult:
    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class ModelError(Exception):
    """模型调用基础异常。"""


class ModelTimeoutError(ModelError):
    """请求超时。"""


class ModelRateLimitError(ModelError):
    """429 限流。"""


class ModelBadResponseError(ModelError):
    """响应格式异常或缺少必要字段。"""


@dataclass
class StreamDelta:
    text: str = ""
    done: bool = False
    result: ChatResult | None = None


class LLMClient(ABC):
    """普通聊天与流式聊天共用的接口。"""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.1,
    ) -> str:
        """返回模型文本回复。"""

    @abstractmethod
    async def chat_with_usage(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.1,
    ) -> ChatResult:
        """返回文本与用量。"""

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.1,
    ) -> AsyncIterator[StreamDelta]:
        result = await self.chat_with_usage(messages, temperature=temperature)
        if result.content:
            yield StreamDelta(text=result.content)
        yield StreamDelta(done=True, result=result)


def _model_error(exc: Exception) -> ModelError:
    if isinstance(exc, ModelError):
        return exc
    if isinstance(exc, (APITimeoutError, httpx.TimeoutException)):
        return ModelTimeoutError("model request timed out")
    if isinstance(exc, RateLimitError):
        return ModelRateLimitError("model rate limit exceeded")
    if isinstance(exc, APIStatusError):
        return ModelBadResponseError(f"model API error {exc.status_code}")
    if isinstance(exc, (APIConnectionError, httpx.HTTPError)):
        return ModelBadResponseError("model API connection failed")
    return ModelBadResponseError("model request failed")


def _chat_result(
    message: AIMessage | AIMessageChunk,
    latency_ms: float,
    usage_override: dict[str, Any] | None = None,
) -> ChatResult:
    content = message.content
    if not isinstance(content, str):
        if content:
            raise ModelBadResponseError("model returned non-text content")
        content = ""

    usage = usage_override or message.usage_metadata or {}
    if not usage:
        usage = message.response_metadata.get("token_usage") or {}
    return ChatResult(
        content=content,
        prompt_tokens=int(usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0),
        completion_tokens=int(usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0),
        latency_ms=latency_ms,
    )


class LangChainChatClient(LLMClient):
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model_id: str,
        timeout: float,
    ) -> None:
        if not api_key:
            raise ValueError("model API key is required")
        self._model = init_chat_model(
            model=model_id,
            model_provider="openai",
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=1,
            stream_usage=True,
        )

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.1,
    ) -> str:
        result = await self.chat_with_usage(messages, temperature=temperature)
        return result.content

    async def chat_with_usage(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.1,
    ) -> ChatResult:
        started_at = perf_counter()
        try:
            response = await self._model.ainvoke(convert_to_messages(messages), temperature=temperature)
            return _chat_result(response, (perf_counter() - started_at) * 1000)
        except Exception as exc:
            logger.exception("LangChain model request failed")
            mapped = _model_error(exc)
            if mapped is exc:
                raise
            raise mapped from exc

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.1,
    ) -> AsyncIterator[StreamDelta]:
        started_at = perf_counter()
        combined: AIMessageChunk | None = None
        latest_usage: dict[str, Any] | None = None
        try:
            async for chunk in self._model.astream(convert_to_messages(messages), temperature=temperature):
                if chunk.content and not isinstance(chunk.content, str):
                    raise ModelBadResponseError("model returned non-text content")
                combined = chunk if combined is None else combined + chunk
                if chunk.usage_metadata:
                    latest_usage = chunk.usage_metadata
                if isinstance(chunk.content, str) and chunk.content:
                    yield StreamDelta(text=chunk.content)
            if combined is None:
                raise ModelBadResponseError("empty model stream")
            result = _chat_result(
                combined,
                (perf_counter() - started_at) * 1000,
                latest_usage,
            )
            yield StreamDelta(done=True, result=result)
        except Exception as exc:
            logger.exception("LangChain model stream failed")
            mapped = _model_error(exc)
            if mapped is exc:
                raise
            raise mapped from exc


def _model_ids(raw: str) -> list[str]:
    return list(dict.fromkeys(item.strip() for item in raw.split(",") if item.strip()))


def _configured_models(settings: Settings) -> dict[str, tuple[str, str, str]]:
    """模型 ID -> (供应商, API Key, OpenAI 兼容地址)。"""
    models: dict[str, tuple[str, str, str]] = {}
    providers = (
        ("deepseek", settings.deepseek_api_key, settings.deepseek_base_url, settings.deepseek_model_ids),
        ("qwen", settings.qwen_api_key, settings.qwen_base_url, settings.qwen_model_ids),
    )
    for provider, api_key, base_url, configured_ids in providers:
        if not api_key:
            continue
        for model_id in _model_ids(configured_ids):
            if any(existing.casefold() == model_id.casefold() for existing in models):
                raise ValueError(f"duplicate model ID: {model_id}")
            models[model_id] = (provider, api_key, base_url)
    return models


def resolve_model_id(requested: str, available: list[str]) -> str:
    """兼容旧的 deepseek/qwen 选择值，内部统一使用具体模型 ID。"""
    choice = requested.strip()
    if choice in available:
        return choice
    for model_id in available:
        if model_id.casefold() == choice.casefold():
            return model_id
    alias = choice.casefold()
    if alias in ("deepseek", "qwen"):
        for model_id in available:
            if model_id.casefold().startswith(alias):
                return model_id
    raise ValueError(f"unsupported model: {choice}; available: {', '.join(available)}")


def get_llm_client(settings: Settings | None = None, *, model: str | None = None) -> LLMClient:
    settings = settings or get_settings()
    configured = _configured_models(settings)
    if not configured:
        logger.error("No LLM model configured")
        raise ValueError("no LLM model configured")
    model_id = resolve_model_id(model or settings.default_model, list(configured))
    _provider, api_key, base_url = configured[model_id]
    return LangChainChatClient(
        api_key=api_key,
        base_url=base_url,
        model_id=model_id,
        timeout=settings.llm_timeout_seconds,
    )


def list_available_models(settings: Settings | None = None) -> list[str]:
    return list(_configured_models(settings or get_settings()))
