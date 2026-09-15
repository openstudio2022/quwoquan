-- 仅供受管停写迁移执行；本增量不对业务库运行。
-- 不为旧Data条目伪造审批：存在任何历史条目时先由owner审计并重新准入。
BEGIN;
LOCK TABLE premium_pool_entries IN ACCESS EXCLUSIVE MODE;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM premium_pool_entries) THEN
    RAISE EXCEPTION 'GATE_BLOCK: nonempty premium pool requires exact owner admission migration; no default/backfill permitted';
  END IF;
END $$;
ALTER TABLE premium_pool_entries ADD COLUMN IF NOT EXISTS release_admissions JSONB;
ALTER TABLE premium_pool_entries ALTER COLUMN release_admissions SET NOT NULL;
COMMIT;
