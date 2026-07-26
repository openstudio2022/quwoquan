-- DeviceRegistration M2：未上线阶段执行破坏性单轨迁移。
-- 删除旧 user_id/platform/单 push token 形态，不保留兼容列、触发器或双写。
DROP TABLE IF EXISTS device_push_endpoints;
DROP TABLE IF EXISTS user_devices CASCADE;

CREATE TABLE user_devices (
    id              VARCHAR(64) PRIMARY KEY,
    account_id      VARCHAR(96) NOT NULL,
    device_id       VARCHAR(128) NOT NULL,
    app_version     VARCHAR(32),
    status          VARCHAR(16) NOT NULL DEFAULT 'active',
    version         BIGINT NOT NULL DEFAULT 1,
    last_active_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_user_devices_account
        FOREIGN KEY (account_id) REFERENCES user_profiles(user_id) ON DELETE CASCADE,
    CONSTRAINT uq_user_devices_account_device UNIQUE (account_id, device_id),
    CONSTRAINT ck_user_devices_status CHECK (status IN ('active', 'revoked', 'stale')),
    CONSTRAINT ck_user_devices_version CHECK (version >= 1)
);

CREATE TABLE device_push_endpoints (
    endpoint_ref        VARCHAR(64) PRIMARY KEY,
    account_id          VARCHAR(96) NOT NULL,
    device_id           VARCHAR(128) NOT NULL,
    endpoint_kind       VARCHAR(16) NOT NULL,
    token_ciphertext    TEXT,
    token_fingerprint   VARCHAR(64),
    status              VARCHAR(16) NOT NULL DEFAULT 'active',
    invalidation_reason VARCHAR(256),
    version             BIGINT NOT NULL DEFAULT 1,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_device_push_endpoints_registration
        FOREIGN KEY (account_id, device_id)
        REFERENCES user_devices(account_id, device_id) ON DELETE CASCADE,
    CONSTRAINT uq_device_push_endpoints_identity
        UNIQUE (account_id, device_id, endpoint_kind),
    CONSTRAINT ck_device_push_endpoints_kind
        CHECK (endpoint_kind IN ('apns_voip', 'fcm')),
    CONSTRAINT ck_device_push_endpoints_status
        CHECK (status IN ('active', 'revoked', 'stale')),
    CONSTRAINT ck_device_push_endpoints_version CHECK (version >= 1),
    CONSTRAINT ck_device_push_endpoints_token_material CHECK (
        (status = 'active' AND token_ciphertext IS NOT NULL AND token_fingerprint IS NOT NULL)
        OR
        (status IN ('revoked', 'stale') AND token_ciphertext IS NULL AND token_fingerprint IS NULL)
    ),
    CONSTRAINT ck_device_push_endpoints_invalidation_reason CHECK (
        (status = 'stale' AND invalidation_reason IS NOT NULL AND BTRIM(invalidation_reason) <> '')
        OR
        (status IN ('active', 'revoked') AND invalidation_reason IS NULL)
    )
);

CREATE UNIQUE INDEX uq_device_push_endpoints_active_token_fingerprint
    ON device_push_endpoints (token_fingerprint)
    WHERE status = 'active' AND token_fingerprint IS NOT NULL;

CREATE INDEX idx_device_push_endpoints_active_account
    ON device_push_endpoints (account_id, device_id, endpoint_kind)
    WHERE status = 'active';
