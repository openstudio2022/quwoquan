"""Research release strict environment probe contracts."""
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
        research_anonymous_convergence=False,
        research_consumer_readback=False,
        research_consumer_attestation="",
        expected_discovery_post_id=[],
        expected_homepage_recommend_post_id=[],
        expected_video_post_id=[],
        expected_premium_video_post_id=[],
        release_search_canary=[],
        release_sample=[],
        release_creator_profile=[],
        release_signed_media=[],
        only_check=[],
    )


def _strict_creator_profile() -> dict[str, str]:
    return {
        "creatorRef": "creator-a",
        "authorId": "author-a",
        "personaId": "persona-a",
        "displayName": "研究创作者",
        "avatarAssetId": "avatar-a",
        "avatarDeliveryRef": "media/objects/sha256/aa/avatar-a",
    }


def _strict_signed_assets() -> list[dict[str, object]]:
    return [
        {
            "assetId": "avatar-a",
            "kind": "avatar",
            "expectedBytes": 10,
            "expectedSha256": "sha256:" + "1" * 64,
            "expectedMimeType": "image/jpeg",
            "privateDeliveryRef": "media/objects/sha256/aa/avatar-a",
            "classifications": ["avatar"],
            "requireRange": False,
        },
        {
            "assetId": "image-a",
            "kind": "image",
            "expectedBytes": 20,
            "expectedSha256": "sha256:" + "2" * 64,
            "expectedMimeType": "image/webp",
            "privateDeliveryRef": "media/objects/sha256/bb/image-a",
            "classifications": ["image"],
            "requireRange": False,
        },
        {
            "assetId": "video-a",
            "kind": "video",
            "expectedBytes": 30,
            "expectedSha256": "sha256:" + "3" * 64,
            "expectedMimeType": "video/mp4",
            "privateDeliveryRef": "media/objects/sha256/cc/video-a",
            "classifications": ["typed_video", "premium_video"],
            "requireRange": True,
        },
    ]


def test_research_strict_probe__happy_path_executes_recommendation_creator_and_media__local_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = _args()
    args.require_non_empty_content_feed = True
    args.research_consumer_readback = True
    args.test_auth_token = "research-token"
    args.research_consumer_attestation = "attestation-secret"
    args.expected_homepage_recommend_post_id = ["post-image-a"]
    args.expected_video_post_id = ["post-video-a"]
    args.expected_premium_video_post_id = ["post-video-a"]
    args.release_creator_profile = [json.dumps(_strict_creator_profile())]
    args.release_signed_media = [json.dumps(row) for row in _strict_signed_assets()]
    args.only_check = [
        "homepage_recommend",
        probe.CREATOR_PROFILE_CHECK_NAME,
        probe.SIGNED_MEDIA_CHECK_NAME,
    ]

    feed_payload = json.dumps(
        {
            "items": [
                {
                    "postId": "post-image-a",
                    "contentType": "image",
                    "likeCount": 0,
                    "commentCount": 0,
                    "shareCount": 0,
                }
            ],
            "objectCards": [],
        }
    )
    creator_payload = json.dumps(
        {
            "personaId": "persona-a",
            "displayName": "研究创作者",
            "avatarUrl": "media/objects/sha256/aa/avatar-a?v=7",
        }
    )

    def fake_request(method, url, **kwargs):
        if "channelId=recommend" in url:
            assert kwargs["headers"]["Authorization"] == "Bearer research-token"
            return True, 200, feed_payload
        if url.endswith("/user/persona-a"):
            return True, 200, creator_payload
        raise AssertionError(f"unexpected strict request {method} {url}")

    signed_calls: list[str] = []

    def fake_signed_media(**kwargs):
        assert kwargs["session"].access_token == "research-token"
        assert kwargs["attestation_token"] == "attestation-secret"
        asset = kwargs["asset"]
        signed_calls.append(str(asset["assetId"]))
        ranged = bool(asset["requireRange"])
        return {
            "assetId": asset["assetId"],
            "kind": asset["kind"],
            "classifications": asset["classifications"],
            "statusCode": 200,
            "mimeType": asset["expectedMimeType"],
            "bytes": asset["expectedBytes"],
            "sha256": asset["expectedSha256"],
            "hashVerified": True,
            "signedUrlHash": "sha256:" + "f" * 64,
            "rangeRequested": ranged,
            "rangeStatusCode": 206 if ranged else 0,
            "rangeBytes": 2 if ranged else 0,
            "contentRange": "bytes 0-1/30" if ranged else "",
            "auditEventId": "audit-" + str(asset["assetId"]),
        }

    monkeypatch.setattr(probe, "request", fake_request)
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.research_isolation_runtime_probe.probe_release_bound_signed_media",
        fake_signed_media,
    )

    report = probe.run_checks(args)

    assert report["status"] == "passed"
    by_name = {row["name"]: row for row in report["checks"]}
    assert by_name["homepage_recommend"]["returnedPostIds"] == ["post-image-a"]
    assert by_name[probe.CREATOR_PROFILE_CHECK_NAME]["returnedPersonaId"] == "persona-a"
    media = by_name[probe.SIGNED_MEDIA_CHECK_NAME]
    assert media["executedAssetCount"] == 3
    assert signed_calls == ["avatar-a", "image-a", "video-a"]
    video = next(row for row in media["assets"] if row["kind"] == "video")
    assert video["rangeStatusCode"] == 206


