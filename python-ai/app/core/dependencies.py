"""FastAPI 公共依赖装配。"""

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends

from app.config import Settings, get_settings
from app.documents.registry import DocumentRegistry
from app.documents.service import DocumentService
from app.labeling.store import LabelStore
from app.models.llm import LLMClient, get_llm_client
from app.storage.local import LocalObjectStore


def get_settings_dep() -> Settings:
    return get_settings()


def get_llm_client_dep(
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> LLMClient:
    return get_llm_client(settings)


@lru_cache
def _label_store_for(root: str) -> LabelStore:
    return LabelStore(Path(root))


def get_label_store(
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> LabelStore:
    return _label_store_for(settings.labeling_data_dir)


@lru_cache
def _object_store_for(
    root: str,
    bucket: str,
    base_url: str,
    presign_secret: str,
) -> LocalObjectStore:
    return LocalObjectStore(
        Path(root),
        default_bucket=bucket,
        public_base_url=base_url,
        presign_secret=presign_secret,
    )


def get_object_store(
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> LocalObjectStore:
    return _object_store_for(
        settings.object_store_root,
        settings.object_store_bucket,
        settings.api_public_base_url,
        settings.object_store_presign_secret,
    )


@lru_cache
def _document_registry_for(root: str) -> DocumentRegistry:
    return DocumentRegistry(Path(root) / "_registry" / "documents.json")


@lru_cache
def _document_service_for(
    store_root: str,
    bucket: str,
    base_url: str,
    presign_secret: str,
) -> DocumentService:
    store = _object_store_for(store_root, bucket, base_url, presign_secret)
    registry = _document_registry_for(store_root)
    return DocumentService(store, registry, default_bucket=bucket)


def get_document_service(
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> DocumentService:
    return _document_service_for(
        settings.object_store_root,
        settings.object_store_bucket,
        settings.api_public_base_url,
        settings.object_store_presign_secret,
    )
