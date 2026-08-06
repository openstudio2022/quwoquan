# spec_ref: specs/feature-tree/recommendation-platform/spec.md#dom-001
# readiness_case: append-feedback-local
import hashlib
import json
from types import SimpleNamespace

import pytest

from internal.recommendation.recommendation_feedback_fact.adapters.inbound.stream.content_behavior_consumer import (
    CONSUMER_GROUP,
    CONTENT_BEHAVIOR_DLQ,
    CONTENT_BEHAVIOR_STREAM,
    ContentBehaviorConsumer,
)


def _fields(*, feed_request_id: str = "feed-request-001") -> dict[bytes, bytes]:
    subject_id = "persona-001"
    client_event_id = "client-event-001"
    event_id = hashlib.sha256(
        f"ContentBehaviorRecorded:{subject_id}:{client_event_id}".encode()
    ).hexdigest()
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
        "feedRequestId": feed_request_id,
        "occurredAt": "2026-07-31T08:00:00Z",
    }
    values = {
        "eventId": event_id,
        "eventName": "ContentBehaviorRecorded",
        "sourceSequence": "64c000000000000000000001",
        "subjectId": subject_id,
        "feedRequestId": feed_request_id,
        "targetId": "post-001",
        "payload": json.dumps(payload),
        "occurredAt": "2026-07-31T08:00:00Z",
    }
    return {key.encode(): value.encode() for key, value in values.items()}


class _Redis:
    def __init__(self, *, feed_request_id: str = "feed-request-001") -> None:
        self.feed_request_id = feed_request_id
        self.deliver = True
        self.pending = False
        self.acked = []
        self.dead_letters = []

    def xgroup_create(self, *_args, **_kwargs):
        return True

    def xautoclaim(self, *_args, **_kwargs):
        if self.pending:
            return ("0-0", [(b"1000-0", _fields(feed_request_id=self.feed_request_id))], [])
        return ("0-0", [], [])

    def xreadgroup(self, *_args, **_kwargs):
        if not self.deliver:
            return []
        self.deliver = False
        self.pending = True
        return [
            (
                CONTENT_BEHAVIOR_STREAM.encode(),
                [(b"1000-0", _fields(feed_request_id=self.feed_request_id))],
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
    def __init__(self) -> None:
        self.facts = {}
        self.attempts = 0

    def append_if_absent(self, fact):
        existing = self.facts.setdefault(fact.feedback_id, fact)
        return existing, existing is fact

    def record_failure(self, _stream_id, _event_id, _error):
        self.attempts += 1
        return self.attempts

    def clear_failure(self, _stream_id):
        return None


class _ExposureStore:
    def __init__(self, *, available: bool = True) -> None:
        self.available = available

    def find_by_attribution(self, feed_request_id, target_id):
        if not self.available:
            return None
        assert (feed_request_id, target_id) == ("feed-request-001", "post-001")
        return SimpleNamespace(
            exposure_id="exposure-001",
            subject_id="persona-001",
        )

    def exists(self, exposure_id):
        return self.available and exposure_id == "exposure-001"


class _Closures:
    def exists(self, _subject_id):
        return False


class _FeatureProjector:
    def __init__(self, *, fail_once: bool = False) -> None:
        self.calls = []
        self.fail_once = fail_once

    def project_behavior(self, **values):
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("feature projection unavailable")
        self.calls.append(values)
        return True


def _consumer(redis, feedback_store, exposure_store, feature_projector=None):
    projector = feature_projector or _FeatureProjector()
    return ContentBehaviorConsumer(
        redis_client=redis,
        feedback_store=feedback_store,
        exposure_store=exposure_store,
        subject_closures=_Closures(),
        feature_projector=projector,
        consumer="feedback-test",
    ), projector


def test_consumer_resolves_persisted_exposure_before_feedback_ack() -> None:
    redis = _Redis()
    feedback_store = _FeedbackStore()
    consumer, projector = _consumer(redis, feedback_store, _ExposureStore())
    assert consumer.process_once() == 1
    fact = next(iter(feedback_store.facts.values()))
    assert fact.exposure_id == "exposure-001"
    assert fact.source_event_id == hashlib.sha256(
        b"ContentBehaviorRecorded:persona-001:client-event-001"
    ).hexdigest()
    assert projector.calls[0]["feedback_fact_id"] == fact.feedback_id
    assert projector.calls[0]["payload"]["state"] == "interaction"
    assert redis.acked == [(CONTENT_BEHAVIOR_STREAM, CONSUMER_GROUP, "1000-0")]


def test_consumer_acks_non_recommendation_behavior_without_fact() -> None:
    redis = _Redis(feed_request_id="")
    feedback_store = _FeedbackStore()
    consumer, projector = _consumer(redis, feedback_store, _ExposureStore())
    assert consumer.process_once() == 1
    assert feedback_store.facts == {}
    assert projector.calls == []
    assert redis.acked == [(CONTENT_BEHAVIOR_STREAM, CONSUMER_GROUP, "1000-0")]


def test_consumer_retries_then_dead_letters_missing_exposure() -> None:
    redis = _Redis()
    feedback_store = _FeedbackStore()
    consumer, _projector = _consumer(redis, feedback_store, _ExposureStore(available=False))
    for attempt in range(1, 6):
        if attempt < 5:
            with pytest.raises(LookupError, match="exposure"):
                consumer.process_once()
        else:
            assert consumer.process_once() == 1
    assert redis.dead_letters[0][0] == CONTENT_BEHAVIOR_DLQ
    assert redis.dead_letters[0][1]["attempts"] == "5"
    assert redis.acked == [(CONTENT_BEHAVIOR_STREAM, CONSUMER_GROUP, "1000-0")]


def test_consumer_retries_projection_after_feedback_fact_is_idempotently_persisted() -> None:
    redis = _Redis()
    feedback_store = _FeedbackStore()
    projector = _FeatureProjector(fail_once=True)
    consumer, _ = _consumer(redis, feedback_store, _ExposureStore(), projector)

    with pytest.raises(RuntimeError, match="feature projection"):
        consumer.process_once()
    assert len(feedback_store.facts) == 1
    assert redis.acked == []

    assert consumer.process_once() == 1
    assert len(feedback_store.facts) == 1
    assert len(projector.calls) == 1
