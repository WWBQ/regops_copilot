from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import urlparse

import httpx

DOWNLOAD_TIMEOUT = 30.0


def is_http_url(url: str) -> bool:
    parsed = urlparse(url or "")
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def pdf_filename_for(url: str, idx: int) -> str:
    digest = hashlib.sha256((url or "").encode("utf-8")).hexdigest()[:12]
    return f"{idx:04d}_{digest}.pdf"


async def download_pdf(url: str, dest_path: Path) -> tuple[bool, str]:
    if not is_http_url(url):
        return False, "URL 必须是 http/https"
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = dest_path.with_suffix(".part")
    try:
        async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
            async with client.stream("GET", url) as resp:
                resp.raise_for_status()
                with open(tmp_path, "wb") as handle:
                    async for chunk in resp.aiter_bytes():
                        handle.write(chunk)
        tmp_path.replace(dest_path)
        return True, ""
    except Exception as exc:
        tmp_path.unlink(missing_ok=True)
        if dest_path.exists() and dest_path.stat().st_size == 0:
            dest_path.unlink(missing_ok=True)
        return False, str(exc)