@pytest.mark.parametrize(
    ("mutate", "expected_fragment"),
    [
        (
            lambda args: setattr(
                args,
                "expected_homepage_recommend_post_id",
                ["other-release-post"],
            ),
            "expected immutable release",
        ),
        (
            lambda args: setattr(
                args,
                "release_creator_profile",
                [
                    json.dumps(
                        {
                            **_strict_creator_profile(),
                            "avatarDeliveryRef": "media/objects/sha256/zz/wrong",
                        }
                    )
                ],
            ),
            "exact release avatar asset",
        ),
    ],
)
def test_research_strict_probe__recommendation_or_creator_drift_gate_blocks__local_contract(
    monkeypatch: pytest.MonkeyPatch,
    mutate,
    expected_fragment: str,
) -> None:
    args = _args()
    args.require_non_empty_content_feed = True
    args.research_consumer_readback = True
    args.test_auth_token = "research-token"
    args.research_consumer_attestation = "attestation-secret"
    args.expected_homepage_recommend_post_id = ["post-image-a"]
    args.release_creator_profile = [json.dumps(_strict_creator_profile())]
    args.release_signed_media = []
    args.only_check = ["homepage_recommend", probe.CREATOR_PROFILE_CHECK_NAME]
    mutate(args)

    def fake_request(method, url, **kwargs):
        if "channelId=recommend" in url:
            return True, 200, json.dumps(
                {
                    "items": [{"postId": "post-image-a"}],
                    "objectCards": [],
                }
            )
        if url.endswith("/user/persona-a"):
            return True, 200, json.dumps(
                {
                    "personaId": "persona-a",
                    "displayName": "研究创作者",
                    "avatarUrl": "media/objects/sha256/aa/avatar-a?v=7",
                }
            )
        raise AssertionError(url)

    monkeypatch.setattr(probe, "request", fake_request)
    report = probe.run_checks(args)

    assert report["status"] == "failed"
    assert any(expected_fragment in finding for finding in report["findings"])


