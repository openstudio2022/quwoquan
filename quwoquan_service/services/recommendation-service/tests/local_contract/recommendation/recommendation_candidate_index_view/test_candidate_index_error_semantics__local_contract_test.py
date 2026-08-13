# spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/spec.md#sit-001
"""候选索引投影 consumer 错误码语义合约。

RECOMMENDATION.SYSTEM.candidate_index_source_event_invalid 与
RECOMMENDATION.SYSTEM.candidate_index_projection_unavailable 只有 consumer 面,
canonical 语义是 errors.yaml 声明的 recovery 行为:invalid -> absorb
(重试穷尽进对象 DLQ,不阻塞后续消息),unavailable -> retry(不 ack、
有界重试直至投影存储恢复)。本测试逐码断言契约声明与 consumer 真实失败
行为同源。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from internal.recommendation.recommendation_candidate_index_view.adapters.inbound.stream.post_lifecycle_consumer import (
    CONSUMER_GROUP,
    POST_LIFECYCLE_DLQ,
    POST_LIFECYCLE_STREAM,
    PostLifecycleConsumer,
)

SERVICE_ROOT = Path(__file__).resolve().parents[4]
ERRORS_YAML = (
    SERVICE_ROOT
    / "contracts/recommendation/recommendation_candidate_index_view/errors.yaml"
)

SOURCE_EVENT_INVALID_CODE = (
    "RECOMMENDATION.SYSTEM.candidate_index_source_event_invalid"
)
PROJECTION_UNAVAILABLE_CODE = (
    "RECOMMENDATION.SYSTEM.candidate_index_projection_unavailable"
)


def _declared(code: str) -> dict:
    document = yaml.safe_load(ERRORS_YAML.read_text(encoding="utf-8"))
    return next(entry for entry in document["errors"] if entry["code"] == code)


def _fields(*, valid_identity: bool = True) -> dict[bytes, bytes]:
    payload = {
        "postId": "post-001",
        "authorId": "persona-001",
        "contentType": "article",
        "status": "published",
        "visibility": "public",
        "moderationStatus": "approved",
        "publishedAt": "2026-07-31T10:00:00Z",
        "updatedAt": "2026-07-31T11:00:00Z",
        "tagRefs": ["Topic/旅行"],
        "entityRefs": [],
        "primaryHomepageId": "homepage-001",
        "primaryHomepageSnapshot": {
            "canonicalEntityId": "地点/景区/色达",
            "title": "色达",
            "subtitle": "川西高原目的地",
            "coverUrl": "https://cdn.example/homepage-001.jpg",
        },
    }
    if not valid_identity:
        payload["id"] = payload.pop("postId")
    values = {
        "eventId": "event-001",
        "eventType": "PostPublished",
        "aggregateType": "Post",
        "aggregateId": "post-001",
        "aggregateVersion": "4",
        "payload": json.dumps(payload),
        "occurredAt": "2026-07-31T11:00:00Z",
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
                POST_LIFECYCLE_STREAM.encode(),
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


class _Projection:
    def __init__(self, *, apply_failures: int = 0) -> None:
        self.apply_failures = apply_failures
        self.events = []
        self.attempts = 0
        self.cleared = []

    def apply_source_event(self, **event):
        if self.apply_failures > 0:
            self.apply_failures -= 1
            raise RuntimeError("candidate index projection unavailable")
        self.events.append(event)
        return True

    def record_source_failure(self, _stream_id, _event_id, _cause):
        self.attempts += 1
        return self.attempts

    def clear_source_failure(self, stream_id):
        self.cleared.append(stream_id)


class _OpenSubjects:
    def exists(self, _subject_id: str) -> bool:
        return False


def _consumer(redis, projection):
    return PostLifecycleConsumer(
        redis_client=redis,
        projection=projection,
        subject_closures=_OpenSubjects(),
        consumer="candidate-error-semantics-test",
    )


def test_source_event_invalid_is_absorbed_into_the_object_dlq() -> None:
    declared = _declared(SOURCE_EVENT_INVALID_CODE)
    assert declared["recovery_action"] == "absorb"
    assert {"surface": "consumer"} in declared["emitted_by"]

    redis = _Redis(valid_identity=False)
    projection = _Projection()
    consumer = _consumer(redis, projection)
    for attempt in range(1, 6):
        if attempt < 5:
            with pytest.raises(ValueError, match="identity mismatch"):
                consumer.process_once()
        else:
            assert consumer.process_once() == 1
    assert projection.events == []
    assert redis.dead_letters[0][0] == POST_LIFECYCLE_DLQ
    assert redis.dead_letters[0][1]["attempts"] == "5"
    assert redis.acked == [(POST_LIFECYCLE_STREAM, CONSUMER_GROUP, "1000-0")]


def test_projection_unavailable_keeps_the_message_pending_until_storage_recovers() -> None:
    declared = _declared(PROJECTION_UNAVAILABLE_CODE)
    assert declared["recovery_action"] == "retry"
    assert declared["recovery_after_seconds"] == 5

    redis = _Redis()
    projection = _Projection(apply_failures=2)
    consumer = _consumer(redis, projection)
    for _ in range(2):
        with pytest.raises(RuntimeError, match="projection unavailable"):
            consumer.process_once()
        assert redis.acked == []
        assert redis.dead_letters == []

    assert consumer.process_once() == 1
    assert len(projection.events) == 1
    assert redis.dead_letters == []
    assert redis.acked == [(POST_LIFECYCLE_STREAM, CONSUMER_GROUP, "1000-0")]
