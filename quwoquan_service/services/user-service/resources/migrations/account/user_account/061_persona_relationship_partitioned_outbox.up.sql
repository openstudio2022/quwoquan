-- T13: fixed-partition PersonaRelationship outbox transport.
-- Aggregate versions remain business ordering; partition_sequence is the
-- independent contiguous transport order. The trigger keeps writers on the
-- single partitioned path without requiring a dual-write compatibility phase.

CREATE TABLE IF NOT EXISTS persona_relationship_outbox_sequences (
    partition_id SMALLINT PRIMARY KEY,
    sequence BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT ck_persona_relationship_outbox_sequence_partition
        CHECK (partition_id >= 0 AND partition_id < 32),
    CONSTRAINT ck_persona_relationship_outbox_sequence_nonnegative
        CHECK (sequence >= 0)
);

ALTER TABLE persona_relationship_outbox
    ADD COLUMN IF NOT EXISTS partition_id SMALLINT,
    ADD COLUMN IF NOT EXISTS partition_sequence BIGINT;

WITH assigned AS (
    SELECT event_id,
           MOD(('x' || SUBSTRING(aggregate_id FROM 1 FOR 8))::bit(32)::bigint, 32)::smallint AS partition_id,
           ROW_NUMBER() OVER (
               PARTITION BY MOD(('x' || SUBSTRING(aggregate_id FROM 1 FOR 8))::bit(32)::bigint, 32)
               ORDER BY occurred_at, event_id
           )::bigint AS partition_sequence
    FROM persona_relationship_outbox
    WHERE partition_id IS NULL OR partition_sequence IS NULL
)
UPDATE persona_relationship_outbox AS outbox
SET partition_id = assigned.partition_id,
    partition_sequence = assigned.partition_sequence
FROM assigned
WHERE outbox.event_id = assigned.event_id;

INSERT INTO persona_relationship_outbox_sequences (partition_id, sequence)
SELECT partition_id, MAX(partition_sequence)
FROM persona_relationship_outbox
GROUP BY partition_id
ON CONFLICT (partition_id) DO UPDATE
SET sequence = GREATEST(persona_relationship_outbox_sequences.sequence, EXCLUDED.sequence);

CREATE OR REPLACE FUNCTION assign_persona_relationship_outbox_partition()
RETURNS TRIGGER AS $$
DECLARE
    assigned_partition SMALLINT;
    assigned_sequence BIGINT;
BEGIN
    assigned_partition := MOD(('x' || SUBSTRING(NEW.aggregate_id FROM 1 FOR 8))::bit(32)::bigint, 32)::smallint;
    INSERT INTO persona_relationship_outbox_sequences (partition_id, sequence)
    VALUES (assigned_partition, 1)
    ON CONFLICT (partition_id) DO UPDATE
    SET sequence = persona_relationship_outbox_sequences.sequence + 1
    RETURNING sequence INTO assigned_sequence;
    NEW.partition_id := assigned_partition;
    NEW.partition_sequence := assigned_sequence;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_persona_relationship_outbox_partition
    ON persona_relationship_outbox;
CREATE TRIGGER trg_persona_relationship_outbox_partition
BEFORE INSERT ON persona_relationship_outbox
FOR EACH ROW EXECUTE FUNCTION assign_persona_relationship_outbox_partition();

ALTER TABLE persona_relationship_outbox
    ALTER COLUMN partition_id SET NOT NULL,
    ALTER COLUMN partition_sequence SET NOT NULL;

ALTER TABLE persona_relationship_outbox
    DROP CONSTRAINT IF EXISTS uq_persona_relationship_outbox_partition_sequence;
ALTER TABLE persona_relationship_outbox
    ADD CONSTRAINT uq_persona_relationship_outbox_partition_sequence
        UNIQUE (partition_id, partition_sequence);

DROP INDEX IF EXISTS idx_persona_relationship_outbox_pending;
CREATE INDEX idx_persona_relationship_outbox_partition_pending
    ON persona_relationship_outbox (partition_id, partition_sequence)
    WHERE published_at IS NULL;

CREATE TABLE IF NOT EXISTS persona_relationship_outbox_checkpoints (
    consumer VARCHAR(160) NOT NULL,
    partition_id SMALLINT NOT NULL,
    sequence BIGINT NOT NULL DEFAULT 0,
    lease_epoch BIGINT NOT NULL DEFAULT 0,
    lease_owner VARCHAR(160),
    lease_until TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (consumer, partition_id),
    CONSTRAINT ck_persona_relationship_checkpoint_partition
        CHECK (partition_id >= 0 AND partition_id < 32),
    CONSTRAINT ck_persona_relationship_checkpoint_sequence
        CHECK (sequence >= 0),
    CONSTRAINT ck_persona_relationship_checkpoint_epoch
        CHECK (lease_epoch >= 0)
);

CREATE INDEX IF NOT EXISTS idx_persona_relationship_outbox_checkpoint_claim
    ON persona_relationship_outbox_checkpoints (consumer, lease_until, partition_id);
