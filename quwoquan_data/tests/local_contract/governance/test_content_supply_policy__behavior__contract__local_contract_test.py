"""Reusable supply policy contains quality rules, never a campaign target list."""
from __future__ import annotations

from governance.content_supply_policy import load_content_supply_policy


def test_content_supply_policy__carrier_requirements__contract__local_contract() -> None:
    policy = load_content_supply_policy("travel")

    assert policy.policy_id == "travel-content-supply"
    assert policy.feed_minimum_posts > 0
    assert policy.content_mix.total_per_entity == (
        policy.content_mix.article
        + policy.content_mix.image
        + policy.content_mix.video
    )
    assert policy.non_empty_rate_minimum > 0
    assert policy.duplicate_exposure_rate_maximum >= 0
    assert 0 < policy.homepage_max_source_fidelity < 1
    assert policy.media_subject.prohibited_indicator(
        "Test Entity A holotype in dorsal view"
    ) == "holotype"
    assert policy.media_subject.prohibited_indicator("Test Entity A scenic view") == ""
    assert policy.media_subject.prohibited_indicator(
        "Habitat landscape of a new species sp. nov."
    ) == ""


def test_content_supply_policy__video_delivery__contract__local_contract() -> None:
    video = load_content_supply_policy("travel").video_delivery

    assert (video.container, video.codec, video.aspect_ratio) == ("mp4", "h264", "9:16")
    assert video.width > 0 and video.height > video.width
    assert video.minimum_duration_seconds <= video.maximum_duration_seconds
    assert 0 < video.minimum_source_frames < video.minimum_segment_count
    assert video.minimum_segment_count > 0
