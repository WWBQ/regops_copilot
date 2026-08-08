from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_llm_client_dep, get_settings_dep
from app.config import Settings
from app.models.base import LLMClient, ModelError
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    settings: Annotated[Settings, Depends(get_settings_dep)],
    client: Annotated[LLMClient, Depends(get_llm_client_dep)],
) -> ChatResponse:
    try:
        reply = await client.chat(
            [{"role": "user", "content": body.message}],
            temperature=body.temperature,
        )
    except ModelError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ChatResponse(reply=reply, model=settings.default_model)
