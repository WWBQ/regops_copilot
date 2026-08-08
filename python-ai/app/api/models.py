from fastapi import APIRouter

from app.models.factory import list_available_models

router = APIRouter(prefix="/models", tags=["models"])


@router.get("")
async def models() -> dict[str, list[str]]:
    return {"available": list_available_models()}
