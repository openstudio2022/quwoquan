-- Align user_profiles media asset id columns with personas VARCHAR(96).
-- Commercial creator avatar assetIds (creator-avatar-<id>-<hash>) exceed VARCHAR(64).
ALTER TABLE user_profiles
  ALTER COLUMN avatar_asset_id TYPE VARCHAR(96),
  ALTER COLUMN background_asset_id TYPE VARCHAR(96);
