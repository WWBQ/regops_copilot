"""预签名 URL：本地模拟 COS 的短期访问凭证。"""

from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import quote


def _sign_payload(method: str, bucket: str, key: str, expires_at: int, secret: str) -> str:
    payload = f"{method.upper()}\n{bucket}\n{key}\n{expires_at}"
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def build_presigned_url(
    *,
    method: str,
    base_url: str,
    bucket: str,
    key: str,
    secret: str,
    expires_in: int,
) -> tuple[str, int]:
    """生成带 HMAC 签名的短期 URL，返回 (url, expires_at_unix)。"""
    expires_at = int(time.time()) + max(expires_in, 1)
    signature = _sign_payload(method, bucket, key, expires_at, secret)
    encoded_key = quote(key, safe="/")
    url = (
        f"{base_url.rstrip('/')}/storage/objects/{bucket}/{encoded_key}"
        f"?expires={expires_at}&signature={signature}"
    )
    return url, expires_at


def verify_presigned_request(
    *,
    method: str,
    bucket: str,
    key: str,
    expires_at: int,
    signature: str,
    secret: str,
) -> bool:
    if int(time.time()) > int(expires_at):
        return False
    expected = _sign_payload(method, bucket, key, int(expires_at), secret)
    return hmac.compare_digest(expected, signature)
