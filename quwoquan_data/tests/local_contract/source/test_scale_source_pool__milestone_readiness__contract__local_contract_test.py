# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-004
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from content.execution.campaign.source_pool_binding import (
    bind_scale_source_pool,
    materialize_bound_scale_source_pool,
    validate_bound_scale_source_pool,
    validate_capsule_scale_source_pool,
)
from content.source.research.scale_source_pool import (
    SOURCE_POOL_CREATE_ONCE_COLLISION,
    SOURCE_POOL_EVIDENCE_INVALID,
    SOURCE_POOL_INVALID,
    SOURCE_POOL_SHORTFALL,
    ScaleSourcePoolError,
    build_scale_source_pool_plan,
    required_candidate_counts,
    validate_scale_source_pool,
    validate_scale_source_pool_evidence,
    write_create_once_scale_source_pool,
)
from content.release.canonical.pool_source_ready_input import (  # noqa: E402
    load_source_ready_input,
)

IDENTITY = {
    "sourceRevision": "sha256:" + "a" * 64,
    "sourceDigest": "sha256:" + "b" * 64,
    "entityCatalogDigest": "sha256:" + "c" * 64,
}
DATA_ROOT = next(
    parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data"
)
CLI = DATA_ROOT / "scripts" / "cli.py"


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _source_attribution(carrier: str, index: int) -> dict[str, object]:
    return {
        "isOriginal": False,
        "originalCreatorName": f"source-author-{index}",
        "platform": f"{carrier}-source",
        "sourcePostUrl": f"https://source.example/{carrier}/{index}",
        "originalAssetUrl": f"https://source.example/{carrier}/{index}/asset",
        "attributionText": f"source-author-{index} / {carrier}-source",
        "rightsBasis": "public research reference",
        "commercialAuthorizationStatus": "unverified",
        "publicationAdmission": "research_release",
        "watermarkStatus": "absent",
        "audioRightsStatus": "no_audio",
        "modelReleaseStatus": "not_required",
        "propertyReleaseStatus": "not_required",
        "collectedAt": "2026-08-08T00:00:00Z",
        "takedownPolicy": "remove on substantiated request",
    }


EVIDENCE_PAYLOADS = {
    "sourceUnit": ("shared/source-unit.json", b'{"kind":"source-unit"}\n'),
    "acquisition": ("shared/acquisition.json", b'{"kind":"acquisition"}\n'),
    "rights": ("shared/rights.json", b'{"kind":"rights"}\n'),
    "quality": ("shared/quality.json", b'{"kind":"quality"}\n'),
    "playability": ("shared/playability.json", b'{"kind":"playability"}\n'),
}


def _byte_digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _lane_selections(
    carriers: tuple[str, ...] = ("homepage", "article", "image", "video"),
) -> dict[str, dict[str, object]]:
    selections: dict[str, dict[str, object]] = {}
    for carrier in carriers:
        stable: dict[str, object] = {
            "carrier": carrier,
            "candidateIds": [f"{carrier}-00000"],
            "candidateCount": 1,
        }
        payload = json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()
        selections[carrier] = {
            **stable,
            "selectionDigest": "sha256:" + hashlib.sha256(payload).hexdigest(),
        }
    return selections


def _write_evidence_root(tmp_path: Path) -> Path:
    root = tmp_path / "evidence"
    for relative, body in EVIDENCE_PAYLOADS.values():
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(body)
    return root


