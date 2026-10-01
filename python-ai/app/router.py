"""所有 HTTP 功能入口的集中清单。"""

from fastapi import APIRouter, Depends

from app.chat.router import router as chat_router
from app.core.health import router as health_router
from app.documents.router import router as documents_router
from app.eval.router import router as evaluation_router
from app.ingest.router import router as ingest_router
from app.labeling.router import router as labeling_router
from app.models.router import router as models_router
from app.ops.router import router as operations_router
from app.prompts.router import router as prompts_router
from app.quality.router import router as quality_router
from app.sessions.router import router as sessions_router
from app.storage.router import router as storage_router
from app.security.service_auth import require_service_token

api_router = APIRouter()
api_router.include_router(health_router)
# 浏览器直接打开短期预签名 URL；该路由由 expires + HMAC signature 自己鉴权。
api_router.include_router(storage_router)

for feature_router in (
    chat_router,
    sessions_router,
    models_router,
    labeling_router,
    documents_router,
    ingest_router,
    operations_router,
    quality_router,
    evaluation_router,
    prompts_router,
):
    api_router.include_router(
        feature_router,
        dependencies=[Depends(require_service_token)],
    )
