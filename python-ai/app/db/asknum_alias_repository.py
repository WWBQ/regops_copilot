"""asknum_alias 读写。"""

from __future__ import annotations

from typing import Any

import psycopg


def list_asknum_aliases(
    conn: psycopg.Connection,
    *,
    kind: str | None = None,
    enabled_only: bool = True,
) -> list[tuple[str, str, str]]:
    """返回 (kind, alias, target)。"""
    clauses = ["1=1"]
    params: list[Any] = []
    if kind:
        clauses.append("kind = %s")
        params.append(kind)
    if enabled_only:
        clauses.append("enabled = TRUE")
    with conn.cursor() as cur:
        cur.execute(
            "SELECT kind, alias, target FROM asknum_alias "
            f"WHERE {' AND '.join(clauses)} ORDER BY length(alias) DESC, alias",
            params,
        )
        return [(str(row[0]), str(row[1]), str(row[2])) for row in cur.fetchall()]


def count_asknum_aliases(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM asknum_alias")
        return int(cur.fetchone()[0])


def upsert_asknum_aliases(
    conn: psycopg.Connection,
    rows: list[tuple[str, str, str]],
) -> int:
    if not rows:
        return 0
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO asknum_alias (kind, alias, target)
            VALUES (%s, %s, %s)
            ON CONFLICT (kind, alias) DO UPDATE SET
                target = EXCLUDED.target,
                enabled = TRUE
            """,
            rows,
        )
    return len(rows)
