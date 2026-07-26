-- B3 批次删除决策（2026-07-19）：invite_record 对象彻底删除；user_work /
-- user_life_item 投影 deferred（无 UI 消费方，公开 route 已删）。
-- personas.invite_count 是 invite 链的冗余计数，随对象一并删除。

DROP TABLE IF EXISTS invite_records;
DROP TABLE IF EXISTS user_works;
DROP TABLE IF EXISTS user_life_items;
ALTER TABLE personas DROP COLUMN IF EXISTS invite_count;
