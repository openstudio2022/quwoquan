ALTER TABLE user_settings
ADD COLUMN IF NOT EXISTS blocked_keywords TEXT[] DEFAULT '{}'::TEXT[];
