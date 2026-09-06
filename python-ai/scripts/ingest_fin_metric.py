#!/usr/bin/env python3
"""F10 JSON → G1/G2/G3 → fin_metric。

Usage:
    python scripts/ingest_fin_metric.py
    python scripts/ingest_fin_metric.py --codes 002594,601633 --year 2024
    python scripts/ingest_fin_metric.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ingest.financial import DEFAULT_F10_ROOT, GOLDEN_CODES
from app.logging_config import setup_logging
from app.ops.quality_service import ingest_f10_to_fin_metric

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    parser = argparse.ArgumentParser(description="Ingest Eastmoney F10 JSON into fin_metric")
    parser.add_argument("--codes", default=",".join(GOLDEN_CODES))
    parser.add_argument("--year", type=int, default=2024)
    parser.add_argument("--root", type=Path, default=DEFAULT_F10_ROOT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    codes = [item.strip() for item in args.codes.split(",") if item.strip()]
    try:
        result = ingest_f10_to_fin_metric(
            codes=codes,
            year=args.year,
            root=args.root,
            dry_run=args.dry_run,
        )
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        return 1

    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    for company in result["companies"]:
        g2 = "PASS" if company["g2"]["passed"] else "REVIEW"
        status = f"accepted={company['auto_accepted']} review={company['human_review']}"
        print(f"{company['company_code']} {company['doc_id']} G2={g2} {status}")
        if company["missing_critical"]:
            print(f"  missing: {', '.join(company['missing_critical'])}")
        for rule in company["g2"]["rules"]:
            if not rule["passed"]:
                print(f"  {rule['rule_id']}: {rule['message']}")
    if result["missing_dirs"]:
        print(f"missing dirs: {result['missing_dirs']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
