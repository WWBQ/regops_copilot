from __future__ import annotations

import time

import pytest

from app.storage.exceptions import ObjectNotFoundError
from app.storage.local import LocalObjectStore
from app.storage.presign import build_presigned_url, verify_presigned_request


@pytest.fixture
def store(tmp_path):
    return LocalObjectStore(
        tmp_path / "objects",
        default_bucket="regops-docs",
        public_base_url="http://test",
        presign_secret="test-secret",
    )


def test_put_get_head_object(store: LocalObjectStore):
    meta = store.put_object("regops-docs", "reports/demo/sha256:abc.pdf", b"%PDF-demo", content_type="application/pdf")
    assert meta.size == 9
    assert meta.content_type == "application/pdf"
    assert store.get_object("regops-docs", "reports/demo/sha256:abc.pdf") == b"%PDF-demo"
    head = store.head_object("regops-docs", "reports/demo/sha256:abc.pdf")
    assert head.etag == meta.etag


def test_object_not_found(store: LocalObjectStore):
    with pytest.raises(ObjectNotFoundError):
        store.get_object("regops-docs", "missing.pdf")


def test_presigned_url_roundtrip(store: LocalObjectStore):
    key = "reports/demo/sha256:deadbeef.pdf"
    store.put_object("regops-docs", key, b"%PDF", content_type="application/pdf")
    url = store.generate_presigned_url("regops-docs", key, expires_in=60, page=42)
    assert url.endswith("#page=42")
    assert "signature=" in url
    assert store.resolve_local_path("regops-docs", key).is_file()


def test_presign_verify():
    url, expires = build_presigned_url(
        method="GET",
        base_url="http://test",
        bucket="b",
        key="reports/a.pdf",
        secret="secret",
        expires_in=120,
    )
    assert "expires=" in url
    assert verify_presigned_request(
        method="GET",
        bucket="b",
        key="reports/a.pdf",
        expires_at=expires,
        signature=url.split("signature=")[1],
        secret="secret",
    )


def test_presign_expired():
    expired_at = int(time.time()) - 10
    assert not verify_presigned_request(
        method="GET",
        bucket="b",
        key="k",
        expires_at=expired_at,
        signature="bad",
        secret="secret",
    )
