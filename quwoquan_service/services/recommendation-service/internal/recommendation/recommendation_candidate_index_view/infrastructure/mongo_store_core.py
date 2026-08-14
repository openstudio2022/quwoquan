"""``MongoCandidateIndexStore`` 组合根：集合装配与索引。

拆分自原 ``mongo_store.py``（行数治理）；生命周期/premium 写入、gathering
写入、受众约束写入与召回读面分别位于 ``mongo_store_lifecycle_writes`` /
``mongo_store_gathering_writes`` / ``mongo_store_audience_writes`` /
``mongo_store_ranking_reads`` 四个 mixin 模块。
"""
from __future__ import annotations

from typing import Any

from pymongo import ASCENDING, DESCENDING

from .mongo_store_audience_writes import MongoCandidateAudienceWriteOps
from .mongo_store_gathering_writes import MongoGatheringCandidateWriteOps
from .mongo_store_lifecycle_writes import MongoCandidateLifecycleWriteOps
from .mongo_store_ranking_reads import MongoCandidateRankingReadOps


class MongoCandidateIndexStore(
    MongoCandidateLifecycleWriteOps,
    MongoGatheringCandidateWriteOps,
    MongoCandidateAudienceWriteOps,
    MongoCandidateRankingReadOps,
):
    """Single owner of candidate, premium, entity-tag and tombstone projections."""

    def __init__(self, database: Any) -> None:
        self._database = database
        self._candidates = database["rm_discovery_feed"]
        self._gathering_candidates = database["rm_gathering_candidates"]
        self._premium = database["rm_premium_pool"]
        self._entity_tags = database["rm_entity_tags"]
        self._tombstones = database["recommendation_candidate_tombstones"]
        self._inbox = database["recommendation_candidate_source_inbox"]
        self._failures = database["recommendation_candidate_source_failures"]
        self._account_restrictions = database[
            "recommendation_candidate_account_restrictions"
        ]
        self._account_restriction_inbox = database[
            "recommendation_candidate_account_restriction_inbox"
        ]
        self._persona_relationships = database[
            "recommendation_candidate_persona_relationships"
        ]
        self._persona_relationship_inbox = database[
            "recommendation_candidate_persona_relationship_inbox"
        ]

    def ensure_indexes(self) -> None:
        self._candidates.create_index(
            [("scenario", ASCENDING), ("contentId", ASCENDING)],
            unique=True,
            name="uq_recommendation_candidate_scenario_content",
        )
        self._candidates.create_index(
            [("scenario", ASCENDING), ("updatedAt", DESCENDING), ("contentId", ASCENDING)],
            name="idx_recommendation_candidate_rank_scan",
        )
        # 热门召回路：按互动量扫描（多路有界召回的 hot lane）。
        self._candidates.create_index(
            [("scenario", ASCENDING), ("likeCount", DESCENDING), ("contentId", ASCENDING)],
            name="idx_recommendation_candidate_hot_scan",
        )
        self._gathering_candidates.create_index(
            [("sourceKey", ASCENDING)],
            unique=True,
            name="uq_recommendation_gathering_candidate_source",
        )
        self._gathering_candidates.create_index(
            [("updatedAt", DESCENDING), ("sourceKey", ASCENDING)],
            name="idx_recommendation_gathering_candidate_rank_scan",
        )
        self._premium.create_index(
            [("scenario", ASCENDING), ("contentId", ASCENDING)],
            unique=True,
            name="uq_recommendation_premium_scenario_content",
        )
        self._entity_tags.create_index(
            [("entityTagId", ASCENDING), ("scenario", ASCENDING), ("contentId", ASCENDING)],
            unique=True,
            name="uq_recommendation_entity_tag_candidate",
        )
        self._tombstones.create_index(
            [("sourceSequence", ASCENDING)],
            name="idx_recommendation_candidate_tombstone_sequence",
        )
        self._failures.create_index(
            [("updatedAt", ASCENDING)],
            name="idx_recommendation_candidate_source_failure_updated",
        )
        self._account_restrictions.create_index(
            [("subjectIds", ASCENDING), ("restricted", ASCENDING)],
            name="idx_recommendation_candidate_restricted_subject",
        )
        self._persona_relationships.create_index(
            [("sourcePersonaId", ASCENDING), ("targetPersonaId", ASCENDING)],
            unique=True,
            name="uq_recommendation_candidate_persona_relationship_direction",
        )
        self._persona_relationships.create_index(
            [
                ("sourcePersonaId", ASCENDING),
                ("following", ASCENDING),
                ("blocked", ASCENDING),
                ("targetPersonaId", ASCENDING),
            ],
            name="idx_recommendation_candidate_following_subject",
        )
