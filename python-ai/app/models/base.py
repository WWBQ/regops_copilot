from abc import ABC, abstractmethod
from dataclasses import dataclass


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


class LLMClient(ABC):
    """统一 LLM 客户端接口。"""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.1,
    ) -> str:
        """返回模型文本回复。"""

    @abstractmethod
    async def chat_with_usage(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.1,
    ) -> ChatResult:
        """返回文本 + Token 用量 + 延迟。"""
