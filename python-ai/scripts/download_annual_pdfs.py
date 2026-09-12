#!/usr/bin/env python3
"""从巨潮资讯网下载 A 股年度报告 PDF 到 data/raw/<code>_<year>_annual.pdf。"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import requests

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from download_xbrl import (  # noqa: E402
    HEADERS,
    parse_codes,
    stock_ref,
    _cninfo_query,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "data" / "raw"
STATIC_BASE = "https://static.cninfo.com.cn/"
DEFAULT_CODES = ["300750", "600519"]


def _is_full_annual(title: str, year: int) -> bool:
    text = title or ""
    if str(year) not in text or "年度报告" not in text:
        return False
    blocked = ("摘要", "已取消", "英文", "English", "更正", "补充", "修订")
    return not any(token in text for token in blocked)


def pick_annual_announcement(payload: dict, year: int) -> dict:
    anns = payload.get("announcements") or []
    matches = [row for row in anns if _is_full_annual(str(row.get("announcementTitle") or ""), year)]
    if not matches:
        titles = [str(row.get("announcementTitle") or "") for row in anns[:8]]
        raise RuntimeError(f"no full annual report for {year}; sample titles={titles}")
    return matches[0]


def download_annual_pdf(
    code: str,
    year: int,
    out_dir: Path,
    session: requests.Session,
    *,
    force: bool = False,
) -> Path:
    dest = out_dir / f"{code}_{year}_annual.pdf"
    if dest.exists() and dest.stat().st_size > 100_000 and not force:
        print(f"[skip] {dest.name} already exists ({dest.stat().st_size} bytes)")
        return dest

    ref = stock_ref(code, session)
    payload = _cninfo_query(ref, year, session)
    ann = pick_annual_announcement(payload, year)
    adjunct = str(ann.get("adjunctUrl") or "").lstrip("/")
    if not adjunct:
        raise RuntimeError(f"{code}: announcement has no adjunctUrl: {ann.get('announcementTitle')}")
    url = adjunct if adjunct.startswith("http") else STATIC_BASE + adjunct
    resp = session.get(url, headers=HEADERS, timeout=120)
    resp.raise_for_status()
    content_type = (resp.headers.get("Content-Type") or "").lower()
    if "pdf" not in content_type and not resp.content.startswith(b"%PDF"):
        raise RuntimeError(f"{code}: not a PDF ({content_type}, {len(resp.content)} bytes) url={url}")
    dest.write_bytes(resp.content)
    print(f"[ok] {code} {ann.get('announcementTitle')} -> {dest} ({len(resp.content)} bytes)")
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download cninfo annual-report PDFs")
    parser.add_argument("--codes", default=",".join(DEFAULT_CODES))
    parser.add_argument("--year", type=int, default=2024)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    codes = parse_codes(args.codes)
    args.out.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    failed: list[tuple[str, str]] = []
    for code in codes:
        try:
            download_annual_pdf(code, args.year, args.out, session, force=args.force)
            time.sleep(0.4)
        except Exception as exc:  # noqa: BLE001 — CLI aggregates per-code failures
            failed.append((code, str(exc)))
            print(f"[fail] {code}: {exc}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
