-- 主动关注人数由系统限额精确裁决。
-- 之前没有任何限额事实：并发关注可以无界增长，命令路径也只能靠全表 COUNT
-- 才能知道当前占用。这里引入两张表：
--   1. 生效政策快照：配置发布的执行物化，不是第二 authoring；
--   2. source 侧精确占用：与关系边在同一事务内增减。

CREATE TABLE IF NOT EXISTS relationship_policy_activation (
    policy_id                VARCHAR(64) PRIMARY KEY,
    revision                 BIGINT NOT NULL,
    max_following_per_persona INTEGER NOT NULL,
    config_digest            VARCHAR(64) NOT NULL,
    activated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_relationship_policy_revision CHECK (revision >= 1),
    CONSTRAINT ck_relationship_policy_limit CHECK (max_following_per_persona >= 1)
);

-- 初始生效政策：单 persona 主动关注上限 1000；升档到 10000 只是同一政策的
-- 新 revision，不改表结构，也不改既有关系。
INSERT INTO relationship_policy_activation (
    policy_id, revision, max_following_per_persona, config_digest
) VALUES ('persona_following', 1, 1000, '')
ON CONFLICT (policy_id) DO NOTHING;

CREATE TABLE IF NOT EXISTS persona_follow_quota (
    source_persona_id  VARCHAR(96) PRIMARY KEY,
    following_count    INTEGER NOT NULL DEFAULT 0,
    policy_revision    BIGINT NOT NULL DEFAULT 1,
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_persona_follow_quota_nonnegative CHECK (following_count >= 0)
);

-- 存量出边一次性回填：按权威 direction 表统计，之后只做条件增减。
INSERT INTO persona_follow_quota (source_persona_id, following_count)
SELECT source_persona_id, COUNT(*)
FROM persona_relationship_directions
WHERE following = TRUE
GROUP BY source_persona_id
ON CONFLICT (source_persona_id) DO UPDATE
SET following_count = EXCLUDED.following_count,
    updated_at = NOW();
