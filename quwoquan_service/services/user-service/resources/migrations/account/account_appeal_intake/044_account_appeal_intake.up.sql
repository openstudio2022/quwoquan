CREATE TABLE IF NOT EXISTS account_appeal_intakes (
    intake_ref                 VARCHAR(64) PRIMARY KEY,
    account_id                 VARCHAR(96) NOT NULL REFERENCES user_profiles(user_id) ON DELETE CASCADE,
    suspension_auth_epoch      BIGINT NOT NULL CHECK (suspension_auth_epoch > 0),
    status                     VARCHAR(16) NOT NULL DEFAULT 'submitted'
                               CHECK (status IN ('submitted', 'claimed')),
    submitted_at               TIMESTAMPTZ NOT NULL,
    claimed_case_id            VARCHAR(128),
    claimed_at                 TIMESTAMPTZ,
    delete_after               TIMESTAMPTZ NOT NULL,
    version                    BIGINT NOT NULL DEFAULT 1 CHECK (version > 0),
    submission_idempotency_key VARCHAR(160) NOT NULL UNIQUE,
    submission_digest          CHAR(64) NOT NULL,
    claim_idempotency_key      VARCHAR(160) UNIQUE,
    claim_digest               CHAR(64),
    CONSTRAINT uq_account_appeal_intakes_account_epoch
        UNIQUE (account_id, suspension_auth_epoch),
    CONSTRAINT ck_account_appeal_intake_retention
        CHECK (delete_after > submitted_at),
    CONSTRAINT ck_account_appeal_intake_claim
        CHECK (
            (status = 'submitted' AND claimed_case_id IS NULL AND claimed_at IS NULL
                AND claim_idempotency_key IS NULL AND claim_digest IS NULL)
            OR
            (status = 'claimed' AND claimed_case_id IS NOT NULL AND claimed_at IS NOT NULL
                AND claim_idempotency_key IS NOT NULL AND claim_digest IS NOT NULL
                AND claimed_at >= submitted_at AND claimed_at < delete_after)
        )
);

CREATE INDEX IF NOT EXISTS idx_account_appeal_intakes_delete_after
    ON account_appeal_intakes (delete_after);
CREATE INDEX IF NOT EXISTS idx_account_appeal_intakes_claimed_case
    ON account_appeal_intakes (claimed_case_id)
    WHERE claimed_case_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS account_appeal_credentials (
    credential_id        VARCHAR(64) PRIMARY KEY,
    credential_digest    CHAR(64) NOT NULL UNIQUE,
    challenge_id         VARCHAR(128) NOT NULL UNIQUE,
    account_id           VARCHAR(96) NOT NULL REFERENCES user_profiles(user_id) ON DELETE CASCADE,
    suspension_auth_epoch BIGINT NOT NULL CHECK (suspension_auth_epoch > 0),
    issued_at             TIMESTAMPTZ NOT NULL,
    expires_at            TIMESTAMPTZ NOT NULL,
    consumed_at           TIMESTAMPTZ,
    intake_ref            VARCHAR(64),
    delete_after          TIMESTAMPTZ NOT NULL,
    CONSTRAINT ck_account_appeal_credential_lifetime
        CHECK (expires_at > issued_at AND delete_after > expires_at),
    CONSTRAINT ck_account_appeal_credential_consumption
        CHECK (
            (consumed_at IS NULL AND intake_ref IS NULL)
            OR
            (consumed_at IS NOT NULL AND intake_ref IS NOT NULL
                AND consumed_at >= issued_at AND consumed_at < delete_after)
        )
);

CREATE INDEX IF NOT EXISTS idx_account_appeal_credentials_account_epoch
    ON account_appeal_credentials (account_id, suspension_auth_epoch, issued_at DESC);
CREATE INDEX IF NOT EXISTS idx_account_appeal_credentials_delete_after
    ON account_appeal_credentials (delete_after);
