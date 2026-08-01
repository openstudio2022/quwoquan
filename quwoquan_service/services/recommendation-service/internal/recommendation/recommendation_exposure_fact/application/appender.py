from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import hmac
import json
import math
from typing import Any, Mapping, Protocol


MAXIMUM_FEATURE_SNAPSHOT_BYTES = 64 * 1024


@dataclass(frozen=True, slots=True)
class ExposureFact:
    exposure_id: str
    source_event_id: str
    delivery_page_id: str
    feed_request_id: str
    window_id: str
    subject_id: str
    persona_id: str | None
    scenario: str
    target_type: str
    target_id: str
    ordinal: int
    model_bucket: str
    model_channel: str | None
    model_release_id: str | None
    feature_snapshot_at: datetime
    feature_snapshot_digest: str
    ranking_snapshot_digest: str
    user_feature_snapshot: Mapping[str, Any]
    item_feature_snapshot: Mapping[str, Any]
    exposed_at: datetime
    recorded_at: datetime


class ExposureFactStore(Protocol):
    def append_if_absent(self, fact: ExposureFact) -> tuple[ExposureFact, bool]: ...

    def find_by_attribution(self, feed_request_id: str, target_id: str) -> ExposureFact | None: ...


class SubjectClosureReader(Protocol):
    def exists(self, account_id: str) -> bool: ...


def canonical_snapshot_digest(
    user_snapshot: Mapping[str, Any],
    item_snapshot: Mapping[str, Any],
) -> str:
    encoded = json.dumps(
        {"item": item_snapshot, "user": user_snapshot},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")
    if len(encoded) > MAXIMUM_FEATURE_SNAPSHOT_BYTES:
        raise ValueError("recommendation feature snapshot exceeds 64 KiB")
    return hashlib.sha256(encoded).hexdigest()


class Appender:
    def __init__(self, store: ExposureFactStore, subject_closures: SubjectClosureReader) -> None:
        self._store = store
        self._subject_closures = subject_closures

    def append(self, fact: ExposureFact) -> tuple[ExposureFact, bool]:
        required = (
            fact.exposure_id,
            fact.source_event_id,
            fact.delivery_page_id,
            fact.feed_request_id,
            fact.window_id,
            fact.subject_id,
            fact.scenario,
            fact.target_type,
            fact.target_id,
            fact.model_bucket,
            fact.feature_snapshot_digest,
            fact.ranking_snapshot_digest,
        )
        if not all(value.strip() for value in required):
            raise ValueError("recommendation exposure fact is incomplete")
        if fact.ordinal < 0:
            raise ValueError("recommendation exposure ordinal cannot be negative")
        if fact.model_bucket not in {"model", "rule"}:
            raise ValueError("recommendation exposure modelBucket is invalid")
        if fact.model_bucket == "model" and (
            fact.model_channel not in {"champion", "challenger"}
            or not fact.model_release_id
        ):
            raise ValueError("model exposure requires a canonical channel and release")
        if fact.model_bucket == "rule" and (
            fact.model_channel is not None or fact.model_release_id is not None
        ):
            raise ValueError("rule exposure cannot claim a model channel or release")
        for digest in (fact.feature_snapshot_digest, fact.ranking_snapshot_digest):
            if len(digest) != 64 or any(value not in "0123456789abcdef" for value in digest):
                raise ValueError("recommendation exposure digest must be canonical SHA-256")
        timestamps = (fact.feature_snapshot_at, fact.exposed_at, fact.recorded_at)
        if any(value.tzinfo is None for value in timestamps):
            raise ValueError("recommendation exposure timestamps must be timezone-aware")
        if fact.exposed_at > fact.recorded_at or fact.feature_snapshot_at > fact.exposed_at:
            raise ValueError("recommendation exposure timestamp ordering is invalid")
        if self._subject_closures.exists(fact.subject_id):
            raise PermissionError("closed subjects cannot append recommendation exposure")
        expected_digest = canonical_snapshot_digest(
            fact.user_feature_snapshot,
            fact.item_feature_snapshot,
        )
        if not hmac.compare_digest(expected_digest, fact.feature_snapshot_digest):
            raise ValueError("recommendation exposure feature snapshot digest mismatch")
        if any(
            isinstance(value, float) and not math.isfinite(value)
            for snapshot in (fact.user_feature_snapshot, fact.item_feature_snapshot)
            for value in snapshot.values()
        ):
            raise ValueError("recommendation exposure feature snapshot contains non-finite values")
        return self._store.append_if_absent(fact)

    def find_by_attribution(self, feed_request_id: str, target_id: str) -> ExposureFact | None:
        if not feed_request_id.strip() or not target_id.strip():
            raise ValueError("recommendation exposure attribution is incomplete")
        return self._store.find_by_attribution(feed_request_id.strip(), target_id.strip())
