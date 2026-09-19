-- Persona 命令 receipt 按 owner 隔离。
-- 同一 Idempotency-Key 在两个 owner 下是两条独立命令：跨 owner 不得回放对方
-- 结果，也不得返回对方的 Persona。原先 idempotency_key 全局唯一会让第二个
-- owner 的首次创建被误判为重放。

ALTER TABLE personas_command_receipts
    ADD COLUMN IF NOT EXISTS owner_id VARCHAR(96) NOT NULL DEFAULT '';

-- 既有 receipt 的 owner 从权威 Persona 行反解；Persona 已退役删除的孤儿
-- receipt 保持空 owner，不猜测归属。
UPDATE personas_command_receipts AS receipts
SET owner_id = personas.user_id
FROM personas
WHERE receipts.aggregate_id = personas.persona_id
  AND receipts.owner_id = '';

ALTER TABLE personas_command_receipts
    DROP CONSTRAINT IF EXISTS personas_command_receipts_idempotency_key_key;

CREATE UNIQUE INDEX IF NOT EXISTS uq_personas_command_receipt_owner_key
    ON personas_command_receipts (owner_id, idempotency_key);
