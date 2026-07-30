"""Release probes fail closed on empty discovery, video-book and premium feeds.

spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/feed-fallback-degrade/spec.md#gwt-001
"""

from __future__ import annotations

from argparse import Namespace

import pytest

from quwoquan_ops.cli.probes import run_environment_integration_probe as probe


def _args() -> Namespace:
    return Namespace(
        env="gamma",
        base_url="https://api.gamma.quwoquan.com",
        product_ops_base_url="",
        media_image_base_url="",
        release_readiness="",
        test_auth_token="",
        require_non_empty_content_feed=True,
    )


def test_release_content_probe__uses_exact_home_video_and_premium_queries__local_contract() -> (
    None
):
    checks = {item["name"]: item for item in probe.build_checks(_args())}

    assert "identity=work&sort=recommend" in checks["content_feed"]["url"]
    assert "identity=work&type=video&sort=recommend" in checks["video_book_feed"]["url"]
    assert "channelId=premium_stream" in checks["premium_feed"]["url"]


def test_release_content_probe__rejects_empty_feed_envelopes__local_contract() -> None:
    issue, count = probe._content_feed_semantic_issue('{"items": []}')

    assert count == 0
    assert issue == 'response payload has empty "items"'


def test_release_content_probe__rejects_non_release_item_even_when_non_empty__local_contract() -> (
    None
):
    issue, count, returned = probe._content_feed_semantic_result(
        '{"items":[{"postId":"unrelated-user-post"}]}',
        expected_post_ids={"pilot-002-video"},
    )

    assert count == 1
    assert returned == {"unrelated-user-post"}
    assert issue == "response has no postId bound to the expected immutable release"


def test_release_content_probe__accepts_expected_release_post_id__local_contract() -> (
    None
):
    issue, count, returned = probe._content_feed_semantic_result(
        '{"items":[{"postId":"pilot-002-video"}]}',
        expected_post_ids={"pilot-002-video"},
    )

    assert issue is None
    assert count == 1
    assert returned == {"pilot-002-video"}


def test_release_media_probe__has_no_fixture_or_parallel_default_identity__local_contract() -> (
    None
):
    args = _args()
    args.media_image_base_url = "https://cdn.gamma.quwoquan.com/media/image"
    checks = {
        item["name"]: item
        for item in probe.build_checks(
            args,
            release_identity={
                "media": {
                    "assetId": "asset-image-a",
                    "version": 3,
                    "publicSliceKey": "media/image/s/asset/asset-image-a/v3/source.webp",
                    "sha256": f"sha256:{'1' * 64}",
                    "contentType": "image/webp",
                },
            },
        )
    }

    assert checks["media_sample"]["url"] == (
        "https://cdn.gamma.quwoquan.com/media/image/s/asset/asset-image-a/"
        "v3/source.webp"
    )
    assert "fixture" not in checks["media_sample"]["url"]


def test_release_media_probe__missing_readiness_is_gate_block__local_contract() -> None:
    args = _args()
    args.media_image_base_url = "https://cdn.gamma.quwoquan.com/media/image"

    with pytest.raises(probe.ReleaseVideoDeliveryError, match="required"):
        probe._release_probe_identity(args)
