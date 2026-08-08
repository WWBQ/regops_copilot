from fastapi import FastAPI

from app.api import chat, health, models

app = FastAPI(
    title="RegOps Copilot AI Service",
    description="Python AI 微服务：模型调用、RAG、Agent（W1 基座）",
    version="0.1.0",
)

app.include_router(health.router)
app.include_router(chat.router)
app.include_router(models.router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "RegOps Copilot python-ai is running"}
