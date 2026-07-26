-- UserAccount lifecycle relay failures must never retain raw dependency
-- messages. This migration is additive for already-managed databases and keeps
-- 031 immutable so its recorded checksum remains valid.
ALTER TABLE user_account_outbox
    ADD COLUMN IF NOT EXISTS last_failure_code VARCHAR(64) NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS last_failure_digest CHAR(64) NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS last_failed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS terminal_failure_at TIMESTAMPTZ;

-- 031 predates the privacy contract and may have stored raw provider errors.
-- Remove the column only in this forward migration; do not rewrite a managed
-- historical migration that existing deployments have already checksummed.
ALTER TABLE user_account_outbox
    DROP COLUMN IF EXISTS last_error;

-- The DLQ is deliberately payload-free: event_id is an opaque replay
-- coordinate, while account_id/aggregate_id and payload_json never leave the
-- authoritative outbox. expires_at is enforced by the relay's hourly prune.
CREATE TABLE IF NOT EXISTS user_account_outbox_dead_letters (
    event_id            VARCHAR(64) PRIMARY KEY,
    event_type          VARCHAR(96) NOT NULL,
    aggregate_version   BIGINT NOT NULL,
    delivery_attempt    INTEGER NOT NULL,
    failure_code        VARCHAR(64) NOT NULL,
    failure_digest      CHAR(64) NOT NULL,
    failed_at           TIMESTAMPTZ NOT NULL,
    expires_at          TIMESTAMPTZ NOT NULL,
    CONSTRAINT chk_user_account_outbox_dead_letter_expiry
        CHECK (expires_at > failed_at)
);

CREATE INDEX IF NOT EXISTS idx_user_account_outbox_dead_letters_expiry
    ON user_account_outbox_dead_letters (expires_at);

CREATE INDEX IF NOT EXISTS idx_user_account_outbox_dead_letters_failed
    ON user_account_outbox_dead_letters (failed_at, event_id);

-- Claim scans exclude terminal records. The partial per-account ordering index
-- prevents a later lifecycle fact from bypassing a failed predecessor.
CREATE INDEX IF NOT EXISTS idx_user_account_outbox_claim_ready
    ON user_account_outbox (
        next_attempt_at,
        lease_until,
        occurred_at,
        event_id
    )
    WHERE published_at IS NULL
      AND terminal_failure_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_user_account_outbox_unpublished_order
    ON user_account_outbox (
        aggregate_id,
        occurred_at,
        event_id
    )
    WHERE published_at IS NULL;
