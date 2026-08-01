import json

import pytest

from internal.recommendation.recommendation_candidate_index_view.adapters.inbound.stream.post_lifecycle_consumer import (
    CONSUMER_GROUP,
    POST_LIFECYCLE_DLQ,
    POST_LIFECYCLE_STREAM,
    PostLifecycleConsumer,
    decode_post_lifecycle,
    lifecycle_snapshot,
)


def _fields() -> dict[bytes, bytes]:
    payload = {
        "postId": "post-001",
        "authorId": "persona-001",
        "contentType": "article",
        "status": "published",
        "visibility": "public",
        "moderationStatus": "approved",
        "publishedAt": "2026-07-31T10:00:00Z",
        "updatedAt": "2026-07-31T11:00:00Z",
        "tagRefs": ["Topic/旅行", "Entity/地点/景区"],
        "entityRefs": ["地点/景区/色达"],
    }
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
    def __init__(self) -> None:
        self.deliver = True
        self.pending = False
        self.acked = []
        self.dead_letters = []
        self.trimmed = []

    def xgroup_create(self, *_args, **_kwargs):
        return True

    def xautoclaim(self, *_args, **_kwargs):
        if self.pending:
            return ("0-0", [(b"1000-0", _fields())], [])
        return ("0-0", [], [])

    def xreadgroup(self, *_args, **_kwargs):
        if not self.deliver:
            return []
        self.deliver = False
        self.pending = True
        return [(POST_LIFECYCLE_STREAM.encode(), [(b"1000-0", _fields())])]

    def xack(self, stream, group, stream_id):
        self.pending = False
        self.acked.append((stream, group, stream_id))

    def xadd(self, stream, fields):
        self.dead_letters.append((stream, fields))
        return "2000-0"

    def time(self):
        return (2_000_000_000, 0)

    def xtrim(self, stream, **kwargs):
        self.trimmed.append((stream, kwargs))

    def expire(self, *_args):
        return True


class _Projection:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.events = []
        self.attempts = 0
        self.cleared = []

    def apply_source_event(self, **event):
        if self.fail:
            raise RuntimeError("projection failed")
        self.events.append(event)
        return True

    def record_source_failure(self, _stream_id, _event_id, _cause):
        self.attempts += 1
        return self.attempts

    def clear_source_failure(self, stream_id):
        self.cleared.append(stream_id)


def test_consumer_projects_then_acks_one_typed_post_event() -> None:
    redis = _Redis()
    projection = _Projection()
    consumer = PostLifecycleConsumer(
        redis_client=redis,
        projection=projection,
        consumer="candidate-test",
    )
    assert consumer.process_once() == 1
    event = projection.events[0]
    assert event["event_id"] == "event-001"
    assert event["snapshot"].source_sequence == 4
    assert event["snapshot"].entity_tag_ids == ("Entity/地点/景区",)
    assert redis.acked == [(POST_LIFECYCLE_STREAM, CONSUMER_GROUP, "1000-0")]
    assert projection.cleared == ["1000-0"]


def test_incomplete_upsert_snapshot_cannot_be_interpreted_as_candidate_removal() -> None:
    values = {
        key.decode(): value.decode()
        for key, value in _fields().items()
    }
    payload = json.loads(values["payload"])
    payload.pop("visibility")
    values["payload"] = json.dumps(payload)

    with pytest.raises(
        ValueError,
        match="complete eligibility snapshot",
    ):
        lifecycle_snapshot(decode_post_lifecycle(values))


def test_consumer_dead_letters_and_acks_only_after_fifth_failure() -> None:
    redis = _Redis()
    projection = _Projection(fail=True)
    consumer = PostLifecycleConsumer(
        redis_client=redis,
        projection=projection,
        consumer="candidate-test",
    )
    for attempt in range(1, 6):
        if attempt < 5:
            with pytest.raises(RuntimeError, match="projection failed"):
                consumer.process_once()
            assert redis.acked == []
        else:
            assert consumer.process_once() == 1
    assert redis.dead_letters[0][0] == POST_LIFECYCLE_DLQ
    assert redis.dead_letters[0][1]["attempts"] == "5"
    assert redis.acked == [(POST_LIFECYCLE_STREAM, CONSUMER_GROUP, "1000-0")]
    assert redis.trimmed[0][0] == POST_LIFECYCLE_DLQ
