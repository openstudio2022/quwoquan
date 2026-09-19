# spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/spec.md#sit-001
# readiness_case: project-candidate-index-local
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
        "sourceOwner": None, "environment": None, "releaseId": None, "manifestDigest": None, "releaseDigest": None, "sourceVersion": 4, "safetyRevision": 1, "title": "旅行", "body": "正文", "summary": "摘要", "authorDisplayNameSnapshot": "作者", "authorAvatarUrlSnapshot": "",
        "coverUrl": "", "thumbnailUrl": "", "videoUrl": "", "width": 0, "height": 0, "durationMs": 0, "contentVertical": "travel", "createdAt": "2026-07-31T10:00:00Z", "visitedAt": None,
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
        if _args[0] != POST_LIFECYCLE_STREAM: return ("0-0", [], [])
        if self.pending:
            return ("0-0", [(b"1000-0", _fields())], [])
        return ("0-0", [], [])

    def xreadgroup(self, *_args, **_kwargs):
        if POST_LIFECYCLE_STREAM not in _args[2]: return []
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


def test_fence_ack_failure_is_not_hidden_by_empty_scan() -> None:
    from datetime import datetime, timezone
    redis = _Redis(); projection = _Projection()
    class Reconciler:
        def apply(self, values): pass
    consumer = PostLifecycleConsumer(redis_client=redis, projection=projection, subject_closures=_SubjectClosures(), consumer="fence", fence_reconciler=Reconciler())
    ack = redis.xack
    def failed_ack(*_): raise RuntimeError("ACK disconnected")
    redis.xack = failed_ack
    with pytest.raises(RuntimeError): consumer._process("fence-1", {"eventType": "ContentReleaseFenceChanged"})
    consumer._last_failure = None; consumer._last_success = datetime.now(timezone.utc)
    assert not consumer.healthy()
    redis.xack = ack; consumer._process("fence-1", {"eventType": "ContentReleaseFenceChanged"})
    assert consumer.healthy()


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
        match="visibility",
    ):
        lifecycle_snapshot(decode_post_lifecycle(values))


def test_post_lifecycle_requires_the_single_canonical_post_id_field() -> None:
    values = {key.decode(): value.decode() for key, value in _fields().items()}
    payload = json.loads(values["payload"])
    payload["id"] = payload.pop("postId")
    values["payload"] = json.dumps(payload)

    with pytest.raises(ValueError, match="extra_forbidden"):
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


def test_consumer_dead_letters_but_keeps_unapplied_fact_pending() -> None:
    redis = _Redis()
    projection = _Projection(fail=True)
    consumer = PostLifecycleConsumer(
        redis_client=redis,
        projection=projection,
        subject_closures=_SubjectClosures(),
        consumer="candidate-test",
    )
    for attempt in range(1, 6):
        with pytest.raises(RuntimeError, match="projection failed"):
            consumer.process_once()
        assert redis.acked == []
    assert redis.dead_letters[0][0] == POST_LIFECYCLE_DLQ
    assert redis.dead_letters[0][1]["attempts"] == "5"
    assert redis.acked == []
    assert redis.trimmed[0][0] == POST_LIFECYCLE_DLQ
