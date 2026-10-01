-- RegOps Copilot · W2 表结构
-- 适用：已有 init_pgvector.sql 的库，手动或 initdb 二次执行
--   psql -U regops -d regops_db -f docs/sql/w2_tables.sql

-- ---------------------------------------------------------------------------
-- pdf_document · PDF 年报 / 公告原件元数据
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pdf_document (
    id               BIGSERIAL PRIMARY KEY,
    doc_id           VARCHAR(64)  NOT NULL,
    company_code     VARCHAR(16),
    report_year      SMALLINT,
    doc_type         VARCHAR(32)  NOT NULL DEFAULT 'annual_report',
    title            VARCHAR(256),
    source_filename  VARCHAR(255) NOT NULL,
    content_type     VARCHAR(128) NOT NULL DEFAULT 'application/pdf',
    content_hash     VARCHAR(80)  NOT NULL,
    storage_backend  VARCHAR(16)  NOT NULL DEFAULT 'local',
    bucket           VARCHAR(128) NOT NULL,
    object_key       VARCHAR(512) NOT NULL,
    parse_object_key VARCHAR(512),
    file_size_bytes  BIGINT       NOT NULL DEFAULT 0,
    page_count       INT,
    version          INT          NOT NULL DEFAULT 1,
    is_active        BOOLEAN      NOT NULL DEFAULT TRUE,
    ingest_status    VARCHAR(32)  NOT NULL DEFAULT 'uploaded',
    disclosure_date  DATE,
    source_site      VARCHAR(64),
    meta             JSONB        NOT NULL DEFAULT '{}',
    dept_acl         JSONB        NOT NULL DEFAULT '[]',
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT uk_pdf_document_doc_id_version UNIQUE (doc_id, version),
    CONSTRAINT ck_pdf_document_ingest_status CHECK (
        ingest_status IN ('uploaded', 'processing', 'ready', 'failed', 'archived')
    )
);

CREATE INDEX IF NOT EXISTS idx_pdf_document_company_year
    ON pdf_document (company_code, report_year);

CREATE INDEX IF NOT EXISTS idx_pdf_document_active
    ON pdf_document (doc_id)
    WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_pdf_document_content_hash
    ON pdf_document (content_hash);

-- ---------------------------------------------------------------------------
-- web_document · 网页 / HTML / 纯文本快照元数据
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS web_document (
    id               BIGSERIAL PRIMARY KEY,
    doc_id           VARCHAR(64)  NOT NULL,
    doc_type         VARCHAR(32)  NOT NULL DEFAULT 'announcement',
    title            VARCHAR(256),
    source_medium    VARCHAR(16)  NOT NULL DEFAULT 'html',
    source_url       TEXT         NOT NULL,
    canonical_url    TEXT,
    source_site      VARCHAR(64),
    content_type     VARCHAR(128) NOT NULL DEFAULT 'text/html',
    content_hash     VARCHAR(80)  NOT NULL,
    storage_backend  VARCHAR(16)  NOT NULL DEFAULT 'local',
    bucket           VARCHAR(128) NOT NULL,
    object_key       VARCHAR(512) NOT NULL,
    parse_object_key VARCHAR(512),
    file_size_bytes  BIGINT       NOT NULL DEFAULT 0,
    version          INT          NOT NULL DEFAULT 1,
    is_active        BOOLEAN      NOT NULL DEFAULT TRUE,
    ingest_status    VARCHAR(32)  NOT NULL DEFAULT 'uploaded',
    fetched_at       TIMESTAMPTZ,
    fetch_status     VARCHAR(32),
    language         VARCHAR(16),
    charset          VARCHAR(32),
    meta             JSONB        NOT NULL DEFAULT '{}',
    dept_acl         JSONB        NOT NULL DEFAULT '[]',
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT uk_web_document_doc_id_version UNIQUE (doc_id, version),
    CONSTRAINT uk_web_document_content_hash UNIQUE (content_hash),
    CONSTRAINT ck_web_document_source_medium CHECK (
        source_medium IN ('html', 'text')
    ),
    CONSTRAINT ck_web_document_ingest_status CHECK (
        ingest_status IN ('uploaded', 'processing', 'ready', 'failed', 'archived')
    ),
    CONSTRAINT ck_web_document_fetch_status CHECK (
        fetch_status IS NULL OR fetch_status IN ('success', 'failed', 'stale')
    )
);

