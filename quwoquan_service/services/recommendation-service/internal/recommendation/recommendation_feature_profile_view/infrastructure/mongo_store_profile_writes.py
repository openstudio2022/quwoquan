"""特征画像投影写入面：行为/曝光/搜索/标签反馈的幂等投影与协同、作者影响力副作用。

本模块是 ``MongoFeatureProfileStore`` 的画像写 mixin，实例属性
（``_profiles`` / ``_checkpoints`` 等集合句柄）由组合类的 ``__init__`` 提供。
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import math
from typing import Any

from pymongo import ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError

from ..application.projector import (
    BehaviorFeatureMutation,
    ExposureFeatureMutation,
    SearchSignalMutation,
    TagFeedbackMutation,
)


MAX_PROFILE_FEATURE_KEYS = 256
MAX_COLLABORATIVE_NEIGHBORS = 128
MAX_HARD_EXCLUSIONS = 1000


class MongoFeatureProfileWriteOps:
    """特征画像投影写入操作（``MongoFeatureProfileStore`` 的一部分）。"""

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
        negative_content_ids = list(source.get("negativeContentIds") or [])
        hidden_author_ids = list(source.get("hiddenAuthorIds") or [])
        hidden_content_types = list(source.get("hiddenContentTypes") or [])
        if mutation.action in {"dislike", "report"}:
            negative_content_ids = self._append_hard_exclusion(
                negative_content_ids,
                mutation.target_id,
            )
        elif mutation.action == "hide_author" and mutation.author_id:
            hidden_author_ids = self._append_hard_exclusion(
                hidden_author_ids,
                mutation.author_id,
            )
        elif mutation.action == "hide_content_type" and mutation.content_type:
            hidden_content_types = self._append_hard_exclusion(
                hidden_content_types,
                mutation.content_type,
            )
        return {
            "_id": subject_id,
            "subjectId": subject_id,
            "lastFeedbackFactId": mutation.feedback_fact_id,
            "lastExposureFactId": mutation.exposure_fact_id,
            "lastTagFeedbackFactId": source.get("lastTagFeedbackFactId"),
            "sparseFeatures": self._merge_features(
                source.get("sparseFeatures"),
                sparse_increments if sparse_increments is not None else mutation.sparse_increments,
                maximum=MAX_PROFILE_FEATURE_KEYS,
            ),
            "tagAffinities": dict(source.get("tagAffinities") or {}),
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
            "negativeContentIds": negative_content_ids,
            "hiddenAuthorIds": hidden_author_ids,
            "hiddenContentTypes": hidden_content_types,
            "checkpoint": int(source.get("checkpoint") or 0) + 1,
            "updatedAt": mutation.occurred_at.astimezone(timezone.utc),
        }

    @staticmethod
    def _append_hard_exclusion(values: list[Any], value: str) -> list[str]:
        normalized = value.strip()
        current = [str(item).strip() for item in values if str(item).strip()]
        current = [item for item in current if item != normalized]
        current.append(normalized)
        return current[-MAX_HARD_EXCLUSIONS:]

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
                        "lastTagFeedbackFactId": current.get("lastTagFeedbackFactId"),
                        "sparseFeatures": self._merge_features(
                            current.get("sparseFeatures"),
                            {"deliveryCount": 1.0},
                            maximum=MAX_PROFILE_FEATURE_KEYS,
                        ),
                        "tagAffinities": dict(current.get("tagAffinities") or {}),
                        "influenceScore": float(current.get("influenceScore") or 0.0),
                        "collaborativeFeatures": dict(
                            current.get("collaborativeFeatures") or {}
                        ),
                        "intersectionFeatures": dict(
                            current.get("intersectionFeatures") or {}
                        ),
                        "negativeContentIds": list(
                            current.get("negativeContentIds") or []
                        ),
                        "hiddenAuthorIds": list(current.get("hiddenAuthorIds") or []),
                        "hiddenContentTypes": list(
                            current.get("hiddenContentTypes") or []
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

    # 搜推联动短期意图的有界衰减参数（契约 business_rules 单一真相源）。
    SEARCH_TERM_AFFINITY_LIMIT = 50
    SEARCH_TERM_HALF_LIFE_DAYS = 7.0
    SEARCH_TERM_MIN_WEIGHT = 0.01

    @classmethod
    def _decayed_search_terms(
        cls,
        current: Any,
        terms: tuple[str, ...],
        *,
        now: datetime,
    ) -> list[dict[str, Any]]:
        now_utc = now.astimezone(timezone.utc)
        merged: dict[str, dict[str, Any]] = {}
        for entry in current or []:
            term = str((entry or {}).get("term") or "").strip()
            if not term:
                continue
            weight = float((entry or {}).get("weight") or 0.0)
            last_seen = (entry or {}).get("lastSeenAt")
            if isinstance(last_seen, datetime):
                elapsed_days = max(
                    (now_utc - last_seen.astimezone(timezone.utc)).total_seconds()
                    / 86400.0,
                    0.0,
                )
                weight *= math.exp(
                    -elapsed_days * math.log(2.0) / cls.SEARCH_TERM_HALF_LIFE_DAYS
                )
            else:
                last_seen = now_utc
            if weight > cls.SEARCH_TERM_MIN_WEIGHT:
                merged[term] = {"weight": weight, "lastSeenAt": last_seen}
        for term in terms:
            previous = float((merged.get(term) or {}).get("weight") or 0.0)
            merged[term] = {"weight": previous + 1.0, "lastSeenAt": now_utc}
        bounded = sorted(
            merged.items(),
            key=lambda item: (-float(item[1]["weight"]), item[0]),
        )[: cls.SEARCH_TERM_AFFINITY_LIMIT]
        return [
            {"term": term, "weight": entry["weight"], "lastSeenAt": entry["lastSeenAt"]}
            for term, entry in bounded
        ]

    def apply_search_signal_if_absent(self, mutation: SearchSignalMutation) -> bool:
        receipt_id = f"{mutation.signal_id}\x1f{mutation.subject_id}"
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
                    next_checkpoint = int(current.get("checkpoint") or 0) + 1
                    update: dict[str, Any] = {
                        "$set": {
                            "subjectId": mutation.subject_id,
                            "checkpoint": next_checkpoint,
                            "updatedAt": mutation.created_at.astimezone(timezone.utc),
                        },
                    }
                    if mutation.signal_type == "query":
                        update["$set"]["searchTermAffinities"] = (
                            self._decayed_search_terms(
                                current.get("searchTermAffinities"),
                                mutation.terms,
                                now=mutation.created_at,
                            )
                        )
                    # click 信号仅推进幂等收据，不投影 engaged objects（契约 business_rules）。
                    self._profiles.update_one(
                        {"_id": mutation.subject_id},
                        update,
                        upsert=True,
                        session=session,
                    )
                    self._checkpoints.insert_one(
                        {
                            "_id": receipt_id,
                            "eventId": mutation.signal_id,
                            "subjectId": mutation.subject_id,
                            "sourceType": "SearchRecommendationSignalPublished",
                            "signalType": mutation.signal_type,
                            # 隐私约束：收据只记 term 数量，绝不落原始查询词。
                            "termCount": len(mutation.terms),
                            "profileCheckpoint": next_checkpoint,
                            "appliedAt": datetime.now(timezone.utc),
                        },
                        session=session,
                    )
            return True
        except DuplicateKeyError:
            if self._checkpoints.find_one({"_id": receipt_id}, {"_id": 1}) is not None:
                return False
            raise

    def apply_tag_feedback_if_absent(self, mutation: TagFeedbackMutation) -> bool:
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
                    ) or {}
                    tag_affinities = dict(current.get("tagAffinities") or {})
                    if mutation.action == "click":
                        tag_affinities[mutation.tag_ref] = 1.0
                    elif mutation.action == "dislike":
                        tag_affinities[mutation.tag_ref] = -1.0
                    elif mutation.action == "ignore":
                        tag_affinities.pop(mutation.tag_ref, None)
                    elif mutation.action != "correct":
                        raise ValueError("unsupported tag feedback action")
                    profile = {
                        "_id": mutation.subject_id,
                        "subjectId": mutation.subject_id,
                        "lastFeedbackFactId": current.get("lastFeedbackFactId"),
                        "lastExposureFactId": current.get("lastExposureFactId"),
                        "lastTagFeedbackFactId": mutation.event_id,
                        "sparseFeatures": dict(current.get("sparseFeatures") or {}),
                        "tagAffinities": tag_affinities,
                        "influenceScore": float(current.get("influenceScore") or 0.0),
                        "collaborativeFeatures": dict(
                            current.get("collaborativeFeatures") or {}
                        ),
                        "intersectionFeatures": dict(
                            current.get("intersectionFeatures") or {}
                        ),
                        "negativeContentIds": list(
                            current.get("negativeContentIds") or []
                        ),
                        "hiddenAuthorIds": list(current.get("hiddenAuthorIds") or []),
                        "hiddenContentTypes": list(
                            current.get("hiddenContentTypes") or []
                        ),
                        "checkpoint": int(current.get("checkpoint") or 0) + 1,
                        "updatedAt": mutation.recorded_at.astimezone(timezone.utc),
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
                            "eventId": mutation.event_id,
                            "subjectId": mutation.subject_id,
                            "sourceType": "TagFeedbackRecorded",
                            "actorKind": mutation.actor_kind,
                            "tagRef": mutation.tag_ref,
                            "action": mutation.action,
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
        help_type = (mutation.impact_help_type or "").strip()
        if not author_id or author_id == mutation.subject_id or not help_type:
            return
        tag_refs = mutation.intersection_tag_refs or ("",)
        occurred_at = mutation.occurred_at.astimezone(timezone.utc)
        for tag_ref in tag_refs:
            source = "behavior"
            impact_id = self._stable_impact_id(
                author_id=author_id,
                help_type=help_type,
                action=mutation.action,
                dimension=(mutation.intersection_dimension or ""),
                tag_ref=tag_ref,
                source=source,
            )
            evidence_id = f"{mutation.event_id}\x1f{author_id}\x1f{tag_ref}"
            self._author_impact_evidence.insert_one(
                {
                    "_id": evidence_id,
                    "eventId": mutation.event_id,
                    "impactId": impact_id,
                    "authorId": author_id,
                    "contentId": mutation.target_id,
                    "contentType": mutation.content_type or "",
                    "helpType": help_type,
                    "action": mutation.action,
                    "intersectionDimension": mutation.intersection_dimension or "",
                    "tagRef": tag_ref,
                    "source": source,
                    "occurredAt": occurred_at,
                },
                session=session,
            )
            self._author_impact.update_one(
                {"_id": f"{author_id}\x1f{impact_id}"},
                {
                    "$setOnInsert": {
                        "authorId": author_id,
                        "impactId": impact_id,
                        "helpType": help_type,
                        "action": mutation.action,
                        "intersectionDimension": mutation.intersection_dimension or "",
                        "tagRef": tag_ref,
                        "source": source,
                        "createdAt": occurred_at,
                    },
                    "$set": {
                        "representativeContentId": mutation.target_id,
                        "updatedAt": occurred_at,
                    },
                    "$inc": {"count": 1},
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

    @staticmethod
    def _stable_impact_id(
        *,
        author_id: str,
        help_type: str,
        action: str,
        dimension: str,
        tag_ref: str,
        source: str,
    ) -> str:
        raw = "|".join(
            value.strip()
            for value in (author_id, help_type, action, dimension, tag_ref, source)
        )
        return hashlib.sha1(raw.encode("utf-8"), usedforsecurity=False).hexdigest()[:20]
