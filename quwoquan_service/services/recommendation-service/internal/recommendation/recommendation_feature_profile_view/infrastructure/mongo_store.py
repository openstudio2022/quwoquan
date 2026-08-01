from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any

from pymongo import ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError

from ..application.projector import BehaviorFeatureMutation, ExposureFeatureMutation


MAX_PROFILE_FEATURE_KEYS = 256
MAX_COLLABORATIVE_NEIGHBORS = 128


class MongoFeatureProfileStore:
    """Single owner of the long-lived recommendation feature profile."""

    def __init__(self, database: Any) -> None:
        self._profiles = database["rm_recommend_feature"]
        self._author_impact = database["rm_author_impact"]
        self._author_impact_evidence = database["rm_author_impact_evidence"]
        self._collaborative_i2i = database["rm_collaborative_i2i"]
        self._collaborative_u2i = database["rm_collaborative_u2i"]
        self._intersection_features = database["rm_intersection_feature"]
        self._checkpoints = database["recommendation_feature_projection_checkpoints"]

    def ensure_indexes(self) -> None:
        self._profiles.create_index(
            [("subjectId", ASCENDING)],
            unique=True,
            name="uq_recommendation_feature_subject",
        )
        self._author_impact.create_index(
            [("authorId", ASCENDING)],
            unique=True,
            name="uq_recommendation_author_impact",
        )
        self._author_impact_evidence.create_index(
            [("eventId", ASCENDING), ("authorId", ASCENDING)],
            unique=True,
            name="uq_recommendation_author_impact_evidence",
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
        self._checkpoints.create_index(
            [("subjectId", ASCENDING), ("appliedAt", DESCENDING)],
            name="idx_recommendation_feature_checkpoint_subject",
        )

    def read_for_scoring(self, subject_id: str) -> dict[str, Any]:
        document = self._profiles.find_one({"_id": subject_id.strip()})
        if document is None:
            return {
                "checkpoint": 0,
                "sparseFeatures": {},
                "influenceScore": 0.0,
                "collaborativeFeatures": {},
                "intersectionFeatures": {},
            }
        sparse = dict(document.get("sparseFeatures") or {})
        return {
            "checkpoint": int(document.get("checkpoint", 0)),
            "sparseFeatures": sparse,
            "influenceScore": float(document.get("influenceScore", 0.0)),
            "collaborativeFeatures": dict(document.get("collaborativeFeatures") or {}),
            "intersectionFeatures": dict(document.get("intersectionFeatures") or {}),
        }

    @staticmethod
    def _merge_features(
        current: Any,
        increments: Any,
        *,
        maximum: int,
    ) -> dict[str, float]:
        merged: dict[str, float] = {}
        for key, value in dict(current or {}).items():
            numeric = float(value)
            if str(key).strip() and math.isfinite(numeric):
                merged[str(key)] = numeric
        for key, value in dict(increments or {}).items():
            numeric = float(value)
            if not str(key).strip() or not math.isfinite(numeric):
                raise ValueError("feature mutation contains an invalid value")
            merged[str(key)] = merged.get(str(key), 0.0) + numeric
        return dict(
            sorted(
                merged.items(),
                key=lambda item: (-abs(item[1]), item[0]),
            )[:maximum]
        )

    def _next_profile(
        self,
        *,
        current: dict[str, Any] | None,
        subject_id: str,
        mutation: BehaviorFeatureMutation,
        influence_delta: float = 0.0,
        sparse_increments: dict[str, float] | None = None,
        include_viewer_features: bool = True,
    ) -> dict[str, Any]:
        source = dict(current or {})
        collaborative_increments = (
            {mutation.target_id: mutation.collaborative_signal}
            if include_viewer_features and mutation.collaborative_signal != 0
            else {}
        )
        return {
            "_id": subject_id,
            "subjectId": subject_id,
            "lastFeedbackFactId": mutation.feedback_fact_id,
            "lastExposureFactId": mutation.exposure_fact_id,
            "sparseFeatures": self._merge_features(
                source.get("sparseFeatures"),
                sparse_increments if sparse_increments is not None else mutation.sparse_increments,
                maximum=MAX_PROFILE_FEATURE_KEYS,
            ),
            "influenceScore": float(source.get("influenceScore") or 0.0) + influence_delta,
            "collaborativeFeatures": self._merge_features(
                source.get("collaborativeFeatures"),
                collaborative_increments,
                maximum=MAX_COLLABORATIVE_NEIGHBORS,
            ),
            "intersectionFeatures": self._merge_features(
                source.get("intersectionFeatures"),
                mutation.intersection_increments if include_viewer_features else {},
                maximum=MAX_PROFILE_FEATURE_KEYS,
            ),
            "checkpoint": int(source.get("checkpoint") or 0) + 1,
            "updatedAt": mutation.occurred_at.astimezone(timezone.utc),
        }

    def apply_behavior_if_absent(self, mutation: BehaviorFeatureMutation) -> bool:
        receipt_id = f"{mutation.event_id}\x1f{mutation.subject_id}"
        if self._checkpoints.find_one({"_id": receipt_id}, {"_id": 1}) is not None:
            return False
        try:
            with self._profiles.database.client.start_session() as session:
                with session.start_transaction():
                    if self._checkpoints.find_one(
                        {"_id": receipt_id},
                        {"_id": 1},
                        session=session,
                    ) is not None:
                        return False
                    current = self._profiles.find_one(
                        {"_id": mutation.subject_id},
                        session=session,
                    )
                    profile = self._next_profile(
                        current=current,
                        subject_id=mutation.subject_id,
                        mutation=mutation,
                    )
                    self._profiles.replace_one(
                        {"_id": mutation.subject_id},
                        profile,
                        upsert=True,
                        session=session,
                    )
                    self._apply_collaborative(mutation, session=session)
                    self._apply_intersection(mutation, session=session)
                    self._apply_author_impact(mutation, session=session)
                    self._checkpoints.insert_one(
                        {
                            "_id": receipt_id,
                            "eventId": mutation.event_id,
                            "subjectId": mutation.subject_id,
                            "sourceSequence": mutation.source_sequence,
                            "profileCheckpoint": profile["checkpoint"],
                            "appliedAt": datetime.now(timezone.utc),
                        },
                        session=session,
                    )
            return True
        except DuplicateKeyError:
            if self._checkpoints.find_one({"_id": receipt_id}, {"_id": 1}) is not None:
                return False
            raise

    def apply_exposure_if_absent(self, mutation: ExposureFeatureMutation) -> bool:
        receipt_id = f"{mutation.exposure_fact_id}\x1f{mutation.subject_id}"
        if self._checkpoints.find_one({"_id": receipt_id}, {"_id": 1}) is not None:
            return False
        try:
            with self._profiles.database.client.start_session() as session:
                with session.start_transaction():
                    if self._checkpoints.find_one(
                        {"_id": receipt_id},
                        {"_id": 1},
                        session=session,
                    ) is not None:
                        return False
                    current = self._profiles.find_one(
                        {"_id": mutation.subject_id},
                        session=session,
                    ) or {}
                    profile = {
                        "_id": mutation.subject_id,
                        "subjectId": mutation.subject_id,
                        "lastFeedbackFactId": current.get("lastFeedbackFactId"),
                        "lastExposureFactId": mutation.exposure_fact_id,
                        "sparseFeatures": self._merge_features(
                            current.get("sparseFeatures"),
                            {"deliveryCount": 1.0},
                            maximum=MAX_PROFILE_FEATURE_KEYS,
                        ),
                        "influenceScore": float(current.get("influenceScore") or 0.0),
                        "collaborativeFeatures": dict(
                            current.get("collaborativeFeatures") or {}
                        ),
                        "intersectionFeatures": dict(
                            current.get("intersectionFeatures") or {}
                        ),
                        "checkpoint": int(current.get("checkpoint") or 0) + 1,
                        "updatedAt": mutation.occurred_at.astimezone(timezone.utc),
                    }
                    self._profiles.replace_one(
                        {"_id": mutation.subject_id},
                        profile,
                        upsert=True,
                        session=session,
                    )
                    self._checkpoints.insert_one(
                        {
                            "_id": receipt_id,
                            "eventId": mutation.exposure_fact_id,
                            "subjectId": mutation.subject_id,
                            "targetId": mutation.target_id,
                            "profileCheckpoint": profile["checkpoint"],
                            "appliedAt": datetime.now(timezone.utc),
                        },
                        session=session,
                    )
            return True
        except DuplicateKeyError:
            if self._checkpoints.find_one({"_id": receipt_id}, {"_id": 1}) is not None:
                return False
            raise

    def _apply_collaborative(self, mutation: BehaviorFeatureMutation, *, session: Any) -> None:
        if mutation.collaborative_signal == 0:
            return
        pair_id = f"{mutation.subject_id}\x1f{mutation.target_id}"
        previous = list(
            self._collaborative_u2i.find(
                {
                    "subjectId": mutation.subject_id,
                    "contentId": {"$ne": mutation.target_id},
                    "score": {"$gt": 0},
                },
                {"contentId": 1},
                session=session,
            )
            .sort([("updatedAt", DESCENDING), ("contentId", ASCENDING)])
            .limit(20)
        )
        self._collaborative_u2i.update_one(
            {"_id": pair_id},
            {
                "$set": {
                    "subjectId": mutation.subject_id,
                    "contentId": mutation.target_id,
                    "lastEventId": mutation.event_id,
                    "updatedAt": mutation.occurred_at.astimezone(timezone.utc),
                },
                "$inc": {
                    "score": mutation.collaborative_signal,
                    "positiveCount": 1 if mutation.collaborative_signal > 0 else 0,
                    "negativeCount": 1 if mutation.collaborative_signal < 0 else 0,
                },
            },
            upsert=True,
            session=session,
        )
        if mutation.collaborative_signal <= 0:
            return
        for document in previous:
            other_id = str(document.get("contentId") or "").strip()
            if not other_id:
                continue
            left, right = sorted((mutation.target_id, other_id))
            self._collaborative_i2i.update_one(
                {"_id": f"{left}\x1f{right}"},
                {
                    "$set": {
                        "leftContentId": left,
                        "rightContentId": right,
                        "updatedAt": mutation.occurred_at.astimezone(timezone.utc),
                    },
                    "$inc": {"cooccurrenceCount": 1},
                },
                upsert=True,
                session=session,
            )

    def _apply_intersection(self, mutation: BehaviorFeatureMutation, *, session: Any) -> None:
        for feature, increment in mutation.intersection_increments.items():
            self._intersection_features.update_one(
                {"_id": f"{mutation.subject_id}\x1f{feature}"},
                {
                    "$set": {
                        "subjectId": mutation.subject_id,
                        "feature": feature,
                        "lastEventId": mutation.event_id,
                        "updatedAt": mutation.occurred_at.astimezone(timezone.utc),
                    },
                    "$inc": {"value": float(increment)},
                },
                upsert=True,
                session=session,
            )

    def _apply_author_impact(self, mutation: BehaviorFeatureMutation, *, session: Any) -> None:
        author_id = (mutation.author_id or "").strip()
        if not author_id or author_id == mutation.subject_id:
            return
        evidence_id = f"{mutation.event_id}\x1f{author_id}"
        self._author_impact_evidence.insert_one(
            {
                "_id": evidence_id,
                "eventId": mutation.event_id,
                "authorId": author_id,
                "targetId": mutation.target_id,
                "action": mutation.action,
                "state": mutation.state,
                "signal": mutation.collaborative_signal,
                "occurredAt": mutation.occurred_at.astimezone(timezone.utc),
            },
            session=session,
        )
        self._author_impact.update_one(
            {"_id": author_id},
            {
                "$set": {
                    "authorId": author_id,
                    "lastEvidenceId": evidence_id,
                    "updatedAt": mutation.occurred_at.astimezone(timezone.utc),
                },
                "$inc": {
                    "evidenceCount": 1,
                    "positiveCount": 1 if mutation.collaborative_signal > 0 else 0,
                    "negativeCount": 1 if mutation.collaborative_signal < 0 else 0,
                    "influenceScore": mutation.collaborative_signal,
                },
            },
            upsert=True,
            session=session,
        )
        author_current = self._profiles.find_one({"_id": author_id}, session=session)
        author_profile = self._next_profile(
            current=author_current,
            subject_id=author_id,
            mutation=mutation,
            influence_delta=mutation.collaborative_signal,
            sparse_increments={},
            include_viewer_features=False,
        )
        self._profiles.replace_one(
            {"_id": author_id},
            author_profile,
            upsert=True,
            session=session,
        )

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
            (self._checkpoints, {"subjectId": normalized}),
        )
        deleted = 0
        for collection, selector in selectors:
            deleted += int(collection.delete_many(selector).deleted_count)
        return deleted
