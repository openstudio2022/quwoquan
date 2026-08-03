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
        "primaryHomepageId": "homepage-001",
        "primaryHomepageSnapshot": {
            "canonicalEntityId": "地点/景区/色达",
            "title": "色达",
            "subtitle": "川西高原目的地",
            "coverUrl": "https://cdn.example/homepage-001.jpg",
        },
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


class _SubjectClosures:
    def __init__(self, *closed_subjects: str) -> None:
        self.closed_subjects = set(closed_subjects)

    def exists(self, subject_id: str) -> bool:
        return subject_id in self.closed_subjects


def test_consumer_projects_then_acks_one_typed_post_event() -> None:
    redis = _Redis()
    projection = _Projection()
    consumer = PostLifecycleConsumer(
        redis_client=redis,
        projection=projection,
        subject_closures=_SubjectClosures(),
        consumer="candidate-test",
    )
    assert consumer.process_once() == 1
    event = projection.events[0]
    assert event["event_id"] == "event-001"
    assert event["snapshot"].source_sequence == 4
    assert event["snapshot"].entity_tag_ids == ("Entity/地点/景区",)
    assert event["snapshot"].object_card.homepage_id == "homepage-001"
    assert event["snapshot"].object_card.canonical_entity_id == "地点/景区/色达"
    assert event["snapshot"].object_card.title == "色达"
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


def test_post_lifecycle_requires_the_single_canonical_post_id_field() -> None:
    values = {key.decode(): value.decode() for key, value in _fields().items()}
    payload = json.loads(values["payload"])
    payload["id"] = payload.pop("postId")
    values["payload"] = json.dumps(payload)

    with pytest.raises(ValueError, match="aggregate identity mismatch"):
        decode_post_lifecycle(values)


def test_homepage_identity_and_public_snapshot_must_arrive_atomically() -> None:
    values = {key.decode(): value.decode() for key, value in _fields().items()}
    payload = json.loads(values["payload"])
    payload.pop("primaryHomepageSnapshot")
    values["payload"] = json.dumps(payload)
    with pytest.raises(ValueError, match="requires primaryHomepageSnapshot"):
        lifecycle_snapshot(decode_post_lifecycle(values))

    payload = json.loads(_fields()[b"payload"])
    payload.pop("primaryHomepageId")
    values["payload"] = json.dumps(payload)
    with pytest.raises(ValueError, match="requires primaryHomepageId"):
        lifecycle_snapshot(decode_post_lifecycle(values))


def test_closed_author_event_can_only_advance_a_removal_tombstone() -> None:
    redis = _Redis()
    projection = _Projection()
    consumer = PostLifecycleConsumer(
        redis_client=redis,
        projection=projection,
        subject_closures=_SubjectClosures("persona-001"),
        consumer="candidate-test",
    )

    assert consumer.process_once() == 1
    event = projection.events[0]
    assert event["snapshot"] is None
    assert event["removal"] == ("content_feed", "post-001", 4)


def test_consumer_dead_letters_and_acks_only_after_fifth_failure() -> None:
    redis = _Redis()
    projection = _Projection(fail=True)
    consumer = PostLifecycleConsumer(
        redis_client=redis,
        projection=projection,
        subject_closures=_SubjectClosures(),
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
