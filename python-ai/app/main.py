import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat, documents, health, labeling, models, sessions, storage
from app.logging_config import setup_logging


@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_logging()
    logging.getLogger(__name__).info("RegOps python-ai starting")
    yield


app = FastAPI(
    title="RegOps Copilot AI Service",
    description="Python AI 微服务：模型调用、RAG、Agent（W1 基座）",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(chat.router)
app.include_router(sessions.router)
app.include_router(models.router)
app.include_router(labeling.router)
app.include_router(documents.router)
app.include_router(storage.router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "RegOps Copilot python-ai is running"}
