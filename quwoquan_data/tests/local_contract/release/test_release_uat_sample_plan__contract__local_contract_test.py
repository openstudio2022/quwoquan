# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/spec.md#req-006
"""ReleaseUatSamplePlan is Data-owned, deterministic, and release-bound."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from content.release.canonical.release_uat_sampling_authority import (  # noqa: E402
    ReleaseUatSamplingAuthorityError,
    exact_byte_digest as authority_byte_digest,
    exact_document_bytes as authority_document_bytes,
)
from content.release.canonical.release_uat_sample_plan import (  # noqa: E402
    PLAN_REF,
    ReleaseUatSamplePlanError,
    build_release_uat_sample_plan,
    exact_document_bytes,
    exact_document_sha256,
    canonical_digest,
    release_identity_digest,
    release_object_digest,
    validate_release_uat_sample_plan,
)

DIGESTS = {
    "pool": "sha256:" + "1" * 64,
    "source": "sha256:" + "2" * 64,
    "merkle": "sha256:" + "3" * 64,
}


def _contents(counts: dict[str, int]) -> list[dict[str, object]]:
    return [
        {
            "contentId": f"{carrier}-{index:04d}",
            "version": 1,
            "postRef": f"{carrier}/work-{index:04d}/1",
            "executionId": "execution-a",
            "sourceIdentityDigest": DIGESTS["source"],
        }
        for carrier in ("article", "image", "video")
        for index in range(counts[carrier])
    ]


def _entities(count: int) -> list[str]:
    return [f"地点/景区/entity-{index:04d}" for index in range(count)]


def _release_objects(
    root: Path,
    *,
    contents: list[dict[str, object]],
    entities: list[str],
) -> Path:
    objects = root / "objects"
    for entity_ref in entities:
        path = objects / "entities" / entity_ref / "manifest.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"entityRef": entity_ref}, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    for row in contents:
        post_ref = str(row["postRef"])
        path = objects / "posts" / post_ref / "manifest.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(row, sort_keys=True) + "\n", encoding="utf-8")
    return objects


def _plan(
    tmp_path: Path,
    *,
    milestone: str | None = "M100",
    counts: dict[str, int] | None = None,
    eligible: dict[str, int] | None = None,
    sampling_authority: dict[str, object] | None = None,
):
    exact = counts or {"homepage": 100, "article": 100, "image": 100, "video": 10}
    contents = _contents(exact)
    entities = _entities(exact["homepage"])
    objects = _release_objects(tmp_path, contents=contents, entities=entities)
    return build_release_uat_sample_plan(
        release_id="release-m100",
        milestone=milestone,
        pool_digest=DIGESTS["pool"],
        source_identity_set_digest=DIGESTS["source"],
        canonical_merkle=DIGESTS["merkle"],
        release_contents=contents,
        entity_refs=entities,
        release_objects_root=objects,
        eligible_population_counts=eligible or exact,
        sampling_authority=sampling_authority,
    )


def _m1000_authority(*, release_id: str, release_digest: str) -> dict[str, object]:
    distribution = {"homepage": 13, "article": 17, "image": 19, "video": 7}
    return {
        "schema": "quwoquan_data.release_uat_sampling_authority",
        "milestone": "M1000",
        "releaseId": release_id,
        "releaseDigest": release_digest,
        "strategy": {
            "ref": "authority/m1000-strategy.json",
            "digest": "sha256:" + "4" * 64,
            "strategyId": "m1000-product-quality-v1",
            "sampleDistribution": distribution,
        },
        "productOwner": {
            "role": "product_owner",
            "ref": "authority/product.json",
            "digest": "sha256:" + "5" * 64,
            "authorityId": "product-owner-a",
            "authenticationContextDigest": "sha256:" + "6" * 64,
            "observedAt": "2026-08-30T00:00:00Z",
        },
        "qualityOwner": {
            "role": "quality_owner",
            "ref": "authority/quality.json",
            "digest": "sha256:" + "7" * 64,
            "authorityId": "quality-owner-b",
            "authenticationContextDigest": "sha256:" + "8" * 64,
            "observedAt": "2026-08-30T00:01:00Z",
        },
    }


def test_m1000_plan__requires_external_joint_authority_and_never_uses_auto_min(
    tmp_path: Path,
) -> None:
    counts = {"homepage": 1000, "article": 1000, "image": 1000, "video": 100}
    with pytest.raises(ReleaseUatSamplePlanError, match="AUTHORITY_MISSING"):
        _plan(tmp_path / "missing", milestone="M1000", counts=counts, eligible=counts)

    # releaseDigest is deterministic from these exact release inputs.
    provisional = _m1000_authority(release_id="release-m100", release_digest="sha256:" + "0" * 64)
    contents = _contents(counts)
    entities = _entities(counts["homepage"])
    objects = _release_objects(tmp_path / "approved", contents=contents, entities=entities)
    selection = {
        "poolDigest": DIGESTS["pool"],
        "sourceIdentitySetDigest": DIGESTS["source"],
        "canonicalMerkle": DIGESTS["merkle"],
        "releaseContentsDigest": canonical_digest(sorted(contents, key=lambda row: (str(row["contentId"]), int(row["version"]), str(row["postRef"])))),
        "releaseEntityCohortDigest": canonical_digest(sorted(entities)),
    }
    release_digest = release_identity_digest(
        release_id="release-m100", canonical_merkle=DIGESTS["merkle"],
        selection_evidence=selection,
    )
    provisional["releaseDigest"] = release_digest
    plan = build_release_uat_sample_plan(
        release_id="release-m100", milestone="M1000",
        pool_digest=DIGESTS["pool"], source_identity_set_digest=DIGESTS["source"],
        canonical_merkle=DIGESTS["merkle"], release_contents=contents,
        entity_refs=entities, release_objects_root=objects,
        eligible_population_counts=counts, sampling_authority=provisional,
    )
    assert plan["sampleStrategy"]["sampleDistribution"] == {
        "homepage": 13, "article": 17, "image": 19, "video": 7,
    }
    assert plan["sampleCount"] == 56
    assert plan["sampleStrategy"]["authority"] == provisional
    assert plan["sampleStrategy"]["sampleDistribution"] != {carrier: 100 for carrier in counts}

    drifted = dict(provisional)
    drifted["releaseDigest"] = "sha256:" + "9" * 64
    with pytest.raises(ReleaseUatSamplePlanError, match="AUTHORITY_DRIFT|SCHEMA_INVALID"):
        build_release_uat_sample_plan(
            release_id="release-m100", milestone="M1000",
            pool_digest=DIGESTS["pool"], source_identity_set_digest=DIGESTS["source"],
            canonical_merkle=DIGESTS["merkle"], release_contents=contents,
            entity_refs=entities, release_objects_root=objects,
            eligible_population_counts=counts, sampling_authority=drifted,
        )


def test_m100_plan__is_exact_stratified_deterministic_and_environment_neutral(
    tmp_path: Path,
) -> None:
    overshoot = {"homepage": 130, "article": 120, "image": 140, "video": 15}
    first = _plan(tmp_path / "first", eligible=overshoot)
    second = _plan(tmp_path / "second", eligible=overshoot)

    assert first == second
    assert first["milestone"] == "M100"
    assert first["eligiblePopulationCounts"] == overshoot
    assert first["exactCohortCounts"] == {
        "homepage": 100,
        "article": 100,
        "image": 100,
        "video": 10,
    }
    assert first["sampleStrategy"]["sampleDistribution"] == {
        "homepage": 25,
        "article": 25,
        "image": 40,
        "video": 10,
    }
    assert first["sampleCount"] == 100
    assert len({row["sampleId"] for row in first["samples"]}) == 100
    assert len({row["objectId"] for row in first["samples"]}) == 100
    assert len(first["entryCarrierCells"]) == 16
    assert all(row["applicability"] == "required" for row in first["entryCarrierCells"])
    assert all("specRef" in row and "runnerClass" in row for row in first["entryCarrierCells"])
    assert not {
        "environment", "target", "targetEnvironment", "package", "device", "deviceId"
    }.intersection(first)


def test_homepage_samples__come_from_actual_desired_entity_refs(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    homepage = [row for row in plan["samples"] if row["carrier"] == "homepage"]

    assert homepage[0] == {
        "sampleId": "m100-homepage-001",
        "carrier": "homepage",
        "objectId": "/entity/地点/景区/entity-0000",
        "objectRef": "objects/entities/地点/景区/entity-0000",
        "objectDigest": release_object_digest(
            tmp_path / "objects/entities/地点/景区/entity-0000"
        ),
    }
    assert {
        row["objectRef"].removeprefix("objects/entities/") for row in homepage
    }.issubset(set(_entities(100)))


def test_nonmilestone_plan__uses_one_baseline_per_required_carrier(
    tmp_path: Path,
) -> None:
    exact = {"homepage": 2, "article": 3, "image": 4, "video": 2}
    plan = _plan(tmp_path, milestone=None, counts=exact, eligible=exact)

    assert plan["milestone"] is None
    assert plan["exactCohortCounts"] == exact
    assert plan["sampleStrategy"]["name"] == "baseline_per_required_carrier"
    assert plan["sampleStrategy"]["sampleDistribution"] == {
        "homepage": 1,
        "article": 1,
        "image": 1,
        "video": 1,
    }
    assert [row["sampleId"] for row in plan["samples"]] == [
        "baseline-homepage-001",
        "baseline-article-001",
        "baseline-image-001",
        "baseline-video-001",
    ]


def test_plan__rejects_eligible_shortfall_and_release_selection_drift(
    tmp_path: Path,
) -> None:
    with pytest.raises(ReleaseUatSamplePlanError, match="ELIGIBLE_POPULATION_SHORTFALL"):
        _plan(
            tmp_path / "shortfall",
            eligible={"homepage": 99, "article": 100, "image": 100, "video": 10},
        )

    plan = _plan(tmp_path / "drift")
    plan["samples"][0]["objectId"] = "/entity/other"
    with pytest.raises(ReleaseUatSamplePlanError, match="SELECTION_DRIFT"):
        validate_release_uat_sample_plan(
            plan,
            release_contents=_contents(
                {"homepage": 100, "article": 100, "image": 100, "video": 10}
            ),
            entity_refs=_entities(100),
            release_objects_root=tmp_path / "drift/objects",
            expected_release_id="release-m100",
            expected_milestone="M100",
            expected_selection_evidence=plan["selectionEvidence"],
        )


def test_release_digest_has_no_payload_self_reference_and_exact_bytes_are_bound(
    tmp_path: Path,
) -> None:
    plan = _plan(tmp_path)
    expected_identity = {
        "schema": "quwoquan_data.release_uat_sample_plan_identity",
        "releaseId": "release-m100",
        "canonicalMerkle": DIGESTS["merkle"],
        "selectionEvidence": plan["selectionEvidence"],
    }
    expected_release_digest = "sha256:" + hashlib.sha256(
        json.dumps(expected_identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    assert plan["releaseDigest"] == expected_release_digest
    assert plan["releaseDigest"] != exact_document_sha256(plan)
    assert exact_document_sha256(plan) == "sha256:" + hashlib.sha256(
        exact_document_bytes(plan)
    ).hexdigest()
    assert PLAN_REF == "uat/sample_plan.json"


def test_schema__rejects_unknown_target_fact_and_invalid_na_cell(tmp_path: Path) -> None:
    plan = _plan(tmp_path / "unknown")
    plan["targetEnvironment"] = "alpha"
    with pytest.raises(ReleaseUatSamplePlanError, match="SCHEMA_INVALID"):
        validate_release_uat_sample_plan(plan, expected_milestone="M100")

    plan = _plan(tmp_path / "invalid-cell")
    plan["entryCarrierCells"][0] = {
        "entry": "feed",
        "carrier": "homepage",
        "applicability": "not_applicable",
    }
    with pytest.raises(ReleaseUatSamplePlanError, match="SCHEMA_INVALID"):
        validate_release_uat_sample_plan(plan, expected_milestone="M100")


def test_sample_binding__rejects_object_bytes_digest_and_ref_drift(tmp_path: Path) -> None:
    counts = {"homepage": 100, "article": 100, "image": 100, "video": 10}
    contents = _contents(counts)
    entities = _entities(100)
    plan = _plan(tmp_path)
    objects = tmp_path / "objects"

    selected = plan["samples"][0]
    selected_path = tmp_path / str(selected["objectRef"])
    selected_path.joinpath("manifest.json").write_text(
        json.dumps({"entityRef": "bytes-changed"}) + "\n", encoding="utf-8"
    )
    with pytest.raises(ReleaseUatSamplePlanError, match="OBJECT_DIGEST_DRIFT"):
        validate_release_uat_sample_plan(
            plan,
            release_contents=contents,
            entity_refs=entities,
            release_objects_root=objects,
        )

    plan = _plan(tmp_path / "digest")
    plan["samples"][0]["objectDigest"] = "sha256:" + "f" * 64
    with pytest.raises(ReleaseUatSamplePlanError, match="OBJECT_DIGEST_DRIFT"):
        validate_release_uat_sample_plan(
            plan,
            release_contents=contents,
            entity_refs=entities,
            release_objects_root=tmp_path / "digest/objects",
        )

    plan = _plan(tmp_path / "ref")
    plan["samples"][0]["objectRef"] = "objects/entities/地点/景区/ref-drift"
    with pytest.raises(ReleaseUatSamplePlanError, match="OBJECT_REF_DRIFT"):
        validate_release_uat_sample_plan(
            plan,
            release_contents=contents,
            entity_refs=entities,
            release_objects_root=tmp_path / "ref/objects",
        )


def test_sample_schema__rejects_retired_or_unknown_sample_fields(tmp_path: Path) -> None:
    plan = _plan(tmp_path / "carrier-ref")
    plan["samples"][0]["carrierRef"] = "地点/景区/entity-0000"
    with pytest.raises(ReleaseUatSamplePlanError, match="SCHEMA_INVALID"):
        validate_release_uat_sample_plan(plan)

    plan = _plan(tmp_path / "unknown-sample")
    plan["samples"][0]["runtimePostId"] = "runtime-123"
    with pytest.raises(ReleaseUatSamplePlanError, match="SCHEMA_INVALID"):
        validate_release_uat_sample_plan(plan)


def test_m1000_plan__loads_projected_authority_by_exact_ref_digest(
    tmp_path: Path,
) -> None:
    from content.release.canonical.release_uat_sampling_authority import (
        load_release_uat_sampling_authority,
    )

    counts = {"homepage": 1000, "article": 1000, "image": 1000, "video": 100}
    contents = _contents(counts)
    entities = _entities(counts["homepage"])
    objects = _release_objects(tmp_path, contents=contents, entities=entities)
    selection = {
        "poolDigest": DIGESTS["pool"],
        "sourceIdentitySetDigest": DIGESTS["source"],
        "canonicalMerkle": DIGESTS["merkle"],
        "releaseContentsDigest": canonical_digest(
            sorted(
                contents,
                key=lambda row: (
                    str(row["contentId"]), int(row["version"]), str(row["postRef"])
                ),
            )
        ),
        "releaseEntityCohortDigest": canonical_digest(sorted(entities)),
    }
    release_digest = release_identity_digest(
        release_id="release-m100",
        canonical_merkle=DIGESTS["merkle"],
        selection_evidence=selection,
    )
    projected = _m1000_authority(
        release_id="release-m100", release_digest=release_digest
    )
    authority_path = tmp_path / "authority/projected.json"
    authority_path.parent.mkdir(parents=True)
    authority_path.write_bytes(authority_document_bytes(projected))
    authority = load_release_uat_sampling_authority(
        artifact_root=tmp_path,
        authority_binding={
            "ref": "authority/projected.json",
            "digest": authority_byte_digest(authority_path.read_bytes()),
        },
        release_id="release-m100",
        release_digest=release_digest,
    )

    plan = build_release_uat_sample_plan(
        release_id="release-m100",
        milestone="M1000",
        pool_digest=DIGESTS["pool"],
        source_identity_set_digest=DIGESTS["source"],
        canonical_merkle=DIGESTS["merkle"],
        release_contents=contents,
        entity_refs=entities,
        release_objects_root=objects,
        eligible_population_counts=counts,
        sampling_authority=authority,
    )
    assert plan["sampleStrategy"]["authority"] == projected
    assert plan["sampleStrategy"]["sampleDistribution"] == {
        "homepage": 13, "article": 17, "image": 19, "video": 7,
    }

    with pytest.raises(ReleaseUatSamplingAuthorityError, match="digest drifted"):
        load_release_uat_sampling_authority(
            artifact_root=tmp_path,
            authority_binding={
                "ref": "authority/projected.json",
                "digest": "sha256:" + "f" * 64,
            },
            release_id="release-m100",
            release_digest=release_digest,
        )
