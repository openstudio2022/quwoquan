-- 从 metadata user/user_profile 的 UserAccount 安全字段派生。
-- 该迁移只补可逆封禁/恢复状态；绝不调用或模拟 UserAccountClosed 的 PII 清理。
ALTER TABLE user_profiles
    ADD COLUMN IF NOT EXISTS auth_epoch BIGINT NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS suspension_case_ref VARCHAR(128),
    ADD COLUMN IF NOT EXISTS suspended_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_user_profiles_account_state
    ON user_profiles (account_state);

CREATE TABLE IF NOT EXISTS user_account_enforcement_receipts (
    decision_id      VARCHAR(128) PRIMARY KEY,
    account_id       VARCHAR(96) NOT NULL REFERENCES user_profiles(user_id),
    action           VARCHAR(16) NOT NULL
        CHECK (action IN ('suspend', 'restore')),
    case_ref         VARCHAR(128) NOT NULL,
    decision_digest  VARCHAR(256) NOT NULL,
    approved_at      TIMESTAMPTZ NOT NULL,
    account_state    VARCHAR(32) NOT NULL,
    auth_epoch       BIGINT NOT NULL,
    account_version  BIGINT NOT NULL,
    occurred_at      TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_user_account_enforcement_receipts_account
    ON user_account_enforcement_receipts (account_id, occurred_at DESC);
