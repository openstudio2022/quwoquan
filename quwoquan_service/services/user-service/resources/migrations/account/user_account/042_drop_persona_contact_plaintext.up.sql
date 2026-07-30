-- Persona 不是登录凭证 owner；手机号与邮箱只保存在 CredentialBinding。
-- 本迁移是单轨切换，不保留旧列或双读兼容。
ALTER TABLE personas DROP COLUMN IF EXISTS phone;
ALTER TABLE personas DROP COLUMN IF EXISTS email;
