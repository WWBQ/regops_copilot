-- RegOps Copilot · W7 身份 / 审计
--   docker compose exec db psql -U regops -d regops_db -f /docker-entrypoint-initdb.d/08_w7_identity.sql
--   或：psql postgresql://regops:regops123@localhost:5432/regops_db -f docs/sql/w7_identity.sql
-- 用户种子由 Java DataSeeder 写入（BCrypt），不在 SQL 里放明文密码哈希。

CREATE EXTENSION IF NOT EXISTS pgcrypto;

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