def _candidate(carrier: str, index: int, *, provider: str) -> dict[str, object]:
    entity_ref = f"/entity/地点/景区/{carrier}-{index:05d}"
    prefix = {
        "homepage": "entities/地点/景区",
        "article": "posts/article/攻略",
        "image": "posts/image/画报",
        "video": "posts/video/旅行",
    }[carrier]
    candidate: dict[str, object] = {
        "candidateId": f"{carrier}-{index:05d}",
        "carrier": carrier,
        "objectRef": f"{prefix}/{carrier}-{index:05d}/1",
        "entityRef": entity_ref,
        "observedEntityRef": entity_ref,
        **IDENTITY,
        "provider": provider,
        "contentSha256": _digest(f"content:{carrier}:{index}"),
        "acquisitionStatus": "acquired",
        "rightsStatus": "unverified",
        "distributionDecision": "research_allowed",
        "qualityStatus": "passed",
        "generated": False,
        "videoReadiness": None,
    }
    if carrier in {"homepage", "article"}:
        candidate.update(
            {
                "sourceReadyEvidenceRootRef": ".",
                "sourceAttribution": _source_attribution(carrier, index),
                "sourceUnitRef": EVIDENCE_PAYLOADS["sourceUnit"][0],
                "sourceUnitDigest": _digest(f"source-unit:{carrier}:{index}"),
                "sourceUnitFileSha256": _byte_digest(
                    EVIDENCE_PAYLOADS["sourceUnit"][1]
                ),
                "acquisitionRef": EVIDENCE_PAYLOADS["acquisition"][0],
                "acquisitionDigest": _digest(f"acquisition:{carrier}:{index}"),
                "acquisitionFileSha256": _byte_digest(
                    EVIDENCE_PAYLOADS["acquisition"][1]
                ),
                "rightsRef": EVIDENCE_PAYLOADS["rights"][0],
                "rightsDigest": _digest(f"rights:{carrier}:{index}"),
                "rightsFileSha256": _byte_digest(EVIDENCE_PAYLOADS["rights"][1]),
                "qualityRef": EVIDENCE_PAYLOADS["quality"][0],
                "qualityDigest": _digest(f"quality:{carrier}:{index}"),
                "qualityFileSha256": _byte_digest(
                    EVIDENCE_PAYLOADS["quality"][1]
                ),
                "playabilityRef": None,
                "playabilityDigest": None,
                "playabilityFileSha256": None,
            }
        )
    else:
        candidate.update(
            {
                "sourceAdmissionRef": (
                    f"receipts/media-source-admission/{carrier}-{index:05d}.json"
                ),
                "sourceAdmissionDigest": _digest(
                    f"source-admission:{carrier}:{index}"
                ),
            }
        )
    if carrier == "article":
        candidate["publishMediaMode"] = "illustrated"
    if carrier == "video":
        candidate.update(
            {
                "videoReadiness": {
                    "playable": True,
                    "motion": True,
                    "premiumEligible": True,
                    "playCount": 10_000 + index,
                    "likeCount": 500 + index,
                    "commentCount": 40 + index,
                    "shareCount": 30 + index,
                    "favoriteCount": 200 + index,
                    "observedAt": "2026-08-08T00:00:00Z",
                    "popularityPercentile": round(index / 18, 6),
                    "comparisonBucket": {
                        "provider": provider,
                        "topic": "西湖旅行",
                        "timeBucket": "2026-W32",
                        "candidateCount": 18,
                    },
                },
            }
        )
    return candidate


def _m100_candidates() -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    for carrier in ("homepage", "article"):
        candidates.extend(
            _candidate(carrier, index, provider=f"{carrier}-source")
            for index in range(180)
        )
    image_providers = (
        ["Pinterest"] * 80
        + ["图虫"] * 20
        + ["Pexels"] * 50
        + ["Wikimedia Commons"] * 30
    )
    candidates.extend(
        _candidate("image", index, provider=provider)
        for index, provider in enumerate(image_providers)
    )
    candidates.extend(
        _candidate("video", index, provider="Pexels Videos")
        for index in range(18)
    )
    return candidates


def _content_candidates() -> list[dict[str, object]]:
    return [
        _candidate(carrier, index, provider=f"{carrier}-source")
        for carrier in ("homepage", "article")
        for index in range(180)
    ]


def _plan(candidates: list[dict[str, object]] | None = None) -> dict[str, object]:
    return build_scale_source_pool_plan(
        pool_id="travel-four-carrier-m100-source-pool",
        target_scale="M100",
        created_at="2026-08-08T00:00:00Z",
        candidates=candidates or _m100_candidates(),
        source_revision=IDENTITY["sourceRevision"],
        source_digest=IDENTITY["sourceDigest"],
        entity_catalog_digest=IDENTITY["entityCatalogDigest"],
    )


def _redigest(plan: dict[str, object]) -> dict[str, object]:
    stable = {key: value for key, value in plan.items() if key != "planDigest"}
    payload = json.dumps(
        stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {**stable, "planDigest": "sha256:" + hashlib.sha256(payload).hexdigest()}


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(CLI), *args],
        cwd=DATA_ROOT.parent,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
        capture_output=True,
        check=False,
    )


