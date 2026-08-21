from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from zipfile import BadZipFile

import pandas as pd

ALLOWED_URL_TYPES = ("pdf", "html", "text")
ALLOWED_UPLOAD_EXTS = (".xlsx",)
REQUIRED_COLUMNS = ("id", "url", "text")
OPTIONAL_COLUMNS = ("info",)
ALLOWED_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS
MAX_ROWS = 5000

TEMPLATE_ROWS = [
    {
        "id": "sample-001",
        "url": "https://example.com/report.pdf",
        "text": "这里填写待核对的原文",
        "info": "可选补充信息",
    },
    {
        "id": "sample-002",
        "url": "https://example.com/page",
        "text": "第二条示例文本",
        "info": "",
    },
]


def json_safe(value: Any) -> Any:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if hasattr(value, "item") and callable(value.item):
        try:
            return json_safe(value.item())
        except Exception:
            return str(value)
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def cell_str(row: pd.Series, key: str, default: str = "") -> str:
    if key not in row.index:
        return default
    val = row[key]
    if pd.isna(val):
        return default
    return str(val).strip()


def build_template_bytes() -> bytes:
    from io import BytesIO

    buf = BytesIO()
    pd.DataFrame(TEMPLATE_ROWS, columns=list(ALLOWED_COLUMNS)).to_excel(buf, index=False)
    return buf.getvalue()


def _read_standard_xlsx(path: Path) -> pd.DataFrame:
    if path.suffix.lower() != ".xlsx":
        raise ValueError("只接受标准模板 .xlsx，请先下载模板再填写上传")
    head = path.read_bytes()[:4]
    if head != b"PK\x03\x04" and not head.startswith(b"PK"):
        raise ValueError(
            "不是标准 Excel .xlsx。请下载模板，用 Excel 或 WPS「另存为 Excel 工作簿 (*.xlsx)」后上传，不要用 csv、xls 或网页另存。"
        )
    try:
        return pd.read_excel(path, engine="openpyxl", dtype=str)
    except BadZipFile as exc:
        raise ValueError("xlsx 已损坏。请重新用模板另存为 .xlsx 后再上传") from exc
    except ValueError as exc:
        raise ValueError(
            "无法按标准 xlsx 读取。请下载模板，用 Excel/WPS 另存为 .xlsx 后上传。"
        ) from exc


def _validate_frame(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(col).strip() for col in df.columns]
    missing = [name for name in REQUIRED_COLUMNS if name not in df.columns]
    if missing:
        raise ValueError(
            f"缺少必填列：{', '.join(missing)}。标准列必须是 id, url, text，可选 info。请下载模板。"
        )
    unknown = [name for name in df.columns if name not in ALLOWED_COLUMNS]
    if unknown:
        raise ValueError(
            f"存在未定义列：{', '.join(unknown)}。只允许 id, url, text, info。请按模板填写。"
        )
    df = df[list(col for col in ALLOWED_COLUMNS if col in df.columns)]
    df = df.dropna(how="all")
    if df.empty:
        raise ValueError("模板中没有数据行，请至少填写 1 条")
    if len(df) > MAX_ROWS:
        raise ValueError(f"最多 {MAX_ROWS} 条，当前 {len(df)} 条")

    seen_ids: set[str] = set()
    errors: list[str] = []
    for i, row in df.iterrows():
        excel_row = int(i) + 2
        item_id = cell_str(row, "id")
        url = cell_str(row, "url")
        if not item_id:
            errors.append(f"第 {excel_row} 行 id 不能为空")
        elif item_id in seen_ids:
            errors.append(f"第 {excel_row} 行 id 重复：{item_id}")
        else:
            seen_ids.add(item_id)
        if not url:
            errors.append(f"第 {excel_row} 行 url 不能为空")
        elif not (url.startswith("http://") or url.startswith("https://")):
            errors.append(f"第 {excel_row} 行 url 必须以 http:// 或 https:// 开头")
        if len(errors) >= 8:
            break
    if errors:
        raise ValueError("数据不符合标准格式：" + "；".join(errors))
    return df


def load_items(data_path: Path, url_type: str = "pdf") -> list[dict[str, Any]]:
    url_type = url_type if url_type in ALLOWED_URL_TYPES else "pdf"
    df = _validate_frame(_read_standard_xlsx(data_path))
    items: list[dict[str, Any]] = []
    for i, (_, row) in enumerate(df.iterrows()):
        text = cell_str(row, "text")
        items.append(
            {
                "index": i,
                "url": cell_str(row, "url"),
                "type": url_type,
                "text": text,
                "otext": text,
                "detailId": cell_str(row, "id"),
                "info": cell_str(row, "info"),
            }
        )
    return items
