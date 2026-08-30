# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#req-002
"""ReleaseUatSamplePlan is Data-owned and bound to exact immutable release bytes."""
from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest
from content.release.canonical.aggregate_release_existing import (
    validate_existing_release_uat_sample_plan,
)
from content.release.canonical.object_transaction_contract import ObjectTransactionError
from content.release.canonical.release_uat_sample_plan import (
    CARRIERS,
    ENTRIES,
    ReleaseUatSamplePlanError,
    build_release_uat_sample_plan,
    exact_document_bytes,
    release_object_digest,
    validate_release_uat_sample_plan,
)


def _digest(seed: str) -> str:
    return "sha256:" + hashlib.sha256(seed.encode()).hexdigest()


def _contents(
    *, article: int = 100, image: int = 100, video: int = 10
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for carrier, count in (("article", article), ("image", image), ("video", video)):
        for index in range(count, 0, -1):
            rows.append(
                {
                    "contentId": f"{carrier}-{index:04d}",
                    "version": 1,
                    "postRef": f"{carrier}/place/{carrier}-{index:04d}",
                    "executionId": "execution-a",
                    "sourceIdentityDigest": _digest(f"source-{carrier}-{index}"),
                }
            )
    return rows


def _entities(count: int = 100) -> list[str]:
    return [f"地点/景区/place-{index:04d}" for index in range(count, 0, -1)]


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
        path = objects / "posts" / str(row["postRef"]) / "manifest.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(row, sort_keys=True) + "\n", encoding="utf-8")
    return objects


def _plan(
    root: Path,
    *,
    contents: list[dict[str, object]] | None = None,
    entities: list[str] | None = None,
    eligible: dict[str, int] | None = None,
) -> dict[str, object]:
    resolved_contents = contents or _contents()
    resolved_entities = entities or _entities()
    objects = _release_objects(
        root, contents=resolved_contents, entities=resolved_entities
    )
    return build_release_uat_sample_plan(
        release_id="release-m100",
        milestone="M100",
        pool_digest=_digest("pool"),
        source_identity_set_digest=_digest("identities"),
        canonical_merkle=_digest("objects"),
        release_contents=resolved_contents,
        entity_refs=resolved_entities,
        release_objects_root=objects,
        eligible_population_counts=eligible
        or {"homepage": 120, "article": 140, "image": 160, "video": 18},
    )


def test_m100_plan_has_exact_distribution_unique_objects_and_two_axis_matrix(
    tmp_path: Path,
) -> None:
    plan = _plan(tmp_path)

    assert plan["exactCohortCounts"] == {
        "homepage": 100,
        "article": 100,
        "image": 100,
        "video": 10,
    }
    assert plan["sampleStrategy"]["sampleDistribution"] == {
        "homepage": 25,
        "article": 25,
        "image": 40,
        "video": 10,
    }
    cases = plan["samples"]
    assert len(cases) == 100
    assert Counter(case["carrier"] for case in cases) == {
        "homepage": 25,
        "article": 25,
        "image": 40,
        "video": 10,
    }
    assert len({case["objectId"] for case in cases}) == 100
    assert cases[0] == {
        "sampleId": "m100-homepage-001",
        "carrier": "homepage",
        "objectId": "/entity/地点/景区/place-0001",
        "objectRef": "objects/entities/地点/景区/place-0001",
        "objectDigest": release_object_digest(
            tmp_path / "objects/entities/地点/景区/place-0001"
        ),
    }
    assert cases[-1] == {
        "sampleId": "m100-video-010",
        "carrier": "video",
        "objectId": "video-0010",
        "objectRef": "objects/posts/video/place/video-0010",
        "objectDigest": release_object_digest(
            tmp_path / "objects/posts/video/place/video-0010"
        ),
    }
    assert [cell["entry"] for cell in plan["entryCarrierCells"]] == [
        entry for entry in ENTRIES for _carrier in CARRIERS
    ]
    assert [cell["carrier"] for cell in plan["entryCarrierCells"]] == [
        carrier for _entry in ENTRIES for carrier in CARRIERS
    ]
    assert {"targetEnvironment", "environment", "target", "device", "package"}.isdisjoint(plan)
    assert all("runnerClass" in cell for cell in plan["entryCarrierCells"])


def test_eligible_overshoot_is_recorded_without_entering_exact_cohort(
    tmp_path: Path,
) -> None:
    eligible = {"homepage": 121, "article": 151, "image": 181, "video": 19}
    plan = _plan(tmp_path, eligible=eligible)

    assert plan["eligiblePopulationCounts"] == eligible
    assert plan["exactCohortCounts"] == {
        "homepage": 100,
        "article": 100,
        "image": 100,
        "video": 10,
    }
    assert (
        max(
            case["objectId"]
            for case in plan["samples"]
            if case["carrier"] == "image"
        )
        == "image-0040"
    )


def test_shortfall_fails_closed_with_typed_error(tmp_path: Path) -> None:
    with pytest.raises(ReleaseUatSamplePlanError, match="UAT_SAMPLE_SHORTFALL"):
        _plan(tmp_path / "shortfall", contents=_contents(video=9))

    plan = _plan(tmp_path / "eligible")
    plan["eligiblePopulationCounts"]["image"] = 99
    with pytest.raises(
        ReleaseUatSamplePlanError,
        match="ELIGIBLE_POPULATION_SHORTFALL",
    ):
        validate_release_uat_sample_plan(plan, expected_milestone="M100")


def test_selection_is_deterministic_and_unknown_fields_fail_closed(
    tmp_path: Path,
) -> None:
    first = _plan(tmp_path / "first", contents=_contents(), entities=_entities())
    second = _plan(
        tmp_path / "second",
        contents=list(reversed(_contents())),
        entities=list(reversed(_entities())),
    )
    assert first == second

    first["targetEnvironment"] = "alpha"
    with pytest.raises(ReleaseUatSamplePlanError, match="SCHEMA_INVALID"):
        validate_release_uat_sample_plan(first)


def test_existing_release_reuse_strictly_recomputes_plan_identity_and_bytes(
    tmp_path: Path,
) -> None:
    contents = _contents()
    entities = _entities()
    expected = _plan(
        tmp_path / "objects-fixture", contents=contents, entities=entities
    )
    final_root = tmp_path / "release-m100"
    sample_path = final_root / "payload" / "uat" / "sample_plan.json"
    sample_path.parent.mkdir(parents=True)
    source_objects = tmp_path / "objects-fixture/objects"
    release_objects = final_root / "payload/objects"
    for source in sorted(source_objects.rglob("*")):
        if source.is_file():
            target = release_objects / source.relative_to(source_objects)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
    eligible = {
        "homepage": 120,
        "article": 140,
        "image": 160,
        "video": 18,
    }

    def validate(
        *,
        pool_digest: str = _digest("pool"),
        source_identity_set_digest: str = _digest("identities"),
    ) -> str:
        return validate_existing_release_uat_sample_plan(
            final_root=final_root,
            release_id="release-m100",
            milestone="M100",
            pool_digest=pool_digest,
            source_identity_set_digest=source_identity_set_digest,
            canonical_merkle=_digest("objects"),
            release_contents=contents,
            entity_refs=entities,
            release_objects_root=release_objects,
            eligible_population_counts=eligible,
        )

    sample_path.write_text(
        json.dumps(expected, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ObjectTransactionError, match="bytes drifted"):
        validate()

    sample_path.write_bytes(exact_document_bytes(expected))
    assert validate() == _digest_bytes(exact_document_bytes(expected))

    stale = copy.deepcopy(expected)
    stale["samples"][0]["objectId"] = "/entity/地点/景区/stale"
    sample_path.write_bytes(exact_document_bytes(stale))
    with pytest.raises(ObjectTransactionError, match="SELECTION_DRIFT"):
        validate()

    sample_path.write_bytes(exact_document_bytes(expected))
    with pytest.raises(ObjectTransactionError, match="SELECTION_EVIDENCE_DRIFT"):
        validate(source_identity_set_digest=_digest("other-identities"))

    unknown = {**expected, "targetEnvironment": "alpha"}
    sample_path.write_bytes(exact_document_bytes(unknown))
    with pytest.raises(ObjectTransactionError, match="SCHEMA_INVALID"):
        validate()


def _digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()
