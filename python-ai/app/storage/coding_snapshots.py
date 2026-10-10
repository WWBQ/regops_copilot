"""Private AI Coding ZIP artifacts in the existing RegOps object store."""

from __future__ import annotations

import io
import hashlib
import stat
import uuid
import zipfile
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.config import Settings
from app.core.dependencies import get_object_store, get_settings_dep
from app.storage.exceptions import ObjectNotFoundError
from app.storage.local import LocalObjectStore

router = APIRouter(prefix="/internal/coding-snapshots", tags=["internal"])
StoreDep = Annotated[LocalObjectStore, Depends(get_object_store)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
MAX_ARCHIVE_BYTES = 20 * 1024 * 1024
MAX_FILES = 2000


def _object_key(thread_id: str) -> str:
    user_id, separator, conversation_id = thread_id.partition("_coding_")
    try:
        if not separator or str(uuid.UUID(user_id)) != user_id or str(uuid.UUID(conversation_id)) != conversation_id:
            raise ValueError
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="invalid coding thread ID") from exc
    return f"coding-snapshots/{thread_id}.zip"


def _validate_archive(body: bytes) -> None:
    if len(body) > MAX_ARCHIVE_BYTES or not zipfile.is_zipfile(io.BytesIO(body)):
        raise HTTPException(status_code=422, detail="invalid or oversized coding ZIP")
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        members = archive.infolist()
        if len(members) > MAX_FILES or sum(item.file_size for item in members) > MAX_ARCHIVE_BYTES:
            raise HTTPException(status_code=422, detail="coding ZIP exceeds file or size limit")
        for item in members:
            parts = item.filename.split("/")
            mode = item.external_attr >> 16
            file_type = stat.S_IFMT(mode)
            if (item.is_dir() or file_type not in {0, stat.S_IFREG} or item.filename.startswith("/") or "\\" in item.filename or
                    any(part in {"", ".", ".."} for part in parts) or
                    stat.S_ISLNK(mode) or item.flag_bits & 1):
                raise HTTPException(status_code=422, detail="unsafe coding ZIP entry")
        if archive.testzip() is not None:
            raise HTTPException(status_code=422, detail="corrupt coding ZIP entry")


@router.put("/{thread_id}")
async def put_coding_snapshot(
    thread_id: str, request: Request, store: StoreDep, settings: SettingsDep,
) -> dict[str, str | int]:
    key = _object_key(thread_id)
    if int(request.headers.get("content-length") or 0) > MAX_ARCHIVE_BYTES:
        raise HTTPException(status_code=413, detail="coding ZIP exceeds 20 MiB")
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_ARCHIVE_BYTES:
            raise HTTPException(status_code=413, detail="coding ZIP exceeds 20 MiB")
        chunks.append(chunk)
    body = b"".join(chunks)
    _validate_archive(body)
    meta = store.put_object(settings.object_store_bucket, key, body, content_type="application/zip")
    return {"key": key, "object_uri": f"object://{settings.object_store_bucket}/{key}", "sha256": meta.etag, "size": meta.size}


@router.get("/{thread_id}")
def get_coding_snapshot(thread_id: str, store: StoreDep, settings: SettingsDep) -> Response:
    key = _object_key(thread_id)
    try:
        body = store.get_object(settings.object_store_bucket, key)
        meta = store.head_object(settings.object_store_bucket, key)
    except ObjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="coding snapshot not found") from exc
    if len(body) > MAX_ARCHIVE_BYTES or meta.etag != hashlib.sha256(body).hexdigest():
        raise HTTPException(status_code=500, detail="coding snapshot integrity check failed")
    return Response(
        content=body,
        media_type="application/zip",
        headers={"X-Content-SHA256": meta.etag, "Cache-Control": "no-store"},
    )


@router.delete("/{thread_id}", status_code=204)
def delete_coding_snapshot(thread_id: str, store: StoreDep, settings: SettingsDep) -> None:
    store.delete_object(settings.object_store_bucket, _object_key(thread_id))
