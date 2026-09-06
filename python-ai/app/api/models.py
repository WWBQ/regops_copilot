from fastapi import APIRouter

from app.config import get_settings
from app.models.factory import list_available_models

router = APIRouter(prefix="/models", tags=["models"])


@router.get("")
async def models() -> dict[str, list[str] | str | None]:
    settings = get_settings()
    available = list_available_models(settings)
    default = (settings.default_model or "").strip().lower() or None
    if default not in available:
        default = available[0] if available else None
    return {"available": available, "default": default}
