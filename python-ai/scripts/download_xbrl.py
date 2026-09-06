#!/usr/bin/env python3
"""Download structured financial statements for golden-sample A-share tickers.

A-share issuers **do** file XBRL instance documents for periodic reports
(JR/T 0021 — parallel to the human-readable PDF). Instance files follow
naming like ``CN_SZ_002594_GB0501_<公告编号>_yyyyMMdd.XML``.

However, cninfo's ``hisAnnouncement/query`` API (what most crawlers use)
only returns **PDF adjuncts**. Instance files historically lived on separate
electronic-disclosure portals (``xbrl.cninfo.com.cn``, ``listxbrl.sse.com.cn``,
``xbrl.szse.cn``); those endpoints are currently unreachable from this
environment, and no alternate public download URL was found in probing.

This script therefore:
1. Probes cninfo for non-PDF annual-report attachments (confirms PDF-only API).
2. Downloads Eastmoney F10 balance / income / cashflow JSON as a **structured
   fallback** for W2-2 ``fin_metric`` prototyping until raw instance access works.

Usage:
    python scripts/download_xbrl.py
    python scripts/download_xbrl.py --codes 002594,601633 --year 2024
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "data" / "raw" / "xbrl"
GOLDEN_CODES = ["002594", "601633", "000333", "000651", "600031"]

CNINFO_QUERY = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
CNINFO_TOP_SEARCH = "https://www.cninfo.com.cn/new/information/topSearch/query"
EM_REPORTS = {
    "balance": "ZCFZB",
    "income": "LRB",
    "cashflow": "XJLLB",
}
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}


@dataclass
class StockRef:
    code: str
    org_id: str
    exchange: str  # szse | sse

    @property
    def em_code(self) -> str:
        market = "SH" if self.code.startswith("6") else "SZ"
        return f"{self.code}.{market}"


def resolve_org_id(code: str, session: requests.Session) -> str:
    resp = session.post(
        CNINFO_TOP_SEARCH,
        data={"keyWord": code, "maxNum": "5"},
        headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
        timeout=20,
    )
    resp.raise_for_status()
    rows = resp.json()
    for row in rows:
        if str(row.get("code")) == code:
            return str(row["orgId"])
    raise RuntimeError(f"orgId not found for {code}")


def stock_ref(code: str, session: requests.Session) -> StockRef:
    org_id = resolve_org_id(code, session)
    exchange = "sse" if code.startswith("6") else "szse"
    return StockRef(code=code, org_id=org_id, exchange=exchange)


def _cninfo_query(ref: StockRef, year: int, session: requests.Session, searchkey: str = "") -> dict[str, Any]:
    stock = f"{ref.code},{ref.org_id}"
    column = "sse" if ref.exchange == "sse" else "szse"
    plate = "sh" if ref.exchange == "sse" else "sz"
    data = {
        "stock": stock,
        "tabName": "fulltext",
        "pageSize": "50",
        "pageNum": "1",
        "column": column,
        "category": "category_ndbg_szsh",
        "plate": plate,
        "seDate": f"{year}-01-01~{year + 1}-12-31",
        "searchkey": searchkey,
    }
    resp = session.post(
        CNINFO_QUERY,
        data=data,
        headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def probe_cninfo_xbrl(ref: StockRef, year: int, session: requests.Session) -> dict[str, Any]:
    """Return cninfo probe summary — expect PDF-only annual reports."""
    xbrl_payload = _cninfo_query(ref, year, session, searchkey="XBRL")
    ndbg_payload = _cninfo_query(ref, year, session)
    anns = ndbg_payload.get("announcements") or []
    annual = [
        a
        for a in anns
        if str(year) in (a.get("announcementTitle") or "")
        and "年度报告" in (a.get("announcementTitle") or "")
        and "摘要" not in (a.get("announcementTitle") or "")
    ]
    adjunct_types = sorted({(a.get("adjunctType") or "NONE") for a in anns})
    return {
        "xbrl_keyword_hits": xbrl_payload.get("totalAnnouncement", 0),
        "annual_reports": [
            {
                "title": a.get("announcementTitle"),
                "adjunctType": a.get("adjunctType"),
                "adjunctUrl": a.get("adjunctUrl"),
            }
            for a in annual[:3]
        ],
        "adjunct_types_seen": adjunct_types,
        "raw_xbrl_available": any(
            (a.get("adjunctType") or "").upper() in {"ZIP", "XML", "XBRL"}
            or str(a.get("adjunctUrl", "")).lower().endswith((".zip", ".xml", ".xbrl"))
            for a in anns
        ),
    }


def fetch_em_report(
    ref: StockRef,
    report_date: str,
    endpoint: str,
    session: requests.Session,
) -> dict[str, Any]:
    url = f"https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/{endpoint}AjaxNew"
    params = {
        "companyType": "4",
        "reportDateType": "0",
        "reportType": "1",
        "dates": report_date,
        "code": ref.em_code,
    }
    resp = session.get(url, params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    rows = payload.get("data") or []
    if not rows:
        raise RuntimeError(f"empty Eastmoney payload for {ref.code} {endpoint} @ {report_date}")
    return {
        "source": "eastmoney_f10",
        "endpoint": endpoint,
        "report_date": report_date,
        "sec_code": ref.em_code,
        "field_count": len(rows[0]),
        "data": rows[0],
    }


def safe_dir_name(code: str, year: int) -> str:
    return f"{code}_{year}"


def download_one(
    ref: StockRef,
    year: int,
    out_root: Path,
    session: requests.Session,
) -> Path:
    out_dir = out_root / safe_dir_name(ref.code, year)
    out_dir.mkdir(parents=True, exist_ok=True)

    probe = probe_cninfo_xbrl(ref, year, session)
    time.sleep(0.3)

    report_date = f"{year}-12-31"
    statements: dict[str, Any] = {}
    for name, endpoint in EM_REPORTS.items():
        statements[name] = fetch_em_report(ref, report_date, endpoint, session)
        time.sleep(0.2)
        target = out_dir / f"{name}.json"
        target.write_text(json.dumps(statements[name], ensure_ascii=False, indent=2), encoding="utf-8")

    manifest = {
        "stock_code": ref.code,
        "org_id": ref.org_id,
        "exchange": ref.exchange,
        "report_year": year,
        "report_date": report_date,
        "downloaded_at": date.today().isoformat(),
        "raw_xbrl": {
            "status": "instance_channel_unavailable",
            "note": (
                "Issuers file XBRL instances (JR/T 0021), but cninfo hisAnnouncement "
                "returns PDF only. Dedicated instance portals (xbrl.cninfo.com.cn, "
                "listxbrl.sse.com.cn, xbrl.szse.cn) were unreachable here; try browser "
                "or exchange data services (webapi.cninfo.com.cn / sseinfo.com)."
            ),
            "cninfo_probe": probe,
        },
        "structured_fallback": {
            "source": "eastmoney_f10",
            "files": list(EM_REPORTS.keys()),
            "purpose": "W2-2 fin_metric prototyping until raw XBRL instance access is restored",
        },
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out_dir


def parse_codes(raw: str) -> list[str]:
    codes = [c.strip() for c in raw.split(",") if c.strip()]
    bad = [c for c in codes if not re.fullmatch(r"\d{6}", c)]
    if bad:
        raise SystemExit(f"invalid stock codes: {bad}")
    return codes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download structured financial data for golden stocks")
    parser.add_argument("--codes", default=",".join(GOLDEN_CODES), help="comma-separated 6-digit codes")
    parser.add_argument("--year", type=int, default=2024)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    codes = parse_codes(args.codes)
    args.out.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    ok: list[str] = []
    failed: list[tuple[str, str]] = []

    for code in codes:
        try:
            ref = stock_ref(code, session)
            out_dir = download_one(ref, args.year, args.out, session)
            ok.append(f"{code} -> {out_dir}")
            print(f"[ok] {code} -> {out_dir}")
        except Exception as exc:  # noqa: BLE001 — CLI aggregates per-code failures
            failed.append((code, str(exc)))
            print(f"[fail] {code}: {exc}", file=sys.stderr)

    summary = {"ok": ok, "failed": failed, "out": str(args.out)}
    summary_path = args.out / f"_download_summary_{args.year}.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"summary -> {summary_path}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
