# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-003
# readiness_case: project-feature-profile-local
# readiness_case: project-feature-persona-relationship-local
# readiness_case: project-feature-circle-membership-local
# readiness_case: project-feature-post-lifecycle-local
from __future__ import annotations

import hashlib
import json

import pytest

from internal.recommendation.recommendation_feature_profile_view.adapters.inbound.stream.circle_membership_consumer import (
    CIRCLE_MEMBERSHIP_STREAM,
    CONSUMER_GROUP as CIRCLE_GROUP,
    CircleMembershipConsumer,
)
from internal.recommendation.recommendation_feature_profile_view.adapters.inbound.stream.content_behavior_consumer import (
    CONSUMER_GROUP as BEHAVIOR_GROUP,
    CONTENT_BEHAVIOR_DLQ,
    CONTENT_BEHAVIOR_STREAM,
    ContentBehaviorConsumer,
)
from internal.recommendation.recommendation_feature_profile_view.adapters.inbound.stream.persona_relationship_consumer import (
    CONSUMER_GROUP as RELATIONSHIP_GROUP,
    PERSONA_RELATIONSHIP_STREAM,
    PersonaRelationshipConsumer,
)
from internal.recommendation.recommendation_feature_profile_view.adapters.inbound.stream.post_lifecycle_consumer import (
    CONSUMER_GROUP as POST_GROUP,
    POST_LIFECYCLE_STREAM,
    PostLifecycleConsumer,
)


class _Redis:
    def __init__(self, stream: str, fields: dict[str, str]) -> None:
        self.stream = stream
        self.fields = {key.encode(): value.encode() for key, value in fields.items()}
        self.deliver = True
        self.pending = False
        self.acked: list[tuple[str, str, str]] = []
        self.dead_letters: list[tuple[str, dict[str, str]]] = []

    def xgroup_create(self, *_args, **_kwargs):
        return True

    def xautoclaim(self, *_args, **_kwargs):
        if self.pending:
            return ("0-0", [(b"1000-0", self.fields)], [])
        return ("0-0", [], [])

    def xreadgroup(self, *_args, **_kwargs):
        if not self.deliver:
            return []
        self.deliver = False
        self.pending = True
        return [(self.stream.encode(), [(b"1000-0", self.fields)])]

    def xack(self, stream, group, stream_id):
        self.pending = False
        self.acked.append((stream, group, stream_id))

    def xadd(self, stream, fields):
        self.dead_letters.append((stream, fields))
        return "2000-0"

    def time(self):
        return (2_000_000_000, 0)

    def xtrim(self, *_args, **_kwargs):
        return 0

    def expire(self, *_args, **_kwargs):
        return True


class _Store:
    def __init__(self) -> None:
        self.attempts = 0
        self.cleared: list[str] = []

    def record_source_failure(self, *_args):
        self.attempts += 1
        return self.attempts

    def clear_source_failure(self, failure_id: str):
        self.cleared.append(failure_id)


class _Projector:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.relationships: list[dict] = []
        self.memberships: list[dict] = []
        self.behaviors: list[dict] = []
        self.posts: list[dict] = []

    def _append(self, target: list[dict], event: dict) -> None:
        if self.fail:
            raise RuntimeError("intersection projection failed")
        target.append(event)

    def project_persona_relationship(self, **event):
        self._append(self.relationships, event)

    def project_circle_membership(self, **event):
        self._append(self.memberships, event)

    def project_behavior(self, **event):
        self._append(self.behaviors, event)

    def project_post_lifecycle(self, **event):
        self._append(self.posts, event)


def test_persona_relationship_and_circle_membership_project_before_ack() -> None:
    relationship_values = {
        "eventId": "relationship-001",
        "eventName": "PersonaBlocked",
        "sourcePersonaId": "persona-a",
        "targetPersonaId": "persona-b",
        "following": "false",
        "sourceFollowCleared": "true",
        "targetFollowCleared": "true",
        "version": "3",
        "occurredAt": "2026-08-02T12:00:00Z",
    }
    relationship_redis = _Redis(PERSONA_RELATIONSHIP_STREAM, relationship_values)
    relationship_store = _Store()
    projector = _Projector()
    relationship = PersonaRelationshipConsumer(
        redis_client=relationship_redis,
        feature_store=relationship_store,
        projector=projector,
        consumer="relationship-test",
    )
    assert relationship.process_once() == 1
    assert projector.relationships[0]["target_follow_cleared"] is True
    assert len(projector.relationships[0]["event_digest"]) == 64
    assert relationship_redis.acked == [
        (PERSONA_RELATIONSHIP_STREAM, RELATIONSHIP_GROUP, "1000-0")
    ]

    payload = {
        "id": "membership-001",
        "version": 4,
        "circleId": "circle-001",
        "personaId": "persona-a",
        "role": "member",
        "state": "active",
    }
    membership_values = {
        "eventId": "membership-event-001",
        "eventType": "CircleMembershipJoined",
        "aggregateType": "CircleMembership",
        "aggregateId": "membership-001",
        "aggregateVersion": "4",
        "payload": json.dumps(payload),
        "occurredAt": "2026-08-02T12:00:00Z",
    }
    membership_redis = _Redis(CIRCLE_MEMBERSHIP_STREAM, membership_values)
    membership = CircleMembershipConsumer(
        redis_client=membership_redis,
        feature_store=_Store(),
        projector=projector,
        consumer="membership-test",
    )
    assert membership.process_once() == 1
    assert projector.memberships[0]["state"] == "active"
    assert membership_redis.acked == [
        (CIRCLE_MEMBERSHIP_STREAM, CIRCLE_GROUP, "1000-0")
    ]


