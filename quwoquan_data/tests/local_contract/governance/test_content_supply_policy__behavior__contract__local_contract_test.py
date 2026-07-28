"""Reusable supply policy contains quality rules, never a campaign target list."""
from __future__ import annotations

from governance.content_supply_policy import load_content_supply_policy
from governance.coverage.vertical_inventory import list_verticals


def test_content_supply_policy__every_vertical_satisfies_the_contract__local_contract() -> None:
    """每个上架 vertical 的 content_policy.yaml 都必须能通过 schema 装载。

    历史缺陷：quality 新增 required 字段后只补了 travel，photography/campus 静默
    失效，直到某条真实链路第一次装载该 vertical 才在运行期炸开。
    """
    verticals = list_verticals()

    assert set(verticals) >= {"travel", "photography", "campus"}
    for vertical in verticals:
        policy = load_content_supply_policy(vertical)
        assert policy.homepage_minimum_body_chars > 0, vertical
        assert policy.homepage_minimum_section_chars > 0, vertical
        assert policy.homepage_source_outline_section_chars > 0, vertical


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
    assert policy.homepage_minimum_body_chars > 0
    assert policy.homepage_minimum_fact_count > 0
    assert policy.homepage_minimum_fact_chars > 0
    assert policy.homepage_minimum_fact_chars < policy.homepage_minimum_body_chars
    assert policy.homepage_minimum_section_chars < policy.homepage_minimum_body_chars
    assert policy.homepage_source_outline_section_chars > 0
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
