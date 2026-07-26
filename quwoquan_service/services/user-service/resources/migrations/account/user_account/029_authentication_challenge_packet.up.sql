-- AuthenticationChallenge object packet.
-- The authoritative row is also the idempotency/completion receipt: no
-- separate receipt or paper outbox is created because metadata events.yaml is
-- empty. Every lifecycle mutation and its completion fingerprint is committed
-- by one PostgreSQL transaction.

ALTER TABLE authentication_challenges
    ADD COLUMN IF NOT EXISTS account_id VARCHAR(96),
    ADD COLUMN IF NOT EXISTS purpose VARCHAR(64),
    ADD COLUMN IF NOT EXISTS channel VARCHAR(32),
    ADD COLUMN IF NOT EXISTS creation_fingerprint VARCHAR(64),
    ADD COLUMN IF NOT EXISTS version BIGINT NOT NULL DEFAULT 1;

-- Normalize rows created by the pre-packet OTP implementation before applying
-- the canonical lifecycle constraint.
UPDATE authentication_challenges
SET status = CASE
    WHEN status IN ('pending_dispatch', 'active') THEN 'pending'
    WHEN status = 'consumed' AND completion_fingerprint IS NOT NULL THEN 'completed'
    WHEN status = 'consumed' THEN 'cancelled'
    WHEN status = 'failed' AND failed_attempts > 0 THEN 'locked'
    WHEN status = 'failed' THEN 'cancelled'
    ELSE status
END;

UPDATE authentication_challenges
SET
    consumed_at = NULL,
    completion_fingerprint = NULL
WHERE status <> 'completed';

UPDATE authentication_challenges
SET
    purpose = COALESCE(NULLIF(purpose, ''), 'phone_login'),
    channel = COALESCE(NULLIF(channel, ''), 'sms'),
    creation_fingerprint = COALESCE(
        NULLIF(creation_fingerprint, ''),
        md5(idempotency_key || E'\x1f' || challenge_id)
    );

ALTER TABLE authentication_challenges
    ALTER COLUMN purpose SET NOT NULL,
    ALTER COLUMN channel SET NOT NULL,
    ALTER COLUMN creation_fingerprint SET NOT NULL,
    ALTER COLUMN request_id DROP NOT NULL,
    ALTER COLUMN phone DROP NOT NULL,
    ALTER COLUMN phone_hash DROP NOT NULL;

ALTER TABLE authentication_challenges
    DROP CONSTRAINT IF EXISTS chk_authentication_challenges_status,
    ADD CONSTRAINT chk_authentication_challenges_status
        CHECK (status IN ('pending', 'completed', 'expired', 'locked', 'cancelled')),
    DROP CONSTRAINT IF EXISTS chk_authentication_challenges_attempt_count,
    ADD CONSTRAINT chk_authentication_challenges_attempt_count
        CHECK (failed_attempts >= 0),
    DROP CONSTRAINT IF EXISTS chk_authentication_challenges_version,
    ADD CONSTRAINT chk_authentication_challenges_version
        CHECK (version >= 1),
    DROP CONSTRAINT IF EXISTS chk_authentication_challenges_completion_receipt,
    ADD CONSTRAINT chk_authentication_challenges_completion_receipt
        CHECK (
            (status = 'completed' AND consumed_at IS NOT NULL AND completion_fingerprint IS NOT NULL)
            OR
            (status <> 'completed' AND consumed_at IS NULL AND completion_fingerprint IS NULL)
        );

CREATE INDEX IF NOT EXISTS idx_authentication_challenges_latest_target
    ON authentication_challenges (purpose, channel, phone_hash, created_at DESC);

COMMENT ON COLUMN authentication_challenges.challenge_id IS
    'AuthenticationChallenge.id';
COMMENT ON COLUMN authentication_challenges.phone_hash IS
    'AuthenticationChallenge.destinationHash; no plaintext destination';
COMMENT ON COLUMN authentication_challenges.code_hash IS
    'AuthenticationChallenge.secretRef; opaque irreversible verifier reference';
COMMENT ON COLUMN authentication_challenges.failed_attempts IS
    'AuthenticationChallenge.attemptCount';
COMMENT ON COLUMN authentication_challenges.consumed_at IS
    'AuthenticationChallenge.completedAt';
COMMENT ON COLUMN authentication_challenges.completion_fingerprint IS
    'Inline successful-verification replay receipt; never plaintext credential';
