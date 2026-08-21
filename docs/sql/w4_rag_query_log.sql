-- RegOps Copilot · RAG 检索 trace 日志（运维监控 / 排障）
--   psql -U regops -d regops_db -f docs/sql/w4_rag_query_log.sql

CREATE TABLE IF NOT EXISTS rag_query_log (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          VARCHAR(64),
    session_id          UUID,
    question            TEXT         NOT NULL,
    outcome             VARCHAR(32)  NOT NULL,
    rag_used            BOOLEAN      NOT NULL DEFAULT FALSE,
    keyword_terms       JSONB        NOT NULL DEFAULT '[]'::jsonb,
    scoped_doc_ids      JSONB        NOT NULL DEFAULT '[]'::jsonb,
    vector_hit_count    INT          NOT NULL DEFAULT 0,
    keyword_hit_count   INT          NOT NULL DEFAULT 0,
    final_hit_count     INT          NOT NULL DEFAULT 0,
    max_vector_score    DOUBLE PRECISION,
    min_score_threshold DOUBLE PRECISION,
    total_rag_ms        DOUBLE PRECISION,
    hits                JSONB        NOT NULL DEFAULT '[]'::jsonb,
    pipeline            JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_rag_query_log_outcome CHECK (
        outcome IN ('ok', 'no_intent', 'no_docs', 'low_score', 'pending_docs')
    )
);

CREATE INDEX IF NOT EXISTS idx_rag_query_log_created
    ON rag_query_log (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_rag_query_log_session
    ON rag_query_log (session_id, created_at DESC)
    WHERE session_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_rag_query_log_outcome
    ON rag_query_log (outcome, created_at DESC);