CREATE INDEX IF NOT EXISTS idx_web_document_source_site
    ON web_document (source_site, fetched_at DESC);

CREATE INDEX IF NOT EXISTS idx_web_document_canonical_url
    ON web_document (canonical_url)
    WHERE canonical_url IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_web_document_active
    ON web_document (doc_id)
    WHERE is_active = TRUE;

-- ---------------------------------------------------------------------------
-- ingest_job · 上传后异步 parse / chunk / embed 任务
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ingest_job (
    id              BIGSERIAL PRIMARY KEY,
    job_id          UUID         NOT NULL DEFAULT gen_random_uuid(),
    target_type     VARCHAR(8)   NOT NULL,
    target_doc_id   VARCHAR(64)  NOT NULL,
    status          VARCHAR(32)  NOT NULL DEFAULT 'PENDING',
    error_message   TEXT,
    retry_count     INT          NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    CONSTRAINT uk_ingest_job_job_id UNIQUE (job_id),
    CONSTRAINT ck_ingest_job_target_type CHECK (target_type IN ('pdf', 'web')),
    CONSTRAINT ck_ingest_job_status CHECK (
        status IN (
            'PENDING', 'PARSING', 'CLEANING', 'EXTRACTING',
            'CHUNKING', 'EMBEDDING', 'DONE', 'FAILED'
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_ingest_job_target
    ON ingest_job (target_type, target_doc_id);

CREATE INDEX IF NOT EXISTS idx_ingest_job_status
    ON ingest_job (status, created_at DESC);

-- ---------------------------------------------------------------------------
-- fin_metric · 三表结构化 fact（G1/G2/G3 后入库）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fin_metric (
    id             BIGSERIAL PRIMARY KEY,
    company_code   VARCHAR(16),
    doc_id         VARCHAR(64)  NOT NULL,
    source_type    VARCHAR(8)   NOT NULL DEFAULT 'pdf',
    fact_key       VARCHAR(64)  NOT NULL,
    concept        VARCHAR(64)  NOT NULL,
    period         DATE         NOT NULL,
    scope          VARCHAR(32)  NOT NULL,
    currency       VARCHAR(8)   NOT NULL DEFAULT 'CNY',
    statement      VARCHAR(32)  NOT NULL,
    value_yuan     NUMERIC(24, 4),
    unit_raw       VARCHAR(16),
    raw_name       VARCHAR(256),
    raw_value      VARCHAR(128),
    page_no        INT,
    bbox_json      JSONB,
    parser         VARCHAR(32),
    status         VARCHAR(32)  NOT NULL DEFAULT 'human_review',
    review_reason  TEXT,
    xbrl_tag       VARCHAR(128),
    content_hash   VARCHAR(80),
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT uk_fin_metric_doc_fact_key UNIQUE (doc_id, fact_key),
    CONSTRAINT ck_fin_metric_source_type CHECK (source_type IN ('pdf', 'web')),
    CONSTRAINT ck_fin_metric_status CHECK (
        status IN ('auto_accepted', 'human_review', 'rejected')
    )
);

CREATE INDEX IF NOT EXISTS idx_fin_metric_company_concept
    ON fin_metric (company_code, concept, period);

CREATE INDEX IF NOT EXISTS idx_fin_metric_doc_id
    ON fin_metric (doc_id);

CREATE INDEX IF NOT EXISTS idx_fin_metric_status
    ON fin_metric (status);

-- ---------------------------------------------------------------------------
-- doc_chunks · W2 扩展：区分 PDF / Web 来源
-- ---------------------------------------------------------------------------
ALTER TABLE doc_chunks
    ADD COLUMN IF NOT EXISTS source_type VARCHAR(8) NOT NULL DEFAULT 'pdf';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_doc_chunks_source_type'
    ) THEN
        ALTER TABLE doc_chunks
            ADD CONSTRAINT ck_doc_chunks_source_type
            CHECK (source_type IN ('pdf', 'web'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_doc_chunks_source_doc
    ON doc_chunks (source_type, doc_id);
