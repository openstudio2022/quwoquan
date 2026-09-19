-- 关系命令的历史结果与到期终结共用同一条 receipt 行。
-- 在此之前 receipt 只保存「已提交」的响应：原写与到期终结无法在同一仲裁中
-- 竞争，客户端也无法区分「确定未执行」与「历史不可判定」。

ALTER TABLE persona_relationship_command_receipts
    ADD COLUMN IF NOT EXISTS outcome VARCHAR(32) NOT NULL DEFAULT 'committed',
    ADD COLUMN IF NOT EXISTS command_digest VARCHAR(64) NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS basis_digest VARCHAR(64) NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS accept_until TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS finalized_at TIMESTAMPTZ;

-- 终结为「未执行」的命令没有对应 Pair，也不应为此建一行空关系。
ALTER TABLE persona_relationship_command_receipts
    ALTER COLUMN pair_id DROP NOT NULL;

ALTER TABLE persona_relationship_command_receipts
    DROP CONSTRAINT IF EXISTS ck_persona_relationship_receipt_outcome;
ALTER TABLE persona_relationship_command_receipts
    ADD CONSTRAINT ck_persona_relationship_receipt_outcome
    CHECK (outcome IN ('committed', 'rejected', 'expired'));

-- committed 必须落在某个 Pair 上；expired/rejected 不得携带 Pair 结果。
ALTER TABLE persona_relationship_command_receipts
    DROP CONSTRAINT IF EXISTS ck_persona_relationship_receipt_pair_presence;
ALTER TABLE persona_relationship_command_receipts
    ADD CONSTRAINT ck_persona_relationship_receipt_pair_presence
    CHECK ((outcome = 'committed') = (pair_id IS NOT NULL));

-- 既有 receipt 的保留期从创建时间推算：接受窗 72h 加恢复余量后的下限 96h。
UPDATE persona_relationship_command_receipts
SET accept_until = created_at + INTERVAL '72 hours',
    expires_at = created_at + INTERVAL '96 hours'
WHERE accept_until IS NULL;

CREATE INDEX IF NOT EXISTS idx_persona_relationship_receipt_expiry
    ON persona_relationship_command_receipts (expires_at)
    WHERE expires_at IS NOT NULL;

-- Direction 的两个端点必须属于同一个 canonical Pair。
-- 摘要碰撞或调用方拼错身份时，数据库直接拒绝第三端点，而不是把方向写到
-- 另一对真实身份上。
CREATE OR REPLACE FUNCTION require_persona_relationship_pair_membership()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    pair_lower TEXT;
    pair_upper TEXT;
BEGIN
    SELECT lower_persona_id, upper_persona_id
    INTO pair_lower, pair_upper
    FROM persona_relationships
    WHERE pair_id = NEW.pair_id;

    IF pair_lower IS NULL THEN
        RAISE EXCEPTION 'persona relationship direction references an unknown pair %', NEW.pair_id;
    END IF;
    IF NEW.source_persona_id = NEW.target_persona_id THEN
        RAISE EXCEPTION 'persona relationship direction cannot be reflexive';
    END IF;
    IF NEW.source_persona_id NOT IN (pair_lower, pair_upper)
       OR NEW.target_persona_id NOT IN (pair_lower, pair_upper) THEN
        RAISE EXCEPTION 'persona relationship direction endpoint does not belong to pair %', NEW.pair_id;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS require_persona_relationship_pair_membership_trigger
    ON persona_relationship_directions;
CREATE TRIGGER require_persona_relationship_pair_membership_trigger
    BEFORE INSERT OR UPDATE ON persona_relationship_directions
    FOR EACH ROW
    EXECUTE FUNCTION require_persona_relationship_pair_membership();
