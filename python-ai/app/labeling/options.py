from __future__ import annotations

import json
from typing import Any

DEFAULT_LABEL_OPTIONS = ["OK", "有问题", "跳过"]
MAX_LABEL_OPTIONS = 20
MAX_LABEL_LEN = 40


def normalize_label_options(raw: Any) -> list[str]:
    if raw is None or raw == "":
        return list(DEFAULT_LABEL_OPTIONS)
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("标注选项格式无效，请传 JSON 数组") from exc
    else:
        data = raw
    if not isinstance(data, list):
        raise ValueError("标注选项必须是字符串数组")
    options: list[str] = []
    seen: set[str] = set()
    for item in data:
        text = str(item).strip()
        if not text:
            continue
        if len(text) > MAX_LABEL_LEN:
            raise ValueError(f"单个选项不超过 {MAX_LABEL_LEN} 字")
        if text in seen:
            continue
        seen.add(text)
        options.append(text)
    if not options:
        raise ValueError("至少添加一个标注选项")
    if len(options) > MAX_LABEL_OPTIONS:
        raise ValueError(f"标注选项最多 {MAX_LABEL_OPTIONS} 个")
    return options


def task_label_options(task: dict[str, Any]) -> list[str]:
    raw = task.get("label_options")
    if not raw:
        return list(DEFAULT_LABEL_OPTIONS)
    try:
        return normalize_label_options(raw)
    except ValueError:
        return list(DEFAULT_LABEL_OPTIONS)
