"""Release probes fail closed on empty discovery, video-book and premium feeds.

spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/feed-fallback-degrade/spec.md#gwt-001
"""

from __future__ import annotations

import json
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


def test_release_content_probe__uses_twenty_video_page_and_exact_search_canaries__local_contract() -> None:
    args = _args()
    args.video_page_size = 20
    args.release_search_canary = [
        json.dumps(
            {
                "kind": "post",
                "query": "灯塔维护手记",
                "expectedObjectType": "content.post",
                "expectedObjectId": "article-a",
            },
            ensure_ascii=False,
        ),
        json.dumps(
            {
                "kind": "homepage",
                "query": "海港灯塔",
                "expectedObjectType": "entity.homepage",
                "expectedObjectId": "homepage-harbour",
            },
            ensure_ascii=False,
        ),
        json.dumps(
            {
                "kind": "persona",
                "query": "灯塔观察员",
                "expectedObjectType": "user.profile",
                "expectedObjectId": "persona-lighthouse",
            },
            ensure_ascii=False,
        ),
    ]

    checks = probe.build_checks(args)
    video = next(item for item in checks if item["name"] == "video_book_feed")
    searches = [item for item in checks if item["name"] == "global_search"]

    assert "limit=20" in video["url"]
    assert [item["searchCanaryKind"] for item in searches] == [
        "post",
        "homepage",
        "persona",
    ]
    assert [json.loads(item["body"])["query"] for item in searches] == [
        "灯塔维护手记",
        "海港灯塔",
        "灯塔观察员",
    ]
    assert "西湖" not in str(searches)


def test_release_content_probe__requires_exact_search_object_projection__local_contract() -> None:
    payload = json.dumps(
        {
            "requestId": "search-release-a",
            "hits": [
                {
                    "objectType": "content.post",
                    "objectId": "article-a",
                }
            ],
        }
    )

    issue, hit_count = probe._search_semantic_issue(
        payload,
        expected_object_type="content.post",
        expected_object_id="article-a",
    )
    missing, _ = probe._search_semantic_issue(
        payload,
        expected_object_type="entity.homepage",
        expected_object_id="homepage-harbour",
    )

    assert issue is None
    assert hit_count == 1
    assert missing == "response has no exact release-bound entity.homepage/homepage-harbour hit"


def test_release_content_probe__executes_exact_homepage_and_post_sample_reads__local_contract() -> None:
    args = _args()
    args.release_sample = [
        json.dumps(
            {
                "sampleId": "m100-homepage-001",
                "carrier": "homepage",
                "sourceReadback": "entityRefs",
                "sourceObjectId": "/entity/place-001",
                "ordinal": 1,
                "readObjectId": "homepage-001",
                "expectedContentType": "",
            }
        ),
        json.dumps(
            {
                "sampleId": "m100-article-001",
                "carrier": "article",
                "sourceReadback": "feedQueries.typed_article",
                "sourceObjectId": "article-001",
                "ordinal": 1,
                "readObjectId": "article-001",
                "expectedContentType": "article",
            }
        ),
    ]

    samples = [
        check for check in probe.build_checks(args) if check["name"] == "release_sample"
    ]

    assert [check["url"] for check in samples] == [
        "https://api.gamma.quwoquan.com/homepages/homepage-001",
        "https://api.gamma.quwoquan.com/content/posts/article-001",
    ]
    homepage = probe._release_sample_semantic_result(
        '{"homepageId":"homepage-001"}',
        carrier="homepage",
        read_object_id="homepage-001",
        expected_content_type="",
    )
    article = probe._release_sample_semantic_result(
        '{"postId":"article-001","contentType":"article"}',
        carrier="article",
        read_object_id="article-001",
        expected_content_type="article",
    )
    assert homepage == (None, "homepage-001", "")
    assert article == (None, "article-001", "article")


def test_release_content_probe__rejects_empty_feed_envelopes__local_contract() -> None:
    issue, count = probe._content_feed_semantic_issue(
        '{"items": [], "objectCards": []}'
    )

    assert count == 0
    assert issue == 'response payload has empty "items"'


def test_release_content_probe__rejects_non_release_item_even_when_non_empty__local_contract() -> (
    None
):
    issue, count, returned = probe._content_feed_semantic_result(
        '{"items":[{"postId":"unrelated-user-post"}],"objectCards":[]}',
        expected_post_ids={"pilot-002-video"},
    )

    assert count == 1
    assert returned == {"unrelated-user-post"}
    assert issue == "response has no postId bound to the expected immutable release"


def test_release_content_probe__accepts_expected_release_post_id__local_contract() -> (
    None
):
    issue, count, returned = probe._content_feed_semantic_result(
        json.dumps(
            {
                "items": [
                    {
                        "postId": "pilot-002-video",
                        "contentType": "video",
                        "likeCount": 0,
                        "commentCount": 0,
                        "shareCount": 0,
                    }
                ],
                "objectCards": [],
            }
        ),
        expected_post_ids={"pilot-002-video"},
    )

    assert issue is None
    assert count == 1
    assert returned == {"pilot-002-video"}


@pytest.mark.parametrize("unknown_field", ["sourceTaskId", "qualityScore"])
def test_release_content_probe__rejects_unknown_projection_field__local_contract(
    unknown_field: str,
) -> None:
    issue, count, returned = probe._content_feed_semantic_result(
        json.dumps(
            {
                "items": [
                    {
                        "postId": "pilot-002-video",
                        unknown_field: "must-not-pass",
                    }
                ],
                "objectCards": [],
            }
        ),
        expected_post_ids={"pilot-002-video"},
    )

    assert issue == (
        "response items[0] has unknown ContentPostProjection fields: "
        f"{unknown_field}"
    )
    assert count is None
    assert returned == set()


@pytest.mark.parametrize(
    ("payload", "expected_issue"),
    [
        ('[]', "response payload must be a JSON object"),
        ('{}', 'response payload is missing array "objectCards"'),
        ('{"items":[]}', 'response payload is missing array "objectCards"'),
        (
            '{"items":[],"objectCards":null}',
            'response payload is missing array "objectCards"',
        ),
        (
            '{"items":[],"objectCards":{}}',
            'response payload is missing array "objectCards"',
        ),
    ],
)
def test_release_content_probe__rejects_invalid_object_cards_envelope__local_contract(
    payload: str,
    expected_issue: str,
) -> None:
    issue, count, returned = probe._content_feed_semantic_result(payload)

    assert issue == expected_issue
    assert count is None
    assert returned == set()


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
