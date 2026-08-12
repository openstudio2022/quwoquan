# spec_ref: specs/feature-tree/circle-community/gathering-coordination/spec.md#sit-001
# readiness_case: project-candidate-gathering-local
from dataclasses import asdict
import json
import time

import pytest

from internal.recommendation.recommendation_candidate_index_view.adapters.inbound.stream.gathering_lifecycle_consumer import (
    CONSUMER_GROUP,
    GATHERING_LIFECYCLE_STREAM,
    GATHERING_STREAM_POLL_BLOCK_MS,
    GatheringLifecycleConsumer,
    decode_gathering_lifecycle,
    gathering_candidate_snapshot,
)
from internal.recommendation.recommendation_candidate_index_view.application.gathering_projector import (
    decide_gathering_projection,
    gathering_event_receipt_is_duplicate,
)


def _event_fields(
    *,
    event_name: str = "GatheringPublished",
    version: int = 4,
    event_id: str = "gathering-event-004",
) -> dict[bytes, bytes]:
    payload = {
        "gatheringId": "gathering-001",
        "aggregateVersion": version,
        "lifecycleStatus": (
            "cancelled" if event_name == "GatheringCancelled" else "published"
        ),
        "occurredAt": "2026-08-05T08:00:00Z",
    }
    values = {
        "eventId": event_id,
        "eventName": event_name,
        "aggregateType": "Gathering",
        "aggregateId": "gathering-001",
        "aggregateVersion": str(version),
        "occurredAt": "2026-08-05T08:00:00Z",
        "payload": json.dumps(payload),
    }
    return {key.encode(): value.encode() for key, value in values.items()}


def _public_detail(
    *,
    version: int = 4,
    title: str = "周末山野徒步",
    audience_policy: str = "public",
) -> dict:
    return {
        "audiencePolicy": audience_policy,
        "card": {
            "gatheringId": "gathering-001",
            "aggregateVersion": version,
            "cardDigest": f"{version:064x}",
            "host": {
                "hostSubjectKind": "persona",
                "hostSubjectId": "persona-host",
                "hostDigest": "host-digest",
            },
            "purpose": {
                "title": title,
                "summary": "公开摘要",
                "coverRef": {
                    "objectTypeRef": "content.Media",
                    "objectId": "media-cover",
                },
                "topicRefs": ["Topic/徒步"],
                "requirementRefs": ["Requirement/自备饮水"],
            },
            "schedule": {
                "startAt": "2026-08-08T01:00:00Z",
                "endAt": "2026-08-08T05:00:00Z",
                "dateLabel": "周六上午",
            },
            "place": {
                "mode": "offline",
                "coarsePlaceRef": {
                    "objectTypeRef": "entity.Homepage",
                    "objectId": "homepage-park",
                },
                "coarsePlaceLabel": "城郊公园",
                "exactMeetingPoint": "东门内 20 米坐标 31.123,121.456",
            },
            "capacity": {
                "maxParticipants": 8,
                "occupiedSeats": 3,
                "remainingSeats": 5,
                "full": False,
            },
            "admission": {
                "admissionState": "accepting",
            },
            "lifecycleStatus": "published",
            "updatedAt": "2026-08-05T08:00:00Z",
        },
        "participation": {
            "personaId": "persona-applicant",
            "applicationAnswers": [{"answerText": "私人健康情况"}],
        },
    }


class _Redis:
    def __init__(self, fields: dict[bytes, bytes]) -> None:
        self._fields = fields
        self._deliver = True
        self.acked = []
        self.dead_letters = []

    def xgroup_create(self, *_args, **_kwargs):
        return True

    def xreadgroup(self, *_args, **_kwargs):
        if not self._deliver:
            return []
        self._deliver = False
        return [
            (
                GATHERING_LIFECYCLE_STREAM.encode(),
                [(b"1000-0", self._fields)],
            )
        ]

    def xack(self, stream, group, stream_id):
        self.acked.append((stream, group, stream_id))

    def xadd(self, stream, fields):
        self.dead_letters.append((stream, fields))
        return "2000-0"


class _SocketDeadlineRedis(_Redis):
    def __init__(self) -> None:
        super().__init__({})
        self.block_values: list[int] = []

    def xreadgroup(self, *_args, **kwargs):
        block_ms = int(kwargs.get("block") or 0)
        self.block_values.append(block_ms)
        if block_ms >= 200:
            raise TimeoutError("socket deadline elapsed before empty stream response")
        return []


