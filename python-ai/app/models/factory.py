import logging

from app.config import Settings, get_settings
from app.models.base import LLMClient
from app.models.deepseek import DeepSeekClient
from app.models.qwen import QwenClient

logger = logging.getLogger(__name__)


def get_llm_client(settings: Settings | None = None, *, model: str | None = None) -> LLMClient:
    settings = settings or get_settings()
    provider = (model or settings.default_model).lower()

    if provider == "deepseek":
        if not settings.deepseek_api_key:
            logger.error("DEEPSEEK_API_KEY is not configured")
            raise ValueError("DEEPSEEK_API_KEY is not configured")
        return DeepSeekClient(
            settings.deepseek_api_key,
            timeout=settings.llm_timeout_seconds,
        )

    if provider == "qwen":
        if not settings.qwen_api_key:
            logger.error("QWEN_API_KEY is not configured")
            raise ValueError("QWEN_API_KEY is not configured")
        return QwenClient(
            settings.qwen_api_key,
            timeout=settings.llm_timeout_seconds,
        )

    logger.error("Unsupported model provider: %s", settings.default_model)
    raise ValueError(f"Unsupported model provider: {settings.default_model}")


def list_available_models(settings: Settings | None = None) -> list[str]:
    settings = settings or get_settings()
    models: list[str] = []
    if settings.deepseek_api_key:
        models.append("deepseek")
    if settings.qwen_api_key:
        models.append("qwen")
    return models
