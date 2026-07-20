-- UserAccount 注销终态必须与 durable outbox 原子提交。下游按 event_id 去重，
-- 因而发布器崩溃后可安全重放。
CREATE TABLE IF NOT EXISTS user_account_outbox (
    event_id            VARCHAR(64) PRIMARY KEY,
    aggregate_id        VARCHAR(64) NOT NULL,
    aggregate_version   BIGINT NOT NULL,
    event_type          VARCHAR(96) NOT NULL,
    payload_json        JSONB NOT NULL,
    occurred_at         TIMESTAMPTZ NOT NULL,
    published_at        TIMESTAMPTZ,
    retry_count         INTEGER NOT NULL DEFAULT 0,
    next_attempt_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_error          TEXT NOT NULL DEFAULT '',
    lease_owner         VARCHAR(96),
    lease_until         TIMESTAMPTZ,
    CONSTRAINT uq_user_account_outbox_version
        UNIQUE (aggregate_id, aggregate_version, event_type)
);

CREATE INDEX IF NOT EXISTS idx_user_account_outbox_ready
    ON user_account_outbox (
        published_at,
        next_attempt_at,
        lease_until,
        occurred_at
    );