def test_research_consumer_readback__all_private_feeds_use_bearer_and_exact_ids__local_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = _args()
    args.research_consumer_readback = True
    args.test_auth_token = "research-token"
    args.research_consumer_attestation = "attestation-secret"
    args.expected_discovery_post_id = ["post-discovery"]
    args.expected_homepage_recommend_post_id = ["post-home"]
    args.expected_video_post_id = ["post-video"]
    args.expected_premium_video_post_id = ["post-video"]
    args.only_check = list(probe.PRIVATE_FEED_CHECK_NAMES)
    expected_by_query = {
        "identity=work&sort=recommend": "post-discovery",
        "channelId=recommend": "post-home",
        "identity=work&type=video": "post-video",
        "channelId=premium_stream": "post-video",
    }
    seen: set[str] = set()

    def fake_request(_method, url, **kwargs):
        assert kwargs["headers"]["Authorization"] == "Bearer research-token"
        for query, post_id in expected_by_query.items():
            if query in url:
                seen.add(query)
                return True, 200, json.dumps(
                    {"items": [{"postId": post_id}], "objectCards": []}
                )
        raise AssertionError(url)

    monkeypatch.setattr(probe, "request", fake_request)
    report = probe.run_checks(args)

    assert report["status"] == "passed"
    assert seen == set(expected_by_query)
    rendered = json.dumps(report, ensure_ascii=False)
    assert "research-token" not in rendered
    assert "attestation-secret" not in rendered


def test_research_consumer_readback__missing_exact_feed_ids_fails_closed__local_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = _args()
    args.research_consumer_readback = True
    args.test_auth_token = "research-token"
    args.research_consumer_attestation = "attestation-secret"
    args.only_check = ["content_feed"]
    monkeypatch.setattr(
        probe,
        "request",
        lambda *_args, **_kwargs: (
            True,
            200,
            json.dumps(
                {"items": [{"postId": "post-discovery"}], "objectCards": []}
            ),
        ),
    )

    report = probe.run_checks(args)

    assert report["status"] == "failed"
    assert any(
        "requires exact immutable release post IDs for content_feed" in finding
        for finding in report["findings"]
    )


def test_research_consumer_readback__redacts_echoed_credentials_from_report__local_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = _args()
    args.research_consumer_readback = True
    args.test_auth_token = "research-token"
    args.research_consumer_attestation = "attestation-secret"
    args.expected_discovery_post_id = ["post-discovery"]
    args.only_check = ["content_feed"]
    monkeypatch.setattr(
        probe,
        "request",
        lambda *_args, **_kwargs: (
            True,
            200,
            json.dumps(
                {
                    "items": [{"postId": "post-discovery"}],
                    "objectCards": [],
                    "debugEcho": (
                        "Bearer research-token attestation-secret"
                    ),
                }
            ),
        ),
    )

    report = probe.run_checks(args)
    rendered = json.dumps(report, ensure_ascii=False)

    assert "research-token" not in rendered
    assert "attestation-secret" not in rendered
    assert rendered.count("[REDACTED]") >= 2


def test_research_consumer_readback__empty_feed_never_passes__local_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = _args()
    args.research_consumer_readback = True
    args.test_auth_token = "research-token"
    args.research_consumer_attestation = "attestation-secret"
    args.expected_discovery_post_id = ["post-discovery"]
    args.only_check = ["content_feed"]
    monkeypatch.setattr(
        probe,
        "request",
        lambda *_args, **_kwargs: (
            True,
            200,
            json.dumps(
                {
                    "items": [],
                    "objectCards": [],
                    "outcome": "empty",
                    "emptyReason": "no_eligible_content",
                    "releaseId": "research-release",
                    "manifestDigest": "sha256:" + "a" * 64,
                }
            ),
        ),
    )

    report = probe.run_checks(args)

    assert report["status"] == "failed"
    assert any('empty "items"' in finding for finding in report["findings"])


@pytest.mark.parametrize(
    ("assets", "expected_fragment"),
    [
        (
            lambda: [row for row in _strict_signed_assets() if "avatar" not in row["classifications"]],
            "classifications are incomplete",
        ),
        (
            lambda: [
                {**row, "requireRange": False}
                if row["kind"] == "video"
                else row
                for row in _strict_signed_assets()
            ],
            "identity is invalid",
        ),
    ],
)
def test_research_strict_probe__missing_category_or_video_range_fails_input__local_contract(
    assets,
    expected_fragment: str,
) -> None:
    args = _args()
    args.release_signed_media = [json.dumps(row) for row in assets()]

    with pytest.raises(ValueError, match=expected_fragment):
        probe.build_checks(args)