class _Projection:
    def __init__(self) -> None:
        self.events = []
        self.failures = []
        self.cleared = []

    def apply_gathering_source_event(self, **event):
        self.events.append(event)
        return True

    def record_source_failure(self, stream_id, event_id, cause):
        self.failures.append((stream_id, event_id, cause))
        return len(self.failures)

    def clear_source_failure(self, stream_id):
        self.cleared.append(stream_id)


class _PublicCards:
    def __init__(self, detail: dict | None) -> None:
        self.detail = detail
        self.reads = []

    def read_public_card(self, gathering_id: str):
        self.reads.append(gathering_id)
        return self.detail


def test_background_empty_stream_poll_stays_inside_runtime_socket_deadline() -> None:
    redis = _SocketDeadlineRedis()
    consumer = GatheringLifecycleConsumer(
        redis_client=redis,
        projection=_Projection(),
        public_cards=_PublicCards(None),
        consumer="gathering-empty-stream-test",
    )

    consumer.start()
    deadline = time.monotonic() + 1.0
    while not consumer.healthy() and time.monotonic() < deadline:
        time.sleep(0.01)
    consumer.stop()

    assert consumer.healthy()
    assert redis.block_values
    assert set(redis.block_values) == {GATHERING_STREAM_POLL_BLOCK_MS}
    assert GATHERING_STREAM_POLL_BLOCK_MS < 200


def test_publish_projects_circle_signed_public_card_then_acks() -> None:
    redis = _Redis(_event_fields())
    projection = _Projection()
    cards = _PublicCards(_public_detail())
    consumer = GatheringLifecycleConsumer(
        redis_client=redis,
        projection=projection,
        public_cards=cards,
        consumer="gathering-candidate-test",
    )

    assert consumer.process_once() == 1
    projected = projection.events[0]
    assert projected["snapshot"].gathering_id == "gathering-001"
    assert projected["snapshot"].source_version == 4
    assert projected["snapshot"].card_digest == f"{4:064x}"
    assert projected["snapshot"].tag_refs == (
        "Topic/徒步",
        "Requirement/自备饮水",
    )
    assert projected["snapshot"].remaining_seats == 5
    assert projected["snapshot"].admission_state == "accepting"
    assert cards.reads == ["gathering-001"]
    assert redis.acked == [
        (GATHERING_LIFECYCLE_STREAM, CONSUMER_GROUP, b"1000-0")
    ]


def test_public_card_projection_discards_private_location_and_participation() -> None:
    event = decode_gathering_lifecycle(_event_fields())
    snapshot = gathering_candidate_snapshot(
        event=event,
        public_detail=_public_detail(),
    )
    assert snapshot is not None
    projected_json = json.dumps(asdict(snapshot), ensure_ascii=False, default=str)
    for forbidden in (
        "exactMeetingPoint",
        "31.123",
        "persona-applicant",
        "applicationAnswers",
        "私人健康情况",
    ):
        assert forbidden not in projected_json
    assert snapshot.coarse_place_label == "城郊公园"


def test_update_order_duplicate_and_tombstone_share_one_monotonic_rule() -> None:
    assert (
        decide_gathering_projection(
            current_version=0,
            current_card_digest=None,
            tombstone_version=0,
            incoming_version=4,
            incoming_card_digest=f"{4:064x}",
            removal=False,
        )
        == "upsert"
    )
    assert (
        decide_gathering_projection(
            current_version=4,
            current_card_digest=f"{4:064x}",
            tombstone_version=0,
            incoming_version=5,
            incoming_card_digest=f"{5:064x}",
            removal=False,
        )
        == "upsert"
    )
    assert (
        decide_gathering_projection(
            current_version=5,
            current_card_digest=f"{5:064x}",
            tombstone_version=0,
            incoming_version=4,
            incoming_card_digest=f"{4:064x}",
            removal=False,
        )
        == "ignore"
    )
    assert (
        decide_gathering_projection(
            current_version=5,
            current_card_digest=f"{5:064x}",
            tombstone_version=0,
            incoming_version=5,
            incoming_card_digest=f"{5:064x}",
            removal=False,
        )
        == "ignore"
    )
    assert (
        decide_gathering_projection(
            current_version=5,
            current_card_digest=f"{5:064x}",
            tombstone_version=0,
            incoming_version=6,
            incoming_card_digest=None,
            removal=True,
        )
        == "remove"
    )
    assert (
        decide_gathering_projection(
            current_version=0,
            current_card_digest=None,
            tombstone_version=6,
            incoming_version=5,
            incoming_card_digest=f"{5:064x}",
            removal=False,
        )
        == "ignore"
    )
    assert gathering_event_receipt_is_duplicate(
        recorded_event_digest="a" * 64,
        incoming_event_digest="a" * 64,
    )
    with pytest.raises(RuntimeError, match="identity conflict"):
        gathering_event_receipt_is_duplicate(
            recorded_event_digest="a" * 64,
            incoming_event_digest="b" * 64,
        )
    with pytest.raises(RuntimeError, match="sourceVersion conflict"):
        decide_gathering_projection(
            current_version=5,
            current_card_digest=f"{5:064x}",
            tombstone_version=0,
            incoming_version=5,
            incoming_card_digest="f" * 64,
            removal=False,
        )


