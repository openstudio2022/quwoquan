from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

from internal.recommendation.recommendation_feedback_fact.domain.fact import (
    RecommendationFeedbackFact,
)


def _bson_datetime(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(
        microsecond=(value.microsecond // 1000) * 1000
    )


class MongoRecommendationFeedbackFactStore:
    def __init__(self, database: Any) -> None:
        self._facts = database["recommendation_feedback_facts"]
        self._failures = database["recommendation_feedback_failures"]

    def ensure_indexes(self) -> None:
        self._facts.create_index(
            [("sourceEventId", ASCENDING)],
            unique=True,
            name="uq_recommendation_feedback_source_event",
        )
        self._facts.create_index(
            [("exposureId", ASCENDING), ("occurredAt", DESCENDING)],
            name="idx_recommendation_feedback_exposure_time",
        )
        self._facts.create_index(
            [("recordedAt", ASCENDING)],
            expireAfterSeconds=30 * 24 * 60 * 60,
            name="ttl_recommendation_feedback_facts",
        )
        self._failures.create_index(
            [("updatedAt", ASCENDING)],
            expireAfterSeconds=7 * 24 * 60 * 60,
            name="ttl_recommendation_feedback_failures",
        )

    @staticmethod
    def _document(fact: RecommendationFeedbackFact) -> dict[str, Any]:
        return {
            "_id": fact.feedback_id,
            "sourceEventId": fact.source_event_id,
            "exposureId": fact.exposure_id,
            "requestId": fact.feed_request_id,
            "userId": fact.subject_id,
            "personaId": fact.persona_id,
            "targetType": fact.target_type,
            "targetId": fact.target_id,
            "feedbackType": fact.feedback_type,
            "value": fact.value,
            "occurredAt": _bson_datetime(fact.occurred_at),
            "recordedAt": _bson_datetime(fact.recorded_at),
        }

    @staticmethod
    def _fact(document: dict[str, Any]) -> RecommendationFeedbackFact:
        return RecommendationFeedbackFact(
            feedback_id=str(document["_id"]),
            source_event_id=str(document["sourceEventId"]),
            exposure_id=str(document["exposureId"]),
            feed_request_id=str(document["requestId"]),
            subject_id=str(document["userId"]),
            persona_id=document.get("personaId"),
            target_type=str(document["targetType"]),
            target_id=str(document["targetId"]),
            feedback_type=str(document["feedbackType"]),
            value=document.get("value"),
            occurred_at=document["occurredAt"],
            recorded_at=document["recordedAt"],
        )

    def append_if_absent(
        self, fact: RecommendationFeedbackFact
    ) -> tuple[RecommendationFeedbackFact, bool]:
        document = self._document(fact)
        try:
            result = self._facts.update_one(
                {"_id": fact.feedback_id},
                {"$setOnInsert": document},
                upsert=True,
            )
        except DuplicateKeyError as error:
            raise RuntimeError("recommendation feedback source event conflict") from error
        existing = self._facts.find_one({"_id": fact.feedback_id})
        if existing is None or self._document(self._fact(existing)) != document:
            raise RuntimeError("recommendation feedback identity conflicts with another payload")
        return self._fact(existing), result.upserted_id is not None

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

    def erase_subject(self, subject_id: str) -> int:
        normalized = subject_id.strip()
        if not normalized:
            raise ValueError("subjectId is required")
        result = self._facts.delete_many(
            {"$or": [{"userId": normalized}, {"personaId": normalized}]}
        )
        return int(result.deleted_count)
