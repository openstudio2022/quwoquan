-- SubjectFollow object packet: aggregate state, idempotency receipt and
-- transactional outbox are committed by one PostgreSQL transaction.
-- Canonical source: services/user-service/contracts/subject_follow/storage.yaml

CREATE TABLE IF NOT EXISTS subject_follows (
    id            VARCHAR(64) PRIMARY KEY,
    persona_id    VARCHAR(96) NOT NULL,
    subject_type  VARCHAR(16) NOT NULL,
    subject_id    VARCHAR(96) NOT NULL,
    state         VARCHAR(16) NOT NULL DEFAULT 'following',
    version       BIGINT NOT NULL DEFAULT 1,
    followed_at   TIMESTAMPTZ,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_subject_follow_identity UNIQUE (persona_id, subject_type, subject_id)
);

CREATE INDEX IF NOT EXISTS idx_subject_follows_subject
    ON subject_follows (subject_type, subject_id, state);

CREATE TABLE IF NOT EXISTS subject_follow_command_receipts (
    receipt_id       VARCHAR(64) PRIMARY KEY,
    persona_id       VARCHAR(96) NOT NULL,
    idempotency_key  VARCHAR(160) NOT NULL,
    operation        VARCHAR(48) NOT NULL,
    aggregate_id     VARCHAR(64) NOT NULL,
    aggregate_version BIGINT NOT NULL,
    response_json    JSONB NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_subject_follow_receipt_key UNIQUE (persona_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS subject_follow_outbox (
    event_id          VARCHAR(96) PRIMARY KEY,
    aggregate_id      VARCHAR(64) NOT NULL,
    aggregate_version BIGINT NOT NULL,
    event_name        VARCHAR(96) NOT NULL,
    payload_json      JSONB NOT NULL,
    occurred_at       TIMESTAMPTZ NOT NULL,
    claim_owner       VARCHAR(96),
    claimed_at        TIMESTAMPTZ,
    published_at      TIMESTAMPTZ,
    CONSTRAINT uq_subject_follow_outbox_version UNIQUE (aggregate_id, aggregate_version)
);

CREATE INDEX IF NOT EXISTS idx_subject_follow_outbox_pending
    ON subject_follow_outbox (published_at, occurred_at);
