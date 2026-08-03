from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pymongo import ASCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

from internal.recommendation.recommendation_subject_closure_fact.application.appender import (
    SubjectClosureFact,
)


def _bson_datetime(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(
        microsecond=(value.microsecond // 1000) * 1000
    )


class MongoSubjectClosureStore:
    def __init__(self, database: Any) -> None:
        self._facts = database["recommendation_subject_closure_facts"]
        self._failures = database["recommendation_subject_closure_failures"]

    def ensure_indexes(self) -> None:
        self._facts.create_index(
            [("accountId", ASCENDING)],
            unique=True,
            name="uq_recommendation_subject_closure_account",
        )
        self._facts.create_index(
            [("sourceEventId", ASCENDING)],
            unique=True,
            name="uq_recommendation_subject_closure_event",
        )
        self._facts.create_index(
            [("subjectIds", ASCENDING)],
            name="idx_recommendation_subject_closure_subject",
        )
        self._failures.create_index(
            [("updatedAt", ASCENDING)],
            expireAfterSeconds=7 * 24 * 60 * 60,
            name="ttl_recommendation_subject_closure_failures",
        )

    @staticmethod
    def _fact(document: dict[str, Any]) -> SubjectClosureFact:
        return SubjectClosureFact(
            account_id=str(document["accountId"]),
            subject_ids=tuple(str(value) for value in document["subjectIds"]),
            source_event_id=str(document["sourceEventId"]),
            source_digest=str(document["sourceDigest"]),
            closed_at=document["closedAt"],
            recorded_at=document["recordedAt"],
        )

    def append_if_absent(self, fact: SubjectClosureFact) -> tuple[SubjectClosureFact, bool]:
        document = {
            "_id": fact.account_id,
            "accountId": fact.account_id,
            "subjectIds": list(fact.subject_ids),
            "sourceEventId": fact.source_event_id,
            "sourceDigest": fact.source_digest,
            "closedAt": _bson_datetime(fact.closed_at),
            "recordedAt": _bson_datetime(fact.recorded_at),
        }
        try:
            result = self._facts.update_one(
                {"_id": fact.account_id},
                {"$setOnInsert": document},
                upsert=True,
            )
        except DuplicateKeyError as error:
            raise RuntimeError("subject closure event identity conflicts with another account") from error
        existing = self._facts.find_one({"_id": fact.account_id})
        if existing is None:
            raise RuntimeError("subject closure fact disappeared after append")
        persisted = self._fact(existing)
        if (
            persisted.source_event_id != fact.source_event_id
            or persisted.source_digest != fact.source_digest
            or persisted.closed_at != document["closedAt"]
            or persisted.recorded_at != document["recordedAt"]
        ):
            raise RuntimeError("subject closure identity conflicts with an existing terminal fact")
        return persisted, result.upserted_id is not None

    def exists(self, account_id: str) -> bool:
        return self._facts.find_one({"subjectIds": account_id}, {"_id": 1}) is not None

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
