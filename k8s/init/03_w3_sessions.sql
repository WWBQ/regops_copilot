-- RegOps Copilot · W3 会话级 PDF 上传（Chat 附件，非公司永久库）
--   psql -U regops -d regops_db -f docs/sql/w3_chat_sessions.sql

CREATE TABLE IF NOT EXISTS chat_session (
    session_id   UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    title        VARCHAR(256),
    expires_at   TIMESTAMPTZ,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS session_document (
    id               BIGSERIAL PRIMARY KEY,
    session_id       UUID         NOT NULL REFERENCES chat_session(session_id) ON DELETE CASCADE,
    doc_id           VARCHAR(64)  NOT NULL,
    source_filename  VARCHAR(255) NOT NULL,
    job_id           UUID,
    status           VARCHAR(32)  NOT NULL DEFAULT 'PENDING',
    page_count       INT,
    chunk_count      INT,
    error_message    TEXT,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT uk_session_document UNIQUE (session_id, doc_id),
    CONSTRAINT ck_session_document_status CHECK (
        status IN ('PENDING', 'PROCESSING', 'READY', 'FAILED')
    )
);

CREATE INDEX IF NOT EXISTS idx_session_document_session
    ON session_document (session_id, status);
