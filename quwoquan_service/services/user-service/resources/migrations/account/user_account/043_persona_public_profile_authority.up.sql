-- Persona 是公开资料唯一写模型；user_profiles 仅保留可重放读投影。
ALTER TABLE personas
    ADD COLUMN IF NOT EXISTS nickname_customized BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS identity_tags TEXT[] NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS taxonomy_release_id VARCHAR(128) NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS gender VARCHAR(16) NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS birth_date DATE,
    ADD COLUMN IF NOT EXISTS region VARCHAR(128) NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS region_tag_ref TEXT NOT NULL DEFAULT '';

-- 一次性把旧 owner 资料基线迁入 Persona。profile_projected_at 同时充当
-- cutover marker，避免迁移脚本重放时用只读投影反向覆盖新的权威状态。
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'personas_outbox'
          AND column_name = 'profile_projected_at'
    ) THEN
        UPDATE personas AS persona
        SET nickname_customized = profile.nickname_customized,
            avatar_media_asset_id = CASE
                WHEN persona.avatar_media_asset_id = '' THEN COALESCE(profile.avatar_asset_id, '')
                ELSE persona.avatar_media_asset_id
            END,
            background_media_asset_id = CASE
                WHEN persona.background_media_asset_id = '' THEN COALESCE(profile.background_asset_id, '')
                ELSE persona.background_media_asset_id
            END,
            bio = CASE WHEN persona.bio = '' THEN COALESCE(profile.bio, '') ELSE persona.bio END,
            identity_tags = CASE
                WHEN COALESCE(profile.identity_tags, '') = '' THEN '{}'::text[]
                ELSE profile.identity_tags::text[]
            END,
            gender = COALESCE(profile.gender, ''),
            birth_date = profile.birth_date,
            region = COALESCE(profile.region, ''),
            region_tag_ref = COALESCE(profile.region_code, ''),
            inherits_profile_from_owner = false,
            updated_at = GREATEST(persona.updated_at, profile.updated_at)
        FROM user_profiles AS profile
        WHERE persona.user_id = profile.user_id
          AND persona.status <> 'retired';
    END IF;
END $$;

ALTER TABLE personas_outbox
    ADD COLUMN IF NOT EXISTS profile_projected_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_personas_outbox_profile_projection
    ON personas_outbox (occurred_at, event_id)
    WHERE profile_projected_at IS NULL
      AND event_type IN ('PersonaCreated', 'PersonaUpdated', 'PersonaRetired', 'PersonaActivated');
