-- RegOps Copilot · W6-4 审查工单草稿（只 PENDING，不提交 maker-checker）
--   docker compose exec db psql -U regops -d regops_db -f /docker-entrypoint-initdb.d/07_review_draft.sql
--   或：psql postgresql://regops:regops123@localhost:5432/regops_db -f docs/sql/w6_review_draft.sql

CREATE TABLE IF NOT EXISTS review_draft (
    id              BIGSERIAL PRIMARY KEY,
    public_id       UUID         NOT NULL DEFAULT gen_random_uuid(),
    status          VARCHAR(16)  NOT NULL DEFAULT 'PENDING',
    dept            VARCHAR(32)  NOT NULL DEFAULT 'public',
    company_code    VARCHAR(6)   NOT NULL,
    company_codes   JSONB        NOT NULL DEFAULT '[]'::jsonb,
    title           VARCHAR(120) NOT NULL,
    reason          TEXT         NOT NULL,
    conclusion      TEXT         NOT NULL DEFAULT '',
    risk_level      VARCHAR(8),
    clause_refs     JSONB        NOT NULL DEFAULT '[]'::jsonb,
    evidence_quotes JSONB        NOT NULL DEFAULT '[]'::jsonb,
    impact_scope    TEXT         NOT NULL DEFAULT '',
    thread_id       VARCHAR(80),
    session_id      UUID,
    request_id      VARCHAR(64),
    idempotency_key VARCHAR(128),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_review_draft_public_id UNIQUE (public_id),
    CONSTRAINT ck_review_draft_status CHECK (status = 'PENDING'),
    CONSTRAINT ck_review_draft_company CHECK (company_code ~ '^\d{6}$')
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_review_draft_thread
    ON review_draft (thread_id)
    WHERE thread_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_review_draft_idempotency
    ON review_draft (idempotency_key)
    WHERE idempotency_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_review_draft_dept_created
    ON review_draft (dept, created_at DESC);
