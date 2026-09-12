"""按 NOISE_PATTERNS 清洗 PageBlock（页眉/页脚、元信息、双栏换行、跨页表头、HTML）。"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field, replace

from app.ingest.models import PageBlock, TableBlock

# 年报每页重复页眉
_ANNUAL_HEADER_LINE_RE = re.compile(
    r"^[\s\d]*(?:[\u4e00-\u9fffA-Za-z（）()·]+)?(?:股份有限公司|有限公司)?\d{4}年年度报告全文\s*$"
)

# 模板化免责声明（高频短句）
_DISCLAIMER_LINES = (
    "请务必阅读正文之后的重要声明",
    "请仔细阅读本报告",
)

# 公告元信息行：剥离出正文，不进 RAG chunk
_META_LINE_RE = re.compile(
    r"^(?:证券代码|股票代码|证券简称|公告编号|公告文号|公告日期)[:：]"
)
_META_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\s*$")

_HTML_BLOCK_RE = re.compile(
    r"<script[\s\S]*?</script>|<style[\s\S]*?</style>|<[^>]+>",
    re.IGNORECASE,
)
_HTML_ENTITY_RE = re.compile(r"&(?:nbsp|amp|lt|gt|quot|#\d+|#x[0-9a-f]+);", re.IGNORECASE)

_TERMINAL_PUNCT = set("。！？；;：:）)」>》")
_HEADING_START_RE = re.compile(
    r"^(?:第[一二三四五六七八九十百千0-9]+[章节编条]"
    r"|[（(][一二三四五六七八九十0-9]+[）)]"
    r"|[0-9]+[、.．]"
    r"|[一二三四五六七八九十]+、)"
)
_TABLE_HEADER_LINE_RE = re.compile(
    r"^项目[\s|｜]+(?:本报告期|本期金额|本期|本年).{0,40}(?:上期金额|上年同期|上期)"
)


@dataclass
class CleanStats:
    chars_before: int = 0
    chars_after: int = 0
    hits: dict[str, int] = field(default_factory=dict)

    def add(self, key: str, n: int = 1) -> None:
        if n:
            self.hits[key] = self.hits.get(key, 0) + n


def _is_header_or_disclaimer(line: str) -> bool:
    text = line.strip()
    if not text:
        return False
    if _ANNUAL_HEADER_LINE_RE.match(text):
        return True
    if "年度报告全文" in text and len(text) < 100:
        return True
    return any(marker in text for marker in _DISCLAIMER_LINES)


def _is_meta_line(line: str) -> bool:
    text = line.strip()
    if not text:
        return False
    if _META_LINE_RE.match(text):
        return True
    return bool(_META_DATE_ONLY_RE.match(text))


def _strip_html(text: str) -> tuple[str, int]:
    if not text:
        return text, 0
    hits = 0
    stripped, n_tags = _HTML_BLOCK_RE.subn(" ", text)
    hits += n_tags
    stripped, n_ent = _HTML_ENTITY_RE.subn(" ", stripped)
    hits += n_ent
    if hits:
        stripped = html.unescape(stripped)
        stripped = re.sub(r"[ \t]{2,}", " ", stripped)
    return stripped, hits


def _looks_tabular(line: str) -> bool:
    stripped = line.strip()
    if "|" in stripped or "｜" in stripped:
        return True
    return bool(re.search(r"\S\s{2,}\S", stripped))


def _merge_hard_wraps(text: str) -> tuple[str, int]:
    """双栏/抽取导致的句中硬换行：行末无句读且下一行像续写时合并。"""
    lines = text.splitlines()
    if len(lines) < 2:
        return text, 0
    merged = [lines[0]]
    hits = 0
    for line in lines[1:]:
        prev = merged[-1]
        prev_s = prev.rstrip()
        line_s = line.strip()
        if (
            prev_s
            and line_s
            and 6 <= len(prev_s) <= 80
            and 2 <= len(line_s) <= 80
            and prev_s[-1] not in _TERMINAL_PUNCT
            and not _HEADING_START_RE.match(line_s)
            and not _looks_tabular(prev_s)
            and not _looks_tabular(line_s)
            and not re.fullmatch(r"\d+", line_s)
            and not _is_header_or_disclaimer(line_s)
            and not _is_meta_line(line_s)
        ):
            merged[-1] = prev_s + line_s
            hits += 1
        else:
            merged.append(line)
    return "\n".join(merged), hits


def _normalize_header_key(cells: list[str]) -> str:
    return re.sub(r"\s+", "", "".join(cell.strip() for cell in cells))


def _table_header_key(table: TableBlock) -> str | None:
    if not table.rows:
        return None
    row0 = table.rows[0]
    joined = _normalize_header_key(row0)
    if "项目" in joined and ("本期" in joined or "本报告期" in joined or "本年" in joined):
        if "上期" in joined or "上年" in joined:
            return joined
    return None


def _drop_repeated_table_header(table: TableBlock, previous_headers: set[str]) -> tuple[TableBlock, str | None, int]:
    key = _table_header_key(table)
    if not key:
        return table, None, 0
    if key in previous_headers:
        if len(table.rows) <= 1:
            return replace(table, rows=[]), key, 1
        return replace(table, rows=table.rows[1:]), key, 1
    return table, key, 0


def clean_page_text(
    text: str,
    *,
    previous_table_headers: set[str] | None = None,
) -> tuple[str, dict[str, int], set[str]]:
    hits: dict[str, int] = {}
    page_headers: set[str] = set()
    stripped, html_hits = _strip_html(text)
    if html_hits:
        hits["html_residue"] = html_hits

    previous = previous_table_headers or set()
    kept: list[str] = []
    header_hits = 0
    meta_hits = 0
    table_header_hits = 0
    for line in stripped.splitlines():
        if _is_header_or_disclaimer(line):
            header_hits += 1
            continue
        if _is_meta_line(line):
            meta_hits += 1
            continue
        if _TABLE_HEADER_LINE_RE.match(line.strip()):
            key = re.sub(r"\s+", "", line.strip())
            page_headers.add(key)
            if key in previous:
                table_header_hits += 1
                continue
        kept.append(line)
    if header_hits:
        hits["annual_header_lines"] = header_hits
    if meta_hits:
        hits["meta_lines"] = meta_hits
    if table_header_hits:
        hits["table_header_lines"] = table_header_hits

    cleaned = "\n".join(kept)
    cleaned, wrap_hits = _merge_hard_wraps(cleaned)
    if wrap_hits:
        hits["hard_wraps"] = wrap_hits
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned, hits, page_headers


def clean_page_blocks(blocks: list[PageBlock]) -> tuple[list[PageBlock], CleanStats]:
    stats = CleanStats(chars_before=sum(len(b.text) for b in blocks))
    cleaned_blocks: list[PageBlock] = []
    previous_headers: set[str] = set()

    for block in blocks:
        page_headers: set[str] = set()
        tables: list[TableBlock] = []
        table_header_hits = 0
        for table in block.tables:
            deduped, key, n = _drop_repeated_table_header(table, previous_headers)
            table_header_hits += n
            if key:
                page_headers.add(key)
            tables.append(deduped)
        if table_header_hits:
            stats.add("cross_page_table_headers", table_header_hits)

        cleaned_text, text_hits, text_headers = clean_page_text(
            block.text, previous_table_headers=previous_headers
        )
        page_headers |= text_headers
        for key, n in text_hits.items():
            stats.add(key, n)

        cleaned_blocks.append(
            PageBlock(
                page_no=block.page_no,
                text=cleaned_text,
                tables=tables,
                source_file=block.source_file,
                content_hash=block.content_hash,
            )
        )
        previous_headers |= page_headers

    stats.chars_after = sum(len(b.text) for b in cleaned_blocks)
    return cleaned_blocks, stats
