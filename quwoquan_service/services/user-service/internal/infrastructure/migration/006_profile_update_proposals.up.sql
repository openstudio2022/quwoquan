-- ProfileUpdateProposal object packet: aggregate state, idempotency receipt and
-- outbox are committed by one PostgreSQL transaction. No legacy user_id column.

CREATE TABLE IF NOT EXISTS profile_update_proposals (
    id                       VARCHAR(64) PRIMARY KEY,
    persona_id               VARCHAR(96) NOT NULL,
    source                   VARCHAR(32) NOT NULL,
    proposed_changes         JSONB NOT NULL,
    status                   VARCHAR(16) NOT NULL DEFAULT 'pending',
    reviewed_by              VARCHAR(96),
    target_persona_expected_version BIGINT,
    version                  BIGINT NOT NULL DEFAULT 1,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at              TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_profile_proposals_persona_status
    ON profile_update_proposals (persona_id, status, created_at);

CREATE TABLE IF NOT EXISTS profile_update_proposals_command_receipts (
    receipt_id               VARCHAR(64) PRIMARY KEY,
    proposal_id              VARCHAR(64) NOT NULL,
    idempotency_key          VARCHAR(160) NOT NULL,
    command_digest           VARCHAR(64) NOT NULL,
    aggregate_version        BIGINT NOT NULL,
    result_json              JSONB NOT NULL,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_profile_proposal_receipt_key UNIQUE (proposal_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS profile_update_proposals_outbox (
    event_id                 VARCHAR(96) PRIMARY KEY,
    aggregate_id             VARCHAR(64) NOT NULL,
    aggregate_version        BIGINT NOT NULL,
    event_type               VARCHAR(96) NOT NULL,
    payload_json             JSONB NOT NULL,
    occurred_at              TIMESTAMPTZ NOT NULL,
    published_at             TIMESTAMPTZ,
    retry_count              INTEGER NOT NULL DEFAULT 0,
    next_attempt_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_error               TEXT NOT NULL DEFAULT '',
    CONSTRAINT uq_profile_proposal_outbox_version UNIQUE (aggregate_id, aggregate_version)
);

CREATE INDEX IF NOT EXISTS idx_profile_proposal_outbox_ready
    ON profile_update_proposals_outbox (published_at, next_attempt_at, occurred_at);