def test_source_pool_uses_a_rolling_wave_default_not_milestone_oversampling() -> None:
    expected = {"homepage": 12, "article": 12, "image": 12, "video": 12}
    assert required_candidate_counts("M100") == expected
    assert required_candidate_counts("M1000") == expected
    assert required_candidate_counts("M10000") == expected


def test_m100_pool_closes_identity_mix_video_and_zero_duplicate_gates() -> None:
    validation = validate_scale_source_pool(_plan())

    counts = {
        row["carrier"]: row["actualCandidateCount"]
        for row in validation["candidateCounts"]
    }
    assert counts == {"homepage": 180, "article": 180, "image": 180, "video": 18}
    assert validation["duplicateCount"] == 0
    assert validation["entityMismatchCount"] == 0
    assert validation["videoPopularityReadyCount"] == 18
    assert validation["videoPlayableMotionCount"] == 18
    assert validation["videoPremiumEligibleCount"] == 18
    mix = validation["professionalImageSourceMix"]
    assert mix["pinterestCandidateCount"] == 80
    assert mix["tuchongCandidateCount"] == 20
    assert mix["pinterestTuchongCandidateRatio"] >= 0.5
    assert mix["largestProvider"] == "pinterest"
    assert mix["maxProviderCandidateRatio"] <= 0.7


def test_smaller_current_wave_is_valid_and_never_substitutes_old_receipt() -> None:
    candidates = _m100_candidates()
    candidates.pop()

    validation = validate_scale_source_pool(_plan(candidates))

    counts = {
        row["carrier"]: row["actualCandidateCount"]
        for row in validation["candidateCounts"]
    }
    assert counts["video"] == 17
    assert validation["decision"] == "GO"


def test_pending_delivery_object_is_not_redispatched_as_semantic_work(
    tmp_path: Path,
) -> None:
    output = tmp_path / "output"
    evidence = _write_evidence_root(output / "evidence-root")
    plan = _plan(_content_candidates())
    plan_ref = "data/source-pools/m100.json"
    plan_path = output / plan_ref
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    consumed_ref = str(plan["candidates"][0]["objectRef"])

    _input, candidates = load_source_ready_input(
        output_root=output,
        publish_root=tmp_path / "publish",
        milestone="M100",
        source_pool_ref=plan_ref,
        evidence_root_ref=evidence.relative_to(output).as_posix(),
        consumed_object_refs=frozenset({consumed_ref}),
    )

    assert all(
        row["objectRef"] != consumed_ref
        for rows in candidates.values()
        for row in rows
    )


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda rows: rows[0].update(
                {"sourceDigest": "sha256:" + "d" * 64}
            ),
            "source identity drift",
        ),
        (
            lambda rows: rows[1].update(
                {"contentSha256": rows[0]["contentSha256"]}
            ),
            "duplicateCount=1",
        ),
        (
            lambda rows: rows[2].update({"observedEntityRef": "/entity/mismatch"}),
            "entityMismatchCount=1",
        ),
    ],
)
def test_pool_rejects_identity_duplicates_and_entity_mismatch(
    mutate: object,
    message: str,
) -> None:
    candidates = _m100_candidates()
    assert callable(mutate)
    mutate(candidates)

    with pytest.raises(ScaleSourcePoolError, match=message) as captured:
        _plan(candidates)

    assert captured.value.code == SOURCE_POOL_SHORTFALL


@pytest.mark.parametrize("field", ["shareCount", "observedAt", "popularityPercentile"])
def test_video_popularity_incompleteness_is_statistical(
    field: str,
) -> None:
    candidates = _m100_candidates()
    video = next(row for row in candidates if row["carrier"] == "video")
    readiness = video["videoReadiness"]
    assert isinstance(readiness, dict)
    readiness[field] = None

    validation = validate_scale_source_pool(_plan(candidates))

    assert validation["decision"] == "GO"
    assert validation["videoPopularityReadyCount"] == 17


@pytest.mark.parametrize("field", ["playable", "motion"])
def test_video_physical_playability_remains_a_hard_object_gate(field: str) -> None:
    candidates = _m100_candidates()
    video = next(row for row in candidates if row["carrier"] == "video")
    readiness = video["videoReadiness"]
    assert isinstance(readiness, dict)
    readiness[field] = False

    with pytest.raises(ScaleSourcePoolError) as captured:
        _plan(candidates)

    assert captured.value.code in {SOURCE_POOL_INVALID, SOURCE_POOL_SHORTFALL}
    assert "playable motion media" in str(captured.value)


