-- UserAccount 生命周期只认 account_state；status/UserStatus 是已退役的第二真相源。
DROP INDEX IF EXISTS idx_user_profiles_status;

ALTER TABLE user_profiles
    DROP COLUMN IF EXISTS status;
