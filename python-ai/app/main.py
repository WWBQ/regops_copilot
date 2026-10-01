import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.logging_config import setup_logging
from app.request_id import RequestIdMiddleware
from app.router import api_router
from app.config import get_settings
from app.core.warmup import warmup_models


@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_logging()
    logging.getLogger(__name__).info("RegOps python-ai starting")
    settings = get_settings()
    if settings.startup_warmup_enabled:
        result = warmup_models(settings)
        logging.getLogger(__name__).info(
            "model warmup complete llm_clients=%s embedding=%s reranker=%s errors=%s",
            result.llm_clients,
            result.embedding_ready,
            result.reranker_ready,
            result.errors,
        )
    yield


app = FastAPI(
    title="RegOps Copilot AI Service",
    description="Python AI 微服务：模型调用、RAG、问数",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8088",
        "http://127.0.0.1:8088",
        "http://localhost",
        "http://127.0.0.1",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "traceparent"],
)
app.add_middleware(RequestIdMiddleware)

app.include_router(api_router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "RegOps Copilot python-ai is running"}
