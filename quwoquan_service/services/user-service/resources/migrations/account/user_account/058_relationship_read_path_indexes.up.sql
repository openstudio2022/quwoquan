-- 关注/粉丝分页读的覆盖索引。
-- 既有索引以 (persona, following, followed_at DESC) 建立，但翻页游标是
-- (followed_at, pair_id) 二元组，且列表还要回表取 pair_id：分页因此既要
-- 额外排序键又要回表。这里改为只覆盖 following=TRUE 行的 partial 索引，
-- 并把 pair_id 纳入键，使同一次扫描即可满足过滤、排序与游标比较。

CREATE INDEX IF NOT EXISTS idx_persona_relationship_following_page
    ON persona_relationship_directions (
        source_persona_id, followed_at DESC, pair_id DESC
    )
    INCLUDE (target_persona_id, following, blocked, follow_source, blocked_at, updated_at)
    WHERE following = TRUE;

CREATE INDEX IF NOT EXISTS idx_persona_relationship_followers_page
    ON persona_relationship_directions (
        target_persona_id, followed_at DESC, pair_id DESC
    )
    INCLUDE (source_persona_id, following, blocked, follow_source, blocked_at, updated_at)
    WHERE following = TRUE;

CREATE INDEX IF NOT EXISTS idx_persona_relationship_blocked_page
    ON persona_relationship_directions (
        source_persona_id, blocked_at DESC, pair_id DESC
    )
    INCLUDE (target_persona_id, following, blocked, follow_source, followed_at, updated_at)
    WHERE blocked = TRUE;

-- 一次批量读取某 viewer 与一组 target 的全部方向：列表每页只需一次边查询，
-- 不再为每个条目分别查 relation 与两个方向的 block。
CREATE INDEX IF NOT EXISTS idx_persona_relationship_direction_endpoints
    ON persona_relationship_directions (source_persona_id, target_persona_id)
    INCLUDE (pair_id, following, blocked, follow_source, followed_at, blocked_at, updated_at);

-- 退役被上面三个 partial 覆盖索引取代的旧索引。
-- 旧索引只把 followed_at/blocked_at 作为前缀，游标的 pair_id 仍需额外排序；
-- 两套索引同时存在只会让每次 follow/unfollow 多付一份写放大，而不会让任何
-- 查询更快。单轨保留新索引，不做双轨并存。
DROP INDEX IF EXISTS idx_persona_relationship_following;
DROP INDEX IF EXISTS idx_persona_relationship_followers;
DROP INDEX IF EXISTS idx_persona_relationship_blocked;
