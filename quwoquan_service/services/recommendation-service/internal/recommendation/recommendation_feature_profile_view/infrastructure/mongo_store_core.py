"""``MongoFeatureProfileStore`` 组合根：集合装配、索引、打分读面与作者影响力读面。

拆分自原 ``mongo_store.py``（行数治理）；交集写入 / 交集读面 / 画像写入
分别位于 ``mongo_store_intersection_writes`` / ``mongo_store_intersection_reads``
/ ``mongo_store_profile_writes`` 三个 mixin 模块。
"""
from __future__ import annotations

from datetime import datetime, timezone
import base64
import json
from typing import Any

from pymongo import ASCENDING, DESCENDING

from ..application.author_impact_reader import (
    AuthorImpactEvidence,
    AuthorImpactEvidencePage,
    AuthorImpactItem,
    AuthorImpactSummary,
)
from .mongo_store_intersection_reads import MongoIntersectionReadOps
from .mongo_store_intersection_writes import MongoIntersectionWriteOps
from .mongo_store_profile_writes import MongoFeatureProfileWriteOps


class MongoFeatureProfileStore(
    MongoIntersectionReadOps,
    MongoIntersectionWriteOps,
    MongoFeatureProfileWriteOps,
):
    """Single owner of the long-lived recommendation feature profile."""

    def __init__(self, database: Any) -> None:
        self._profiles = database["rm_recommend_feature"]
        self._author_impact = database["rm_author_impact"]
        self._author_impact_evidence = database["rm_author_impact_evidence"]
        self._collaborative_i2i = database["rm_collaborative_i2i"]
        self._collaborative_u2i = database["rm_collaborative_u2i"]
        self._intersection_features = database["rm_intersection_feature"]
        self._intersection_reasons = database["rm_viewer_object_intersection"]
        self._intersection_supply = database["rm_intersection_supply"]
        self._intersection_inbox = database[
            "recommendation_intersection_projection_inbox"
        ]
        self._intersection_relationships = database[
            "recommendation_intersection_persona_relationships"
        ]
        self._intersection_memberships = database[
            "recommendation_intersection_circle_memberships"
        ]
        self._intersection_behaviors = database[
            "recommendation_intersection_behaviors"
        ]
        self._intersection_wishlist = database[
            "recommendation_intersection_wishlist_state"
        ]
        self._intersection_persona_profiles = database[
            "recommendation_intersection_persona_profiles"
        ]
        self._intersection_declared_visits = database[
            "recommendation_intersection_declared_visits"
        ]
        self._intersection_gathering_participations = database[
            "recommendation_intersection_gathering_participations"
        ]
        self._intersection_gathering_recaps = database[
            "recommendation_intersection_gathering_recaps"
        ]
        self._intersection_gathering_publications = database[
            "recommendation_intersection_gathering_publications"
        ]
        self._intersection_post_authors = database[
            "recommendation_intersection_post_authors"
        ]
        self._intersection_facilitations = database[
            "recommendation_intersection_facilitations"
        ]
        self._checkpoints = database["recommendation_feature_projection_checkpoints"]
        self._failures = database["recommendation_feature_projection_failures"]

    def ensure_indexes(self) -> None:
        self._profiles.create_index(
            [("subjectId", ASCENDING)],
            unique=True,
            name="uq_recommendation_feature_subject",
        )
        self._author_impact.create_index(
            [("authorId", ASCENDING), ("impactId", ASCENDING)],
            unique=True,
            name="uq_recommendation_author_impact",
        )
        self._author_impact.create_index(
            [("authorId", ASCENDING), ("count", DESCENDING), ("updatedAt", DESCENDING)],
            name="idx_recommendation_author_impact_rank",
        )
        self._author_impact_evidence.create_index(
            [("eventId", ASCENDING), ("authorId", ASCENDING), ("impactId", ASCENDING)],
            unique=True,
            name="uq_recommendation_author_impact_evidence",
        )
        self._author_impact_evidence.create_index(
            [
                ("authorId", ASCENDING),
                ("impactId", ASCENDING),
                ("occurredAt", DESCENDING),
                ("_id", DESCENDING),
            ],
            name="idx_recommendation_author_impact_evidence_page",
        )
        self._collaborative_i2i.create_index(
            [("leftContentId", ASCENDING), ("rightContentId", ASCENDING)],
            unique=True,
            name="uq_recommendation_collaborative_i2i_pair",
        )
        self._collaborative_u2i.create_index(
            [("subjectId", ASCENDING), ("contentId", ASCENDING)],
            unique=True,
            name="uq_recommendation_collaborative_u2i_pair",
        )
        self._collaborative_u2i.create_index(
            [("subjectId", ASCENDING), ("score", DESCENDING), ("updatedAt", DESCENDING)],
            name="idx_recommendation_collaborative_u2i_subject_score",
        )
        self._intersection_features.create_index(
            [("subjectId", ASCENDING), ("feature", ASCENDING)],
            unique=True,
            name="uq_recommendation_intersection_subject_feature",
        )
        self._intersection_reasons.create_index(
            [("subjectId", ASCENDING), ("scopeKind", ASCENDING), ("scopeKey", ASCENDING)],
            unique=True,
            name="uq_recommendation_intersection_subject_scope",
        )
        self._intersection_reasons.create_index(
            [("generatedAt", DESCENDING)],
            name="idx_recommendation_intersection_generated",
        )
        self._intersection_supply.create_index(
            [("supplyKey", ASCENDING)],
            unique=True,
            name="uq_recommendation_intersection_supply_key",
        )
        self._intersection_inbox.create_index(
            [("sourceEventId", ASCENDING), ("scopeKind", ASCENDING)],
            name="idx_recommendation_intersection_projection_source",
        )
        self._intersection_relationships.create_index(
            [("sourcePersonaId", ASCENDING), ("following", ASCENDING), ("targetPersonaId", ASCENDING)],
            name="idx_recommendation_intersection_following",
        )
        self._intersection_relationships.create_index(
            [("targetPersonaId", ASCENDING), ("following", ASCENDING), ("sourcePersonaId", ASCENDING)],
            name="idx_recommendation_intersection_followers",
        )
        self._intersection_memberships.create_index(
            [("personaId", ASCENDING), ("active", ASCENDING), ("circleId", ASCENDING)],
            name="idx_recommendation_intersection_membership_persona",
        )
        self._intersection_memberships.create_index(
            [("circleId", ASCENDING), ("active", ASCENDING), ("personaId", ASCENDING)],
            name="idx_recommendation_intersection_membership_circle",
        )
        self._intersection_behaviors.create_index(
            [("subjectId", ASCENDING), ("occurredAt", DESCENDING), ("_id", DESCENDING)],
            name="idx_recommendation_intersection_behavior_subject",
        )
        self._intersection_behaviors.create_index(
            [("action", ASCENDING), ("entityRefs", ASCENDING)],
            name="idx_recommendation_intersection_behavior_entity",
        )
        self._intersection_wishlist.create_index(
            [("active", ASCENDING), ("entityId", ASCENDING)],
            name="idx_recommendation_intersection_wishlist_active",
        )
        self._intersection_declared_visits.create_index(
            [("active", ASCENDING), ("entityId", ASCENDING)],
            name="idx_recommendation_intersection_declared_visit_active",
        )
        self._intersection_persona_profiles.create_index(
            [("personaId", ASCENDING), ("occurredAt", DESCENDING), ("_id", DESCENDING)],
            name="idx_recommendation_intersection_persona_profile_latest",
        )
        self._intersection_gathering_participations.create_index(
            [("personaId", ASCENDING), ("active", ASCENDING), ("gatheringId", ASCENDING)],
            name="idx_recommendation_intersection_gathering_participation_persona",
        )
        self._intersection_gathering_participations.create_index(
            [("gatheringId", ASCENDING), ("active", ASCENDING), ("personaId", ASCENDING)],
            name="idx_recommendation_intersection_gathering_participation_gathering",
        )
        self._intersection_gathering_recaps.create_index(
            [("personaId", ASCENDING), ("active", ASCENDING), ("gatheringId", ASCENDING)],
            name="idx_recommendation_intersection_gathering_recap_persona",
        )
        self._intersection_gathering_publications.create_index(
            [("organizerId", ASCENDING), ("occurredAt", DESCENDING)],
            name="idx_recommendation_intersection_publication_organizer",
        )
        self._intersection_gathering_publications.create_index(
            [("sourceRefs.objectId", ASCENDING)],
            name="idx_recommendation_intersection_publication_source",
        )
        self._intersection_post_authors.create_index(
            [("authorId", ASCENDING), ("active", ASCENDING)],
            name="idx_recommendation_intersection_post_author",
        )
        self._intersection_facilitations.create_index(
            [("occurredAt", DESCENDING)],
            name="idx_recommendation_intersection_facilitation_occurred",
        )
        self._checkpoints.create_index(
            [("subjectId", ASCENDING), ("appliedAt", DESCENDING)],
            name="idx_recommendation_feature_checkpoint_subject",
        )
        self._failures.create_index(
            [("updatedAt", DESCENDING)],
            name="idx_recommendation_feature_failure_updated",
        )

    def record_source_failure(
        self,
        stream_id: str,
        event_id: str,
        cause: Exception,
    ) -> int:
        normalized_stream_id = stream_id.strip()
        if not normalized_stream_id:
            raise ValueError("feature projection failure streamId is required")
        self._failures.update_one(
            {"_id": normalized_stream_id},
            {
                "$set": {
                    "eventId": event_id.strip(),
                    "error": str(cause)[:1024],
                    "updatedAt": datetime.now(timezone.utc),
                },
                "$inc": {"attempts": 1},
            },
            upsert=True,
        )
        document = self._failures.find_one(
            {"_id": normalized_stream_id},
            {"attempts": 1},
        ) or {}
        return int(document.get("attempts") or 0)

    def clear_source_failure(self, stream_id: str) -> None:
        self._failures.delete_one({"_id": stream_id.strip()})

    def read_for_scoring(self, subject_id: str) -> dict[str, Any]:
        document = self._profiles.find_one({"_id": subject_id.strip()})
        if document is None:
            return {
                "checkpoint": 0,
                "sparseFeatures": {},
                "tagAffinities": {},
                "searchTermAffinities": {},
                "influenceScore": 0.0,
                "collaborativeFeatures": {},
                "intersectionFeatures": {},
                "negativeContentIds": [],
                "hiddenAuthorIds": [],
                "hiddenContentTypes": [],
            }
        sparse = dict(document.get("sparseFeatures") or {})
        return {
            "checkpoint": int(document.get("checkpoint", 0)),
            "sparseFeatures": sparse,
            "tagAffinities": dict(document.get("tagAffinities") or {}),
            # 搜推联动短期意图：存储为有界列表，打分侧压平为 term → weight。
            "searchTermAffinities": {
                str(entry.get("term")): float(entry.get("weight") or 0.0)
                for entry in (document.get("searchTermAffinities") or [])
                if str((entry or {}).get("term") or "").strip()
            },
            "influenceScore": float(document.get("influenceScore", 0.0)),
            "collaborativeFeatures": dict(document.get("collaborativeFeatures") or {}),
            "intersectionFeatures": dict(document.get("intersectionFeatures") or {}),
            "negativeContentIds": list(document.get("negativeContentIds") or []),
            "hiddenAuthorIds": list(document.get("hiddenAuthorIds") or []),
            "hiddenContentTypes": list(document.get("hiddenContentTypes") or []),
        }

    def read_author_impact(self, author_id: str, limit: int) -> AuthorImpactSummary:
        normalized = author_id.strip()
        if not normalized or limit < 1 or limit > 50:
            raise ValueError("author impact query is invalid")
        documents = list(
            self._author_impact.find({"authorId": normalized})
            .sort([("count", DESCENDING), ("updatedAt", DESCENDING), ("_id", ASCENDING)])
            .limit(limit)
        )
        total_rows = list(
            self._author_impact.aggregate(
                [
                    {"$match": {"authorId": normalized}},
                    {"$group": {"_id": None, "total": {"$sum": "$count"}}},
                ]
            )
        )
        total = int(total_rows[0].get("total") or 0) if total_rows else 0
        return AuthorImpactSummary(
            author_id=normalized,
            total=total,
            items=tuple(
                AuthorImpactItem(
                    impact_id=str(document.get("impactId") or ""),
                    help_type=str(document.get("helpType") or ""),
                    action=str(document.get("action") or ""),
                    intersection_dimension=str(
                        document.get("intersectionDimension") or ""
                    ),
                    tag_ref=str(document.get("tagRef") or ""),
                    source=str(document.get("source") or ""),
                    count=int(document.get("count") or 0),
                    updated_at=self._utc_datetime(document.get("updatedAt")),
                    representative_content_id=str(
                        document.get("representativeContentId") or ""
                    ),
                )
                for document in documents
            ),
        )

    def read_author_impact_evidence(
        self,
        author_id: str,
        impact_id: str,
        cursor: str | None,
        limit: int,
    ) -> AuthorImpactEvidencePage:
        normalized_author = author_id.strip()
        normalized_impact = impact_id.strip()
        if not normalized_author or not normalized_impact or limit < 1 or limit > 50:
            raise ValueError("author impact evidence query is invalid")
        query: dict[str, Any] = {
            "authorId": normalized_author,
            "impactId": normalized_impact,
        }
        if cursor:
            occurred_at, evidence_id = self._decode_impact_cursor(cursor)
            query["$or"] = [
                {"occurredAt": {"$lt": occurred_at}},
                {"occurredAt": occurred_at, "_id": {"$lt": evidence_id}},
            ]
        documents = list(
            self._author_impact_evidence.find(query)
            .sort([("occurredAt", DESCENDING), ("_id", DESCENDING)])
            .limit(limit + 1)
        )
        has_more = len(documents) > limit
        page_documents = documents[:limit]
        next_cursor = None
        if has_more and page_documents:
            tail = page_documents[-1]
            next_cursor = self._encode_impact_cursor(
                self._utc_datetime(tail.get("occurredAt")),
                str(tail.get("_id") or ""),
            )
        total = self._author_impact_evidence.count_documents(
            {"authorId": normalized_author, "impactId": normalized_impact}
        )
        return AuthorImpactEvidencePage(
            impact_id=normalized_impact,
            total_count=int(total),
            items=tuple(
                AuthorImpactEvidence(
                    evidence_id=str(document.get("_id") or ""),
                    impact_id=str(document.get("impactId") or ""),
                    content_id=str(document.get("contentId") or ""),
                    content_type=str(document.get("contentType") or ""),
                    help_type=str(document.get("helpType") or ""),
                    action=str(document.get("action") or ""),
                    intersection_dimension=str(
                        document.get("intersectionDimension") or ""
                    ),
                    occurred_at=self._utc_datetime(document.get("occurredAt")),
                )
                for document in page_documents
            ),
            next_cursor=next_cursor,
            has_more=has_more,
        )

    @staticmethod
    def _utc_datetime(value: Any) -> datetime:
        if not isinstance(value, datetime):
            raise ValueError("author impact projection timestamp is invalid")
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _encode_impact_cursor(occurred_at: datetime, evidence_id: str) -> str:
        payload = json.dumps(
            {
                "occurredAt": occurred_at.astimezone(timezone.utc).isoformat(),
                "evidenceId": evidence_id,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")

    @staticmethod
    def _decode_impact_cursor(cursor: str) -> tuple[datetime, str]:
        try:
            padded = cursor + "=" * (-len(cursor) % 4)
            raw = base64.urlsafe_b64decode(padded.encode("ascii"))
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict) or set(payload) != {
                "occurredAt",
                "evidenceId",
            }:
                raise ValueError
            occurred_at = datetime.fromisoformat(str(payload["occurredAt"]))
            if occurred_at.tzinfo is None:
                raise ValueError
            evidence_id = str(payload["evidenceId"]).strip()
            if not evidence_id:
                raise ValueError
            return occurred_at.astimezone(timezone.utc), evidence_id
        except Exception as error:
            raise ValueError("author impact cursor is invalid") from error

    def erase_subject(self, subject_id: str) -> int:
        normalized = subject_id.strip()
        if not normalized:
            raise ValueError("subjectId is required")
        selectors = (
            (self._profiles, {"$or": [{"_id": normalized}, {"subjectId": normalized}, {"userId": normalized}]}),
            (self._author_impact, {"authorId": normalized}),
            (
                self._author_impact_evidence,
                {"$or": [{"authorId": normalized}, {"subjectId": normalized}, {"userId": normalized}]},
            ),
            (
                self._collaborative_i2i,
                {"$or": [{"subjectId": normalized}, {"userId": normalized}, {"authorId": normalized}]},
            ),
            (
                self._collaborative_u2i,
                {"$or": [{"subjectId": normalized}, {"userId": normalized}]},
            ),
            (
                self._intersection_features,
                {"$or": [{"subjectId": normalized}, {"userId": normalized}, {"personaId": normalized}]},
            ),
            (self._intersection_reasons, {"subjectId": normalized}),
            (self._intersection_inbox, {"subjectId": normalized}),
            (
                self._intersection_relationships,
                {"$or": [{"sourcePersonaId": normalized}, {"targetPersonaId": normalized}]},
            ),
            (self._intersection_memberships, {"personaId": normalized}),
            (self._intersection_behaviors, {"subjectId": normalized}),
            (self._intersection_wishlist, {"subjectId": normalized}),
            (self._intersection_persona_profiles, {"personaId": normalized}),
            (self._intersection_declared_visits, {"personaId": normalized}),
            (self._checkpoints, {"subjectId": normalized}),
            (self._failures, {"subjectId": normalized}),
        )
        deleted = 0
        for collection, selector in selectors:
            deleted += int(collection.delete_many(selector).deleted_count)
        return deleted
