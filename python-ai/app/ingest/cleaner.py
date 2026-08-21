"""按 NOISE_PATTERNS 清洗 PageBlock（页眉/页脚等）。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.ingest.models import PageBlock

# 年报每页重复页眉
_ANNUAL_HEADER_LINE_RE = re.compile(
    r"^[\s\d]*(?:[\u4e00-\u9fffA-Za-z（）()·]+)?(?:股份有限公司|有限公司)?\d{4}年年度报告全文\s*$"
)

# 模板化免责声明（高频短句）
_DISCLAIMER_LINES = (
    "请务必阅读正文之后的重要声明",
    "请仔细阅读本报告",
)


@dataclass
class CleanStats:
    chars_before: int = 0
    chars_after: int = 0
    hits: dict[str, int] = field(default_factory=dict)


def _is_noise_line(line: str) -> bool:
    text = line.strip()
    if not text:
        return False
    if _ANNUAL_HEADER_LINE_RE.match(text):
        return True
    if "年度报告全文" in text and len(text) < 100:
        return True
    return any(marker in text for marker in _DISCLAIMER_LINES)


def clean_page_text(text: str) -> tuple[str, int]:
    kept: list[str] = []
    hits = 0
    for line in text.splitlines():
        if _is_noise_line(line):
            hits += 1
            continue
        kept.append(line)
    cleaned = "\n".join(kept)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned, hits


def clean_page_blocks(blocks: list[PageBlock]) -> tuple[list[PageBlock], CleanStats]:
    stats = CleanStats(chars_before=sum(len(b.text) for b in blocks))
    cleaned_blocks: list[PageBlock] = []
    header_hits = 0

    for block in blocks:
        cleaned_text, hits = clean_page_text(block.text)
        header_hits += hits
        cleaned_blocks.append(
            PageBlock(
                page_no=block.page_no,
                text=cleaned_text,
                tables=block.tables,
                source_file=block.source_file,
                content_hash=block.content_hash,
            )
        )

    stats.chars_after = sum(len(b.text) for b in cleaned_blocks)
    if header_hits:
        stats.hits["annual_header_lines"] = header_hits
    return cleaned_blocks, stats
