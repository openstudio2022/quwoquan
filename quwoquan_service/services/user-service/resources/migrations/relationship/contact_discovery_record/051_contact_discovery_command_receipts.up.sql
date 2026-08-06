CREATE TABLE IF NOT EXISTS contact_discovery_command_receipts (
    receipt_id VARCHAR(80) PRIMARY KEY,
    owner_account_id VARCHAR(96) NOT NULL,
    operation VARCHAR(64) NOT NULL,
    idempotency_key VARCHAR(256) NOT NULL,
    command_digest CHAR(64) NOT NULL,
    aggregate_id VARCHAR(64) NOT NULL
        REFERENCES contact_discovery_records(id) ON DELETE CASCADE,
    result_status VARCHAR(16) NOT NULL,
    result_json JSONB NOT NULL,
    result_error VARCHAR(32) NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_contact_discovery_command_receipt
        UNIQUE (owner_account_id, operation, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_contact_discovery_command_receipt_aggregate
    ON contact_discovery_command_receipts (aggregate_id);
