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


def test_research_convergence__accepts_no_active_release_empty_page__local_contract() -> (
    None
):
    issue, count = probe._research_anonymous_convergence_issue(
        json.dumps(
            {
                "items": [],
                "objectCards": [],
                "outcome": "empty",
                "emptyReason": "no_active_release",
                "feedRequestId": "frq_01",
            }
        )
    )

    assert issue is None
    assert count == 0


def test_research_convergence__rejects_no_eligible_content_even_without_identity__local_contract() -> None:
    issue, count = probe._research_anonymous_convergence_issue(
        json.dumps(
            {
                "items": [],
                "objectCards": [],
                "outcome": "empty",
                "emptyReason": "no_eligible_content",
            }
        )
    )

    assert count == 0
    assert issue == (
        'research convergence expects emptyReason "no_active_release", '
        'got "no_eligible_content"'
    )


def test_research_convergence__rejects_release_bound_no_eligible_content_identity__local_contract() -> None:
    issue, count = probe._research_anonymous_convergence_issue(
        json.dumps(
            {
                "items": [],
                "objectCards": [],
                "outcome": "empty",
                "emptyReason": "no_eligible_content",
                "releaseId": "research-release",
                "manifestDigest": "sha256:" + "a" * 64,
            }
        )
    )

    assert count == 0
    assert issue is not None and "no_active_release" in issue


def test_research_convergence__rejects_leaked_items__local_contract() -> None:
    issue, count = probe._research_anonymous_convergence_issue(
        json.dumps(
            {
                "items": [{"postId": "research-post"}],
                "objectCards": [],
                "outcome": "content",
            }
        )
    )

    assert count == 1
    assert issue is not None and "research isolation leak" in issue


@pytest.mark.parametrize(
    ("payload", "expected_fragment"),
    [
        (
            {
                "items": [],
                "objectCards": [],
                "outcome": "empty",
                "emptyReason": "no_active_release",
                "releaseId": "rel-research-001",
            },
            "echoes release identity",
        ),
        (
            {"items": [], "objectCards": [], "outcome": "content"},
            'expects outcome "empty"',
        ),
    ],
)
def test_research_convergence__rejects_wrong_empty_semantics__local_contract(
    payload: dict[str, object],
    expected_fragment: str,
) -> None:
    issue, _count = probe._research_anonymous_convergence_issue(json.dumps(payload))

    assert issue is not None and expected_fragment in issue


def test_research_convergence__mode_builds_feed_checks_and_report_flag__local_contract() -> (
    None
):
    args = _args()
    args.require_non_empty_content_feed = False
    args.research_anonymous_convergence = True

    checks = {item["name"] for item in probe.build_checks(args)}

    assert {"content_feed", "video_book_feed", "premium_feed"} <= checks


def test_research_convergence__all_private_feeds_are_explicitly_anonymous__local_contract() -> None:
    args = _args()
    args.require_non_empty_content_feed = False
    args.research_anonymous_convergence = True
    args.test_auth_token = "ambient-non-research-token"

    checks = {row["name"]: row for row in probe.build_checks(args)}

    for name in probe.PRIVATE_FEED_CHECK_NAMES:
        assert "Authorization" not in checks[name]["headers"]


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


def test_author_posts_contract__accepts_contract_subset_page__local_contract() -> None:
    issue, count = probe._author_posts_semantic_result(
        json.dumps(
            {
                "items": [
                    {
                        "postId": "article-001",
                        "contentType": "article",
                        "authorId": "persona-a",
                        "authorDisplayName": "灯塔观察员",
                        "likeCount": 0,
                        "commentCount": 0,
                        "shareCount": 0,
                    }
                ],
                "hasMore": False,
            }
        )
    )

    assert issue is None
    assert count == 1


