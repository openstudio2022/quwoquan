CREATE TABLE IF NOT EXISTS consent_records (
    id VARCHAR(64) PRIMARY KEY,
    owner_id VARCHAR(96) NOT NULL,
    agreement_version VARCHAR(64) NOT NULL,
    privacy_version VARCHAR(64) NOT NULL,
    accepted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    device_id VARCHAR(128),
    platform VARCHAR(32),
    source_operation VARCHAR(64) NOT NULL,
    CONSTRAINT fk_consent_records_owner_id FOREIGN KEY (owner_id) REFERENCES user_profiles(user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_consent_records_owner_id ON consent_records(owner_id);
CREATE INDEX IF NOT EXISTS idx_consent_records_source_operation ON consent_records(source_operation);
