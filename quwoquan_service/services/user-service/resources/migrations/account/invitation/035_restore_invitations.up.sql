-- Invitation 是独立聚合；027 删除旧对象后由本迁移以当前契约恢复。
CREATE TABLE IF NOT EXISTS invite_records (
    id                       VARCHAR(64) PRIMARY KEY,
    inviter_sub_account_id   VARCHAR(96) NOT NULL,
    inviter_owner_account_id VARCHAR(96) NOT NULL,
    channel                  VARCHAR(16) NOT NULL,
    link_code                VARCHAR(32) NOT NULL UNIQUE,
    invitee_phone_hash       VARCHAR(64),
    status                   VARCHAR(16) NOT NULL DEFAULT 'generated',
    expire_at                TIMESTAMPTZ NOT NULL,
    generated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    delivered_at             TIMESTAMPTZ,
    viewed_at                TIMESTAMPTZ,
    accepted_at              TIMESTAMPTZ,
    converted_at             TIMESTAMPTZ,
    CONSTRAINT ck_invite_records_status CHECK (
        status IN ('generated', 'delivered', 'viewed', 'accepted', 'activated', 'expired', 'revoked')
    )
);

CREATE INDEX IF NOT EXISTS idx_invite_records_inviter_sub
    ON invite_records (inviter_sub_account_id);
CREATE INDEX IF NOT EXISTS idx_invite_records_status
    ON invite_records (status);
CREATE INDEX IF NOT EXISTS idx_invite_records_expire_at
    ON invite_records (expire_at);
CREATE UNIQUE INDEX IF NOT EXISTS uq_invite_idempotent
    ON invite_records (inviter_sub_account_id, channel, invitee_phone_hash)
    WHERE status = 'generated' AND invitee_phone_hash IS NOT NULL;
