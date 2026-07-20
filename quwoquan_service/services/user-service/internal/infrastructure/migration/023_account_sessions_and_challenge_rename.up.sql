-- AccountSession object packet: per-session rows with refresh token hash and
-- rotation lineage; state and outbox commit in one PostgreSQL transaction.
-- Plaintext refresh token columns are removed from user_auth (kept only for
-- login lockout state). otp_challenges is renamed to authentication_challenges
-- to align storage with contracts/metadata/user/authentication_challenge.

CREATE TABLE IF NOT EXISTS account_sessions (
    session_id          VARCHAR(64) PRIMARY KEY,
    account_id          VARCHAR(96) NOT NULL,
    device_id           VARCHAR(128) NOT NULL DEFAULT '',
    refresh_token_hash  VARCHAR(64) NOT NULL,
    lineage_id          VARCHAR(64) NOT NULL,
    rotated_from_hash   VARCHAR(64),
    status              VARCHAR(16) NOT NULL DEFAULT 'active',
    issued_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at          TIMESTAMPTZ NOT NULL,
    revoked_at          TIMESTAMPTZ,
    revoke_reason       VARCHAR(64),
    version             BIGINT NOT NULL DEFAULT 1,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_account_sessions_refresh_hash UNIQUE (refresh_token_hash)
);

CREATE INDEX IF NOT EXISTS idx_account_sessions_account_status
    ON account_sessions (account_id, status);

CREATE INDEX IF NOT EXISTS idx_account_sessions_lineage
    ON account_sessions (lineage_id);

CREATE TABLE IF NOT EXISTS account_sessions_outbox (
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
    CONSTRAINT uq_account_sessions_outbox_version UNIQUE (aggregate_id, aggregate_version)
);

CREATE INDEX IF NOT EXISTS idx_account_sessions_outbox_ready
    ON account_sessions_outbox (published_at, next_attempt_at, occurred_at);

ALTER TABLE user_auth DROP COLUMN IF EXISTS refresh_token;
ALTER TABLE user_auth DROP COLUMN IF EXISTS refresh_token_expires_at;

ALTER TABLE IF EXISTS otp_challenges RENAME TO authentication_challenges;
ALTER INDEX IF EXISTS idx_otp_challenges_phone_status_expires
    RENAME TO idx_authentication_challenges_phone_status_expires;
ALTER INDEX IF EXISTS idx_otp_challenges_request_id
    RENAME TO idx_authentication_challenges_request_id;

ALTER TABLE authentication_challenges
    ADD COLUMN IF NOT EXISTS completion_fingerprint VARCHAR(64);
