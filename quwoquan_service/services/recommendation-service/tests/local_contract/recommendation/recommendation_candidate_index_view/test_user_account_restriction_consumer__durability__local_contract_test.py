# spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-003
import json

from internal.recommendation.recommendation_candidate_index_view.adapters.inbound.stream.user_account_restriction_consumer import (
    CONSUMER_GROUP,
    USER_ACCOUNT_STREAM,
    UserAccountRestrictionConsumer,
    decode_user_account_restriction,
)


def _fields(event_name: str = "UserSuspended") -> dict[bytes, bytes]:
    state = "suspended" if event_name == "UserSuspended" else "active"
    payload = {
        "userId": "account-001",
        "personaIds": ["persona-001"],
        "accountState": state,
        "authEpoch": 4,
        "decisionRef": "decision-001",
        "occurredAt": "2026-08-02T08:00:00Z",
    }
    values = {
        "eventId": f"event-{event_name}",
        "eventName": event_name,
        "accountId": "account-001",
        "accountVersion": "7",
        "payload": json.dumps(payload),
        "occurredAt": "2026-08-02T08:00:00Z",
    }
    return {key.encode(): value.encode() for key, value in values.items()}


class _Redis:
    def __init__(self, event_name: str = "UserSuspended") -> None:
        self.event_name = event_name
        self.deliver = True
        self.pending = False
        self.acked = []

    def xgroup_create(self, *_args, **_kwargs):
        return True

    def xautoclaim(self, *_args, **_kwargs):
        if self.pending:
            return ("0-0", [(b"1000-0", _fields(self.event_name))], [])
        return ("0-0", [], [])

    def xreadgroup(self, *_args, **_kwargs):
        if not self.deliver:
            return []
        self.deliver = False
        self.pending = True
        return [
            (
                USER_ACCOUNT_STREAM.encode(),
                [(b"1000-0", _fields(self.event_name))],
            )
        ]

    def xack(self, stream, group, stream_id):
        self.pending = False
        self.acked.append((stream, group, stream_id))


class _Projection:
    def __init__(self) -> None:
        self.events = []
        self.failures = []
        self.cleared = []

    def apply_account_restriction_event(self, **event):
        self.events.append(event)
        return 1

    def record_source_failure(self, stream_id, event_id, cause):
        self.failures.append((stream_id, event_id, cause))
        return len(self.failures)

    def clear_source_failure(self, stream_id):
        self.cleared.append(stream_id)


class _Closures:
    def __init__(self, closed: bool = False) -> None:
        self.closed = closed

    def exists(self, _subject_id: str) -> bool:
        return self.closed


def test_consumer_projects_reversible_restriction_before_ack() -> None:
    redis = _Redis()
    projection = _Projection()
    consumer = UserAccountRestrictionConsumer(
        redis_client=redis,
        projection=projection,
        subject_closures=_Closures(),
        consumer="restriction-test",
    )

    assert consumer.process_once() == 1
    event = projection.events[0]
    assert event["account_id"] == "account-001"
    assert event["account_version"] == 7
    assert event["subject_ids"] == ("account-001", "persona-001")
    assert event["restricted"] is True
    assert event["terminal"] is False
    assert len(event["event_digest"]) == 64
    assert redis.acked == [(USER_ACCOUNT_STREAM, CONSUMER_GROUP, "1000-0")]


def test_restore_after_subject_closure_is_persisted_only_as_terminal_noop() -> None:
    redis = _Redis("UserRestored")
    projection = _Projection()
    consumer = UserAccountRestrictionConsumer(
        redis_client=redis,
        projection=projection,
        subject_closures=_Closures(closed=True),
        consumer="restriction-test",
    )

    assert consumer.process_once() == 1
    event = projection.events[0]
    assert event["restricted"] is False
    assert event["terminal"] is True


def test_decoder_rejects_a_second_payload_field_track() -> None:
    values = {key.decode(): value.decode() for key, value in _fields().items()}
    payload = json.loads(values["payload"])
    payload["unknownUserId"] = payload["userId"]
    values["payload"] = json.dumps(payload)

    try:
        decode_user_account_restriction(values)
    except ValueError as error:
        assert "payload fields" in str(error)
    else:
        raise AssertionError("unknown payload field was accepted")
