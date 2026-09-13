"""问数多轮补槽：只记当前未完成请求，不把旧数字当记忆。"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any
from uuid import UUID

from app.asknum.slots import (
    CONCEPT_LABELS,
    AsknumSlots,
    company_display_name,
    format_year_span,
    infer_asknum_intent,
    merge_slots,
    missing_slot_names,
)
from app.db.connection import get_connection
from app.db.session_repository import (
    clear_session_pending_asknum,
    load_session_pending_asknum,
    save_session_pending_asknum,
)

logger = logging.getLogger(__name__)

PENDING_TTL_MINUTES = 30

_TOPIC_CHANGE_RE = re.compile(
    r"换个话题|换一家|换个公司|换个问题|重新查|重新问|"
    r"不问这个|取消查询|别查了"
)
_CANCEL_PENDING_RE = re.compile(
    r"^(?:取消|取消查询|算了|别查了|不问了)\s*[。.!！]?$"
)

_MISSING_LABELS = {
    "company": "公司",
    "metric": "指标",
}

_memory: dict[str, dict[str, Any]] = {}
_lock = Lock()


@dataclass(frozen=True)
class PendingAsknum:
    intent: str
    slots: AsknumSlots
    expires_at: float

    def expired(self, now: float | None = None) -> bool:
        return (now or time.time()) >= self.expires_at

    def missing(self) -> list[str]:
        return missing_slot_names(self.slots)

    def to_record(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "company_codes": list(self.slots.company_codes),
            "concepts": list(self.slots.concepts),
            "years": list(self.slots.years),
            "year_defaulted": self.slots.year_defaulted,
            "scope": self.slots.scope,
            "scope_explicit": self.slots.scope_explicit,
            "expires_at": self.expires_at,
        }

    def to_ui(self) -> dict[str, Any]:
        company = self.slots.company_codes[0] if self.slots.company_codes else None
        metric = self.slots.concepts[0] if self.slots.concepts else None
        return {
            "intent": self.intent,
            "company": company,
            "years": [int(year) for year in self.slots.years],
            "metric": metric,
            "scope": self.slots.scope,
            "missing": self.missing(),
            "hint": pending_hint(self.slots),
        }


def reset_pending_store() -> None:
    with _lock:
        _memory.clear()


def is_topic_change(question: str) -> bool:
    text = (question or "").strip()
    if _CANCEL_PENDING_RE.match(text):
        return True
    return bool(_TOPIC_CHANGE_RE.search(text))


def pending_hint(slots: AsknumSlots) -> str:
    parts: list[str] = []
    if slots.company_codes:
        parts.append("、".join(company_display_name(code) for code in slots.company_codes))
    if not slots.year_defaulted:
        parts.append(format_year_span(slots.years))
    if slots.concepts:
        parts.append("、".join(CONCEPT_LABELS.get(item, item) for item in slots.concepts))
    missing = [label for key, label in _MISSING_LABELS.items() if key in missing_slot_names(slots)]
    if missing:
        parts.append(f"缺少{'、'.join(missing)}")
    return "正在补充查询：" + "｜".join(parts)


def is_complete_new_request(incoming: AsknumSlots, pending: PendingAsknum) -> bool:
    if not incoming.company_codes or not incoming.concepts:
        return False
    if pending.slots.company_codes and incoming.company_codes != pending.slots.company_codes:
        return True
    if not pending.slots.concepts:
        return False
    return True


def should_merge(question: str, incoming: AsknumSlots, pending: PendingAsknum | None) -> bool:
    if pending is None or pending.expired():
        return False
    if is_topic_change(question) or incoming.narrative:
        return False
    if is_complete_new_request(incoming, pending):
        return False
    return bool(
        incoming.company_codes
        or incoming.concepts
        or not incoming.year_defaulted
        or incoming.scope_explicit
    )


def should_continue_pending(question: str, session_id: str | None) -> bool:
    pending = load_pending(session_id)
    if pending is None:
        return False
    from app.asknum.slots import parse_slots

    return should_merge(question, parse_slots(question), pending)


def _session_key(session_id: str | None) -> str | None:
    if not session_id:
        return None
    try:
        return str(UUID(session_id))
    except ValueError:
        return session_id


def _from_record(payload: dict[str, Any] | None) -> PendingAsknum | None:
    if not payload:
        return None
    try:
        expires_at = float(payload.get("expires_at") or 0)
        years = tuple(int(year) for year in (payload.get("years") or ()))
        if not years:
            return None
        slots = AsknumSlots(
            company_codes=tuple(str(code) for code in (payload.get("company_codes") or ())),
            concepts=tuple(str(item) for item in (payload.get("concepts") or ())),
            year=years[0],
            year_defaulted=bool(payload.get("year_defaulted")),
            scope=str(payload.get("scope") or "consolidated"),
            narrative=False,
            years=years,
            scope_explicit=bool(payload.get("scope_explicit")),
        )
        pending = PendingAsknum(
            intent=str(payload.get("intent") or "asknum"),
            slots=slots,
            expires_at=expires_at,
        )
    except (TypeError, ValueError):
        return None
    if pending.expired():
        return None
    return pending


def load_pending(session_id: str | None) -> PendingAsknum | None:
    key = _session_key(session_id)
    if not key:
        return None
    with _lock:
        cached = _from_record(_memory.get(key))
        if cached is not None:
            return cached
        _memory.pop(key, None)
    persisted = None
    try:
        with get_connection() as conn:
            persisted = load_session_pending_asknum(conn, key)
    except Exception:
        logger.debug("load pending_asknum skipped", exc_info=True)
    pending = _from_record(persisted)
    if pending is None:
        return None
    with _lock:
        _memory[key] = pending.to_record()
    return pending


def save_pending(session_id: str | None, slots: AsknumSlots, *, intent: str) -> PendingAsknum | None:
    key = _session_key(session_id)
    if not key:
        return PendingAsknum(
            intent=intent,
            slots=slots,
            expires_at=time.time() + PENDING_TTL_MINUTES * 60,
        )
    pending = PendingAsknum(
        intent=intent,
        slots=slots,
        expires_at=time.time() + PENDING_TTL_MINUTES * 60,
    )
    record = pending.to_record()
    with _lock:
        _memory[key] = record
    expires = datetime.now(timezone.utc) + timedelta(minutes=PENDING_TTL_MINUTES)
    try:
        with get_connection() as conn:
            save_session_pending_asknum(conn, key, record, expires)
            conn.commit()
    except Exception:
        logger.debug("save pending_asknum skipped", exc_info=True)
    return pending


def clear_pending(session_id: str | None) -> None:
    key = _session_key(session_id)
    if not key:
        return
    with _lock:
        _memory.pop(key, None)
    try:
        with get_connection() as conn:
            clear_session_pending_asknum(conn, key)
            conn.commit()
    except Exception:
        logger.debug("clear pending_asknum skipped", exc_info=True)


def resolve_slots(
    question: str,
    *,
    session_id: str | None,
    incoming: AsknumSlots,
) -> tuple[AsknumSlots, str, PendingAsknum | None]:
    """合并或替换当前轮槽位。换话题时清掉 pending。"""
    pending = load_pending(session_id)
    if pending is not None and pending.expired():
        clear_pending(session_id)
        pending = None

    if is_topic_change(question):
        if pending is not None:
            clear_pending(session_id)
        return incoming, infer_asknum_intent(question, incoming), None

    if incoming.narrative:
        if pending is not None:
            clear_pending(session_id)
        return incoming, infer_asknum_intent(question, incoming), None

    if should_merge(question, incoming, pending) and pending is not None:
        merged = merge_slots(pending.slots, incoming)
        intent = pending.intent
        if infer_asknum_intent(question, merged) == "asknum_compare":
            intent = "asknum_compare"
        return merged, intent, pending

    if pending is not None and is_complete_new_request(incoming, pending):
        clear_pending(session_id)
    return incoming, infer_asknum_intent(question, incoming), pending if pending and not is_complete_new_request(incoming, pending) else None
