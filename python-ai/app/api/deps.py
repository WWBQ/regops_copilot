from typing import Annotated

from fastapi import Depends

from app.config import Settings, get_settings
from app.models.base import LLMClient
from app.models.factory import get_llm_client


def get_settings_dep() -> Settings:
    return get_settings()


def get_llm_client_dep(
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> LLMClient:
    return get_llm_client(settings)
