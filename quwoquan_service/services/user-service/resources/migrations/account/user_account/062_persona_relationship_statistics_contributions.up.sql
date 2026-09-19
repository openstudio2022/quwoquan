-- PersonaRelationship persona-owned current-contribution ledger and fixed
-- buckets. Normal projection and rollup never COUNT relationship edges and do
-- not mutate user_profiles/profile edit timestamps.

CREATE TABLE IF NOT EXISTS persona_relationship_statistics_inbox (
    event_id             VARCHAR(128) PRIMARY KEY,
    pair_id              VARCHAR(64) NOT NULL,
    aggregate_version    BIGINT NOT NULL CHECK (aggregate_version >= 1),
    payload_digest       VARCHAR(64) NOT NULL,
    applied_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS persona_relationship_statistics_members (
    member_id                VARCHAR(256) PRIMARY KEY,
    pair_id                  VARCHAR(64) NOT NULL,
    persona_id               VARCHAR(96) NOT NULL,
    contribution_kind        VARCHAR(16) NOT NULL CHECK (contribution_kind IN ('follower','following')),
    bucket                   INTEGER NOT NULL CHECK (bucket >= 0 AND bucket < 64),
    last_applied_version     BIGINT NOT NULL CHECK (last_applied_version >= 1),
    current_contribution     BIGINT NOT NULL CHECK (current_contribution IN (0,1)),
    payload_digest           VARCHAR(64) NOT NULL,
    source_event_id          VARCHAR(128) NOT NULL,
    updated_at               TIMESTAMPTZ NOT NULL,
    UNIQUE (pair_id, persona_id, contribution_kind)
);

CREATE INDEX IF NOT EXISTS idx_persona_relationship_statistics_member_persona
    ON persona_relationship_statistics_members (persona_id, contribution_kind, bucket);

CREATE TABLE IF NOT EXISTS persona_relationship_statistics_buckets (
    generation          VARCHAR(64) NOT NULL,
    persona_id          VARCHAR(96) NOT NULL,
    contribution_kind   VARCHAR(16) NOT NULL CHECK (contribution_kind IN ('follower','following')),
    bucket              INTEGER NOT NULL CHECK (bucket >= 0 AND bucket < 64),
    value               BIGINT NOT NULL CHECK (value >= 0),
    max_source_version  BIGINT NOT NULL CHECK (max_source_version >= 0),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (generation, persona_id, contribution_kind, bucket)
);

CREATE TABLE IF NOT EXISTS persona_relationship_statistics_rollups (
    generation          VARCHAR(64) NOT NULL,
    persona_id          VARCHAR(96) NOT NULL,
    stats_version       BIGINT NOT NULL CHECK (stats_version >= 0),
    follower_count      BIGINT NOT NULL CHECK (follower_count >= 0),
    following_count     BIGINT NOT NULL CHECK (following_count >= 0),
    source_checkpoint   VARCHAR(128) NOT NULL,
    as_of               TIMESTAMPTZ NOT NULL,
    expires_at          TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (generation, persona_id)
);

CREATE TABLE IF NOT EXISTS persona_relationship_statistics_reader_generation (
    id                  VARCHAR(16) PRIMARY KEY,
    generation          VARCHAR(64) NOT NULL,
    source_checkpoint   VARCHAR(128) NOT NULL,
    published_at        TIMESTAMPTZ NOT NULL
);

-- Old rows were projected into owner profile counters by a retired path. They
-- are not interpreted as ledger events; current statistics become available
-- after source outbox replay or an explicit repair/import generation.
DROP INDEX IF EXISTS idx_persona_relationship_counter_projection_pending;
