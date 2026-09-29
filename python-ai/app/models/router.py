"""已配置模型列表接口。"""

from fastapi import APIRouter

from app.config import get_settings
from app.models.llm import list_available_models, resolve_model_id

router = APIRouter(prefix="/models", tags=["models"])


@router.get("")
async def models() -> dict[str, list[str] | str | None]:
    settings = get_settings()
    available = list_available_models(settings)
    try:
        default = resolve_model_id(settings.default_model, available)
    except ValueError:
        default = available[0] if available else None
    return {"available": available, "default": default}
