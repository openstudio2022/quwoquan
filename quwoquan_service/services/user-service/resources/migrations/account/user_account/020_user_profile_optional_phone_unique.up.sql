ALTER TABLE user_profiles
  DROP CONSTRAINT IF EXISTS user_profiles_phone_key;

CREATE UNIQUE INDEX IF NOT EXISTS uq_user_profiles_non_empty_phone
  ON user_profiles(phone)
  WHERE phone IS NOT NULL AND phone <> '';
