-- Ordinary profile search projection must not be best-effort. Persist only
-- durable replay coordinates; the relay reads the authoritative profile again
-- and advances published_at only after the idempotent ES/OpenSearch write.
CREATE TABLE IF NOT EXISTS user_profile_search_outbox (
    event_id             VARCHAR(64) PRIMARY KEY,
    user_id              VARCHAR(96) NOT NULL,
    profile_version      BIGINT NOT NULL,
    event_type           VARCHAR(96) NOT NULL,
    occurred_at          TIMESTAMPTZ NOT NULL,
    published_at         TIMESTAMPTZ,
    retry_count          INTEGER NOT NULL DEFAULT 0,
    next_attempt_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_failure_code    VARCHAR(64) NOT NULL DEFAULT '',
    last_failure_digest  CHAR(64) NOT NULL DEFAULT '',
    last_failed_at       TIMESTAMPTZ,
    lease_owner          VARCHAR(96),
    lease_until          TIMESTAMPTZ,
    CONSTRAINT uq_user_profile_search_outbox_version
        UNIQUE (user_id, profile_version, event_type)
);

CREATE INDEX IF NOT EXISTS idx_user_profile_search_outbox_claim_ready
    ON user_profile_search_outbox (
        next_attempt_at,
        lease_until,
        occurred_at,
        event_id
    )
    WHERE published_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_user_profile_search_outbox_unpublished_order
    ON user_profile_search_outbox (
        user_id,
        occurred_at,
        event_id
    )
    WHERE published_at IS NULL;
