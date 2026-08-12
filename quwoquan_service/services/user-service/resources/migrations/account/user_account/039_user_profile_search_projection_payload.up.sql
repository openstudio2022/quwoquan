-- user_profile_search_outbox is an object-owned custom relay table excluded
-- from codegen.tables. Persist the exact public snapshot so replay never reads
-- a later Persona version and User never writes the Search provider directly.
ALTER TABLE user_profile_search_outbox
    ADD COLUMN IF NOT EXISTS payload_json JSONB;

-- 已发布的旧记录不会再被 relay claim。用显式 JSON null 标记其历史 payload
-- 不可恢复，既保留审计行，也避免从当前 Persona 反推、伪造旧版本快照。
UPDATE user_profile_search_outbox
SET payload_json = 'null'::JSONB
WHERE payload_json IS NULL
  AND published_at IS NOT NULL;

-- 仍待发布的旧记录必须携带当时的不可变快照；缺失时无法安全重放，继续
-- fail closed，禁止退化为读取当前 Persona 或跳过事件。
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM user_profile_search_outbox
        WHERE payload_json IS NULL
    ) THEN
        RAISE EXCEPTION 'USER.PROFILE_SEARCH.LEGACY_PAYLOAD_MISSING';
    END IF;
END
$$;

ALTER TABLE user_profile_search_outbox
    ALTER COLUMN payload_json SET NOT NULL;
