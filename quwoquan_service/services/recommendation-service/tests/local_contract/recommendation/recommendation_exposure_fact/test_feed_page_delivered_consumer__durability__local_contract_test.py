import hashlib
import json

import pytest

from internal.recommendation.recommendation_exposure_fact.adapters.inbound.stream.feed_page_delivered_consumer import (
    CONSUMER_GROUP,
    FEED_PAGE_DELIVERED_DLQ,
    FEED_PAGE_DELIVERED_STREAM,
    FeedPageDeliveredConsumer,
)
from internal.recommendation.recommendation_exposure_fact.application.appender import (
    canonical_snapshot_digest,
)


def _fields(*, valid_digest: bool = True) -> dict[bytes, bytes]:
    delivery_page_id = "delivery-page-001"
    event_id = hashlib.sha256(
        f"FeedPageDelivered:{delivery_page_id}".encode()
    ).hexdigest()
    user_snapshot = {"travelAffinity": 0.8}
    item_snapshot = {"contentId": "post-001", "qualityScore": 0.9}
    feature_digest = canonical_snapshot_digest(user_snapshot, item_snapshot)
    if not valid_digest:
        feature_digest = "0" * 64
    payload = {
        "deliveryPageId": delivery_page_id,
        "feedRequestId": "feed-request-001",
        "subjectId": "persona-viewer",
        "personaId": "persona-viewer",
        "scenario": "content_feed",
        "windowId": "window-001",
        "modelBucket": "model",
        "modelChannel": "champion",
        "modelReleaseId": "release-001",
        "rankingSnapshotDigest": "a" * 64,
        "featureSnapshotAt": "2026-07-31T07:59:59Z",
        "userFeatureSnapshot": user_snapshot,
        "items": [
            {
                "ordinal": 0,
                "contentId": "post-001",
                "contentType": "post",
                "featureSnapshotDigest": feature_digest,
                "itemFeatureSnapshot": item_snapshot,
            }
        ],
        "occurredAt": "2026-07-31T08:00:00Z",
    }
    values = {
        "eventId": event_id,
        "eventName": "FeedPageDelivered",
        "deliveryPageId": delivery_page_id,
        "payload": json.dumps(payload),
        "occurredAt": payload["occurredAt"],
    }
    return {key.encode(): value.encode() for key, value in values.items()}


class _Redis:
    def __init__(self, *, valid_digest: bool = True) -> None:
        self.valid_digest = valid_digest
        self.deliver = True
        self.pending = False
        self.acked = []
        self.dead_letters = []

    def xgroup_create(self, *_args, **_kwargs):
        return True

    def xautoclaim(self, *_args, **_kwargs):
        if self.pending:
            return ("0-0", [(b"1000-0", _fields(valid_digest=self.valid_digest))], [])
        return ("0-0", [], [])

    def xreadgroup(self, *_args, **_kwargs):
        if not self.deliver:
            return []
        self.deliver = False
        self.pending = True
        return [
            (
                FEED_PAGE_DELIVERED_STREAM.encode(),
                [(b"1000-0", _fields(valid_digest=self.valid_digest))],
            )
        ]

    def xack(self, stream, group, stream_id):
        self.pending = False
        self.acked.append((stream, group, stream_id))

    def xadd(self, stream, fields):
        self.dead_letters.append((stream, fields))
        return "2000-0"

    def time(self):
        return (2_000_000_000, 0)

    def xtrim(self, *_args, **_kwargs):
        return True

    def expire(self, *_args):
        return True


class _Store:
    def __init__(self) -> None:
        self.facts = {}
        self.attempts = 0

    def append_if_absent(self, fact):
        existing = self.facts.setdefault(fact.exposure_id, fact)
        return existing, existing is fact

    def find_by_attribution(self, feed_request_id, target_id):
        return next(
            (
                fact
                for fact in self.facts.values()
                if fact.feed_request_id == feed_request_id and fact.target_id == target_id
            ),
            None,
        )

    def record_failure(self, _stream_id, _event_id, _error):
        self.attempts += 1
        return self.attempts

    def clear_failure(self, _stream_id):
        return None


class _Closures:
    def exists(self, _subject_id):
        return False


class _Projector:
    def __init__(self, *, fail_once: bool = False) -> None:
        self.fail_once = fail_once
        self.calls = []

    def project_exposure(self, **values):
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("feature projection unavailable")
        self.calls.append(values)
        return True


def _consumer(redis, store, projector):
    return FeedPageDeliveredConsumer(
        redis_client=redis,
        exposure_store=store,
        subject_closures=_Closures(),
        feature_projector=projector,
        consumer="exposure-test",
    )


def test_consumer_persists_exposure_and_projects_before_ack() -> None:
    redis = _Redis()
    store = _Store()
    projector = _Projector()
    consumer = _consumer(redis, store, projector)

    assert consumer.process_once() == 1
    fact = next(iter(store.facts.values()))
    assert fact.window_id == "window-001"
    assert fact.target_id == "post-001"
    assert projector.calls[0]["exposure_fact_id"] == fact.exposure_id
    assert redis.acked == [(FEED_PAGE_DELIVERED_STREAM, CONSUMER_GROUP, "1000-0")]


def test_consumer_retries_projection_without_duplicating_exposure() -> None:
    redis = _Redis()
    store = _Store()
    projector = _Projector(fail_once=True)
    consumer = _consumer(redis, store, projector)

    with pytest.raises(RuntimeError, match="feature projection"):
        consumer.process_once()
    assert len(store.facts) == 1
    assert redis.acked == []

    assert consumer.process_once() == 1
    assert len(store.facts) == 1
    assert len(projector.calls) == 1


def test_consumer_dead_letters_snapshot_drift_after_bounded_retries() -> None:
    redis = _Redis(valid_digest=False)
    store = _Store()
    consumer = _consumer(redis, store, _Projector())

    for attempt in range(1, 6):
        if attempt < 5:
            with pytest.raises(ValueError, match="digest mismatch"):
                consumer.process_once()
        else:
            assert consumer.process_once() == 1
    assert store.facts == {}
    assert redis.dead_letters[0][0] == FEED_PAGE_DELIVERED_DLQ
