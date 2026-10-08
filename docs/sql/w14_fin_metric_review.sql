-- 人工复核完成记录：保留复核前金额、状态、原因和来源快照，允许按可回溯证据确认或拒绝。
ALTER TABLE fin_metric DROP CONSTRAINT IF EXISTS ck_fin_metric_status;
ALTER TABLE fin_metric ADD CONSTRAINT ck_fin_metric_status CHECK (
    status IN ('auto_accepted', 'human_review', 'manually_accepted', 'rejected')
);

CREATE TABLE IF NOT EXISTS fin_metric_review (
    id                    BIGSERIAL PRIMARY KEY,
    metric_id             BIGINT NOT NULL REFERENCES fin_metric(id),
    source_updated_at     TIMESTAMPTZ NOT NULL,
    original_value_yuan   NUMERIC(24, 4),
    original_status       VARCHAR(32) NOT NULL,
    original_reason       TEXT,
    reviewed_value_yuan   NUMERIC(24, 4),
    decision              VARCHAR(16) NOT NULL CHECK (decision IN ('approve', 'reject')),
    note                  TEXT NOT NULL,
    source_content_hash   VARCHAR(80),
    reviewer_id           UUID NOT NULL,
    reviewer_name         VARCHAR(128) NOT NULL,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_fin_metric_review_note CHECK (length(btrim(note)) BETWEEN 10 AND 1000),
    CONSTRAINT ck_fin_metric_review_value CHECK (
        (decision = 'approve' AND reviewed_value_yuan IS NOT NULL)
        OR decision = 'reject'
    )
);

CREATE INDEX IF NOT EXISTS idx_fin_metric_review_metric
    ON fin_metric_review (metric_id, created_at DESC, id DESC);