@pytest.mark.parametrize(
    "event_name",
    ["GatheringCancelled", "GatheringCompleted"],
)
def test_terminal_events_tombstone_without_rehydrating_public_detail(
    event_name: str,
) -> None:
    redis = _Redis(
        _event_fields(
            event_name=event_name,
            version=6,
            event_id=f"{event_name}-006",
        )
    )
    projection = _Projection()
    cards = _PublicCards(_public_detail(version=6))
    consumer = GatheringLifecycleConsumer(
        redis_client=redis,
        projection=projection,
        public_cards=cards,
        consumer="gathering-terminal-test",
    )

    assert consumer.process_once() == 1
    assert projection.events[0]["snapshot"] is None
    assert projection.events[0]["removal"] == ("gathering-001", 6)
    assert cards.reads == []


@pytest.mark.parametrize("audience_policy", ["unlisted", "invite_only"])
def test_material_change_rehydrates_latest_card_and_non_public_tombstones(
    audience_policy: str,
) -> None:
    event = decode_gathering_lifecycle(
        _event_fields(
            event_name="GatheringRevisionAppended",
            version=5,
            event_id="GatheringRevisionAppended-005",
        )
    )
    snapshot = gathering_candidate_snapshot(
        event=event,
        public_detail=_public_detail(version=5, title="变更后的标题"),
    )
    assert snapshot is not None
    assert snapshot.title == "变更后的标题"
    assert (
        gathering_candidate_snapshot(
            event=event,
            public_detail=_public_detail(
                version=5,
                audience_policy=audience_policy,
            ),
        )
        is None
    )


@pytest.mark.parametrize(
    "event_name",
    ["GatheringParticipationChanged", "GatheringAdmissionControlChanged"],
)
def test_capacity_and_admission_events_rehydrate_canonical_public_card(
    event_name: str,
) -> None:
    detail = _public_detail(version=8)
    detail["card"]["capacity"] = {
        "maxParticipants": 8,
        "occupiedSeats": 8,
        "remainingSeats": 0,
        "full": True,
    }
    detail["card"]["admission"] = {"admissionState": "full"}
    redis = _Redis(
        _event_fields(
            event_name=event_name,
            version=8,
            event_id=f"{event_name}-008",
        )
    )
    projection = _Projection()
    cards = _PublicCards(detail)
    consumer = GatheringLifecycleConsumer(
        redis_client=redis,
        projection=projection,
        public_cards=cards,
        consumer="gathering-capacity-test",
    )

    assert consumer.process_once() == 1
    snapshot = projection.events[0]["snapshot"]
    assert snapshot.full is True
    assert snapshot.remaining_seats == 0
    assert snapshot.admission_state == "full"
    assert cards.reads == ["gathering-001"]

    recovered_event = decode_gathering_lifecycle(
        _event_fields(
            event_name="GatheringParticipationChanged",
            version=9,
            event_id="GatheringParticipationChanged-009",
        )
    )
    recovered = gathering_candidate_snapshot(
        event=recovered_event,
        public_detail=_public_detail(version=9),
    )
    assert recovered is not None
    assert recovered.full is False
    assert recovered.remaining_seats == 5
    assert recovered.admission_state == "accepting"
