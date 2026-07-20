-- B1 object packets: UserSettings CAS + audit outbox, CredentialBinding
-- transactional security outbox, and DeviceRegistration encrypted push tokens.

ALTER TABLE user_settings
    ADD COLUMN IF NOT EXISTS version BIGINT NOT NULL DEFAULT 1;

CREATE TABLE IF NOT EXISTS user_settings_outbox (
    event_id            VARCHAR(64) PRIMARY KEY,
    aggregate_id        VARCHAR(96) NOT NULL,
    aggregate_version   BIGINT NOT NULL,
    event_type          VARCHAR(96) NOT NULL,
    payload_json        JSONB NOT NULL,
    occurred_at         TIMESTAMPTZ NOT NULL,
    published_at        TIMESTAMPTZ,
    retry_count         INTEGER NOT NULL DEFAULT 0,
    next_attempt_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_error          TEXT NOT NULL DEFAULT '',
    CONSTRAINT uq_user_settings_outbox_version
        UNIQUE (aggregate_id, aggregate_version)
);

CREATE INDEX IF NOT EXISTS idx_user_settings_outbox_ready
    ON user_settings_outbox (published_at, next_attempt_at, occurred_at);

ALTER TABLE credential_bindings
    ADD COLUMN IF NOT EXISTS version BIGINT NOT NULL DEFAULT 1;

CREATE TABLE IF NOT EXISTS credential_bindings_outbox (
    event_id            VARCHAR(64) PRIMARY KEY,
    aggregate_id        VARCHAR(64) NOT NULL,
    aggregate_version   BIGINT NOT NULL,
    event_type          VARCHAR(96) NOT NULL,
    payload_json        JSONB NOT NULL,
    occurred_at         TIMESTAMPTZ NOT NULL,
    published_at        TIMESTAMPTZ,
    retry_count         INTEGER NOT NULL DEFAULT 0,
    next_attempt_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_error          TEXT NOT NULL DEFAULT '',
    CONSTRAINT uq_credential_bindings_outbox_version
        UNIQUE (aggregate_id, aggregate_version)
);

CREATE INDEX IF NOT EXISTS idx_credential_bindings_outbox_ready
    ON credential_bindings_outbox (published_at, next_attempt_at, occurred_at);

-- 未上线阶段零兼容：删除历史明文 push_token，改为 AES-GCM 密文与 keyed
-- fingerprint。fingerprint 只用于唯一约束/查重，不能反推出 token。
ALTER TABLE user_devices DROP COLUMN IF EXISTS push_token;
ALTER TABLE user_devices
    ADD COLUMN IF NOT EXISTS push_token_ciphertext TEXT,
    ADD COLUMN IF NOT EXISTS push_token_fingerprint VARCHAR(64),
    ADD COLUMN IF NOT EXISTS status VARCHAR(16) NOT NULL DEFAULT 'active',
    ADD COLUMN IF NOT EXISTS version BIGINT NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE UNIQUE INDEX IF NOT EXISTS uq_user_devices_active_token_fingerprint
    ON user_devices (push_token_fingerprint)
    WHERE status = 'active' AND push_token_fingerprint IS NOT NULL;
