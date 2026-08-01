from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

from internal.recommendation.recommendation_exposure_fact.application.appender import ExposureFact


class MongoExposureFactStore:
    def __init__(self, database: Any) -> None:
        self._facts = database["recommendation_exposure_facts"]
        self._failures = database["recommendation_exposure_failures"]

    def ensure_indexes(self) -> None:
        self._facts.create_index(
            [("deliveryPageId", ASCENDING), ("ordinal", ASCENDING), ("targetId", ASCENDING)],
            unique=True,
            name="uq_recommendation_exposure_delivery_item",
        )
        self._facts.create_index(
            [("requestId", ASCENDING), ("targetId", ASCENDING), ("exposedAt", DESCENDING)],
            name="idx_recommendation_exposure_attribution",
        )
        self._facts.create_index(
            [("recordedAt", ASCENDING)],
            expireAfterSeconds=30 * 24 * 60 * 60,
            name="ttl_recommendation_exposure_facts",
        )
        self._failures.create_index(
            [("updatedAt", ASCENDING)],
            expireAfterSeconds=7 * 24 * 60 * 60,
            name="ttl_recommendation_exposure_failures",
        )

    @staticmethod
    def _document(fact: ExposureFact) -> dict[str, Any]:
        return {
            "_id": fact.exposure_id,
            "sourceEventId": fact.source_event_id,
            "deliveryPageId": fact.delivery_page_id,
            "requestId": fact.feed_request_id,
            "windowId": fact.window_id,
            "userId": fact.subject_id,
            "personaId": fact.persona_id,
            "scenario": fact.scenario,
            "targetType": fact.target_type,
            "targetId": fact.target_id,
            "ordinal": fact.ordinal,
            "modelBucket": fact.model_bucket,
            "modelChannel": fact.model_channel,
            "modelReleaseId": fact.model_release_id,
            "featureSnapshotAt": fact.feature_snapshot_at,
            "featureSnapshotDigest": fact.feature_snapshot_digest,
            "rankingSnapshotDigest": fact.ranking_snapshot_digest,
            "userFeatureSnapshot": dict(fact.user_feature_snapshot),
            "itemFeatureSnapshot": dict(fact.item_feature_snapshot),
            "exposedAt": fact.exposed_at,
            "recordedAt": fact.recorded_at,
        }

    @staticmethod
    def _fact(document: dict[str, Any]) -> ExposureFact:
        return ExposureFact(
            exposure_id=str(document["_id"]),
            source_event_id=str(document["sourceEventId"]),
            delivery_page_id=str(document["deliveryPageId"]),
            feed_request_id=str(document["requestId"]),
            window_id=str(document["windowId"]),
            subject_id=str(document["userId"]),
            persona_id=document.get("personaId"),
            scenario=str(document["scenario"]),
            target_type=str(document["targetType"]),
            target_id=str(document["targetId"]),
            ordinal=int(document["ordinal"]),
            model_bucket=str(document["modelBucket"]),
            model_channel=document.get("modelChannel"),
            model_release_id=document.get("modelReleaseId"),
            feature_snapshot_at=document["featureSnapshotAt"],
            feature_snapshot_digest=str(document["featureSnapshotDigest"]),
            ranking_snapshot_digest=str(document["rankingSnapshotDigest"]),
            user_feature_snapshot=dict(document["userFeatureSnapshot"]),
            item_feature_snapshot=dict(document["itemFeatureSnapshot"]),
            exposed_at=document["exposedAt"],
            recorded_at=document["recordedAt"],
        )

    def append_if_absent(self, fact: ExposureFact) -> tuple[ExposureFact, bool]:
        document = self._document(fact)
        try:
            result = self._facts.update_one(
                {"_id": fact.exposure_id},
                {"$setOnInsert": document},
                upsert=True,
            )
        except DuplicateKeyError as error:
            raise RuntimeError("recommendation exposure delivery identity conflict") from error
        existing = self._facts.find_one({"_id": fact.exposure_id})
        if existing is None or self._document(self._fact(existing)) != document:
            raise RuntimeError("recommendation exposure identity conflicts with another payload")
        return self._fact(existing), result.upserted_id is not None

    def find_by_attribution(self, feed_request_id: str, target_id: str) -> ExposureFact | None:
        document = self._facts.find_one(
            {"requestId": feed_request_id, "targetId": target_id},
            sort=[("exposedAt", DESCENDING)],
        )
        return self._fact(document) if document is not None else None

    def exists(self, exposure_id: str) -> bool:
        return self._facts.find_one({"_id": exposure_id}, {"_id": 1}) is not None

    def erase_subject(self, subject_id: str) -> int:
        normalized = subject_id.strip()
        if not normalized:
            raise ValueError("subjectId is required")
        result = self._facts.delete_many(
            {"$or": [{"userId": normalized}, {"personaId": normalized}]}
        )
        return int(result.deleted_count)

    def record_failure(self, stream_id: str, event_id: str, error: Exception) -> int:
        now = datetime.now(timezone.utc)
        result = self._failures.find_one_and_update(
            {"_id": stream_id},
            {
                "$set": {
                    "sourceEventId": event_id,
                    "error": str(error)[:1024],
                    "updatedAt": now,
                },
                "$inc": {"attempts": 1},
                "$setOnInsert": {"createdAt": now},
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return int(result.get("attempts") or 0)

    def clear_failure(self, stream_id: str) -> None:
        self._failures.delete_one({"_id": stream_id})
