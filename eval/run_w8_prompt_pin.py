#!/usr/bin/env python3
"""钉扎 / 回滚 Prompt 当前版本（只改 pins.json，不删正文）。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python-ai"))

from app.prompts.library import (  # noqa: E402
    PromptLibraryError,
    active_version,
    changelog,
    list_templates,
    pin,
    rollback,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Pin or rollback a Prompt template")
    parser.add_argument("action", choices=["list", "pin", "rollback", "changelog"])
    parser.add_argument("--name", default="")
    parser.add_argument("--version", default="")
    args = parser.parse_args()
    try:
        if args.action == "list":
            print(json.dumps(list_templates(), ensure_ascii=False, indent=2))
            return 0
        if not args.name:
            parser.error("--name 必填")
        if args.action == "changelog":
            print(json.dumps(changelog(args.name), ensure_ascii=False, indent=2))
            return 0
        if not args.version:
            parser.error("--version 必填")
        if args.action == "pin":
            pin(args.name, args.version)
        else:
            rollback(args.name, args.version)
        print(
            json.dumps(
                {"name": args.name, "current_version": active_version(args.name)},
                ensure_ascii=False,
            )
        )
        return 0
    except PromptLibraryError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
