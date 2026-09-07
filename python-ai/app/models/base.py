from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCallRequest:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ChatResult:
    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    tool_calls: list[ToolCallRequest] = field(default_factory=list)

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
    """统一 LLM 客户端接口。"""

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
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResult:
        """返回文本 + Token 用量 + 延迟；传入 tools 时可能带 tool_calls。"""

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.1,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[StreamDelta]:
        """默认整段回退；DeepSeek / Qwen 覆盖为真正的 token 流。"""
        result = await self.chat_with_usage(messages, temperature=temperature, tools=tools)
        if result.content:
            yield StreamDelta(text=result.content)
        yield StreamDelta(done=True, result=result)