def test_video_premium_eligibility_is_statistical() -> None:
    candidates = _m100_candidates()
    video = next(row for row in candidates if row["carrier"] == "video")
    readiness = video["videoReadiness"]
    assert isinstance(readiness, dict)
    readiness["premiumEligible"] = False

    validation = validate_scale_source_pool(_plan(candidates))

    assert validation["decision"] == "GO"
    assert validation["videoPlayableMotionCount"] == 18
    assert validation["videoPremiumEligibleCount"] == 17


@pytest.mark.parametrize(
    "providers",
    [
        ["Pinterest"] * 80 + ["图虫"] * 20 + ["Pexels"] * 80,
        ["Pinterest"] * 100 + ["Pexels"] * 80,
        ["Pinterest"] * 70 + ["图虫"] * 10 + ["Pexels"] * 100,
        ["Pinterest"] * 130 + ["图虫"] * 10 + ["Pexels"] * 40,
    ],
)
def test_image_provider_mix_is_statistical(providers: list[str]) -> None:
    candidates = [
        row for row in _m100_candidates() if row["carrier"] != "image"
    ]
    candidates.extend(
        _candidate("image", index, provider=provider)
        for index, provider in enumerate(providers)
    )

    validation = validate_scale_source_pool(_plan(candidates))

    assert validation["decision"] == "GO"
    assert validation["professionalImageSourceMix"]["totalCandidateCount"] == 180


def test_plan_is_create_once_digest_bound_and_rejects_legacy_fields(
    tmp_path: Path,
) -> None:
    plan = _plan(_content_candidates())
    evidence_root = _write_evidence_root(tmp_path)
    destination = tmp_path / "scale-source-pools" / "m100.json"
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _index: write_create_once_scale_source_pool(
                    destination,
                    plan,
                    evidence_root=evidence_root,
                ),
                range(2),
            )
        )
    assert results[0] == results[1]
    assert results[0] == plan

    changed = {**plan, "poolId": "different-pool"}
    changed = _redigest(changed)
    with pytest.raises(ScaleSourcePoolError) as collision:
        write_create_once_scale_source_pool(
            destination,
            changed,
            evidence_root=evidence_root,
        )
    assert collision.value.code == SOURCE_POOL_CREATE_ONCE_COLLISION

    legacy = _redigest({**plan, "legacyReceiptRef": "old/pilot.json"})
    with pytest.raises(ScaleSourcePoolError) as invalid:
        validate_scale_source_pool(legacy)
    assert invalid.value.code == SOURCE_POOL_INVALID


def test_evidence_closure_hashes_unique_files_once_and_all_bindings(
    tmp_path: Path,
) -> None:
    validation = validate_scale_source_pool_evidence(
        _plan(_content_candidates()),
        evidence_root=_write_evidence_root(tmp_path),
    )

    assert validation["evidenceFileSha256Verified"] is True
    assert validation["evidenceFileCount"] == 4
    assert validation["evidenceBindingCount"] == 1_440


@pytest.mark.parametrize(
    "mutation",
    ["digest_drift", "missing", "absolute", "parent_escape"],
)
def test_evidence_closure_rejects_drift_missing_and_path_escape(
    tmp_path: Path,
    mutation: str,
) -> None:
    evidence_root = _write_evidence_root(tmp_path)
    plan = _plan(_content_candidates())
    candidate = plan["candidates"][0]
    if mutation == "digest_drift":
        candidate["sourceUnitFileSha256"] = "sha256:" + "f" * 64
    elif mutation == "missing":
        candidate["sourceUnitRef"] = "shared/missing.json"
    elif mutation == "absolute":
        candidate["sourceUnitRef"] = str(
            (evidence_root / EVIDENCE_PAYLOADS["sourceUnit"][0]).resolve()
        )
    elif mutation == "parent_escape":
        candidate["sourceUnitRef"] = "../outside.json"
    plan = _redigest(plan)

    with pytest.raises(ScaleSourcePoolError) as captured:
        validate_scale_source_pool_evidence(plan, evidence_root=evidence_root)

    assert captured.value.code == SOURCE_POOL_EVIDENCE_INVALID


