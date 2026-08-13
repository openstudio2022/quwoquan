# spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#sit-008
#
# 交集飞轮回流环的事件解码契约：
# - GatheringParticipationChanged：只接受 Gathering aggregate 的合法参与状态闭集；
#   身份漂移（payload gatheringId 与 aggregateId 不一致）、缺参与者、非法状态一律拒收。
# - Post 生命周期：gatheringRef 进入 canonical digest；公开可见 + 作者主动关联才构成
#   recap 事实；删除/隐私撤回事件 recap 回落 False（经历交集据此收敛）。
from __future__ import annotations

import json

import pytest

from internal.recommendation.recommendation_feature_profile_view.adapters.inbound.stream.gathering_participation_consumer import (
    decode_gathering_participation,
)
from internal.recommendation.recommendation_feature_profile_view.adapters.inbound.stream.post_lifecycle_consumer import (
    decode_post_lifecycle,
)


def _participation_values(**overrides) -> dict[str, str]:
    payload = {
        "gatheringId": "gathering-001",
        "participantPersonaId": "persona-b",
        "participationState": "active",
    }
    payload.update(overrides.pop("payload", {}))
    values = {
        "eventId": "evt-participation-1",
        "eventType": "GatheringParticipationChanged",
        "aggregateType": "Gathering",
        "aggregateId": "gathering-001",
        "aggregateVersion": "7",
        "occurredAt": "2026-08-12T12:00:00Z",
        "payload": json.dumps(payload),
    }
    values.update(overrides)
    return values


def test_participation_decode_accepts_canonical_event() -> None:
    event = decode_gathering_participation(_participation_values())
    assert event is not None
    assert event.gathering_id == "gathering-001"
    assert event.persona_id == "persona-b"
    assert event.state == "active"
    assert event.version == 7
    assert event.event_digest


def test_participation_decode_ignores_unsupported_events() -> None:
    assert (
        decode_gathering_participation(
            _participation_values(eventType="GatheringPublished")
        )
        is None
    )


def test_participation_decode_rejects_identity_drift() -> None:
    with pytest.raises(ValueError):
        decode_gathering_participation(
            _participation_values(payload={"gatheringId": "gathering-other"})
        )


def test_participation_decode_rejects_unknown_state_and_missing_persona() -> None:
    with pytest.raises(ValueError):
        decode_gathering_participation(
            _participation_values(payload={"participationState": "attended"})
        )
    with pytest.raises(ValueError):
        decode_gathering_participation(
            _participation_values(payload={"participantPersonaId": ""})
        )


def _post_values(**overrides) -> dict[str, str]:
    payload = {
        "postId": "post-001",
        "authorId": "persona-a",
        "authorDisplayNameSnapshot": "小雅",
        "authorAvatarUrlSnapshot": "",
        "status": "published",
        "visibility": "public",
        "moderationStatus": "approved",
        "primaryHomepageId": "",
        "visitedAt": "",
        "gatheringRef": "gathering-001",
    }
    payload.update(overrides.pop("payload", {}))
    values = {
        "eventId": "evt-post-1",
        "eventType": "PostPublished",
        "aggregateType": "Post",
        "aggregateId": "post-001",
        "aggregateVersion": "1",
        "occurredAt": "2026-08-12T12:30:00Z",
        "payload": json.dumps(payload),
    }
    values.update(overrides)
    return values


def test_post_decode_marks_public_gathering_recap() -> None:
    event = decode_post_lifecycle(_post_values())
    assert event is not None
    assert event.gathering_id == "gathering-001"
    assert event.recap is True


def test_post_decode_private_post_is_not_a_recap() -> None:
    event = decode_post_lifecycle(_post_values(payload={"visibility": "private"}))
    assert event is not None
    assert event.gathering_id == "gathering-001"
    assert event.recap is False


def test_post_decode_removal_clears_recap() -> None:
    event = decode_post_lifecycle(
        _post_values(
            eventType="PostDeleted",
            payload={"status": "", "visibility": "", "moderationStatus": ""},
        )
    )
    assert event is not None
    assert event.recap is False


def test_post_decode_digest_binds_gathering_ref() -> None:
    with_ref = decode_post_lifecycle(_post_values())
    without_ref = decode_post_lifecycle(_post_values(payload={"gatheringRef": ""}))
    assert with_ref is not None and without_ref is not None
    assert with_ref.event_digest != without_ref.event_digest
