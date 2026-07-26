-- PersonaRelationship command latency no longer includes derived follower /
-- following counter updates. Existing outbox rows were created by the former
-- synchronous counter path, so they are baselined as already projected exactly
-- once; rows inserted after this migration start with NULL and are projected by
-- the outbox fanout before its delivery checkpoint advances.

ALTER TABLE persona_relationship_outbox
    ADD COLUMN IF NOT EXISTS counter_projected_at TIMESTAMPTZ;

UPDATE persona_relationship_outbox
SET counter_projected_at = COALESCE(published_at, NOW())
WHERE counter_projected_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_persona_relationship_counter_projection_pending
    ON persona_relationship_outbox (counter_projected_at, occurred_at, event_id);