def test_evidence_closure_rejects_symlink_even_when_target_hash_matches(
    tmp_path: Path,
) -> None:
    evidence_root = _write_evidence_root(tmp_path)
    link = evidence_root / "shared" / "source-unit-link.json"
    link.symlink_to(evidence_root / EVIDENCE_PAYLOADS["sourceUnit"][0])
    plan = _plan(_content_candidates())
    plan["candidates"][0]["sourceUnitRef"] = "shared/source-unit-link.json"
    plan = _redigest(plan)

    with pytest.raises(ScaleSourcePoolError, match="symlink") as captured:
        validate_scale_source_pool_evidence(plan, evidence_root=evidence_root)

    assert captured.value.code == SOURCE_POOL_EVIDENCE_INVALID


def test_media_candidate_rejects_retired_pre_admission_physical_bindings() -> None:
    plan = _plan()
    video = next(row for row in plan["candidates"] if row["carrier"] == "video")
    video.update(
        {
            "playabilityRef": EVIDENCE_PAYLOADS["playability"][0],
            "playabilityDigest": _digest("retired-playability"),
            "playabilityFileSha256": _byte_digest(
                EVIDENCE_PAYLOADS["playability"][1]
            ),
        }
    )
    plan = _redigest(plan)

    with pytest.raises(ScaleSourcePoolError) as captured:
        validate_scale_source_pool(plan)

    assert captured.value.code == SOURCE_POOL_INVALID


def test_evidence_root_must_exist_and_must_not_be_a_symlink(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    with pytest.raises(ScaleSourcePoolError) as captured:
        validate_scale_source_pool_evidence(
            _plan(_content_candidates()), evidence_root=missing
        )
    assert captured.value.code == SOURCE_POOL_EVIDENCE_INVALID

    real = _write_evidence_root(tmp_path)
    linked_root = tmp_path / "evidence-link"
    linked_root.symlink_to(real, target_is_directory=True)
    with pytest.raises(ScaleSourcePoolError) as captured:
        validate_scale_source_pool_evidence(
            _plan(_content_candidates()), evidence_root=linked_root
        )
    assert captured.value.code == SOURCE_POOL_EVIDENCE_INVALID


def test_cli_plans_validates_writes_and_reports_create_once_collision(
    tmp_path: Path,
) -> None:
    help_result = _run_cli("source-pool", "--help")
    assert help_result.returncode == 0, help_result.stderr
    assert "plan" in help_result.stdout
    assert "validate" in help_result.stdout
    assert "write" in help_result.stdout
    validate_help = _run_cli("source-pool", "validate", "--help")
    write_help = _run_cli("source-pool", "write", "--help")
    assert "--evidence-root" in validate_help.stdout
    assert "--evidence-root" in write_help.stdout

    candidates_path = tmp_path / "candidates.json"
    candidates_path.write_text(
        json.dumps({"candidates": _content_candidates()}, ensure_ascii=False),
        encoding="utf-8",
    )
    plan_result = _run_cli(
        "source-pool",
        "plan",
        "--pool-id",
        "travel-four-carrier-m100-source-pool",
        "--target-scale",
        "M100",
        "--source-revision",
        IDENTITY["sourceRevision"],
        "--source-digest",
        IDENTITY["sourceDigest"],
        "--entity-catalog-digest",
        IDENTITY["entityCatalogDigest"],
        "--created-at",
        "2026-08-08T00:00:00Z",
        "--candidates",
        str(candidates_path),
    )
    assert plan_result.returncode == 0, plan_result.stderr
    plan = json.loads(plan_result.stdout)
    assert plan["schema"] == "quwoquan_data.scale_source_pool"
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        json.dumps(plan, ensure_ascii=False),
        encoding="utf-8",
    )
    evidence_root = _write_evidence_root(tmp_path)

    validation_result = _run_cli(
        "source-pool",
        "validate",
        "--plan",
        str(plan_path),
        "--evidence-root",
        str(evidence_root),
    )
    assert validation_result.returncode == 0, validation_result.stderr
    validation = json.loads(validation_result.stdout)
    assert validation["decision"] == "GO"
    assert validation["planDigest"] == plan["planDigest"]

    output_root = tmp_path / "canonical-output"
    write_result = _run_cli(
        "source-pool",
        "write",
        "--plan",
        str(plan_path),
        "--output-root",
        str(output_root),
        "--evidence-root",
        str(evidence_root),
    )
    assert write_result.returncode == 0, write_result.stderr
    write_receipt = json.loads(write_result.stdout)
    frozen_path = output_root / write_receipt["planRef"]
    assert frozen_path.is_file()
    replay = _run_cli(
        "source-pool",
        "write",
        "--plan",
        str(plan_path),
        "--output-root",
        str(output_root),
        "--evidence-root",
        str(evidence_root),
    )
    assert replay.returncode == 0, replay.stderr
    assert json.loads(replay.stdout) == write_receipt

    collision_root = tmp_path / "collision-output"
    collision_path = (
        collision_root
        / "scale-source-pools"
        / "m100"
        / f"{str(plan['planDigest']).removeprefix('sha256:')}.json"
    )
    collision_path.parent.mkdir(parents=True)
    collision_path.write_text("{}\n", encoding="utf-8")
    collision = _run_cli(
        "source-pool",
        "write",
        "--plan",
        str(plan_path),
        "--output-root",
        str(collision_root),
        "--evidence-root",
        str(evidence_root),
    )
    assert collision.returncode != 0
    assert SOURCE_POOL_CREATE_ONCE_COLLISION in collision.stderr


