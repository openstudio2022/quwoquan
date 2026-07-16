-- Persona target-side Command Facade support for ProfileUpdateProposal.
-- All Persona updates participate in optimistic versioning; the proposal
-- command commits state, receipt and outbox in one transaction.

ALTER TABLE personas ADD COLUMN IF NOT EXISTS bio TEXT NOT NULL DEFAULT '';
ALTER TABLE personas ADD COLUMN IF NOT EXISTS avatar_media_asset_id VARCHAR(96) NOT NULL DEFAULT '';
ALTER TABLE personas ADD COLUMN IF NOT EXISTS background_media_asset_id VARCHAR(96) NOT NULL DEFAULT '';
ALTER TABLE personas ADD COLUMN IF NOT EXISTS version BIGINT NOT NULL DEFAULT 1;

CREATE OR REPLACE FUNCTION bump_persona_version_if_unchanged()
RETURNS trigger AS $$
BEGIN
    IF NEW.version = OLD.version THEN
        NEW.version := OLD.version + 1;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_personas_version ON personas;
CREATE TRIGGER trg_personas_version
    BEFORE UPDATE ON personas
    FOR EACH ROW
    EXECUTE FUNCTION bump_persona_version_if_unchanged();

CREATE TABLE IF NOT EXISTS personas_command_receipts (
    receipt_id               VARCHAR(64) PRIMARY KEY,
    aggregate_id             VARCHAR(96) NOT NULL,
    idempotency_key          VARCHAR(160) NOT NULL UNIQUE,
    command_digest           VARCHAR(64) NOT NULL,
    aggregate_version        BIGINT NOT NULL,
    result_json              JSONB NOT NULL,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS personas_outbox (
    event_id                 VARCHAR(64) PRIMARY KEY,
    aggregate_id             VARCHAR(96) NOT NULL,
    aggregate_version        BIGINT NOT NULL,
    event_type               VARCHAR(96) NOT NULL,
    payload_json             JSONB NOT NULL,
    occurred_at              TIMESTAMPTZ NOT NULL,
    published_at             TIMESTAMPTZ,
    retry_count              INTEGER NOT NULL DEFAULT 0,
    next_attempt_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_error               TEXT NOT NULL DEFAULT '',
    CONSTRAINT uq_personas_outbox_version UNIQUE (aggregate_id, aggregate_version)
);

CREATE INDEX IF NOT EXISTS idx_personas_outbox_ready
    ON personas_outbox (published_at, next_attempt_at, occurred_at);
