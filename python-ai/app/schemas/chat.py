from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)


class ChatResponse(BaseModel):
    reply: str
    model: str
    disclaimer: str = "本回答由 AI 生成，仅供参考，不构成合规或投资建议。"
