-- bind_phone OTP challenges are scoped to exactly one internal federated
-- binding ticket identity. Existing non-binding challenges remain unscoped.
ALTER TABLE authentication_challenges
    ADD COLUMN IF NOT EXISTS binding_ticket_id VARCHAR(64);

ALTER TABLE authentication_challenges
    DROP CONSTRAINT IF EXISTS fk_authentication_challenge_binding_ticket,
    ADD CONSTRAINT fk_authentication_challenge_binding_ticket
        FOREIGN KEY (binding_ticket_id)
        REFERENCES federated_phone_binding_tickets(ticket_id)
        ON DELETE RESTRICT,
    DROP CONSTRAINT IF EXISTS ck_authentication_challenge_binding_ticket_scope,
    ADD CONSTRAINT ck_authentication_challenge_binding_ticket_scope
        CHECK (
            binding_ticket_id IS NULL
            OR purpose = 'bind_phone'
        );

CREATE INDEX IF NOT EXISTS idx_authentication_challenge_binding_ticket
    ON authentication_challenges (binding_ticket_id)
    WHERE binding_ticket_id IS NOT NULL;
