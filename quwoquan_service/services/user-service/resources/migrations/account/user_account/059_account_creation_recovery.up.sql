-- Stable recovery state for the multi-step UserAccount -> Persona -> public
-- profile -> Credential bootstrap. This table stores only workflow coordinates
-- and selected immutable identities; profile and credential data remain owned by
-- their authoritative objects.
CREATE TABLE IF NOT EXISTS user_account_creation_flows (
    flow_id              VARCHAR(96) PRIMARY KEY,
    intent_digest        VARCHAR(64) NOT NULL,
    owner_id             VARCHAR(96) NOT NULL,
    persona_id           VARCHAR(96) NOT NULL,
    default_nickname     VARCHAR(96) NOT NULL,
    identity_origin      VARCHAR(32) NOT NULL,
    account_committed    BOOLEAN NOT NULL DEFAULT FALSE,
    persona_committed    BOOLEAN NOT NULL DEFAULT FALSE,
    profile_projected    BOOLEAN NOT NULL DEFAULT FALSE,
    credential_bound     BOOLEAN NOT NULL DEFAULT FALSE,
    completed            BOOLEAN NOT NULL DEFAULT FALSE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_user_account_creation_owner UNIQUE (owner_id),
    CONSTRAINT uq_user_account_creation_persona UNIQUE (persona_id)
);
CREATE INDEX IF NOT EXISTS idx_user_account_creation_incomplete
    ON user_account_creation_flows (updated_at)
    WHERE completed = FALSE;
