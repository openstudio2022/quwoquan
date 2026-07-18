"""Cold-start supply is a typed, master-list-backed launch contract."""
from __future__ import annotations

from collections import Counter

from core.control_types import RolloutMilestone
from governance.coverage.cold_start_supply import (
    cold_start_execution_parameters,
    load_cold_start_supply_policy,
)


def test_cold_start_supply_policy_closes_twenty_targets_and_sixty_posts() -> None:
    policy = load_cold_start_supply_policy()
    counts = Counter(target.province for target in policy.targets)

    assert counts == {"浙江省": 10, "四川省": 10}
    assert policy.content_mix.total_per_entity == 3
    assert policy.expected_post_count == 60
    assert policy.feed_minimum_posts == 20


def test_cold_start_video_delivery_is_vertical_h264_with_required_evidence() -> None:
    video = load_cold_start_supply_policy().video_delivery

    assert (video.width, video.height, video.aspect_ratio) == (1080, 1920, "9:16")
    assert (video.container, video.codec, video.pixel_format) == ("mp4", "h264", "yuv420p")
    assert (
        video.frames_per_second,
        video.segment_duration_seconds,
        video.minimum_duration_seconds,
        video.maximum_duration_seconds,
    ) == (24, 2, 6, 30)


def test_cold_start_execution_freezes_policy_targets_after_m3(monkeypatch) -> None:
    closed: list[RolloutMilestone] = []
    monkeypatch.setattr(
        "content.release.canonical.rollout_milestone.assert_milestone_closed",
        lambda milestone: closed.append(milestone),
    )

    parameters = cold_start_execution_parameters(
        execution_id="20260718--travel-video-cold-start--cn-zhejiang--m3-001"
    )

    assert closed == [RolloutMilestone.M3]
    assert parameters.province == "浙江省"
    assert parameters.limit == 10
    assert parameters.target_names[:2] == ("普陀山", "东钱湖")
    assert parameters.mandatory == ",".join(parameters.target_names)