def _behavior_values() -> dict[str, str]:
    subject = "persona-a"
    client_event_id = "behavior-client-001"
    event_id = hashlib.sha256(
        f"ContentBehaviorRecorded:{subject}:{client_event_id}".encode()
    ).hexdigest()
    payload = {
        "clientEventId": client_event_id,
        "personaId": subject,
        "contentId": "entity-001",
        "contentType": "entity",
        "objectId": "entity-001",
        "objectKind": "entity",
        "displayName": "西湖",
        "action": "entity_page_view",
        "entityRefs": ["entity-001"],
        "occurredAt": "2026-08-02T12:00:00Z",
    }
    return {
        "eventId": event_id,
        "eventName": "ContentBehaviorRecorded",
        "subjectId": subject,
        "targetId": "entity-001",
        "payload": json.dumps(payload),
        "occurredAt": "2026-08-02T12:00:00Z",
    }


def test_behavior_and_post_lifecycle_project_typed_evidence_before_ack() -> None:
    projector = _Projector()
    behavior_redis = _Redis(CONTENT_BEHAVIOR_STREAM, _behavior_values())
    behavior = ContentBehaviorConsumer(
        redis_client=behavior_redis,
        feature_store=_Store(),
        projector=projector,
        consumer="behavior-test",
    )
    assert behavior.process_once() == 1
    assert projector.behaviors[0]["display_name"] == "西湖"
    assert projector.behaviors[0]["entity_refs"] == ("entity-001",)
    assert behavior_redis.acked == [
        (CONTENT_BEHAVIOR_STREAM, BEHAVIOR_GROUP, "1000-0")
    ]

    payload = {
        "postId": "post-001",
        "authorId": "persona-author",
        "authorDisplayNameSnapshot": "公开作者",
        "authorAvatarUrlSnapshot": "https://image.invalid/author",
        "status": "published",
        "visibility": "public",
        "moderationStatus": "approved",
        "primaryHomepageId": "homepage-001",
        "visitedAt": "2026-08-01T12:00:00Z",
    }
    post_values = {
        "eventId": "post-event-001",
        "eventType": "PostPublished",
        "aggregateType": "Post",
        "aggregateId": "post-001",
        "aggregateVersion": "2",
        "payload": json.dumps(payload),
        "occurredAt": "2026-08-02T12:00:00Z",
    }
    post_redis = _Redis(POST_LIFECYCLE_STREAM, post_values)
    post = PostLifecycleConsumer(
        redis_client=post_redis,
        feature_store=_Store(),
        projector=projector,
        consumer="post-test",
    )
    assert post.process_once() == 1
    assert projector.posts[0]["visited"] is True
    assert projector.posts[0]["author_display_name"] == "公开作者"
    assert post_redis.acked == [(POST_LIFECYCLE_STREAM, POST_GROUP, "1000-0")]


def test_feature_consumer_dead_letters_only_after_fifth_failed_projection() -> None:
    redis = _Redis(CONTENT_BEHAVIOR_STREAM, _behavior_values())
    consumer = ContentBehaviorConsumer(
        redis_client=redis,
        feature_store=_Store(),
        projector=_Projector(fail=True),
        consumer="behavior-failure-test",
    )
    for attempt in range(1, 6):
        if attempt < 5:
            with pytest.raises(RuntimeError, match="projection failed"):
                consumer.process_once()
            assert redis.acked == []
        else:
            assert consumer.process_once() == 1
    assert redis.dead_letters[0][0] == CONTENT_BEHAVIOR_DLQ
    assert redis.dead_letters[0][1]["attempts"] == "5"
