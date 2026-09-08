-- RegOps Copilot · 问数 trace 日志（受控 lookup 排障 / 评测对照）
--   docker compose exec db psql -U regops -d regops_db -f /docker-entrypoint-initdb.d/05_asknum_log.sql
--   或：psql -U regops -d regops_db -f docs/sql/w4_asknum_query_log.sql

CREATE TABLE IF NOT EXISTS asknum_query_log (
    id              BIGSERIAL PRIMARY KEY,
    request_id      VARCHAR(64),
    session_id      UUID,
    question        TEXT         NOT NULL,
    route           VARCHAR(32)  NOT NULL,
    company_codes   JSONB        NOT NULL DEFAULT '[]'::jsonb,
    concepts        JSONB        NOT NULL DEFAULT '[]'::jsonb,
    year            INT,
    year_defaulted  BOOLEAN      NOT NULL DEFAULT FALSE,
    scope           VARCHAR(32),
    narrative       BOOLEAN      NOT NULL DEFAULT FALSE,
    lookups         JSONB        NOT NULL DEFAULT '[]'::jsonb,
    total_ms        DOUBLE PRECISION,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_asknum_query_log_route CHECK (
        route IN ('metric', 'metric_clarify', 'metric_blocked', 'skip')
    )
);

CREATE INDEX IF NOT EXISTS idx_asknum_query_log_created
    ON asknum_query_log (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_asknum_query_log_session
    ON asknum_query_log (session_id, created_at DESC)
    WHERE session_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_asknum_query_log_route
    ON asknum_query_log (route, created_at DESC);
