-- 合规问答的持久会话与消息。仅 Java BFF 按 JWT 用户读写。
CREATE TABLE IF NOT EXISTS chat_history (
    user_id      UUID        NOT NULL REFERENCES app_user(public_id) ON DELETE CASCADE,
    session_id   UUID        NOT NULL,
    title        VARCHAR(256) NOT NULL,
    custom_title BOOLEAN     NOT NULL DEFAULT FALSE,
    messages_json TEXT       NOT NULL DEFAULT '[]',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, session_id)
);

CREATE INDEX IF NOT EXISTS idx_chat_history_user_updated
    ON chat_history (user_id, updated_at DESC);
