from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

DATA_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(DATA_SCRIPTS))

from content.release.canonical import pool_inspection as subject  # noqa: E402
from content.release.canonical.content_pool_record import (  # noqa: E402
    append_pool_record,
    build_canonical_pool_record,
    pool_payload_digest,
)
from content.release.canonical.object_source_identity import (  # noqa: E402
    source_identity_digest,
)
from content.release.canonical.pool_inspection import inspect_pool  # noqa: E402
from content.release.canonical.pool_semantic_scheduling import (  # noqa: E402
    semantic_scheduling_projection,
)
from core.io import write_json  # noqa: E402
from core.schema import assert_valid  # noqa: E402
from core.source_digest import (  # noqa: E402
    SourceDefinitionSnapshot,
    content_source_revision,
)


def _source_attribution() -> dict[str, object]:
    return {
        "isOriginal": False,
        "originalCreatorName": "来源作者",
        "platform": "source-platform",
        "sourcePostUrl": "https://source.example/post",
        "originalAssetUrl": "https://source.example/asset.jpg",
        "attributionText": "来源作者 / source-platform",
        "rightsBasis": "public research reference",
        "commercialAuthorizationStatus": "unverified",
        "publicationAdmission": "research_release",
        "watermarkStatus": "absent",
        "audioRightsStatus": "no_audio",
        "modelReleaseStatus": "not_required",
        "propertyReleaseStatus": "not_required",
        "collectedAt": "2026-08-11T00:00:00Z",
        "takedownPolicy": "remove on substantiated request",
    }


def _source_identity(
    execution_id: str,
) -> tuple[dict[str, object], SourceDefinitionSnapshot]:
    source_digest = "sha256:" + "1" * 64
    entity_catalog_digest = "sha256:" + "2" * 64
    identity: dict[str, object] = {
        "executionId": execution_id,
        "sourceRevision": content_source_revision(
            source_digest=source_digest,
            entity_catalog_digest=entity_catalog_digest,
        ),
        "sourceDigest": source_digest,
        "entityCatalogDigest": entity_catalog_digest,
    }
    identity["identityDigest"] = source_identity_digest(identity)
    return identity, SourceDefinitionSnapshot(source_digest)


