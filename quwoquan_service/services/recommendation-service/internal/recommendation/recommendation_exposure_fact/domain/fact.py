from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import hmac
import json
import math
from typing import Any, Mapping


MAXIMUM_FEATURE_SNAPSHOT_BYTES = 64 * 1024


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
    experiment_bucket: str
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

    def validate(self) -> None:
        required = (
            self.exposure_id,
            self.source_event_id,
            self.delivery_page_id,
            self.feed_request_id,
            self.window_id,
            self.subject_id,
            self.scenario,
            self.target_type,
            self.target_id,
            self.experiment_bucket,
            self.model_bucket,
            self.feature_snapshot_digest,
            self.ranking_snapshot_digest,
        )
        if not all(value.strip() for value in required):
            raise ValueError("recommendation exposure fact is incomplete")
        if self.ordinal < 0:
            raise ValueError("recommendation exposure ordinal cannot be negative")
        if self.experiment_bucket not in {"model", "rule"}:
            raise ValueError("recommendation exposure experimentBucket is invalid")
        if self.model_bucket not in {"model", "rule"}:
            raise ValueError("recommendation exposure modelBucket is invalid")
        if self.model_bucket == "model" and (
            self.model_channel not in {"champion", "challenger"}
            or not self.model_release_id
        ):
            raise ValueError("model exposure requires a canonical channel and release")
        if self.model_bucket == "rule" and (
            self.model_channel is not None or self.model_release_id is not None
        ):
            raise ValueError("rule exposure cannot claim a model channel or release")
        for digest in (self.feature_snapshot_digest, self.ranking_snapshot_digest):
            if len(digest) != 64 or any(value not in "0123456789abcdef" for value in digest):
                raise ValueError("recommendation exposure digest must be canonical SHA-256")
        timestamps = (self.feature_snapshot_at, self.exposed_at, self.recorded_at)
        if any(value.tzinfo is None for value in timestamps):
            raise ValueError("recommendation exposure timestamps must be timezone-aware")
        if self.exposed_at > self.recorded_at or self.feature_snapshot_at > self.exposed_at:
            raise ValueError("recommendation exposure timestamp ordering is invalid")
        expected_digest = canonical_snapshot_digest(
            self.user_feature_snapshot,
            self.item_feature_snapshot,
        )
        if not hmac.compare_digest(expected_digest, self.feature_snapshot_digest):
            raise ValueError("recommendation exposure feature snapshot digest mismatch")
        if any(
            isinstance(value, float) and not math.isfinite(value)
            for snapshot in (self.user_feature_snapshot, self.item_feature_snapshot)
            for value in snapshot.values()
        ):
            raise ValueError("recommendation exposure feature snapshot contains non-finite values")