def test_campaign_binding_freezes_exact_sorted_lane_selection_and_physical_bytes(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    plan_path = output_root / "data/local/workspace/source-pool/plan.json"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text(
        json.dumps(_plan(_content_candidates()), ensure_ascii=False),
        encoding="utf-8",
    )
    evidence_root = _write_evidence_root(output_root)

    binding, evidence_ref, selection = bind_scale_source_pool(
        plan_path,
        evidence_root=evidence_root,
        output_root=output_root,
        target_scale="M100",
        carrier="article",
        count=10,
        source_revision=IDENTITY["sourceRevision"],
        source_digest=IDENTITY["sourceDigest"],
        entity_catalog_digest=IDENTITY["entityCatalogDigest"],
    )

    assert selection["candidateCount"] == 10
    assert selection["candidateIds"] == [
        f"article-{index:05d}" for index in range(10)
    ]
    assert binding["planRef"] == "data/local/workspace/source-pool/plan.json"
    validate_bound_scale_source_pool(
        binding,
        evidence_root_ref=evidence_ref,
        output_root=output_root,
    )

    (evidence_root / EVIDENCE_PAYLOADS["quality"][0]).write_bytes(b"tampered")
    with pytest.raises(ValueError, match=SOURCE_POOL_SHORTFALL):
        validate_bound_scale_source_pool(
            binding,
            evidence_root_ref=evidence_ref,
            output_root=output_root,
        )


def test_capsule_snapshot_revalidates_plan_and_evidence_without_media_payload(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    plan_path = output_root / "pool/plan.json"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text(
        json.dumps(_plan(_content_candidates()), ensure_ascii=False),
        encoding="utf-8",
    )
    evidence_root = _write_evidence_root(output_root)
    binding, evidence_ref, _selection = bind_scale_source_pool(
        plan_path,
        evidence_root=evidence_root,
        output_root=output_root,
        target_scale="M100",
        carrier="article",
        count=100,
        source_revision=IDENTITY["sourceRevision"],
        source_digest=IDENTITY["sourceDigest"],
        entity_catalog_digest=IDENTITY["entityCatalogDigest"],
    )
    snapshot = tmp_path / "capsule/scale-source-pool"
    selections = _lane_selections(("homepage", "article"))
    snapshot_digest = materialize_bound_scale_source_pool(
        binding,
        evidence_root_ref=evidence_ref,
        output_root=output_root,
        destination=snapshot,
        lane_selections=selections,
    )

    validate_capsule_scale_source_pool(
        binding,
        snapshot_root=snapshot,
        lane_selections=selections,
        expected_snapshot_digest=snapshot_digest,
    )
    assert {path.relative_to(snapshot).as_posix() for path in snapshot.rglob("*") if path.is_file()} == {
        "plan.json",
        "selected.json",
        "evidence/shared/source-unit.json",
        "evidence/shared/acquisition.json",
        "evidence/shared/rights.json",
        "evidence/shared/quality.json",
    }
