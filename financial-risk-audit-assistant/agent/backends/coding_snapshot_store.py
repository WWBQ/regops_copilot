"""Private HTTP client for AI Coding ZIP artifacts in RegOps object storage."""

from __future__ import annotations

import hashlib
import re

import requests

from agent.env_utils import get_env


def _endpoint(thread_id: str) -> tuple[str, dict[str, str]]:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", thread_id):
        raise ValueError("会话 ID 无效")
    base = get_env("REGOPS_API_BASE_URL").strip()
    if not base:
        mcp_url = get_env("REGOPS_MCP_URL", "http://127.0.0.1:8000/mcp/").rstrip("/")
        base = mcp_url.removesuffix("/mcp")
    token = get_env("REGOPS_SERVICE_TOKEN").strip()
    if not base.startswith(("http://", "https://")) or not token:
        raise RuntimeError("RegOps 对象存储服务地址或服务令牌未配置")
    return f"{base.rstrip('/')}/internal/coding-snapshots/{thread_id}", {
        "X-Regops-Service-Token": token,
    }


def put_snapshot(thread_id: str, archive: bytes) -> str:
    url, headers = _endpoint(thread_id)
    try:
        response = requests.put(
            url, data=archive, headers={**headers, "Content-Type": "application/zip"}, timeout=(5, 90),
        )
    except requests.RequestException as exc:
        raise RuntimeError("RegOps 对象存储服务不可达，未保存导出快照") from exc
    if response.status_code != 200:
        raise RuntimeError(f"RegOps 对象存储保存失败（HTTP {response.status_code}）")
    try:
        payload = response.json()
        stored_hash = payload["sha256"]
        uri = payload["object_uri"]
    except (KeyError, ValueError, TypeError) as exc:
        raise RuntimeError("RegOps 对象存储未返回快照校验值") from exc
    if stored_hash != hashlib.sha256(archive).hexdigest():
        raise RuntimeError("RegOps 对象存储快照校验失败")
    if not isinstance(uri, str) or not uri.startswith("object://"):
        raise RuntimeError("RegOps 对象存储未返回稳定对象引用")
    return uri


def get_snapshot(thread_id: str) -> bytes | None:
    url, headers = _endpoint(thread_id)
    try:
        response = requests.get(url, headers=headers, timeout=(5, 90))
    except requests.RequestException as exc:
        raise RuntimeError("RegOps 对象存储服务不可达，不能恢复沙箱") from exc
    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise RuntimeError(f"RegOps 对象存储读取失败（HTTP {response.status_code}）")
    expected = response.headers.get("X-Content-SHA256", "")
    if len(response.content) > 20 * 1024 * 1024 or not expected or hashlib.sha256(response.content).hexdigest() != expected:
        raise RuntimeError("RegOps 对象存储快照校验失败，拒绝恢复沙箱")
    return response.content


def delete_snapshot(thread_id: str) -> None:
    url, headers = _endpoint(thread_id)
    try:
        response = requests.delete(url, headers=headers, timeout=(5, 30))
    except requests.RequestException as exc:
        raise RuntimeError("RegOps 对象存储服务不可达，未删除导出快照") from exc
    if response.status_code not in {204, 404}:
        raise RuntimeError(f"RegOps 对象存储删除失败（HTTP {response.status_code}）")
