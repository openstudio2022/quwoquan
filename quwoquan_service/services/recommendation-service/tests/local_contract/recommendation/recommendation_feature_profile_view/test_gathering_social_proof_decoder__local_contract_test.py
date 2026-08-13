# spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#req-009
# spec_ref: specs/feature-tree/circle-community/gathering-coordination/spec.md#sit-003
#
# 四锚点社会证明的发起级事件解码契约：
# - GatheringPublished 只接受 owner outbox 的 published 事实；身份漂移、缺
#   organizer、非 published 生命周期一律拒收。
# - sourceRefs 可为空（无溯源的行动只进发起人锚点）；引用身份不完整拒收。
# - 读面 anchorKind 只接受 organizer/entity/content/creator 闭集。
from __future__ import annotations

import json

import pytest

from internal.recommendation.recommendation_feature_profile_view.adapters.inbound.stream.gathering_publication_consumer import (
    decode_gathering_publication,
)
from internal.recommendation.recommendation_feature_profile_view.application.intersection_reader import (
    Reader,
)


def _publication_values(**overrides) -> dict[str, str]:
    payload = {
        "gatheringId": "gathering-001",
        "actorPersonaId": "persona-organizer",
        "lifecycleStatus": "published",
        "sourceRefs": [
            {"objectKind": "content", "objectId": "post-seed-1"},
            {"objectKind": "place", "objectId": "homepage-1"},
        ],
    }
    payload.update(overrides.pop("payload", {}))
    values = {
        "eventId": "evt-publication-1",
        "eventType": "GatheringPublished",
        "aggregateType": "Gathering",
        "aggregateId": "gathering-001",
        "aggregateVersion": "5",
        "occurredAt": "2026-08-12T12:00:00Z",
        "payload": json.dumps(payload),
    }
    values.update(overrides)
    return values


def test_publication_decode_accepts_canonical_event() -> None:
    event = decode_gathering_publication(_publication_values())
    assert event is not None
    assert event.gathering_id == "gathering-001"
    assert event.organizer_id == "persona-organizer"
    assert event.source_refs == (
        ("content", "post-seed-1"),
        ("place", "homepage-1"),
    )
    assert event.version == 5
    assert event.event_digest


def test_publication_decode_ignores_other_events() -> None:
    assert (
        decode_gathering_publication(
            _publication_values(eventType="GatheringParticipationChanged")
        )
        is None
    )


def test_publication_decode_rejects_identity_drift_and_missing_organizer() -> None:
    with pytest.raises(ValueError):
        decode_gathering_publication(
            _publication_values(payload={"gatheringId": "gathering-other"})
        )
    with pytest.raises(ValueError):
        decode_gathering_publication(
            _publication_values(payload={"actorPersonaId": ""})
        )
    with pytest.raises(ValueError):
        decode_gathering_publication(
            _publication_values(payload={"lifecycleStatus": "draft"})
        )


def test_publication_decode_allows_empty_refs_rejects_incomplete_ref() -> None:
    event = decode_gathering_publication(
        _publication_values(payload={"sourceRefs": []})
    )
    assert event is not None
    assert event.source_refs == ()
    with pytest.raises(ValueError):
        decode_gathering_publication(
            _publication_values(
                payload={"sourceRefs": [{"objectKind": "content", "objectId": ""}]}
            )
        )


class _RecordingStore:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def read_gathering_social_proof(self, *, anchor_kind: str, object_id: str):
        self.calls.append((anchor_kind, object_id))
        return {"publishedCount": 1, "formedCount": 1, "experiencedCount": 0}


class _UnusedMaterializer:
    pass


class _OpenSubjects:
    def exists(self, _subject_id: str) -> bool:
        return False


def test_publication_decode_carries_frozen_policy_dimensions() -> None:
    """发布时冻结的公开政策维度事实（漏斗活动特征切片）；旧事件缺字段归零。"""
    event = decode_gathering_publication(
        _publication_values(
            payload={"maxParticipants": 2, "admissionPolicy": "invite_only"}
        )
    )
    assert event is not None
    assert event.max_participants == 2
    assert event.admission_policy == "invite_only"

    legacy = decode_gathering_publication(_publication_values())
    assert legacy is not None
    assert legacy.max_participants == 0
    assert legacy.admission_policy == ""


def test_funnel_reader_rejects_invalid_capacity_tier() -> None:
    store = _RecordingStore()
    reader = Reader(store, _UnusedMaterializer(), _OpenSubjects())
    from datetime import datetime, timezone

    with pytest.raises(ValueError):
        reader.get_flywheel_funnel(
            window_from=datetime(2026, 8, 1, tzinfo=timezone.utc),
            window_to=datetime(2026, 8, 31, tzinfo=timezone.utc),
            capacity_tier="rating",
        )


def test_social_proof_reader_enforces_anchor_closed_set() -> None:
    store = _RecordingStore()
    reader = Reader(store, _UnusedMaterializer(), _OpenSubjects())

    counts = reader.get_gathering_social_proof(
        anchor_kind="organizer",
        object_id=" persona-1 ",
    )
    assert counts == {"publishedCount": 1, "formedCount": 1, "experiencedCount": 0}
    assert store.calls == [("organizer", "persona-1")]

    with pytest.raises(ValueError):
        reader.get_gathering_social_proof(anchor_kind="rating", object_id="x")
    with pytest.raises(ValueError):
        reader.get_gathering_social_proof(anchor_kind="entity", object_id="  ")
