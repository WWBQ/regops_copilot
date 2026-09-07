"""review_draft：只存 PENDING 审查工单草稿。"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg.errors import UniqueViolation, UndefinedTable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReviewDraftRow:
    id: int
    public_id: str
    status: str
    dept: str
    company_code: str
    company_codes: list[str]
    title: str
    reason: str
    conclusion: str
    risk_level: str | None
    clause_refs: list[str]
    evidence_quotes: list[str]
    impact_scope: str
    thread_id: str | None
    session_id: str | None
    request_id: str | None
    idempotency_key: str | None
    created_at: datetime | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "draft_id": self.public_id,
            "status": self.status,
            "dept": self.dept,
            "company_code": self.company_code,
            "company_codes": self.company_codes,
            "title": self.title,
            "reason": self.reason,
            "conclusion": self.conclusion,
            "risk_level": self.risk_level,
            "clause_refs": self.clause_refs,
            "evidence_quotes": self.evidence_quotes,
            "impact_scope": self.impact_scope,
            "thread_id": self.thread_id,
            "session_id": self.session_id,
            "request_id": self.request_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


def _as_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    return json.loads(value or "[]")


def _row(raw: tuple) -> ReviewDraftRow:
    session_id = raw[14]
    return ReviewDraftRow(
        id=int(raw[0]),
        public_id=str(raw[1]),
        status=str(raw[2]),
        dept=str(raw[3]),
        company_code=str(raw[4]),
        company_codes=[str(item) for item in _as_list(raw[5])],
        title=str(raw[6]),
        reason=str(raw[7]),
        conclusion=str(raw[8] or ""),
        risk_level=str(raw[9]) if raw[9] else None,
        clause_refs=[str(item) for item in _as_list(raw[10])],
        evidence_quotes=[str(item) for item in _as_list(raw[11])],
        impact_scope=str(raw[12] or ""),
        thread_id=str(raw[13]) if raw[13] else None,
        session_id=str(session_id) if session_id else None,
        request_id=str(raw[15]) if raw[15] else None,
        idempotency_key=str(raw[16]) if raw[16] else None,
        created_at=raw[17],
    )


_SELECT_COLS = """
    id, public_id, status, dept, company_code, company_codes, title, reason,
    conclusion, risk_level, clause_refs, evidence_quotes, impact_scope,
    thread_id, session_id, request_id, idempotency_key, created_at
"""


def get_by_thread_id(conn: psycopg.Connection, thread_id: str) -> ReviewDraftRow | None:
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {_SELECT_COLS} FROM review_draft WHERE thread_id = %s", (thread_id,))
            raw = cur.fetchone()
    except UndefinedTable as exc:
        raise RuntimeError("缺少 review_draft 表，请执行 docs/sql/w6_review_draft.sql") from exc
    return _row(raw) if raw else None


def get_by_idempotency_key(conn: psycopg.Connection, key: str) -> ReviewDraftRow | None:
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {_SELECT_COLS} FROM review_draft WHERE idempotency_key = %s", (key,))
            raw = cur.fetchone()
    except UndefinedTable as exc:
        raise RuntimeError("缺少 review_draft 表，请执行 docs/sql/w6_review_draft.sql") from exc
    return _row(raw) if raw else None


def get_by_public_id(conn: psycopg.Connection, public_id: str) -> ReviewDraftRow | None:
    try:
        UUID(str(public_id))
    except (ValueError, TypeError):
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {_SELECT_COLS} FROM review_draft WHERE public_id = %s::uuid", (public_id,))
            raw = cur.fetchone()
    except UndefinedTable as exc:
        raise RuntimeError("缺少 review_draft 表，请执行 docs/sql/w6_review_draft.sql") from exc
    return _row(raw) if raw else None


def list_review_drafts(
    conn: psycopg.Connection,
    *,
    dept: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[ReviewDraftRow], int]:
    where = ""
    params: list[Any] = []
    if dept:
        where = "WHERE dept = %s"
        params.append(dept)
    with conn.cursor() as cur:
        try:
            cur.execute(f"SELECT COUNT(*) FROM review_draft {where}", params)
            total = int(cur.fetchone()[0])
            cur.execute(
                f"SELECT {_SELECT_COLS} FROM review_draft {where} ORDER BY created_at DESC LIMIT %s OFFSET %s",
                [*params, limit, offset],
            )
            rows = [_row(item) for item in cur.fetchall()]
        except UndefinedTable as exc:
            raise RuntimeError("缺少 review_draft 表，请执行 docs/sql/w6_review_draft.sql") from exc
    return rows, total


def insert_review_draft(
    conn: psycopg.Connection,
    *,
    dept: str,
    company_code: str,
    company_codes: list[str],
    title: str,
    reason: str,
    conclusion: str,
    risk_level: str | None,
    clause_refs: list[str],
    evidence_quotes: list[str],
    impact_scope: str,
    thread_id: str | None,
    session_id: str | None,
    request_id: str | None,
    idempotency_key: str | None,
) -> tuple[ReviewDraftRow, bool]:
    if thread_id:
        existing = get_by_thread_id(conn, thread_id)
        if existing:
            return existing, True
    if idempotency_key:
        existing = get_by_idempotency_key(conn, idempotency_key)
        if existing:
            return existing, True
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO review_draft (
                    dept, company_code, company_codes, title, reason, conclusion, risk_level,
                    clause_refs, evidence_quotes, impact_scope, thread_id, session_id,
                    request_id, idempotency_key
                )
                VALUES (
                    %s, %s, %s::jsonb, %s, %s, %s, %s,
                    %s::jsonb, %s::jsonb, %s, %s, %s::uuid, %s, %s
                )
                RETURNING {_SELECT_COLS}
                """,
                (
                    dept,
                    company_code,
                    json.dumps(company_codes, ensure_ascii=False),
                    title,
                    reason,
                    conclusion,
                    risk_level,
                    json.dumps(clause_refs, ensure_ascii=False),
                    json.dumps(evidence_quotes, ensure_ascii=False),
                    impact_scope,
                    thread_id,
                    session_id,
                    request_id,
                    idempotency_key,
                ),
            )
            raw = cur.fetchone()
        logger.info("review_draft inserted thread=%s company=%s", thread_id, company_code)
        return _row(raw), False
    except UniqueViolation:
        conn.rollback()
        if thread_id:
            existing = get_by_thread_id(conn, thread_id)
            if existing:
                return existing, True
        if idempotency_key:
            existing = get_by_idempotency_key(conn, idempotency_key)
            if existing:
                return existing, True
        raise
    except UndefinedTable as exc:
        raise RuntimeError(
            "缺少 review_draft 表，请执行 docs/sql/w6_review_draft.sql"
        ) from exc
