"""终稿数字校验：抽取 → 回溯事实/引用 → 拦截或降级。不靠 Prompt 保证不编造。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from itertools import combinations
from typing import Any, Sequence

from app.chat.schemas import Citation

_RELATIVE_TOL = Decimal("0.0001")
_ABS_TOL = Decimal("0.01")


def parse_claimed_yuan(text: str) -> Decimal:
    raw = text.strip().replace(",", "").replace("，", "").replace(" ", "")
    multiplier = Decimal("1")
    if raw.endswith("亿元"):
        raw, multiplier = raw[:-2], Decimal("100000000")
    elif raw.endswith("亿"):
        raw, multiplier = raw[:-1], Decimal("100000000")
    elif raw.endswith("万元"):
        raw, multiplier = raw[:-2], Decimal("10000")
    elif raw.endswith("万"):
        raw, multiplier = raw[:-1], Decimal("10000")
    elif raw.endswith("元"):
        raw = raw[:-1]
    try:
        return Decimal(raw) * multiplier
    except InvalidOperation as exc:
        raise ValueError(f"无法解析金额：{text}") from exc


def _same_amount(claimed: Decimal, fact: Decimal) -> bool:
    tolerance = max(_ABS_TOL, abs(fact) * _RELATIVE_TOL)
    return abs(claimed - fact) <= tolerance

INTERCEPT_PREFIX = "【数字校验拦截】"
REDACT_TOKEN = "〔无证据〕"
OK_STATUSES = frozenset({"fact", "citation"})
BLOCK_STATUSES = frozenset({"unit_error", "percent_scale", "computed", "unbacked"})
STATUS_ZH = {
    "unit_error": "量纲错误",
    "percent_scale": "百分数/小数量纲",
    "computed": "手算差额或比率",
    "unbacked": "无证据",
}
_UNIT_SCALES = (
    ("亿元", Decimal("100000000")),
    ("亿", Decimal("100000000")),
    ("万元", Decimal("10000")),
    ("万", Decimal("10000")),
    ("元", Decimal("1")),
)
_PERCENT_TOL = Decimal("0.05")
_SKIP_RES = (
    re.compile(r"第\s*\d+\s*页"),
    re.compile(r"\[\d{1,2}\]"),
    re.compile(r"-?\d+(?:\.\d+)?\s*元/股"),
    re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)\s*年?"),
    re.compile(r"(?<!\d)\d{6}(?:_\d{4})?(?!\d)"),
    re.compile(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
    ),
    re.compile(r"-?\d{1,3}(?:,\d{3})+(?:\.\d+)?\s*余?(?:项|件|人|次|个|家)"),
    re.compile(r"-?\d+(?:\.\d+)?\s*余?(?:项|件|人)"),
    re.compile(r"\d+\s*(?:小时|分钟|秒|次|轮|步|个|家|条|页|项|科|种|日)"),
    re.compile(r"\d{1,2}\s*月"),
    re.compile(r"[pP]\s*\.?\s*\d+\b"),
)
_PERCENT_RE = re.compile(r"-?\d+(?:\.\d+)?\s*[%％]")
_AMOUNT_RE = re.compile(
    r"约?\s*(?:-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|-?\d+(?:\.\d+)?)\s*(?:亿元|万元|亿|万|元)?"
)


@dataclass(frozen=True)
class NumberClaim:
    text: str
    start: int
    end: int
    kind: str
    mantissa: Decimal
    yuan: Decimal | None
    percent: Decimal | None
    unit: str


@dataclass
class GroundedClaim:
    claim: NumberClaim
    status: str
    detail: str = ""


@dataclass(frozen=True)
class EvidencePack:
    facts_yuan: tuple[Decimal, ...] = ()
    citation_yuan: tuple[Decimal, ...] = ()
    percents: tuple[Decimal, ...] = ()
    snippets: tuple[str, ...] = ()


@dataclass
class NumberCheckResult:
    ok: bool
    claims: list[GroundedClaim] = field(default_factory=list)
    reply: str = ""

    @property
    def blocked(self) -> list[GroundedClaim]:
        return [item for item in self.claims if item.status not in OK_STATUSES]

    def to_trace(self) -> dict[str, Any]:
        return {
            "name": "number_check",
            "node": "number_check",
            "ok": self.ok,
            "stop": not self.ok,
            "blocked": [
                {"text": item.claim.text, "status": item.status, "detail": item.detail}
                for item in self.blocked
            ],
        }


def _mask_skips(text: str) -> str:
    masked = text
    for pattern in _SKIP_RES:
        masked = pattern.sub(lambda match: " " * len(match.group(0)), masked)
    return masked


def _to_decimal(raw: str) -> Decimal:
    return Decimal(raw.strip().replace(",", "").replace("，", "").replace(" ", ""))


def _parse_amount_span(text: str) -> tuple[Decimal, Decimal | None, str]:
    cleaned = text.strip().replace("约", "").strip()
    unit = ""
    for name, _scale in _UNIT_SCALES:
        if cleaned.endswith(name):
            unit = name
            break
    mantissa_text = cleaned[: -len(unit)] if unit else cleaned
    mantissa = _to_decimal(mantissa_text)
    if unit:
        return mantissa, parse_claimed_yuan(cleaned), unit
    return mantissa, mantissa, ""


def extract_claims(text: str) -> list[NumberClaim]:
    if not text:
        return []
    masked = _mask_skips(text)
    occupied = [False] * len(masked)
    claims: list[NumberClaim] = []

    def _take(start: int, end: int) -> None:
        for index in range(start, end):
            occupied[index] = True

    def _free(start: int, end: int) -> bool:
        return not any(occupied[start:end])

    for match in _PERCENT_RE.finditer(masked):
        start, end = match.start(), match.end()
        if not _free(start, end):
            continue
        raw = text[start:end]
        try:
            percent = _to_decimal(re.sub(r"[%％]", "", raw))
        except InvalidOperation:
            continue
        _take(start, end)
        claims.append(
            NumberClaim(
                text=raw.strip(),
                start=start,
                end=end,
                kind="percent",
                mantissa=percent,
                yuan=None,
                percent=percent,
                unit="%",
            )
        )

    for match in _AMOUNT_RE.finditer(masked):
        start, end = match.start(), match.end()
        if not _free(start, end):
            continue
        raw = text[start:end].strip()
        if not raw or raw in {"-", ".", ","}:
            continue
        try:
            mantissa, yuan, unit = _parse_amount_span(raw)
        except (InvalidOperation, ValueError):
            continue
        if not unit:
            if yuan is None:
                continue
            abs_value = abs(yuan)
            has_comma = "," in raw or "，" in raw
            has_dot = "." in raw
            if abs_value == 0:
                continue
            if abs_value < 1:
                _take(start, end)
                claims.append(
                    NumberClaim(
                        text=raw,
                        start=start,
                        end=end,
                        kind="percent",
                        mantissa=yuan,
                        yuan=None,
                        percent=yuan,
                        unit="",
                    )
                )
                continue
            if not has_comma and not has_dot and abs_value < 1000:
                continue
        _take(start, end)
        claims.append(
            NumberClaim(
                text=raw,
                start=start,
                end=end,
                kind="amount",
                mantissa=mantissa,
                yuan=yuan,
                percent=None,
                unit=unit,
            )
        )

    claims.sort(key=lambda item: item.start)
    return claims


def _same_percent(left: Decimal, right: Decimal) -> bool:
    return abs(left - right) <= _PERCENT_TOL


def _dedupe_decimals(values: Sequence[Decimal]) -> list[Decimal]:
    unique: list[Decimal] = []
    for item in values:
        if any(_same_amount(item, seen) for seen in unique):
            continue
        unique.append(item)
    return unique


def pack_from_facts_and_snippets(
    facts: Sequence[Any] | None = None,
    snippets: Sequence[str] | None = None,
) -> EvidencePack:
    facts_yuan: list[Decimal] = []
    for item in facts or []:
        if item is None or item == "":
            continue
        try:
            facts_yuan.append(Decimal(str(item)))
        except (InvalidOperation, ValueError):
            continue
    citation_yuan: list[Decimal] = []
    percents: list[Decimal] = []
    clean_snippets: list[str] = []
    for snippet in snippets or []:
        text = str(snippet or "").strip()
        if not text:
            continue
        clean_snippets.append(text)
        for claim in extract_claims(text):
            if claim.percent is not None:
                percents.append(claim.percent)
            if claim.yuan is not None:
                citation_yuan.append(claim.yuan)
    return EvidencePack(
        facts_yuan=tuple(_dedupe_decimals(facts_yuan)),
        citation_yuan=tuple(_dedupe_decimals(citation_yuan)),
        percents=tuple(percents),
        snippets=tuple(clean_snippets),
    )


def pack_from_citations(
    citations: Sequence[Citation] | None,
    extra_facts: Sequence[Any] | None = None,
) -> EvidencePack:
    facts = list(extra_facts or [])
    snippets: list[str] = []
    for cite in citations or []:
        snippet = cite.snippet or ""
        if snippet:
            snippets.append(snippet)
        if cite.kind == "facts":
            token = snippet.strip().split()[-1] if snippet.strip() else ""
            try:
                facts.append(Decimal(token.replace(",", "")))
            except (InvalidOperation, ValueError, IndexError):
                pass
    return pack_from_facts_and_snippets(facts, snippets)


def _unit_error(claim: NumberClaim, facts: Sequence[Decimal]) -> bool:
    if claim.yuan is None:
        return False
    if any(_same_amount(claim.yuan, fact) for fact in facts):
        return False
    for _name, scale in _UNIT_SCALES:
        alt = claim.mantissa * scale
        if any(_same_amount(alt, fact) for fact in facts):
            return True
    return False


def _percent_scale(claim: NumberClaim, pack: EvidencePack) -> bool:
    if claim.kind != "percent" or claim.percent is None:
        return False
    value = claim.percent
    for pct in pack.percents:
        if claim.unit == "%" and _same_percent(value, pct):
            return False
        if claim.unit != "%" and _same_percent(value * Decimal(100), pct):
            return True
        if claim.unit == "%" and _same_percent(value, pct * Decimal(100)):
            return True
        if claim.unit != "%" and _same_percent(value, pct * Decimal("0.01")):
            return True
    return False


def _computed(claim: NumberClaim, facts: Sequence[Decimal]) -> bool:
    unique = _dedupe_decimals(list(facts))
    if len(unique) < 2:
        return False
    for left, right in combinations(unique, 2):
        if claim.yuan is not None:
            for value in (left - right, right - left, left + right):
                if _same_amount(claim.yuan, abs(value)):
                    return True
            for num, den in ((left, right), (right, left)):
                if den == 0:
                    continue
                if _same_amount(claim.yuan, num / den):
                    return True
        if claim.percent is not None:
            for num, den in ((left, right), (right, left)):
                if den == 0:
                    continue
                ratio = (num / den) * Decimal(100)
                if _same_percent(claim.percent, ratio):
                    return True
    return False


def _in_snippets(claim: NumberClaim, snippets: Sequence[str]) -> bool:
    needle = claim.text.replace(" ", "")
    if not needle:
        return False
    for snippet in snippets:
        compact = snippet.replace(" ", "")
        if needle and needle in compact:
            return True
        if claim.percent is not None and f"{_plain(claim.percent)}%" in compact:
            return True
    return False


def _plain(value: Decimal) -> str:
    return format(value, "f").rstrip("0").rstrip(".")


def ground_claim(claim: NumberClaim, pack: EvidencePack) -> GroundedClaim:
    facts = pack.facts_yuan
    if claim.yuan is not None and any(_same_amount(claim.yuan, fact) for fact in facts):
        return GroundedClaim(claim, "fact", "匹配财务事实库金额")
    if claim.yuan is not None and any(_same_amount(claim.yuan, item) for item in pack.citation_yuan):
        return GroundedClaim(claim, "citation", "匹配引用片段金额")
    if claim.percent is not None and claim.unit == "%" and any(_same_percent(claim.percent, pct) for pct in pack.percents):
        return GroundedClaim(claim, "citation", "匹配引用片段百分数")
    if _in_snippets(claim, pack.snippets):
        return GroundedClaim(claim, "citation", "原文出现在引用片段")
    if _unit_error(claim, facts):
        return GroundedClaim(claim, "unit_error", "同一数字、量纲与事实库不一致")
    if _percent_scale(claim, pack):
        return GroundedClaim(claim, "percent_scale", "百分数与小数未对齐")
    if _computed(claim, facts):
        return GroundedClaim(claim, "computed", "可由已给事实加减乘除得到，禁止手算")
    return GroundedClaim(claim, "unbacked", "无法回溯到事实或引用")


def check_reply(reply: str, pack: EvidencePack) -> NumberCheckResult:
    claims = [ground_claim(item, pack) for item in extract_claims(reply)]
    blocked = [item for item in claims if item.status not in OK_STATUSES]
    if not blocked:
        return NumberCheckResult(ok=True, claims=claims, reply=reply)
    redacted = reply
    for item in sorted(blocked, key=lambda row: row.claim.start, reverse=True):
        redacted = redacted[: item.claim.start] + REDACT_TOKEN + redacted[item.claim.end :]
    bits = "、".join(f"{item.claim.text}（{STATUS_ZH.get(item.status, item.status)}）" for item in blocked)
    prefix = (
        f"{INTERCEPT_PREFIX}未回溯到事实库或引用：{bits}。"
        f"已替换为{REDACT_TOKEN}，未放行编造金额。\n\n"
    )
    if redacted.lstrip().startswith(INTERCEPT_PREFIX):
        return NumberCheckResult(ok=False, claims=claims, reply=redacted)
    return NumberCheckResult(ok=False, claims=claims, reply=prefix + redacted)


def apply_checked_reply(
    reply: str,
    pack: EvidencePack,
    *,
    route: str,
) -> tuple[str, str, NumberCheckResult]:
    result = check_reply(reply, pack)
    if result.ok:
        return reply, route, result
    mapped = route
    if route == "rag":
        mapped = "rag_blocked"
    return result.reply, mapped, result
