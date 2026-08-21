"""COS 风格对象访问：预签名 GET 下载/预览。"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from app.api.deps import get_object_store, get_settings_dep
from app.config import Settings
from app.storage.exceptions import ObjectNotFoundError
from app.storage.local import LocalObjectStore
from app.storage.presign import verify_presigned_request

router = APIRouter(prefix="/storage", tags=["storage"])
logger = logging.getLogger(__name__)

StoreDep = Annotated[LocalObjectStore, Depends(get_object_store)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]


@router.get("/objects/{bucket}/{key:path}")
def get_object_with_presign(
    bucket: str,
    key: str,
    store: StoreDep,
    settings: SettingsDep,
    expires: int = Query(..., description="Unix 过期时间"),
    signature: str = Query(..., min_length=16),
) -> FileResponse:
    """模拟 COS GetObject：必须携带有效预签名，私有桶不可裸访。"""
    if not verify_presigned_request(
        method="GET",
        bucket=bucket,
        key=key,
        expires_at=expires,
        signature=signature,
        secret=settings.object_store_presign_secret,
    ):
        raise HTTPException(status_code=403, detail="invalid or expired presigned URL")

    try:
        path = store.resolve_local_path(bucket, key)
        meta = store.head_object(bucket, key)
    except ObjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    headers = {"Cache-Control": "private, max-age=60"}
    if meta.content_type == "application/pdf" or path.suffix.lower() == ".pdf":
        headers["Content-Disposition"] = f'inline; filename="{path.name}"'
        return FileResponse(path, media_type="application/pdf", headers=headers)

    return FileResponse(
        path,
        media_type=meta.content_type,
        filename=path.name,
        headers=headers,
    )
