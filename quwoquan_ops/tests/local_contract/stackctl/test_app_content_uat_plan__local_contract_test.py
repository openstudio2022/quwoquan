"""Release-bound, user-readable App content UAT plan contract.

spec_ref: specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-001
"""

from __future__ import annotations

from quwoquan_ops.cli.lib.app_content_uat_plan import build_app_content_uat_plan


def _readiness(video_count: int) -> dict[str, object]:
    video_ids = [f"video-{index:02d}" for index in range(1, video_count + 1)]
    return {
        "releaseId": "release-m100-a",
        "postIds": ["article-a", "image-a", *video_ids],
        "feedQueries": [
            {
                "name": "typed_video",
                "matchedPostIds": video_ids,
            },
            {
                "name": "homepage_recommend",
                "matchedPostIds": ["article-a", "image-a", *video_ids],
            },
        ],
        "appUatEnvelope": {
            "releaseId": "release-m100-a",
            "releaseClass": "research",
            "productLifecycleState": "research",
            "homepageId": "homepage-harbour",
            "homepageTitle": "海港灯塔",
            "articleWorkId": "article-a",
            "articleTitle": "灯塔维护手记",
            "imageWorkId": "image-a",
            "imageTitle": "潮汐时刻",
            "videoWorkId": video_ids[0],
            "creatorName": "灯塔观察员",
            "creatorUserHandle": "lighthouse_observer",
            "creatorPersonaId": "persona-lighthouse",
            "creatorAvatarAssetId": "avatar-lighthouse",
            "tagLabel": "海港",
            "videoAttribution": "公开来源",
        },
    }


def _milestone_readiness(milestone: str) -> dict[str, object]:
    if milestone == "M100":
        homepages, articles, images, videos = 100, 100, 100, 10
    else:
        homepages, articles, images, videos = 1000, 1000, 1000, 100
    article_ids = [f"article-{index:04d}" for index in range(articles, 0, -1)]
    image_ids = [f"image-{index:04d}" for index in range(images, 0, -1)]
    video_ids = [f"video-{index:04d}" for index in range(videos, 0, -1)]
    entity_refs = [f"/entity/place-{index:04d}" for index in range(homepages, 0, -1)]
    readiness = _readiness(videos)
    readiness.update(
        {
            "counts": {
                "entities": homepages,
                "posts": articles + images + videos,
                "premiumPlayableVideos": videos,
            },
            "entityRefs": entity_refs,
            "postIds": [*article_ids, *image_ids, *video_ids],
            "feedQueries": [
                {"name": "typed_article", "matchedPostIds": article_ids},
                {"name": "typed_image", "matchedPostIds": image_ids},
                {"name": "typed_video", "matchedPostIds": video_ids},
                {
                    "name": "homepage_recommend",
                    "matchedPostIds": [*article_ids, *image_ids, *video_ids],
                },
            ],
        }
    )
    envelope = dict(readiness["appUatEnvelope"])  # type: ignore[arg-type]
    envelope.update(
        {
            "articleWorkId": article_ids[0],
            "imageWorkId": image_ids[0],
            "videoWorkId": video_ids[0],
        }
    )
    readiness["appUatEnvelope"] = envelope
    return readiness


def test_uat_plan__derives_release_search_and_twenty_video_page__local_contract() -> None:
    plan = build_app_content_uat_plan(_readiness(20))

    assert plan["releaseId"] == "release-m100-a"
    assert plan["videoPagination"] == {
        "pageSize": 20,
        "expectedWorkIds": [
            f"video-{index:02d}" for index in range(1, 21)
        ],
    }
    assert plan["videoPlaybackCanaries"] == [
        {"position": "first", "index": 0, "workId": "video-01"},
        {"position": "middle", "index": 10, "workId": "video-11"},
        {"position": "last", "index": 19, "workId": "video-20"},
    ]
    assert plan["searchCanaries"] == [
        {
            "kind": "post",
            "query": "灯塔维护手记",
            "expectedObjectType": "content.post",
            "expectedObjectId": "article-a",
        },
        {
            "kind": "homepage",
            "query": "海港灯塔",
            "expectedObjectType": "entity.homepage",
            "expectedObjectId": "homepage-harbour",
        },
        {
            "kind": "persona",
            "query": "灯塔观察员",
            "expectedObjectType": "user.profile",
            "expectedObjectId": "persona-lighthouse",
        },
    ]
    assert "西湖" not in str(plan)


def test_uat_plan__deduplicates_first_middle_last_for_one_video__local_contract() -> None:
    plan = build_app_content_uat_plan(_readiness(1))

    assert plan["videoPlaybackCanaries"] == [
        {"position": "first", "index": 0, "workId": "video-01"},
    ]


def test_uat_plan__m100_uses_exact_deterministic_stratified_matrix__local_contract() -> None:
    plan = build_app_content_uat_plan(_milestone_readiness("M100"))

    samples = plan["stratifiedSamples"]
    assert samples["milestone"] == "M100"
    assert samples["sampleCount"] == 100
    assert samples["distribution"] == {
        "homepage": 25,
        "article": 25,
        "image": 40,
        "video": 10,
    }
    cases = samples["cases"]
    assert len(cases) == 100
    assert cases[0] == {
        "sampleId": "m100-homepage-001",
        "carrier": "homepage",
        "sourceReadback": "entityRefs",
        "objectId": "/entity/place-0001",
        "ordinal": 1,
    }
    assert cases[-1] == {
        "sampleId": "m100-video-010",
        "carrier": "video",
        "sourceReadback": "feedQueries.typed_video",
        "objectId": "video-0010",
        "ordinal": 10,
    }
    assert len({case["objectId"] for case in cases}) == 100


def test_uat_plan__m1000_uses_twenty_five_per_carrier__local_contract() -> None:
    readiness = _milestone_readiness("M1000")
    plan = build_app_content_uat_plan(readiness)

    samples = plan["stratifiedSamples"]
    assert samples["milestone"] == "M1000"
    assert samples["distribution"] == {
        "homepage": 25,
        "article": 25,
        "image": 25,
        "video": 25,
    }
    assert len(samples["cases"]) == 100


def test_uat_plan__milestone_typed_populations_must_be_exact__local_contract() -> None:
    readiness = _milestone_readiness("M100")
    readiness["feedQueries"][0]["matchedPostIds"].pop()  # type: ignore[index]

    try:
        build_app_content_uat_plan(readiness)
    except ValueError as exc:
        assert "carrier population is not exact" in str(exc)
    else:
        raise AssertionError("M100 population shortfall must fail closed")
