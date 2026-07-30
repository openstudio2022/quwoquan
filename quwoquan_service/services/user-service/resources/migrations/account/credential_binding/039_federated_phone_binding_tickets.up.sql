-- CredentialBinding-owned federated first-login ticket. The public opaque
-- value is never persisted; only its SHA-256 digest identifies the row.
CREATE TABLE IF NOT EXISTS federated_phone_binding_tickets (
    ticket_id           VARCHAR(64) PRIMARY KEY,
    ticket_hash         CHAR(64) NOT NULL UNIQUE,
    provider            VARCHAR(16) NOT NULL,
    credential_type     VARCHAR(16) NOT NULL,
    credential_key      VARCHAR(256) NOT NULL,
    display_name        VARCHAR(64) NOT NULL DEFAULT '',
    avatar_url          TEXT NOT NULL DEFAULT '',
    device_id           VARCHAR(128) NOT NULL,
    platform            VARCHAR(16) NOT NULL,
    app_version         VARCHAR(32) NOT NULL,
    agreement_version   VARCHAR(64) NOT NULL,
    privacy_version     VARCHAR(64) NOT NULL,
    status              VARCHAR(16) NOT NULL DEFAULT 'pending',
    expires_at          TIMESTAMPTZ NOT NULL,
    consumed_at         TIMESTAMPTZ,
    version             BIGINT NOT NULL DEFAULT 1,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_federated_phone_binding_ticket_provider
        CHECK (provider IN ('wechat', 'alipay', 'qq')),
    CONSTRAINT ck_federated_phone_binding_ticket_provider_identity
        CHECK (
            (provider = 'wechat' AND credential_type = 'federated_slot_a')
            OR (provider = 'alipay' AND credential_type = 'federated_slot_b')
            OR (provider = 'qq' AND credential_type = 'federated_slot_c')
        ),
    CONSTRAINT ck_federated_phone_binding_ticket_status
        CHECK (status IN ('pending', 'consumed')),
    CONSTRAINT ck_federated_phone_binding_ticket_version
        CHECK (version >= 1),
    CONSTRAINT ck_federated_phone_binding_ticket_expiry_window
        CHECK (expires_at > created_at),
    CONSTRAINT ck_federated_phone_binding_ticket_consumption
        CHECK (
            (status = 'pending' AND consumed_at IS NULL)
            OR
            (status = 'consumed' AND consumed_at IS NOT NULL)
        )
);

CREATE INDEX IF NOT EXISTS idx_federated_phone_binding_ticket_expiry
    ON federated_phone_binding_tickets (status, expires_at);

CREATE INDEX IF NOT EXISTS idx_federated_phone_binding_ticket_identity
    ON federated_phone_binding_tickets (credential_type, credential_key, status);

COMMENT ON COLUMN federated_phone_binding_tickets.ticket_hash IS
    'SHA-256 of the one-time opaque ticket; plaintext is never persisted';
