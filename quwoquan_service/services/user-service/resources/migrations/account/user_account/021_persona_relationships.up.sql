-- PersonaRelationship is the sole persona-to-persona relationship aggregate.
-- The removed block_edges table and the former Mongo follow collection are not
-- migration sources: this service starts from the canonical relationship model.

DROP TABLE IF EXISTS block_edges;

CREATE TABLE IF NOT EXISTS persona_relationships (
    pair_id            VARCHAR(64) PRIMARY KEY,
    lower_persona_id   VARCHAR(96) NOT NULL,
    upper_persona_id   VARCHAR(96) NOT NULL,
    version            BIGINT NOT NULL DEFAULT 0,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_persona_relationship_pair UNIQUE (lower_persona_id, upper_persona_id),
    CONSTRAINT ck_persona_relationship_pair_order CHECK (lower_persona_id < upper_persona_id)
);

CREATE TABLE IF NOT EXISTS persona_relationship_directions (
    pair_id              VARCHAR(64) NOT NULL REFERENCES persona_relationships(pair_id) ON DELETE CASCADE,
    source_persona_id    VARCHAR(96) NOT NULL,
    target_persona_id    VARCHAR(96) NOT NULL,
    following            BOOLEAN NOT NULL DEFAULT FALSE,
    blocked              BOOLEAN NOT NULL DEFAULT FALSE,
    follow_source        VARCHAR(64),
    followed_at          TIMESTAMPTZ,
    blocked_at           TIMESTAMPTZ,
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (pair_id, source_persona_id),
    CONSTRAINT ck_persona_relationship_direction_pair CHECK (source_persona_id <> target_persona_id)
);

CREATE INDEX IF NOT EXISTS idx_persona_relationship_following
    ON persona_relationship_directions (source_persona_id, following, followed_at DESC);
CREATE INDEX IF NOT EXISTS idx_persona_relationship_followers
    ON persona_relationship_directions (target_persona_id, following, followed_at DESC);
CREATE INDEX IF NOT EXISTS idx_persona_relationship_blocked
    ON persona_relationship_directions (source_persona_id, blocked, blocked_at DESC);

CREATE TABLE IF NOT EXISTS persona_relationship_command_receipts (
    receipt_id            VARCHAR(64) PRIMARY KEY,
    actor_persona_id      VARCHAR(96) NOT NULL,
    idempotency_key       VARCHAR(128) NOT NULL,
    operation             VARCHAR(32) NOT NULL,
    target_persona_id     VARCHAR(96) NOT NULL,
    pair_id               VARCHAR(64) NOT NULL REFERENCES persona_relationships(pair_id) ON DELETE CASCADE,
    aggregate_version     BIGINT NOT NULL,
    response_json         JSONB NOT NULL,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_persona_relationship_command_receipt UNIQUE (actor_persona_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS persona_relationship_outbox (
    event_id              VARCHAR(64) PRIMARY KEY,
    aggregate_id          VARCHAR(64) NOT NULL REFERENCES persona_relationships(pair_id) ON DELETE CASCADE,
    aggregate_version     BIGINT NOT NULL,
    event_name            VARCHAR(96) NOT NULL,
    payload_json          JSONB NOT NULL,
    occurred_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    claim_owner           VARCHAR(64),
    claimed_at            TIMESTAMPTZ,
    published_at          TIMESTAMPTZ,
    CONSTRAINT uq_persona_relationship_outbox_version UNIQUE (aggregate_id, aggregate_version)
);

CREATE INDEX IF NOT EXISTS idx_persona_relationship_outbox_pending
    ON persona_relationship_outbox (published_at, claimed_at, occurred_at);
