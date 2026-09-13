-- 问数多轮补槽：当前未完成请求挂在 chat_session，短 TTL，不算长期记忆。
--   psql -U regops -d regops_db -f docs/sql/w4_asknum_pending.sql

ALTER TABLE chat_session
    ADD COLUMN IF NOT EXISTS pending_asknum JSONB,
    ADD COLUMN IF NOT EXISTS pending_asknum_expires_at TIMESTAMPTZ;
