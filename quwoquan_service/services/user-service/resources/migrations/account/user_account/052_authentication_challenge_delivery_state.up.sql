-- AuthenticationChallenge owns the authoritative OTP delivery projection.
-- request_id already exists from the original OTP table and now carries
-- deliveryRequestId; provider result facts are consumed from the Integration
-- durable stream, never from a parallel HTTP callback.

ALTER TABLE authentication_challenges
    ADD COLUMN IF NOT EXISTS delivery_status VARCHAR(32),
    ADD COLUMN IF NOT EXISTS delivery_updated_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_delivery_event_id VARCHAR(128);

UPDATE authentication_challenges
SET
    delivery_status = 'sent_unconfirmed',
    delivery_updated_at = COALESCE(updated_at, created_at)
WHERE request_id IS NOT NULL
  AND delivery_status IS NULL;

ALTER TABLE authentication_challenges
    DROP CONSTRAINT IF EXISTS chk_authentication_challenges_delivery_state,
    ADD CONSTRAINT chk_authentication_challenges_delivery_state
        CHECK (
            (request_id IS NULL
                AND delivery_status IS NULL
                AND delivery_updated_at IS NULL
                AND last_delivery_event_id IS NULL)
            OR
            (request_id IS NOT NULL
                AND delivery_status IN ('queued', 'sent_unconfirmed', 'delivered', 'failed')
                AND delivery_updated_at IS NOT NULL)
        );

CREATE UNIQUE INDEX IF NOT EXISTS uq_authentication_challenges_delivery_request
    ON authentication_challenges (request_id)
    WHERE request_id IS NOT NULL;

COMMENT ON COLUMN authentication_challenges.request_id IS
    'AuthenticationChallenge.deliveryRequestId; privacy-safe Integration request identity';
COMMENT ON COLUMN authentication_challenges.delivery_status IS
    'AuthenticationChallenge.deliveryStatus authoritative durable result projection';
COMMENT ON COLUMN authentication_challenges.delivery_updated_at IS
    'AuthenticationChallenge.deliveryUpdatedAt from the accepted or durable result time';
COMMENT ON COLUMN authentication_challenges.last_delivery_event_id IS
    'AuthenticationChallenge.lastDeliveryEventId for duplicate and out-of-order suppression';
