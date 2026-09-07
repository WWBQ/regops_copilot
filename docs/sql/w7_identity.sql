-- RegOps Copilot · W7 身份 / 客户档案 / 工单状态机 / 审计
--   docker compose exec db psql -U regops -d regops_db -f /docker-entrypoint-initdb.d/08_w7_identity.sql
--   或：psql postgresql://regops:regops123@localhost:5432/regops_db -f docs/sql/w7_identity.sql
-- 用户种子由 Java DataSeeder 写入（BCrypt），不在 SQL 里放明文密码哈希。

CREATE EXTENSION IF NOT EXISTS pgcrypto;

ALTER TABLE review_draft DROP CONSTRAINT IF EXISTS ck_review_draft_status;
ALTER TABLE review_draft ADD CONSTRAINT ck_review_draft_status
    CHECK (status IN ('PENDING', 'SUBMITTED', 'REVIEWED', 'REJECTED'));

ALTER TABLE review_draft ADD COLUMN IF NOT EXISTS submitted_by VARCHAR(64);
ALTER TABLE review_draft ADD COLUMN IF NOT EXISTS reviewed_by VARCHAR(64);
ALTER TABLE review_draft ADD COLUMN IF NOT EXISTS review_reason TEXT;
ALTER TABLE review_draft ADD COLUMN IF NOT EXISTS input_summary TEXT;
ALTER TABLE review_draft ADD COLUMN IF NOT EXISTS version BIGINT NOT NULL DEFAULT 0;
ALTER TABLE review_draft ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_review_draft_status_dept
    ON review_draft (status, dept, updated_at DESC);

CREATE TABLE IF NOT EXISTS app_user (
    id            BIGSERIAL PRIMARY KEY,
    public_id     UUID         NOT NULL DEFAULT gen_random_uuid(),
    username      VARCHAR(64)  NOT NULL,
    password_hash VARCHAR(120) NOT NULL,
    display_name  VARCHAR(80)  NOT NULL,
    email         VARCHAR(120) NOT NULL DEFAULT '',
    role          VARCHAR(32)  NOT NULL,
    dept          VARCHAR(32)  NOT NULL,
    enabled       BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_app_user_username UNIQUE (username),
    CONSTRAINT uq_app_user_public_id UNIQUE (public_id),
    CONSTRAINT ck_app_user_role CHECK (role IN ('ANALYST', 'CHECKER', 'RM', 'ADMIN')),
    CONSTRAINT ck_app_user_dept CHECK (dept IN ('research', 'compliance', 'rm'))
);

CREATE TABLE IF NOT EXISTS customer_profile (
    id              BIGSERIAL PRIMARY KEY,
    public_id       UUID         NOT NULL DEFAULT gen_random_uuid(),
    company_code    VARCHAR(6)   NOT NULL,
    display_name    VARCHAR(80)  NOT NULL,
    classification  VARCHAR(32)  NOT NULL,
    masked_id_no    VARCHAR(32)  NOT NULL DEFAULT '',
    masked_phone    VARCHAR(32)  NOT NULL DEFAULT '',
    risk_level      VARCHAR(8)   NOT NULL DEFAULT '中',
    notes           TEXT         NOT NULL DEFAULT '',
    dept            VARCHAR(32)  NOT NULL,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_customer_profile_public_id UNIQUE (public_id),
    CONSTRAINT uq_customer_profile_company UNIQUE (company_code),
    CONSTRAINT ck_customer_company CHECK (company_code ~ '^\d{6}$'),
    CONSTRAINT ck_customer_class CHECK (classification IN ('INTERNAL_RESEARCH', 'CLIENT'))
);

CREATE TABLE IF NOT EXISTS audit_event (
    id             BIGSERIAL PRIMARY KEY,
    occurred_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    actor_username VARCHAR(64)  NOT NULL,
    actor_role     VARCHAR(32)  NOT NULL,
    dept           VARCHAR(32)  NOT NULL,
    action         VARCHAR(64)  NOT NULL,
    entity_type    VARCHAR(32)  NOT NULL,
    entity_id      VARCHAR(80)  NOT NULL,
    request_id     VARCHAR(64),
    reason         TEXT         NOT NULL DEFAULT '',
    input_summary  TEXT         NOT NULL DEFAULT '',
    before_json    TEXT         NOT NULL DEFAULT '',
    after_json     TEXT         NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_audit_event_entity
    ON audit_event (entity_type, entity_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_event_actor
    ON audit_event (actor_username, occurred_at DESC);

INSERT INTO customer_profile (company_code, display_name, classification, masked_id_no, masked_phone, risk_level, notes, dept)
VALUES
    ('002594', '比亚迪（投研内核）', 'INTERNAL_RESEARCH', '310***********1024', '138****0001', '中', '投研内部客户档案，含未对外纪要。客户经理不可见。', 'research'),
    ('601633', '长城汽车（投研内核）', 'INTERNAL_RESEARCH', '130***********8831', '139****0002', '中', '投研内部客户档案。客户经理不可见。', 'research'),
    ('000333', '美的集团（客户）', 'CLIENT', '440***********5566', '136****0003', '低', '对客档案，已脱敏。', 'rm'),
    ('000651', '格力电器（客户）', 'CLIENT', '440***********7788', '137****0004', '低', '对客档案，已脱敏。', 'rm')
ON CONFLICT (company_code) DO NOTHING;