def _execution_identity_files(output: Path, execution_id: str) -> None:
    identity, source_digest = _source_identity(execution_id)
    target = {
        "executionId": execution_id,
        "entityCatalogDigest": identity["entityCatalogDigest"],
    }
    encoded = json.dumps(
        target, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    root = output / "data/tasks" / execution_id
    write_json(root / "0.plan/target_set.json", target)
    write_json(
        root / "execution_manifest.json",
        {
            "executionId": execution_id,
            "sourceTaskId": execution_id,
            "sourceDigest": source_digest.to_document(),
            "targetSetRef": "0.plan/target_set.json",
            "targetSetDigest": hashlib.sha256(encoded).hexdigest(),
        },
    )


def _author(publish: Path, author_id: str = "author-a") -> None:
    write_json(
        publish / f"creators/{author_id}/profile.json",
        {
            "authorId": author_id,
            "version": 1,
            "status": "active",
            "admission": {
                "processResult": "completed",
                "qualityResult": "passed",
                "evidenceRef": "evidence.json",
                "evidenceDigest": "sha256:" + "a" * 64,
            },
        },
    )


def _legacy_author_history(publish: Path, author_id: str = "author-a") -> None:
    payload_digest = "sha256:" + "d" * 64
    legacy = {
        "schema": "quwoquan_data.pool_object_record",
        "objectType": "author",
        "objectId": author_id,
        "objectRef": author_id,
        "status": "active",
        "processResult": "completed",
        "qualityResult": "passed",
        "eligibilityResult": "passed",
        "usageScope": None,
        "evidenceRef": "evidence.json",
        "evidenceDigest": "sha256:" + "a" * 64,
        "payloadDigest": payload_digest,
        "version": 1,
    }
    versions = publish / f"creators/{author_id}/_pool/versions"
    write_json(versions / "1.json", legacy)
    canonical = dict(legacy)
    canonical.pop("version")
    canonical.update(recordSequence=2, contentVersion=1)
    write_json(versions / "2.json", canonical)


def _homepage(
    publish: Path,
    name: str = "实体甲",
    execution_id: str = "execution-a",
) -> None:
    root = publish / f"entities/地点/景区/{name}"
    source_identity, source_digest = _source_identity(execution_id)
    write_json(
        root / "manifest.json",
        {
            "schema": "quwoquan_data.entity_manifest",
            "entityId": f"entity-{name}",
            "entityRef": f"/entity/地点/景区/{name}",
            "executionId": execution_id,
            "sourceDigest": source_digest.to_document(),
            "sourceIdentity": source_identity,
            "sourceAttribution": _source_attribution(),
            "version": 1,
            "status": "active",
            "admission": {
                "processResult": "completed",
                "qualityResult": "passed",
                "usageScope": "research",
                "evidenceRef": "attestation.json",
                "evidenceDigest": "sha256:" + "b" * 64,
            },
        },
    )
    write_json(root / "creator.refs.json", {"creatorRefs": ["author-a"]})
    attestation = _approved_attestation(root)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["admission"]["evidenceDigest"] = (
        "sha256:" + hashlib.sha256(attestation.read_bytes()).hexdigest()
    )
    write_json(manifest_path, manifest)
    append_pool_record(
        object_root=root,
        record=build_canonical_pool_record(
            object_root=root,
            object_type="homepage",
            object_ref=root.relative_to(publish / "entities").as_posix(),
        ),
    )


def _post(
    publish: Path,
    *,
    carrier: str,
    work: str,
    entity_name: str = "实体甲",
    usage_scope: str = "research",
    execution_id: str = "execution-a",
) -> None:
    root = publish / "posts" / carrier / work / "1"
    source_identity, source_digest = _source_identity(execution_id)
    write_json(
        root / "manifest.json",
        {
            "contentId": f"content-{work}",
            "version": 1,
            "executionId": execution_id,
            "sourceTaskId": execution_id,
            "sourceDigest": source_digest.to_document(),
            "sourceIdentity": source_identity,
            "contentType": carrier,
            "authorId": "author-a",
            "status": "active",
            "entityRefs": [f"/entity/地点/景区/{entity_name}"],
            "sourceAttribution": _source_attribution(),
            "admission": {
                "processResult": "completed",
                "qualityResult": "passed",
                "usageScope": usage_scope,
                "evidenceRef": "attestation.json",
                "evidenceDigest": "sha256:" + "c" * 64,
            },
        },
    )
    write_json(root / "creator.refs.json", {"creatorRefs": ["author-a"]})
    attestation = _approved_attestation(root)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["admission"]["evidenceDigest"] = (
        "sha256:" + hashlib.sha256(attestation.read_bytes()).hexdigest()
    )
    write_json(manifest_path, manifest)
    append_pool_record(
        object_root=root,
        record=build_canonical_pool_record(
            object_root=root,
            object_type="content",
            object_ref=root.relative_to(publish / "posts").as_posix(),
        ),
    )


def _approved_attestation(root: Path) -> Path:
    write_json(
        root / "attestation.json",
        {
            "schema": "quwoquan_data.review_attestation",
            "decision": "approved",
            "deterministicGate": {"status": "passed", "issues": []},
            "independentReviewer": {"status": "passed"},
            "mediaRefReview": {"status": "passed", "issues": []},
        },
    )
    return root / "attestation.json"


def test_pool_inspection_requires_explicit_eligibility_result() -> None:
    assert subject._eligibility_passed({"eligibilityResult": "passed"}) is True
    assert subject._eligibility_passed({"eligibilityResult": None}) is False
    assert subject._eligibility_passed({}) is False


def test_pre_sequence_record_shape_stays_excluded(tmp_path: Path) -> None:
    """A sidecar without recordSequence fails closed instead of being inferred."""

    publish = tmp_path / "publish"
    _author(publish)
    _homepage(publish)
    root = publish / "posts/article/pre-seq1/1"
    _post(publish, carrier="article", work="pre-seq1")
    current = json.loads(
        (root / "_pool/versions/1.json").read_text(encoding="utf-8")
    )
    current["version"] = current.pop("recordSequence")
    current.pop("contentVersion")
    write_json(root / "_pool/versions/1.json", current)

    report = inspect_pool(
        publish_root=publish,
        include_issues=True,
        strict_delivery=False,
    )

    assert report["supply"]["article"]["admitted"] == 0
    assert report["supply"]["article"]["publishable"] == 0
    assert any(
        row["ref"] == "posts/article/pre-seq1/1"
        and row["code"] == "DATA.POOL.OBJECT_NOT_ADMITTED"
        for row in report["issues"]
    )


def test_pool_inspection_uses_canonical_author_after_exact_legacy_repair(
    tmp_path: Path,
) -> None:
    publish = tmp_path / "publish"
    _author(publish)
    _legacy_author_history(publish)
    _homepage(publish)
    _post(publish, carrier="article", work="ready")

    report = inspect_pool(
        publish_root=publish,
        include_issues=True,
        strict_delivery=False,
    )

    assert report["authors"] == {"observed": 1, "admitted": 1}
    assert report["supply"]["article"]["publishable"] == 1
    assert not any(
        row["ref"] == "creators/author-a" for row in report["issues"]
    )


def test_pool_inspection_reports_partial_without_blocking_publishable_supply(
    tmp_path: Path,
) -> None:
    publish = tmp_path / "publish"
    _author(publish)
    _homepage(publish)
    for carrier in ("article", "image", "video"):
        _post(
            publish,
            carrier=carrier,
            work=f"work-{carrier}",
            usage_scope="commercial" if carrier == "video" else "research",
        )
    pending = publish / "posts/article/admission-pending/1"
    write_json(
        pending / "manifest.json",
        {
            "contentType": "article",
            "reviewDecision": "approved",
            "status": "active",
            "entityRefs": ["/entity/地点/景区/实体甲"],
        },
    )
    write_json(pending / "creator.refs.json", {"creatorRefs": ["author-a"]})
    _approved_attestation(pending)

    report = inspect_pool(
        publish_root=publish,
        include_issues=True,
        strict_delivery=False,
    )

    assert_valid(report, "release", "pool_inspection", label="pool_inspection")
    assert report["result"] == "partial"
    assert report["checks"] == {
        "quality": "passed",
        "eligibility": "failed",
        "delivery": "passed",
    }
    assert report["authors"] == {"observed": 1, "admitted": 1}
    assert report["supply"] == {
        "homepage": {
            "observed": 1,
            "admitted": 1,
            "publishable": 1,
            "deliveryPending": 0,
            "explicitAdmissionPending": 0,
            "target": 100,
            "gap": 99,
        },
        "article": {
            "observed": 2,
            "admitted": 1,
            "publishable": 1,
            "deliveryPending": 0,
            "explicitAdmissionPending": 1,
            "target": 100,
            "gap": 99,
        },
        "image": {
            "observed": 1,
            "admitted": 1,
            "publishable": 1,
            "deliveryPending": 0,
            "explicitAdmissionPending": 0,
            "target": 100,
            "gap": 99,
        },
        "video": {
            "observed": 1,
            "admitted": 1,
            "publishable": 1,
            "deliveryPending": 0,
            "explicitAdmissionPending": 0,
            "target": 10,
            "gap": 9,
        },
    }
    assert report["usageScope"] == {"research": 3, "commercial": 1}
    assert report["environmentCapacity"] == {
        "alpha": 3,
        "beta": 3,
        "gamma": 3,
        "prod": 3,
    }
    assert report["reasons"] == [{
        "gate": "eligibility",
        "code": "DATA.POOL.EXPLICIT_ADMISSION_MISSING",
        "count": 1,
        "message": "对象缺少显式准入记录，需要补录",
    }]
    assert report["milestone"] == "M100"
    assert report["targetAttained"] is False
    assert report["nextWave"] == [
        {"carrier": "homepage", "requestedCandidateCount": 99},
        {"carrier": "article", "requestedCandidateCount": 99},
        {"carrier": "image", "requestedCandidateCount": 99},
        {"carrier": "video", "requestedCandidateCount": 9},
    ]


def test_missing_entity_only_makes_that_object_delivery_pending(tmp_path: Path) -> None:
    publish = tmp_path / "publish"
    _author(publish)
    _homepage(publish)
    _post(publish, carrier="article", work="ready")
    _post(
        publish,
        carrier="image",
        work="pending",
        entity_name="尚未追加的实体",
    )

    report = inspect_pool(publish_root=publish, strict_delivery=False)

    assert report["result"] == "partial"
    assert report["checks"]["delivery"] == "failed"
    assert report["supply"]["article"]["publishable"] == 1
    assert report["supply"]["image"]["admitted"] == 1
    assert report["supply"]["image"]["publishable"] == 0
    assert report["supply"]["image"]["deliveryPending"] == 1
    assert report["environmentCapacity"]["alpha"] == 1


def test_superseded_content_version_is_not_delivery_pending(tmp_path: Path) -> None:
    publish = tmp_path / "publish"
    _author(publish)
    _homepage(publish)
    _post(publish, carrier="article", work="old")
    _post(publish, carrier="article", work="new")
    for work, version in (("old", 1), ("new", 2)):
        root = publish / f"posts/article/{work}/1"
        manifest_path = root / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["contentId"] = "content-versioned"
        manifest["version"] = version
        write_json(manifest_path, manifest)
        record_path = root / "_pool/versions/1.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["objectId"] = "content-versioned"
        record["contentVersion"] = version
        record["payloadDigest"] = record["canonicalObjectDigest"] = pool_payload_digest(root)
        write_json(record_path, record)

    report = inspect_pool(publish_root=publish, strict_delivery=True)

    assert report["supply"]["article"]["admitted"] == 2
    assert report["supply"]["article"]["publishable"] == 1
    assert report["supply"]["article"]["deliveryPending"] == 0


def test_incomplete_attribution_only_excludes_that_post_from_strict_capacity(
    monkeypatch,
    tmp_path: Path,
) -> None:
    publish = tmp_path / "publish"
    _author(publish)
    _homepage(publish)
    _post(publish, carrier="article", work="ready")
    _post(publish, carrier="image", work="incomplete")
    manifest_path = publish / "posts/image/incomplete/1/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["sourceAttribution"] = {"isOriginal": False}
    write_json(manifest_path, manifest)
    monkeypatch.setattr(subject, "entity_candidate_closure", lambda *_args, **_kwargs: ([], []))

    report = inspect_pool(
        publish_root=publish,
        include_issues=True,
        strict_delivery=True,
    )

    assert report["supply"]["article"]["publishable"] == 1
    assert report["supply"]["image"]["admitted"] == 0
    assert report["supply"]["image"]["publishable"] == 0
    assert report["supply"]["image"]["deliveryPending"] == 0
    assert report["environmentCapacity"]["alpha"] == 1
    assert [
        issue for issue in report["issues"]
        if issue["code"] == "DATA.POOL.OBJECT_NOT_ADMITTED"
    ] == [{
        "gate": "eligibility",
        "code": "DATA.POOL.OBJECT_NOT_ADMITTED",
        "ref": "posts/image/incomplete/1",
    }]


def test_m1000_inspection_uses_cumulative_target_and_deterministic_wave(
    monkeypatch,
    tmp_path: Path,
) -> None:
    publish = tmp_path / "publish"
    _author(publish)
    _homepage(publish)
    _post(publish, carrier="video", work="ready")
    monkeypatch.setattr(subject, "entity_candidate_closure", lambda *_args, **_kwargs: ([], []))

    report = inspect_pool(
        publish_root=publish,
        strict_delivery=True,
        milestone="M1000",
    )

    assert report["milestone"] == "M1000"
    assert report["supply"]["homepage"]["target"] == 1_000
    assert report["supply"]["article"]["gap"] == 1_000
    assert report["supply"]["video"]["target"] == 100
    assert report["supply"]["video"]["gap"] == 99
    assert report["nextWave"] == [
        {"carrier": "article", "requestedCandidateCount": 1_000},
        {"carrier": "image", "requestedCandidateCount": 1_000},
        {"carrier": "homepage", "requestedCandidateCount": 999},
        {"carrier": "video", "requestedCandidateCount": 99},
    ]


def test_m10000_inspection_is_a_lower_bound_and_keeps_rolling_wave(
    monkeypatch,
    tmp_path: Path,
) -> None:
    publish = tmp_path / "publish"
    _author(publish)
    _homepage(publish)
    _post(publish, carrier="video", work="ready")
    monkeypatch.setattr(
        subject,
        "entity_candidate_closure",
        lambda *_args, **_kwargs: ([], []),
    )

    report = inspect_pool(
        publish_root=publish,
        strict_delivery=True,
        milestone="M10000",
    )

    assert report["milestone"] == "M10000"
    assert report["supply"]["homepage"]["target"] == 10_000
    assert report["supply"]["article"]["target"] == 10_000
    assert report["supply"]["image"]["target"] == 10_000
    assert report["supply"]["video"]["target"] == 1_000
    assert report["nextWave"] == [
        {"carrier": "article", "requestedCandidateCount": 10_000},
        {"carrier": "image", "requestedCandidateCount": 10_000},
        {"carrier": "homepage", "requestedCandidateCount": 9_999},
        {"carrier": "video", "requestedCandidateCount": 999},
    ]


def test_admission_missing_pool_is_blocked_but_reports_observed_homepage(tmp_path: Path) -> None:
    publish = tmp_path / "publish"
    root = publish / "entities/地点/景区/历史实体"
    write_json(root / "manifest.json", {"schema": "quwoquan_data.entity_object"})
    write_json(root / "attestation.json", {"schema": "test"})

    report = inspect_pool(publish_root=publish, strict_delivery=False)

    assert report["result"] == "blocked"
    assert report["supply"]["homepage"]["observed"] == 1
    assert report["supply"]["homepage"]["explicitAdmissionPending"] == 1
    assert report["supply"]["homepage"]["gap"] == 100
    assert {reason["gate"] for reason in report["reasons"]} == {
        "eligibility",
        "delivery",
    }


def test_approved_attestation_without_record_requires_explicit_admission(tmp_path: Path) -> None:
    publish = tmp_path / "publish"
    _author(publish)
    _homepage(publish)
    root = publish / "posts/video/approved-no-record/1"
    write_json(
        root / "manifest.json",
        {
            "contentType": "video",
            "reviewDecision": "approved",
            "status": "active",
            "entityRefs": ["/entity/地点/景区/实体甲"],
        },
    )
    write_json(root / "creator.refs.json", {"creatorRefs": ["author-a"]})
    _approved_attestation(root)

    report = inspect_pool(
        publish_root=publish,
        include_issues=True,
        strict_delivery=False,
    )

    assert report["supply"]["video"]["admitted"] == 0
    assert report["supply"]["video"]["publishable"] == 0
    assert report["supply"]["video"]["explicitAdmissionPending"] == 1
    assert report["usageScope"] == {"research": 1, "commercial": 0}
    assert any(
        issue["code"] == "DATA.POOL.EXPLICIT_ADMISSION_MISSING"
        for issue in report["issues"]
    )


def test_review_without_quality_evidence_remains_excluded(tmp_path: Path) -> None:
    publish = tmp_path / "publish"
    root = publish / "posts/video/no-quality/1"
    write_json(
        root / "manifest.json",
        {"contentType": "video", "reviewDecision": "approved"},
    )
    write_json(
        root / "attestation.json",
        {"schema": "quwoquan_data.review_attestation", "decision": "approved"},
    )

    report = inspect_pool(
        publish_root=publish,
        include_issues=True,
        strict_delivery=False,
    )

    assert report["supply"]["video"]["admitted"] == 0
    assert report["supply"]["video"]["explicitAdmissionPending"] == 1


def test_pool_inspection_by_task_reports_funnel_without_changing_admission(
    tmp_path: Path,
) -> None:
    publish = tmp_path / "publish"
    output = tmp_path / "output"
    task_id = "20260811--travel-image-m1--batch-observability--scale-001"
    _author(publish)
    _homepage(publish)
    _post(
        publish,
        carrier="image",
        work="ready",
        execution_id=task_id,
    )
    _execution_identity_files(output, task_id)
    write_json(
        output / f"data/tasks/{task_id}/0.plan/request.json",
        {"quota": 3},
    )
    write_json(
        output / f"data/tasks/{task_id}/_shared/execution_state.json",
        {
            "startedAt": "2026-08-11T00:00:00Z",
            "updatedAt": "2026-08-11T00:00:02Z",
            "status": "succeeded",
        },
    )

    report = inspect_pool(
        publish_root=publish,
        strict_delivery=False,
        include_batches=True,
        output_root=output,
        execution_ids=(task_id,),
    )

    assert_valid(report, "release", "pool_inspection", label="pool_inspection")
    assert next(
        row for row in report["batches"] if row["sourceTaskId"] == task_id
    ) == {
            "sourceTaskId": task_id,
            "target": 3,
            "generated": 1,
            "quality": {"passed": 1, "failed": 0},
            "usageScope": {"research": 1, "commercial": 0, "unknown": 0},
            "admitted": 1,
            "publishable": 1,
            "deliveryPending": 0,
            "excluded": 0,
            "successRate": 1.0,
            "durationMs": 2000,
            "stages": [],
        }


def test_semantic_scheduling_requires_physical_backlog() -> None:
    supply = {
        carrier: {"gap": gap}
        for carrier, gap in {
            "homepage": 91,
            "article": 83,
            "image": 75,
            "video": 0,
        }.items()
    }

    projection = semantic_scheduling_projection(
        milestone="M100",
        supply=supply,
    )

    assert projection["totalSemanticSlots"] == 0
    assert projection["dispatchBlockedWithoutPhysicalBacklog"] is True
    assert projection["waveInput"]["candidates"] == []
    assert [row["sourceReadyHighWater"] for row in projection["carriers"]] == [
        0,
        0,
        0,
        0,
    ]


def test_semantic_scheduling_dispatches_all_physical_source_ready_slots() -> None:
    supply = {
        carrier: {"gap": gap}
        for carrier, gap in {
            "homepage": 24,
            "article": 72,
            "image": 12,
            "video": 0,
        }.items()
    }
    candidates = {
        carrier: [
            {
                "carrier": carrier,
                "candidateId": f"{carrier}-{index:03d}",
                "objectRef": f"posts/{carrier}/{index:03d}",
                "entityRef": f"/entity/地点/景区/{carrier}-{index:03d}",
                "sourceUnitRef": f"source/{carrier}/{index:03d}.json",
                "sourceReadyEvidenceRootRef": ".",
            }
            for index in range(count)
        ]
        for carrier, count in {
            "homepage": 12,
            "article": 36,
            "image": 12,
            "video": 0,
        }.items()
    }

    projection = semantic_scheduling_projection(
        milestone="M100",
        supply=supply,
        source_ready_backlog={key: len(value) for key, value in candidates.items()},
        source_ready_candidates=candidates,
    )

    assigned = {
        row["carrier"]: row["assignedSlots"] for row in projection["carriers"]
    }
    assert assigned == {"homepage": 1, "article": 3, "image": 1, "video": 0}
    assert projection["totalSemanticSlots"] == 5
    assert projection["totalSemanticSlots"] > 4
    assert len(projection["waveInput"]["candidates"]) == 60


def test_semantic_scheduling_defers_same_entity_candidates_to_later_waves() -> None:
    candidates = {
        "image": [
            {
                "carrier": "image",
                "candidateId": f"image-{index}",
                "objectRef": f"posts/image/{index}",
                "entityRef": "/entity/地点/景区/乌镇",
                "sourceUnitRef": f"source/image/{index}.json",
                "sourceReadyEvidenceRootRef": ".",
            }
            for index in range(2)
        ]
    }
    projection = semantic_scheduling_projection(
        milestone="M100",
        supply={
            carrier: {"gap": 75 if carrier == "image" else 0}
            for carrier in ("homepage", "article", "image", "video")
        },
        source_ready_backlog={"image": 2},
        source_ready_candidates=candidates,
    )

    image = next(
        row for row in projection["carriers"] if row["carrier"] == "image"
    )
    assert image["sourceReadyBacklog"] == 2
    assert image["dispatchCandidateCount"] == 1
    assert [
        row["candidateId"] for row in projection["waveInput"]["candidates"]
    ] == ["image-0"]


def test_video_gap_never_allocates_empty_semantic_slots() -> None:
    supply = {
        carrier: {"gap": 0 if carrier != "video" else 10}
        for carrier in ("homepage", "article", "image", "video")
    }
    projection = semantic_scheduling_projection(
        milestone="M100",
        supply=supply,
        source_ready_backlog={"video": 24},
        source_ready_candidates={
            "video": [
                {
                    "carrier": "video",
                    "candidateId": f"video-{index}",
                    "objectRef": f"posts/video/{index}",
                    "entityRef": f"/entity/地点/景区/video-{index}",
                    "sourceUnitRef": f"source/video/{index}.json",
                    "sourceReadyEvidenceRootRef": ".",
                }
                for index in range(24)
            ]
        },
    )

    video = next(
        row for row in projection["carriers"] if row["carrier"] == "video"
    )
    assert video["assignedSlots"] == 1
    assert video["sourceReadyHighWater"] == 10
    assert video["dispatchCandidateCount"] == 10


def test_extra_bad_object_does_not_block_attained_milestone(
    monkeypatch,
    tmp_path: Path,
) -> None:
    publish = tmp_path / "publish"
    monkeypatch.setitem(
        subject.MILESTONE_TARGETS,
        "M100",
        {"homepage": 1, "article": 1, "image": 1, "video": 1},
    )
    _author(publish)
    _homepage(publish)
    for carrier in ("article", "image", "video"):
        _post(publish, carrier=carrier, work=f"ready-{carrier}")
    pending = publish / "posts/article/admission-pending-extra/1"
    write_json(
        pending / "manifest.json",
        {"contentType": "article", "reviewDecision": "approved"},
    )
    _approved_attestation(pending)

    report = inspect_pool(
        publish_root=publish,
        include_issues=True,
        strict_delivery=False,
    )

    assert report["targetAttained"] is True
    assert report["result"] == "ready"
    assert report["nextWave"] == []
    assert report["issueCount"] == 1
    assert report["issues"][0]["code"] == "DATA.POOL.EXPLICIT_ADMISSION_MISSING"
    assert report["nextAction"].startswith("build Research milestone release")
