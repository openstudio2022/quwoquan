ALTER TABLE user_profiles
  ADD COLUMN IF NOT EXISTS background_asset_id VARCHAR(64),
  ADD COLUMN IF NOT EXISTS region_code VARCHAR(32);

CREATE TABLE IF NOT EXISTS profile_qr_tokens (
  token_id VARCHAR(64) PRIMARY KEY,
  token_hash VARCHAR(128) NOT NULL UNIQUE,
  owner_user_id VARCHAR(96) NOT NULL REFERENCES user_profiles(user_id) ON DELETE CASCADE,
  sub_account_id VARCHAR(96) NOT NULL,
  user_handle VARCHAR(64) NOT NULL,
  style_version VARCHAR(16) NOT NULL DEFAULT 'v1',
  status VARCHAR(16) NOT NULL DEFAULT 'active',
  expires_at TIMESTAMPTZ,
  revoked_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_profile_qr_tokens_owner_status
  ON profile_qr_tokens(owner_user_id, status);

CREATE INDEX IF NOT EXISTS idx_profile_qr_tokens_handle
  ON profile_qr_tokens(user_handle);

CREATE INDEX IF NOT EXISTS idx_profile_qr_tokens_hash
  ON profile_qr_tokens(token_hash);
