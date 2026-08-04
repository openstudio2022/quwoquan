-- Nonprod deterministic Idempotency-Key segments exceed VARCHAR(128)
-- (e.g. gamma-local/<64-hex-epoch>/nonprod_reference_identity/.../FollowUser/...).
ALTER TABLE persona_relationship_command_receipts
    ALTER COLUMN idempotency_key TYPE VARCHAR(160);
