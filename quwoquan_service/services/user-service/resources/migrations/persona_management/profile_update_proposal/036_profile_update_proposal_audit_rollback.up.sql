-- ProfileUpdateProposal single-track cutover.
-- The product is pre-release: existing proposal packets are intentionally
-- discarded instead of dual-reading incomplete unaudited records.
TRUNCATE profile_update_proposals_command_receipts,
         profile_update_proposals_outbox,
         profile_update_proposals;

ALTER TABLE profile_update_proposals
    ADD COLUMN reason TEXT NOT NULL,
    ADD COLUMN evidence_refs JSONB NOT NULL,
    ADD COLUMN impact_scope JSONB NOT NULL,
    ADD COLUMN created_by VARCHAR(96) NOT NULL,
    ADD COLUMN created_request_id VARCHAR(128) NOT NULL,
    ADD COLUMN created_trace_id VARCHAR(128) NOT NULL,
    ADD COLUMN apply_actor_persona_id VARCHAR(96),
    ADD COLUMN apply_request_id VARCHAR(128),
    ADD COLUMN apply_trace_id VARCHAR(128),
    ADD COLUMN apply_audit_id VARCHAR(96),
    ADD COLUMN rollback_deadline TIMESTAMPTZ,
    ADD COLUMN rollback_actor_persona_id VARCHAR(96),
    ADD COLUMN rollback_request_id VARCHAR(128),
    ADD COLUMN rollback_trace_id VARCHAR(128),
    ADD COLUMN rollback_audit_id VARCHAR(96);

ALTER TABLE profile_update_proposals_command_receipts
    DROP CONSTRAINT uq_profile_proposal_receipt_key,
    ADD COLUMN actor_persona_id VARCHAR(96) NOT NULL,
    ADD CONSTRAINT uq_profile_proposal_actor_receipt_key
        UNIQUE (actor_persona_id, idempotency_key);

CREATE TABLE profile_update_proposal_audits (
    audit_id                VARCHAR(96) PRIMARY KEY,
    proposal_id             VARCHAR(64) NOT NULL
                            REFERENCES profile_update_proposals(id) ON DELETE CASCADE,
    action                  VARCHAR(16) NOT NULL
                            CHECK (action IN ('apply', 'rollback')),
    actor_persona_id        VARCHAR(96) NOT NULL,
    request_id              VARCHAR(128) NOT NULL,
    trace_id                VARCHAR(128) NOT NULL,
    before_snapshot         JSONB NOT NULL,
    after_snapshot          JSONB NOT NULL,
    before_persona_version  BIGINT NOT NULL,
    after_persona_version   BIGINT NOT NULL,
    occurred_at             TIMESTAMPTZ NOT NULL,
    rollback_deadline       TIMESTAMPTZ,
    CONSTRAINT uq_profile_update_proposal_audit_action
        UNIQUE (proposal_id, action)
);

CREATE INDEX idx_profile_update_proposal_audits_proposal
    ON profile_update_proposal_audits (proposal_id, occurred_at);
