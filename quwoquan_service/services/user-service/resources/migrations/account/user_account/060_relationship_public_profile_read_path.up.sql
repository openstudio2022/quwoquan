-- 粉丝/关注列表的规范化公开资料索引。关系图只与该公开索引 join；私密、
-- strict、退役 Persona 不进入候选集，搜索与可见性都不再由应用层 substring
-- overfetch/fill 实现。
CREATE TABLE IF NOT EXISTS persona_public_profile_search (
    persona_id VARCHAR(96) PRIMARY KEY REFERENCES personas(persona_id) ON DELETE CASCADE,
    display_name VARCHAR(64) NOT NULL,
    user_handle VARCHAR(64) NOT NULL,
    search_document TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_persona_public_profile_search_document
    ON persona_public_profile_search USING GIN (search_document gin_trgm_ops);

CREATE OR REPLACE FUNCTION refresh_persona_public_profile_search()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF COALESCE(NEW.status, 'active') = 'retired'
       OR COALESCE(NEW.is_private, FALSE)
       OR COALESCE(NEW.isolation_level, 'open') = 'strict' THEN
        DELETE FROM persona_public_profile_search WHERE persona_id = NEW.persona_id;
        RETURN NEW;
    END IF;
    INSERT INTO persona_public_profile_search (
        persona_id, display_name, user_handle, search_document, updated_at
    ) VALUES (
        NEW.persona_id,
        COALESCE(NULLIF(BTRIM(NEW.display_name), ''), NEW.persona_id),
        COALESCE(NULLIF(BTRIM(NEW.user_handle), ''), NEW.persona_id),
        LOWER(CONCAT_WS(' ', NEW.persona_id, NEW.display_name, NEW.user_handle)),
        NEW.updated_at
    )
    ON CONFLICT (persona_id) DO UPDATE SET
        display_name = EXCLUDED.display_name,
        user_handle = EXCLUDED.user_handle,
        search_document = EXCLUDED.search_document,
        updated_at = EXCLUDED.updated_at;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_refresh_persona_public_profile_search ON personas;
CREATE TRIGGER trg_refresh_persona_public_profile_search
AFTER INSERT OR UPDATE OF display_name, user_handle, is_private, isolation_level, status, updated_at
ON personas FOR EACH ROW EXECUTE FUNCTION refresh_persona_public_profile_search();

INSERT INTO persona_public_profile_search (
    persona_id, display_name, user_handle, search_document, updated_at
)
SELECT persona_id,
       COALESCE(NULLIF(BTRIM(display_name), ''), persona_id),
       COALESCE(NULLIF(BTRIM(user_handle), ''), persona_id),
       LOWER(CONCAT_WS(' ', persona_id, display_name, user_handle)),
       updated_at
FROM personas
WHERE COALESCE(status, 'active') <> 'retired'
  AND NOT COALESCE(is_private, FALSE)
  AND COALESCE(isolation_level, 'open') <> 'strict'
ON CONFLICT (persona_id) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    user_handle = EXCLUDED.user_handle,
    search_document = EXCLUDED.search_document,
    updated_at = EXCLUDED.updated_at;
