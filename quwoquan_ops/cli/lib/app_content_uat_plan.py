"""Build release-bound inputs consumed by App content UAT.

Small releases retain the canary plan.  Exact M100/M1000 readiness receipts
add a deterministic one-hundred-object sample matrix; execution evidence for
that matrix is produced by :mod:`app_content_uat_release_samples`, never by
this pure planner.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

VIDEO_PAGE_SIZE = 20
_MILESTONE_PROFILES: dict[str, dict[str, object]] = {
    "M100": {
        "counts": {"entities": 100, "posts": 210, "premiumPlayableVideos": 10},
        "population": {"homepage": 100, "article": 100, "image": 100, "video": 10},
        "samples": {"homepage": 25, "article": 25, "image": 40, "video": 10},
    },
    "M1000": {
        "counts": {
            "entities": 1000,
            "posts": 2100,
            "premiumPlayableVideos": 100,
        },
        "population": {
            "homepage": 1000,
            "article": 1000,
            "image": 1000,
            "video": 100,
        },
        "samples": {"homepage": 25, "article": 25, "image": 25, "video": 25},
    },
}


def _required_text(value: object, *, label: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"App content UAT {label} is missing")
    return normalized


def _release_post_ids(readiness: Mapping[str, Any]) -> set[str]:
    raw = readiness.get("postIds")
    if not isinstance(raw, list):
        raise ValueError("App content UAT release postIds are missing")
    values = [_required_text(item, label="postId") for item in raw]
    if len(values) != len(set(values)):
        raise ValueError("App content UAT release postIds are duplicated")
    return set(values)


def _query_post_ids(readiness: Mapping[str, Any], name: str) -> list[str]:
    matches: list[str] | None = None
    for raw_query in readiness.get("feedQueries") or []:
        if not isinstance(raw_query, Mapping) or raw_query.get("name") != name:
            continue
        if matches is not None:
            raise ValueError(f"App content UAT feed query {name} is duplicated")
        raw_matches = raw_query.get("matchedPostIds")
        if not isinstance(raw_matches, list):
            raise ValueError(f"App content UAT feed query {name} has no matches")
        matches = [
            _required_text(item, label=f"feedQueries.{name}.matchedPostId")
            for item in raw_matches
        ]
    if not matches:
        raise ValueError(f"App content UAT feed query {name} is empty")
    if len(matches) != len(set(matches)):
        raise ValueError(f"App content UAT feed query {name} has duplicate matches")
    return matches


def _exact_milestone(readiness: Mapping[str, Any]) -> str | None:
    raw_counts = readiness.get("counts")
    if not isinstance(raw_counts, Mapping):
        return None
    for milestone, profile in _MILESTONE_PROFILES.items():
        expected = profile["counts"]
        assert isinstance(expected, Mapping)
        if all(raw_counts.get(field) == value for field, value in expected.items()):
            return milestone
    return None


def _release_entity_refs(readiness: Mapping[str, Any]) -> list[str]:
    raw = readiness.get("entityRefs")
    if not isinstance(raw, list):
        raise ValueError("App content UAT release entityRefs are missing")
    values = [_required_text(item, label="entityRef") for item in raw]
    if len(values) != len(set(values)):
        raise ValueError("App content UAT release entityRefs are duplicated")
    return values


def _stratified_sample_plan(
    readiness: Mapping[str, Any],
    *,
    milestone: str,
    release_post_ids: set[str],
) -> dict[str, Any]:
    profile = _MILESTONE_PROFILES[milestone]
    population = profile["population"]
    distribution = profile["samples"]
    assert isinstance(population, Mapping)
    assert isinstance(distribution, Mapping)

    populations = {
        "homepage": sorted(_release_entity_refs(readiness)),
        "article": sorted(_query_post_ids(readiness, "typed_article")),
        "image": sorted(_query_post_ids(readiness, "typed_image")),
        "video": sorted(_query_post_ids(readiness, "typed_video")),
    }
    observed_population = {carrier: len(values) for carrier, values in populations.items()}
    if observed_population != dict(population):
        raise ValueError(
            f"App content UAT {milestone} carrier population is not exact: "
            f"{observed_population}"
        )

    typed_sets = {
        carrier: set(populations[carrier])
        for carrier in ("article", "image", "video")
    }
    if any(
        typed_sets[left].intersection(typed_sets[right])
        for index, left in enumerate(typed_sets)
        for right in tuple(typed_sets)[index + 1 :]
    ):
        raise ValueError(f"App content UAT {milestone} typed feed populations overlap")
    if set().union(*typed_sets.values()) != release_post_ids:
        raise ValueError(
            f"App content UAT {milestone} typed feeds do not exactly cover release postIds"
        )

    source_names = {
        "homepage": "entityRefs",
        "article": "feedQueries.typed_article",
        "image": "feedQueries.typed_image",
        "video": "feedQueries.typed_video",
    }
    cases: list[dict[str, object]] = []
    for carrier in ("homepage", "article", "image", "video"):
        sample_count = int(distribution[carrier])
        for ordinal, object_id in enumerate(populations[carrier][:sample_count], start=1):
            cases.append(
                {
                    "sampleId": f"{milestone.lower()}-{carrier}-{ordinal:03d}",
                    "carrier": carrier,
                    "sourceReadback": source_names[carrier],
                    "objectId": object_id,
                    "ordinal": ordinal,
                }
            )
    object_ids = [str(case["objectId"]) for case in cases]
    sample_ids = [str(case["sampleId"]) for case in cases]
    if len(cases) != 100 or len(object_ids) != len(set(object_ids)):
        raise ValueError(f"App content UAT {milestone} sample identities are not unique")
    if len(sample_ids) != len(set(sample_ids)):
        raise ValueError(f"App content UAT {milestone} sample IDs are not unique")
    return {
        "milestone": milestone,
        "selection": "lexicographic_prefix_v1",
        "sampleCount": 100,
        "distribution": dict(distribution),
        "cases": cases,
    }


def _video_canaries(work_ids: list[str]) -> list[dict[str, object]]:
    positions = (
        ("first", 0),
        ("middle", len(work_ids) // 2),
        ("last", len(work_ids) - 1),
    )
    selected: list[dict[str, object]] = []
    observed: set[str] = set()
    for position, index in positions:
        work_id = work_ids[index]
        if work_id in observed:
            continue
        observed.add(work_id)
        selected.append({"position": position, "index": index, "workId": work_id})
    return selected


def build_app_content_uat_plan(readiness: Mapping[str, Any]) -> dict[str, Any]:
    """Project Data readiness into user-visible Search and video UAT inputs.

    The plan never invents fixtures: every expected object comes from the exact
    release envelope or one release-bound feed query.
    """

    raw_envelope = readiness.get("appUatEnvelope")
    if not isinstance(raw_envelope, Mapping):
        raise ValueError("App content UAT appUatEnvelope is missing")
    envelope = {
        key: _required_text(raw_envelope.get(key), label=f"appUatEnvelope.{key}")
        for key in (
            "releaseId",
            "homepageId",
            "homepageTitle",
            "articleWorkId",
            "articleTitle",
            "imageWorkId",
            "imageTitle",
            "videoWorkId",
            "creatorName",
            "creatorPersonaId",
            "creatorAvatarAssetId",
        )
    }
    release_id = _required_text(readiness.get("releaseId"), label="releaseId")
    if envelope["releaseId"] != release_id:
        raise ValueError("App content UAT appUatEnvelope releaseId mismatch")

    release_post_ids = _release_post_ids(readiness)
    expected_posts = {
        envelope["articleWorkId"],
        envelope["imageWorkId"],
        envelope["videoWorkId"],
    }
    if not expected_posts.issubset(release_post_ids):
        raise ValueError("App content UAT envelope posts are not release-bound")

    video_work_ids = _query_post_ids(readiness, "typed_video")[:VIDEO_PAGE_SIZE]
    if not set(video_work_ids).issubset(release_post_ids):
        raise ValueError("App content UAT video page is not release-bound")
    if envelope["videoWorkId"] not in video_work_ids:
        raise ValueError("App content UAT envelope video is not in the first video page")

    recommendation_ids = set(_query_post_ids(readiness, "homepage_recommend"))
    if not recommendation_ids.issubset(release_post_ids):
        raise ValueError("App content UAT homepage recommendation is not release-bound")

    plan = {
        "releaseId": release_id,
        "searchCanaries": [
            {
                "kind": "post",
                "query": envelope["articleTitle"],
                "expectedObjectType": "content.post",
                "expectedObjectId": envelope["articleWorkId"],
            },
            {
                "kind": "homepage",
                "query": envelope["homepageTitle"],
                "expectedObjectType": "entity.homepage",
                "expectedObjectId": envelope["homepageId"],
            },
            {
                "kind": "persona",
                "query": envelope["creatorName"],
                "expectedObjectType": "user.profile",
                "expectedObjectId": envelope["creatorPersonaId"],
            },
        ],
        "videoPagination": {
            "pageSize": VIDEO_PAGE_SIZE,
            "expectedWorkIds": video_work_ids,
        },
        "videoPlaybackCanaries": _video_canaries(video_work_ids),
        "mediaChecks": {
            "automatic": True,
            "avatarAssetId": envelope["creatorAvatarAssetId"],
            "imageWorkId": envelope["imageWorkId"],
            "videoWorkIds": video_work_ids,
        },
    }
    milestone = _exact_milestone(readiness)
    if milestone is not None:
        plan["stratifiedSamples"] = _stratified_sample_plan(
            readiness,
            milestone=milestone,
            release_post_ids=release_post_ids,
        )
    return plan
