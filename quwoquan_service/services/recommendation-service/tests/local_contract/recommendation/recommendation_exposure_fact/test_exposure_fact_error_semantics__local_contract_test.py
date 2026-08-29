# spec_ref: specs/feature-tree/discovery-content/exposure-governance/served-dedup-write-behind/spec.md#gwt-001
"""曝光事实 consumer 错误码语义合约。

RECOMMENDATION.SYSTEM.exposure_fact_source_event_invalid 与
RECOMMENDATION.SYSTEM.exposure_fact_append_unavailable 只有 consumer 面,
canonical 语义是 errors.yaml 声明的 recovery 行为:invalid -> absorb
(重试穷尽进对象 DLQ,不阻塞 stream),unavailable -> retry(不 ack、
有界重试直至存储恢复)。本测试逐码断言契约声明与 consumer 真实失败
行为同源。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from internal.recommendation.recommendation_exposure_fact.adapters.inbound.stream.feed_page_delivered_consumer import (
    CONSUMER_GROUP,
    FEED_PAGE_DELIVERED_DLQ,
    FEED_PAGE_DELIVERED_STREAM,
    FeedPageDeliveredConsumer,
)
from internal.recommendation.recommendation_exposure_fact.application.appender import (
    canonical_snapshot_digest,
)

SERVICE_ROOT = Path(__file__).resolve().parents[4]
ERRORS_YAML = (
    SERVICE_ROOT
    / "contracts/recommendation/recommendation_exposure_fact/errors.yaml"
)

SOURCE_EVENT_INVALID_CODE = "RECOMMENDATION.SYSTEM.exposure_fact_source_event_invalid"
APPEND_UNAVAILABLE_CODE = "RECOMMENDATION.SYSTEM.exposure_fact_append_unavailable"


def _declared(code: str) -> dict:
    document = yaml.safe_load(ERRORS_YAML.read_text(encoding="utf-8"))
    return next(entry for entry in document["errors"] if entry["code"] == code)


def _fields(*, valid_event_name: bool = True) -> dict[bytes, bytes]:
    delivery_page_id = "delivery-page-001"
    event_id = hashlib.sha256(
        f"FeedPageDelivered:{delivery_page_id}".encode()
    ).hexdigest()
    user_snapshot = {"travelAffinity": 0.8}
    item_snapshot = {"contentId": "post-001", "qualityScore": 0.9}
    payload = {
        "deliveryPageId": delivery_page_id,
        "feedRequestId": "feed-request-001",
        "subjectId": "persona-viewer",
        "personaId": "persona-viewer",
        "scenario": "content_feed",
        "windowId": "window-001",
        "experimentBucket": "rule",
        "modelBucket": "rule",
        "rankingSnapshotDigest": "a" * 64,
        "featureSnapshotAt": "2026-07-31T07:59:59Z",
        "userFeatureSnapshot": user_snapshot,
        "items": [
            {
                "ordinal": 0,
                "contentId": "post-001",
                "contentType": "post",
                "featureSnapshotDigest": canonical_snapshot_digest(
                    user_snapshot, item_snapshot
                ),
                "itemFeatureSnapshot": item_snapshot,
            }
        ],
        "occurredAt": "2026-07-31T08:00:00Z",
    }
    values = {
        "eventId": event_id,
        "eventName": "FeedPageDelivered" if valid_event_name else "NotAFeedEvent",
        "deliveryPageId": delivery_page_id,
        "payload": json.dumps(payload),
        "occurredAt": payload["occurredAt"],
    }
    return {key.encode(): value.encode() for key, value in values.items()}


class _Redis:
    def __init__(self, *, valid_event_name: bool = True) -> None:
        self.valid_event_name = valid_event_name
        self.deliver = True
        self.pending = False
        self.acked = []
        self.dead_letters = []

    def xgroup_create(self, *_args, **_kwargs):
        return True

    def xautoclaim(self, *_args, **_kwargs):
        if self.pending:
            return (
                "0-0",
                [(b"1000-0", _fields(valid_event_name=self.valid_event_name))],
                [],
            )
        return ("0-0", [], [])

    def xreadgroup(self, *_args, **_kwargs):
        if not self.deliver:
            return []
        self.deliver = False
        self.pending = True
        return [
            (
                FEED_PAGE_DELIVERED_STREAM.encode(),
                [(b"1000-0", _fields(valid_event_name=self.valid_event_name))],
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
    def __init__(self, *, append_failures: int = 0) -> None:
        self.append_failures = append_failures
        self.facts = {}
        self.attempts = 0

    def append_if_absent(self, fact):
        if self.append_failures > 0:
            self.append_failures -= 1
            raise RuntimeError("exposure fact append unavailable")
        existing = self.facts.setdefault(fact.exposure_id, fact)
        return existing, existing is fact

    def find_by_attribution(self, _feed_request_id, _target_id):
        return None

    def record_failure(self, _stream_id, _event_id, _error):
        self.attempts += 1
        return self.attempts

    def clear_failure(self, _stream_id):
        return None


class _Closures:
    def exists(self, _subject_id):
        return False


class _Projector:
    def __init__(self) -> None:
        self.calls = []

    def project_exposure(self, **values):
        self.calls.append(values)
        return True


def _consumer(redis, store):
    return FeedPageDeliveredConsumer(
        redis_client=redis,
        exposure_store=store,
        subject_closures=_Closures(),
        feature_projector=_Projector(),
        consumer="exposure-error-semantics-test",
    )


def test_source_event_invalid_is_absorbed_into_the_object_dlq() -> None:
    declared = _declared(SOURCE_EVENT_INVALID_CODE)
    assert declared["recovery_action"] == "absorb"
    assert {"surface": "consumer"} in declared["emitted_by"]

    redis = _Redis(valid_event_name=False)
    store = _Store()
    consumer = _consumer(redis, store)
    for attempt in range(1, 6):
        if attempt < 5:
            with pytest.raises(ValueError, match="unsupported"):
                consumer.process_once()
        else:
            assert consumer.process_once() == 1
    assert store.facts == {}
    assert redis.dead_letters[0][0] == FEED_PAGE_DELIVERED_DLQ
    assert redis.dead_letters[0][1]["attempts"] == "5"
    assert redis.acked == [(FEED_PAGE_DELIVERED_STREAM, CONSUMER_GROUP, "1000-0")]


def test_append_unavailable_keeps_the_message_pending_until_storage_recovers() -> None:
    declared = _declared(APPEND_UNAVAILABLE_CODE)
    assert declared["recovery_action"] == "retry"
    assert declared["recovery_after_seconds"] == 5

    redis = _Redis()
    store = _Store(append_failures=2)
    consumer = _consumer(redis, store)
    for _ in range(2):
        with pytest.raises(RuntimeError, match="append unavailable"):
            consumer.process_once()
        assert redis.acked == []
        assert redis.dead_letters == []

    assert consumer.process_once() == 1
    assert len(store.facts) == 1
    assert redis.dead_letters == []
    assert redis.acked == [(FEED_PAGE_DELIVERED_STREAM, CONSUMER_GROUP, "1000-0")]
