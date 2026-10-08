-- RAG / 问数监控按登录用户隔离。不能可靠判定归属的旧 trace 保持 NULL，不对任何用户显示。
ALTER TABLE rag_query_log ADD COLUMN IF NOT EXISTS user_id UUID;
ALTER TABLE asknum_query_log ADD COLUMN IF NOT EXISTS user_id UUID;

-- 仅当一个会话在持久会话表中恰好归属于一位用户时回填。
WITH owners AS (
    SELECT session_id, MIN(user_id::text)::uuid AS user_id
    FROM chat_history GROUP BY session_id HAVING COUNT(DISTINCT user_id) = 1
)
UPDATE rag_query_log AS logs SET user_id = owners.user_id
FROM owners WHERE logs.session_id = owners.session_id AND logs.user_id IS NULL;

WITH owners AS (
    SELECT session_id, MIN(user_id::text)::uuid AS user_id
    FROM chat_history GROUP BY session_id HAVING COUNT(DISTINCT user_id) = 1
)
UPDATE asknum_query_log AS logs SET user_id = owners.user_id
FROM owners WHERE logs.session_id = owners.session_id AND logs.user_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_rag_query_log_user_created
    ON rag_query_log (user_id, created_at DESC) WHERE user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_asknum_query_log_user_created
    ON asknum_query_log (user_id, created_at DESC) WHERE user_id IS NOT NULL;
