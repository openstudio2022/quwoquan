ALTER TABLE profile_update_proposals_outbox
    ADD COLUMN claim_owner VARCHAR(160),
    ADD COLUMN claimed_at TIMESTAMPTZ;

DROP INDEX IF EXISTS idx_profile_proposal_outbox_ready;

CREATE INDEX idx_profile_proposal_outbox_ready
    ON profile_update_proposals_outbox (
        published_at,
        claim_owner,
        claimed_at,
        next_attempt_at,
        occurred_at
    );
