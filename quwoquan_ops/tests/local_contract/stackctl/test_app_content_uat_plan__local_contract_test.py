"""Release-bound App content UAT plan consumes exact Data-owned bytes.

spec_ref: specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-001.t6
spec_ref: specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-004.t1
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from quwoquan_ops.cli.lib.app_content_uat_plan import (
    build_app_content_uat_plan,
    load_release_uat_sample_plan,
)

CARRIERS = ("homepage", "article", "image", "video")
ENTRIES = ("feed", "search", "recommendation", "direct_or_object_route")
DIGESTS = {
    "manifest": "sha256:" + "1" * 64,
    "pool": "sha256:" + "2" * 64,
    "source": "sha256:" + "3" * 64,
    "merkle": "sha256:" + "4" * 64,
    "contents": "sha256:" + "5" * 64,
    "entities": "sha256:" + "6" * 64,
}


def _canonical_digest(document: object) -> str:
    raw = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _readiness(
    *,
    release_id: str = "release-m100-a",
    eligible_homepages: int = 100,
) -> dict[str, object]:
    del eligible_homepages
    article_ids = [f"article-{index:03d}" for index in range(1, 101)]
    image_ids = [f"image-{index:03d}" for index in range(1, 101)]
    video_ids = [f"video-{index:03d}" for index in range(1, 11)]
    return {
        "releaseId": release_id,
        "releaseClass": "research",
        "productLifecycleState": "research",
        "manifestDigest": DIGESTS["manifest"],
        "sourceIdentities": [{"executionId": "execution-a"}],
        "sourceIdentitySetDigest": DIGESTS["source"],
        "entityRefs": [f"/entity/place-{index:03d}" for index in range(1, 101)],
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


def _contents() -> list[dict[str, object]]:
    return [
        {
            "contentId": f"{carrier}-{index:03d}",
            "version": 1,
            "postRef": f"{carrier}/work-{index:03d}/1",
            "executionId": f"{carrier}-execution",
            "sourceIdentityDigest": DIGESTS["source"],
        }
        for carrier, count in (("article", 100), ("image", 100), ("video", 10))
        for index in range(1, count + 1)
    ]


def _selection_evidence() -> dict[str, str]:
    return {
        "poolDigest": DIGESTS["pool"],
        "sourceIdentitySetDigest": DIGESTS["source"],
        "canonicalMerkle": DIGESTS["merkle"],
        "releaseContentsDigest": DIGESTS["contents"],
        "releaseEntityCohortDigest": DIGESTS["entities"],
    }


def _release_digest(release_id: str, evidence: dict[str, str]) -> str:
    return _canonical_digest(
        {
            "schema": "quwoquan_data.release_uat_sample_plan_identity",
            "releaseId": release_id,
            "canonicalMerkle": evidence["canonicalMerkle"],
            "selectionEvidence": evidence,
        }
    )


def _samples() -> list[dict[str, str]]:
    distribution = {"homepage": 25, "article": 25, "image": 40, "video": 10}
    rows: list[dict[str, str]] = []
    for carrier, count in distribution.items():
        for ordinal in range(1, count + 1):
            rows.append(
                {
                    "sampleId": f"m100-{carrier}-{ordinal:03d}",
                    "carrier": carrier,
                    "objectId": (
                        f"/entity/place-{ordinal:03d}"
                        if carrier == "homepage"
                        else f"{carrier}-{ordinal:03d}"
                    ),
                    "objectRef": (
                        f"objects/entities/place-{ordinal:03d}"
                        if carrier == "homepage"
                        else f"objects/posts/{carrier}/work-{ordinal:03d}/1"
                    ),
                    "objectDigest": _canonical_digest(
                        {"carrier": carrier, "ordinal": ordinal}
                    ),
                }
            )
    return rows


def _entry_carrier_cells() -> list[dict[str, str]]:
    return [
        {
            "entry": entry,
            "carrier": carrier,
            "applicability": "required",
            "specRef": "specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#req-006",
            "runnerClass": f"qwq.content_consumer.{entry}.{carrier}",
        }
        for entry in ENTRIES
        for carrier in CARRIERS
    ]


def _sample_plan(*, eligible_homepages: int = 100) -> dict[str, object]:
    evidence = _selection_evidence()
    distribution = {"homepage": 25, "article": 25, "image": 40, "video": 10}
    release_digest = _release_digest("release-m100-a", evidence)
    return {
        "schema": "quwoquan_data.release_uat_sample_plan",
        "releaseId": "release-m100-a",
        "releaseDigest": release_digest,
        "milestone": "M100",
        "selectionEvidence": evidence,
        "eligiblePopulationCounts": {
            "homepage": eligible_homepages,
            "article": 120,
            "image": 140,
            "video": 15,
        },
        "exactCohortCounts": {
            "homepage": 100,
            "article": 100,
            "image": 100,
            "video": 10,
        },
        "entryCarrierCells": _entry_carrier_cells(),
        "sampleStrategy": {
            "name": "stratified_exact",
            "version": 1,
            "seedDigest": _canonical_digest(
                {
                    "releaseDigest": release_digest,
                    "sampleDistribution": distribution,
                }
            ),
            "carrierOrder": list(CARRIERS),
            "sortKey": "identity",
            "direction": "ascending",
            "objectDigestAlgorithm": "sha256-path-blob-merkle",
            "sampleDistribution": distribution,
        },
        "sampleCount": 100,
        "samples": _samples(),
    }


def _header(plan_digest: str) -> dict[str, object]:
    return {
        "schema": "quwoquan_data.release",
        "releaseId": "release-m100-a",
        "sourceOwner": "qwq_data",
        "releaseKind": "content",
        "releaseClass": "research",
        "productLifecycleState": "research",
        "selectionScope": "milestone",
        "milestone": "M100",
        "milestoneTargets": {
            "homepage": 100,
            "article": 100,
            "image": 100,
            "video": 10,
        },
        "poolDigest": DIGESTS["pool"],
        "canonicalMerkle": DIGESTS["merkle"],
        "sourceIdentities": [{"executionId": "execution-a"}],
        "sourceIdentitySetDigest": DIGESTS["source"],
        "contents": _contents(),
        "samplePlanRef": "uat/sample_plan.json",
        "samplePlanDigest": plan_digest,
    }


def _build(
    *,
    readiness: dict[str, object] | None = None,
    sample_plan: dict[str, object] | None = None,
    header_digest: str | None = None,
) -> dict[str, object]:
    resolved_plan = sample_plan or _sample_plan()
    observed_digest = _canonical_digest(resolved_plan)
    return build_app_content_uat_plan(
        readiness or _readiness(),
        release_header=_header(header_digest or observed_digest),
        release_uat_sample_plan=resolved_plan,
        release_uat_sample_plan_digest=observed_digest,
        release_payload_sha256=DIGESTS["manifest"],
    )


def test_uat_plan__missing_header_and_sample_plan_fail_closed__local_contract() -> None:
    readiness = _readiness()
    readiness["counts"] = {
        "entities": 100,
        "posts": 210,
        "premiumPlayableVideos": 10,
    }

    with pytest.raises(ValueError, match="explicit release header is missing"):
        build_app_content_uat_plan(readiness)
    with pytest.raises(ValueError, match="ReleaseUatSamplePlan is missing"):
        build_app_content_uat_plan(
            readiness, release_header=_header("sha256:" + "9" * 64)
        )


def test_uat_plan__retired_readiness_envelope_fails_closed__local_contract() -> None:
    readiness = _readiness()
    readiness["appUatEnvelope"] = {"releaseId": readiness["releaseId"]}

    with pytest.raises(ValueError, match="retired fields: appUatEnvelope"):
        _build(readiness=readiness)


def test_uat_plan__projects_canonical_samples_and_required_cells__local_contract() -> None:
    plan = _build(sample_plan=_sample_plan(eligible_homepages=130))

    assert plan["releaseIdentity"]["releaseId"] == "release-m100-a"
    assert plan["releaseIdentity"]["payloadSha256"] == DIGESTS["manifest"]
    assert plan["releaseUatSamplePlanRef"] == "uat/sample_plan.json"
    assert len(plan["orderedSamples"]) == 100
    assert plan["orderedSamples"][0] == _samples()[0]
    assert len(plan["requiredCasePlan"]) == 16
    assert plan["requiredCasePlan"][0]["runnerClass"] == (
        "qwq.content_consumer.feed.homepage"
    )
    assert len(plan["searchCanaries"]) == 4
    assert plan["videoPagination"]["expectedWorkIds"] == [
        f"video-{index:03d}" for index in range(1, 11)
    ]
    assert plan["mediaChecks"]["homepageRecommendation"]["expectedPostIds"] == [
        *[f"article-{index:03d}" for index in range(1, 101)],
        *[f"image-{index:03d}" for index in range(1, 101)],
        *[f"video-{index:03d}" for index in range(1, 11)],
    ]
    assert plan["mediaChecks"]["typedVideo"]["expectedPostIds"] == [
        f"video-{index:03d}" for index in range(1, 11)
    ]
    # Legacy fixture has no premium_stream row; plan preserves the old typed-video
    # fallback only for that historical shape. Current readiness carries an exact
    # premium_stream row and strict Research tests exercise it directly.
    assert plan["mediaChecks"]["premiumVideo"]["expectedPostIds"] == [
        f"video-{index:03d}" for index in range(1, 11)
    ]
    assert "stratifiedSamples" not in plan
    assert "appUatEnvelope" not in plan


def test_uat_plan__eligible_overshoot_is_allowed_but_shortfall_fails__local_contract() -> None:
    _build(sample_plan=_sample_plan(eligible_homepages=130))

    with pytest.raises(ValueError, match="eligible population has a shortfall"):
        _build(sample_plan=_sample_plan(eligible_homepages=99))


def test_uat_plan__counts_cannot_infer_or_replace_explicit_plan__local_contract() -> None:
    readiness = _readiness()
    readiness["counts"] = {
        "entities": 999,
        "posts": 999,
        "premiumPlayableVideos": 99,
    }

    with pytest.raises(ValueError, match="ReleaseUatSamplePlan is missing"):
        build_app_content_uat_plan(
            readiness,
            release_header=_header("sha256:" + "9" * 64),
        )


def test_uat_plan__rejects_digest_release_and_distribution_drift__local_contract() -> None:
    with pytest.raises(ValueError, match="digest binding drifted"):
        _build(header_digest="sha256:" + "9" * 64)

    drifted_release = _sample_plan()
    drifted_release["releaseId"] = "release-other"
    with pytest.raises(ValueError, match="releaseId mismatch"):
        _build(sample_plan=drifted_release)

    drifted_distribution = _sample_plan()
    drifted_distribution["sampleStrategy"]["sampleDistribution"] = {  # type: ignore[index]
        "homepage": 25,
        "article": 26,
        "image": 39,
        "video": 10,
    }
    with pytest.raises(ValueError, match="distribution drifted"):
        _build(sample_plan=drifted_distribution)


def test_load_release_uat_sample_plan__uses_header_ref_and_exact_bytes__local_contract(
    tmp_path: Path,
) -> None:
    sample_plan = _sample_plan()
    raw = (
        json.dumps(sample_plan, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    path = tmp_path / "uat/sample_plan.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(raw)
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()

    loaded, ref, observed_digest = load_release_uat_sample_plan(
        release_root=tmp_path,
        release_header=_header(digest),
    )
    assert loaded == sample_plan
    assert ref == "uat/sample_plan.json"
    assert observed_digest == digest

    path.write_bytes(raw + b"\n")
    with pytest.raises(ValueError, match="digest drifted"):
        load_release_uat_sample_plan(
            release_root=tmp_path,
            release_header=_header(digest),
        )



def test_uat_plan__research_feed_projection_rejects_missing_or_nonrelease_ids__local_contract() -> None:
    readiness = _readiness()
    readiness["feedQueries"].append(
        {
            "name": "premium_stream",
            "query": "sort=recommend&channelId=premium_stream&limit=10",
            "matchedPostIds": ["video-001"],
        }
    )
    plan = _build(readiness=readiness)
    assert plan["mediaChecks"]["premiumVideo"]["expectedPostIds"] == ["video-001"]

    drifted = _readiness()
    drifted["feedQueries"].append(
        {
            "name": "premium_stream",
            "query": "sort=recommend&channelId=premium_stream&limit=10",
            "matchedPostIds": ["other-release-video"],
        }
    )
    with pytest.raises(ValueError, match="not release-bound"):
        _build(readiness=drifted)