@pytest.mark.parametrize(
    "unknown_field",
    ["status", "visibility", "viewCount", "authorDisplayNameSnapshot"],
)
def test_author_posts_contract__rejects_leaked_internal_fields__local_contract(
    unknown_field: str,
) -> None:
    # 回归 gamma 真实事故：ListUserPosts 泄露契约外字段导致 App
    # ContentPostProjection decoder 整页失败（作者主页「记录」错误态）。
    issue, count = probe._author_posts_semantic_result(
        json.dumps(
            {
                "items": [
                    {
                        "postId": "article-001",
                        unknown_field: "must-not-pass",
                    }
                ],
                "hasMore": False,
            }
        )
    )

    assert issue == (
        "response items[0] has unknown ContentPostProjection fields: "
        f"{unknown_field}"
    )
    assert count is None


def test_author_posts_contract__rejects_unknown_page_wrapper_field__local_contract() -> (
    None
):
    issue, count = probe._author_posts_semantic_result(
        '{"items":[],"hasMore":false,"totalCount":3}'
    )

    assert issue == "response has unknown AuthorPostPageSlice fields: totalCount"
    assert count is None


def test_author_posts_contract__chains_from_release_sample_author__local_contract() -> (
    None
):
    args = _args()
    args.release_sample = [
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
    args.only_check = [
        "release_sample",
        probe.AUTHOR_POSTS_CHECK_NAME,
    ]

    author_page = json.dumps(
        {
            "items": [
                {
                    "postId": "article-001",
                    "contentType": "article",
                    "authorId": "persona-a",
                    "likeCount": 0,
                    "commentCount": 0,
                    "shareCount": 0,
                }
            ],
            "hasMore": False,
        }
    )

    def _fake_request(method, url, **kwargs):
        if url.endswith("/content/posts/article-001"):
            return True, 200, json.dumps(
                {
                    "postId": "article-001",
                    "contentType": "article",
                    "authorId": "persona-a",
                }
            )
        if "/content/personas/persona-a/posts" in url:
            return True, 200, author_page
        raise AssertionError(f"unexpected probe request: {url}")

    original_request = probe.request
    probe.request = _fake_request
    try:
        report = probe.run_checks(args)
    finally:
        probe.request = original_request

    names = [item["name"] for item in report["checks"]]
    assert probe.AUTHOR_POSTS_CHECK_NAME in names
    author_entry = next(
        item
        for item in report["checks"]
        if item["name"] == probe.AUTHOR_POSTS_CHECK_NAME
    )
    assert author_entry["ok"] is True
    assert author_entry["authorPersonaId"] == "persona-a"
    assert author_entry["contentItemCount"] == 1
    assert report["status"] == "passed"


def test_feed_media_slices__collects_all_media_urls_from_feed_items__local_contract() -> (
    None
):
    urls = probe._feed_media_slice_urls(
        json.dumps(
            {
                "items": [
                    {
                        "postId": "post-image-a",
                        "mediaUrls": [
                            "media/image/s/asset/a/v1/source.webp",
                            "media/image/s/asset/b/v1/source.webp",
                        ],
                        "coverUrl": "media/image/s/asset/a/v1/source.webp",
                    },
                    {
                        "postId": "post-video-a",
                        "videoUrl": "media/video/s/asset/c/v1/source.mp4",
                        "thumbnailUrl": (
                            "https://cdn.gamma.quwoquan.com:19100/media/video/s/"
                            "asset/c/v1/source.mp4?variant=thumb"
                        ),
                    },
                ],
                "objectCards": [],
            }
        ),
        "https://cdn.gamma.quwoquan.com:19100",
    )

    assert urls == {
        "https://cdn.gamma.quwoquan.com:19100/media/image/s/asset/a/v1/source.webp": "image",
        "https://cdn.gamma.quwoquan.com:19100/media/image/s/asset/b/v1/source.webp": "image",
        "https://cdn.gamma.quwoquan.com:19100/media/video/s/asset/c/v1/source.mp4": "video",
        "https://cdn.gamma.quwoquan.com:19100/media/video/s/asset/c/v1/source.mp4?variant=thumb": "image",
    }


def test_feed_media_slices__missing_object_fails_run__local_contract() -> None:
    # 回归首页真实事故：feed items 正常返回，但 media-edge 缺对象导致
    # 图片灰块/视频黑屏；items 非空绝不等于媒体可显示。
    args = _args()
    args.media_image_base_url = "https://cdn.gamma.quwoquan.com:19100/media/image"
    args.release_readiness = ""
    args.only_check = ["content_feed", probe.FEED_MEDIA_SLICES_CHECK_NAME]

    feed_payload = json.dumps(
        {
            "items": [
                {
                    "postId": "post-image-a",
                    "contentType": "image",
                    "mediaUrls": ["media/image/s/asset/a/v1/source.webp"],
                    "likeCount": 0,
                    "commentCount": 0,
                    "shareCount": 0,
                },
                {
                    "postId": "post-video-a",
                    "contentType": "video",
                    "videoUrl": "media/video/s/asset/c/v1/source.mp4",
                    "likeCount": 0,
                    "commentCount": 0,
                    "shareCount": 0,
                },
            ],
            "objectCards": [],
        }
    )

    def _fake_request(method, url, **kwargs):
        if "/content/feed" in url:
            return True, 200, feed_payload
        if url.endswith("source.webp"):
            return True, 200, "bytes"
        if url.endswith("source.mp4"):
            return True, 404, "missing"
        raise AssertionError(f"unexpected probe request: {url}")

    original_request = probe.request
    original_identity = probe._release_probe_identity
    probe.request = _fake_request
    probe._release_probe_identity = lambda _args: None
    try:
        report = probe.run_checks(args)
    finally:
        probe.request = original_request
        probe._release_probe_identity = original_identity

    entry = next(
        item
        for item in report["checks"]
        if item["name"] == probe.FEED_MEDIA_SLICES_CHECK_NAME
    )
    assert entry["ok"] is False
    assert entry["sliceCount"] == 2
    assert any("source.mp4" in failure for failure in entry["sliceFailures"])
    assert report["status"] == "failed"
    assert any(
        probe.FEED_MEDIA_SLICES_CHECK_NAME in finding
        and "unreadable" in finding
        for finding in report["findings"]
    )


def test_feed_media_slices__all_readable_passes__local_contract() -> None:
    args = _args()
    args.media_image_base_url = "https://cdn.gamma.quwoquan.com:19100/media/image"
    args.release_readiness = ""
    args.only_check = ["content_feed", probe.FEED_MEDIA_SLICES_CHECK_NAME]

    feed_payload = json.dumps(
        {
            "items": [
                {
                    "postId": "post-image-a",
                    "contentType": "image",
                    "mediaUrls": ["media/image/s/asset/a/v1/source.webp"],
                    "likeCount": 0,
                    "commentCount": 0,
                    "shareCount": 0,
                }
            ],
            "objectCards": [],
        }
    )

    def _fake_request(method, url, **kwargs):
        if "/content/feed" in url:
            return True, 200, feed_payload
        if url.endswith("source.webp"):
            return True, 200, "bytes"
        raise AssertionError(f"unexpected probe request: {url}")

    original_request = probe.request
    original_identity = probe._release_probe_identity
    probe.request = _fake_request
    probe._release_probe_identity = lambda _args: None
    try:
        report = probe.run_checks(args)
    finally:
        probe.request = original_request
        probe._release_probe_identity = original_identity

    entry = next(
        item
        for item in report["checks"]
        if item["name"] == probe.FEED_MEDIA_SLICES_CHECK_NAME
    )
    assert entry["ok"] is True
    assert entry["sliceCount"] == 1
    assert report["status"] == "passed"


def test_author_posts_contract__leaked_field_fails_run__local_contract() -> None:
    args = _args()
    args.release_sample = [
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
    args.only_check = [
        "release_sample",
        probe.AUTHOR_POSTS_CHECK_NAME,
    ]

    def _fake_request(method, url, **kwargs):
        if url.endswith("/content/posts/article-001"):
            return True, 200, json.dumps(
                {
                    "postId": "article-001",
                    "contentType": "article",
                    "authorId": "persona-a",
                }
            )
        if "/content/personas/persona-a/posts" in url:
            return True, 200, json.dumps(
                {
                    "items": [{"postId": "article-001", "status": "published"}],
                    "hasMore": False,
                }
            )
        raise AssertionError(f"unexpected probe request: {url}")

    original_request = probe.request
    probe.request = _fake_request
    try:
        report = probe.run_checks(args)
    finally:
        probe.request = original_request

    assert report["status"] == "failed"
    assert any(
        probe.AUTHOR_POSTS_CHECK_NAME in finding
        and "unknown ContentPostProjection fields: status" in finding
        for finding in report["findings"]
    )


def _runtime_error_body(nature: str, action: str, after_seconds: object) -> str:
    return json.dumps(
        {
            "code": "GATEWAY.MIDDLEWARE.upstream_unavailable",
            "origin": "remoteDependency",
            "nature": nature,
            "module": "GATEWAY",
            "kind": "unavailable",
            "reason": "upstream_unavailable",
            "recovery": {"action": action, "afterSeconds": after_seconds},
        }
    )


def test_transient_retry__declared_recovery_directive_is_honoured__local_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """服务端声明 nature=transient + recovery.action=retry 时必须重试，
    且重试留痕，不把瞬时抖动误判为准出失败也不静默掩盖它。"""
    delay = probe._declared_transient_retry_delay(
        _runtime_error_body("transient", "retry", 1)
    )
    assert delay == 1.0


@pytest.mark.parametrize(
    "body",
    [
        _runtime_error_body("permanent", "retry", 1),
        _runtime_error_body("requiresPermission", "retry", 1),
        _runtime_error_body("bug", "retry", 1),
        _runtime_error_body("transient", "reauthenticate", 1),
        "not-json",
        "",
    ],
)
def test_transient_retry__non_transient_or_non_retry_stays_terminal__local_contract(
    body: str,
) -> None:
    assert probe._declared_transient_retry_delay(body) is None


def test_transient_retry__five_hundred_retries_and_four_hundred_does_not__local_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import urllib.error

    from quwoquan_ops.cli.probes import environment_probe_transport as transport

    monkeypatch.setattr(transport.time, "sleep", lambda _seconds: None)
    transient_body = _runtime_error_body("transient", "retry", 1).encode("utf-8")

    class _Body:
        def __init__(self, payload: bytes) -> None:
            self._payload = payload

        def read(self) -> bytes:
            return self._payload

        def close(self) -> None:
            return None

    def _raise(status: int, payload: bytes):
        def _open(_request, timeout=None):
            raise urllib.error.HTTPError(
                "https://api.invalid/probe", status, "err", {}, _Body(payload)
            )

        return _open

    monkeypatch.setattr(
        transport.urllib.request, "urlopen", _raise(503, transient_body)
    )
    trace: list[dict[str, object]] = []
    ok, status, _payload = probe.request(
        "POST",
        "https://api.invalid/probe",
        retry_attempts=3,
        retry_sleep_seconds=0.0,
        retry_trace=trace,
    )
    assert (ok, status) == (False, 503)
    assert [item["attempt"] for item in trace] == [1, 2]

    # 4xx 即使声明 transient 也不重试：客户端请求错误不是上游抖动。
    monkeypatch.setattr(
        transport.urllib.request, "urlopen", _raise(400, transient_body)
    )
    client_trace: list[dict[str, object]] = []
    ok, status, _payload = probe.request(
        "POST",
        "https://api.invalid/probe",
        retry_attempts=3,
        retry_sleep_seconds=0.0,
        retry_trace=client_trace,
    )
    assert (ok, status) == (False, 400)
    assert client_trace == []
