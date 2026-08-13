# spec_ref: specs/feature-tree/recommendation-platform/spec.md#dom-001
"""反馈事实 consumer 错误码语义合约。

RECOMMENDATION.SYSTEM.feedback_fact_source_event_invalid 与
RECOMMENDATION.SYSTEM.feedback_fact_append_unavailable 只有 consumer 面,
canonical 语义是 errors.yaml 声明的 recovery 行为:invalid -> absorb
(重试穷尽进对象 DLQ),unavailable -> retry(不 ack、有界重试直至
存储恢复)。本测试逐码断言契约声明与 consumer 真实失败行为同源。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from internal.recommendation.recommendation_feedback_fact.adapters.inbound.stream.content_behavior_consumer import (
    CONSUMER_GROUP,
    CONTENT_BEHAVIOR_DLQ,
    CONTENT_BEHAVIOR_STREAM,
    ContentBehaviorConsumer,
)

SERVICE_ROOT = Path(__file__).resolve().parents[4]
ERRORS_YAML = (
    SERVICE_ROOT
    / "contracts/recommendation/recommendation_feedback_fact/errors.yaml"
)

SOURCE_EVENT_INVALID_CODE = "RECOMMENDATION.SYSTEM.feedback_fact_source_event_invalid"
APPEND_UNAVAILABLE_CODE = "RECOMMENDATION.SYSTEM.feedback_fact_append_unavailable"


def _declared(code: str) -> dict:
    document = yaml.safe_load(ERRORS_YAML.read_text(encoding="utf-8"))
    return next(entry for entry in document["errors"] if entry["code"] == code)


def _fields(*, valid_identity: bool = True) -> dict[bytes, bytes]:
    subject_id = "persona-001"
    client_event_id = "client-event-001"
    event_id = hashlib.sha256(
        f"ContentBehaviorRecorded:{subject_id}:{client_event_id}".encode()
    ).hexdigest()
    if not valid_identity:
        event_id = "0" * 64
    payload = {
        "clientEventId": client_event_id,
        "personaId": subject_id,
        "deviceActorId": "",
        "sessionId": "session-001",
        "contentId": "post-001",
        "contentType": "post",
        "action": "like",
        "state": "interaction",
        "duration": 0.0,
        "tagRefs": ["Topic/旅行"],
        "entityRefs": [],
        "authorId": "persona-author",
        "feedRequestId": "feed-request-001",
        "occurredAt": "2026-07-31T08:00:00Z",
    }
    values = {
        "eventId": event_id,
        "eventName": "ContentBehaviorRecorded",
        "sourceSequence": "64c000000000000000000001",
        "subjectId": subject_id,
        "feedRequestId": "feed-request-001",
        "targetId": "post-001",
        "payload": json.dumps(payload),
        "occurredAt": "2026-07-31T08:00:00Z",
    }
    return {key.encode(): value.encode() for key, value in values.items()}


class _Redis:
    def __init__(self, *, valid_identity: bool = True) -> None:
        self.valid_identity = valid_identity
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
                [(b"1000-0", _fields(valid_identity=self.valid_identity))],
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
                CONTENT_BEHAVIOR_STREAM.encode(),
                [(b"1000-0", _fields(valid_identity=self.valid_identity))],
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


class _FeedbackStore:
    def __init__(self, *, append_failures: int = 0) -> None:
        self.append_failures = append_failures
        self.facts = {}
        self.attempts = 0

    def append_if_absent(self, fact):
        if self.append_failures > 0:
            self.append_failures -= 1
            raise RuntimeError("feedback fact append unavailable")
        existing = self.facts.setdefault(fact.feedback_id, fact)
        return existing, existing is fact

    def record_failure(self, _stream_id, _event_id, _error):
        self.attempts += 1
        return self.attempts

    def clear_failure(self, _stream_id):
        return None


class _ExposureStore:
    def find_by_attribution(self, feed_request_id, target_id):
        assert (feed_request_id, target_id) == ("feed-request-001", "post-001")
        return SimpleNamespace(
            exposure_id="exposure-001",
            subject_id="persona-001",
        )

    def exists(self, exposure_id):
        return exposure_id == "exposure-001"


class _Closures:
    def exists(self, _subject_id):
        return False


class _FeatureProjector:
    def __init__(self) -> None:
        self.calls = []

    def project_behavior(self, **values):
        self.calls.append(values)
        return True


def _consumer(redis, feedback_store):
    return ContentBehaviorConsumer(
        redis_client=redis,
        feedback_store=feedback_store,
        exposure_store=_ExposureStore(),
        subject_closures=_Closures(),
        feature_projector=_FeatureProjector(),
        consumer="feedback-error-semantics-test",
    )


def test_source_event_invalid_is_absorbed_into_the_object_dlq() -> None:
    declared = _declared(SOURCE_EVENT_INVALID_CODE)
    assert declared["recovery_action"] == "absorb"
    assert {"surface": "consumer"} in declared["emitted_by"]

    redis = _Redis(valid_identity=False)
    store = _FeedbackStore()
    consumer = _consumer(redis, store)
    for attempt in range(1, 6):
        if attempt < 5:
            with pytest.raises(ValueError, match="identity"):
                consumer.process_once()
        else:
            assert consumer.process_once() == 1
    assert store.facts == {}
    assert redis.dead_letters[0][0] == CONTENT_BEHAVIOR_DLQ
    assert redis.dead_letters[0][1]["attempts"] == "5"
    assert redis.acked == [(CONTENT_BEHAVIOR_STREAM, CONSUMER_GROUP, "1000-0")]


def test_append_unavailable_keeps_the_message_pending_until_storage_recovers() -> None:
    declared = _declared(APPEND_UNAVAILABLE_CODE)
    assert declared["recovery_action"] == "retry"
    assert declared["recovery_after_seconds"] == 5

    redis = _Redis()
    store = _FeedbackStore(append_failures=2)
    consumer = _consumer(redis, store)
    for _ in range(2):
        with pytest.raises(RuntimeError, match="append unavailable"):
            consumer.process_once()
        assert redis.acked == []
        assert redis.dead_letters == []

    assert consumer.process_once() == 1
    assert len(store.facts) == 1
    assert redis.dead_letters == []
    assert redis.acked == [(CONTENT_BEHAVIOR_STREAM, CONSUMER_GROUP, "1000-0")]
