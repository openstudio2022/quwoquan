# spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/spec.md#sit-001
# readiness_case: project-candidate-persona-relationship-local
from internal.recommendation.recommendation_candidate_index_view.adapters.inbound.stream.persona_relationship_consumer import (
    CONSUMER_GROUP,
    PERSONA_RELATIONSHIP_STREAM,
    PersonaRelationshipConsumer,
    decode_persona_relationship,
)


def _fields(event_name: str = "PersonaFollowStateChanged") -> dict[bytes, bytes]:
    values = {
        "eventId": f"event-{event_name}",
        "eventName": event_name,
        "pairId": "pair-001",
        "sourcePersonaId": "persona-viewer",
        "targetPersonaId": "persona-author",
        "following": "true" if event_name == "PersonaFollowStateChanged" else "false",
        "version": "7",
        "occurredAt": "2026-08-02T08:00:00Z",
    }
    return {key.encode(): value.encode() for key, value in values.items()}


class _Redis:
    def __init__(self, event_name: str) -> None:
        self.event_name = event_name
        self.deliver = True
        self.acked = []

    def xgroup_create(self, *_args, **_kwargs):
        return True

    def xautoclaim(self, *_args, **_kwargs):
        return ("0-0", [], [])

    def xreadgroup(self, *_args, **_kwargs):
        if not self.deliver:
            return []
        self.deliver = False
        return [
            (
                PERSONA_RELATIONSHIP_STREAM.encode(),
                [(b"1000-0", _fields(self.event_name))],
            )
        ]

    def xack(self, stream, group, stream_id):
        self.acked.append((stream, group, stream_id))


class _Projection:
    def __init__(self) -> None:
        self.events = []
        self.cleared = []

    def apply_persona_relationship_event(self, **event):
        self.events.append(event)
        return True

    def record_source_failure(self, *_args):
        raise AssertionError("valid event must not enter failure tracking")

    def clear_source_failure(self, stream_id):
        self.cleared.append(stream_id)


def test_follow_event_is_projected_before_stream_ack() -> None:
    redis = _Redis("PersonaFollowStateChanged")
    projection = _Projection()
    consumer = PersonaRelationshipConsumer(
        redis_client=redis,
        projection=projection,
        consumer="relationship-test",
    )

    assert consumer.process_once() == 1
    event = projection.events[0]
    assert event["source_persona_id"] == "persona-viewer"
    assert event["target_persona_id"] == "persona-author"
    assert event["following"] is True
    assert event["version"] == 7
    assert len(event["event_digest"]) == 64
    assert redis.acked == [
        (PERSONA_RELATIONSHIP_STREAM, CONSUMER_GROUP, "1000-0")
    ]


def test_block_event_cannot_retain_following_state() -> None:
    values = {key.decode(): value.decode() for key, value in _fields("PersonaBlocked").items()}
    values["following"] = "true"
    try:
        decode_persona_relationship(values)
    except ValueError as error:
        assert "cannot retain following" in str(error)
    else:
        raise AssertionError("blocked relationship accepted following=true")
