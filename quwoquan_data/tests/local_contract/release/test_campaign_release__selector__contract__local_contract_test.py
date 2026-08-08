from __future__ import annotations

import hashlib
import inspect
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from content.execution.campaign import submission_reconciliation as campaign_submission_reconciliation
from content.release.canonical import campaign_release
from content.release.canonical.campaign_release import (
    CampaignReleaseError,
    CampaignReleaseRoots,
    build_campaign_release,
)
from core.release_layout import payload_digest
from core.runtime_policy import runtime_profile_digest
from core.schema import assert_valid
from support.semantic_preflight_fixture import ready_semantic_preflight

CARRIERS = ("homepage", "article", "image", "video")
SOURCE_DIGEST = "sha256:" + "a" * 64
CATALOG_DIGEST = "sha256:" + "b" * 64
RUN_ID = "campaign-run-current"
FENCE = "sha256:" + "f" * 64
RELEASE_ID = "campaign-release-selector-001"


def _digest(value: object, *, prefix: bool = True) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    return "sha256:" + digest if prefix else digest


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _execution_id(carrier: str, sequence: int = 201) -> str:
    return f"20260805--travel-{carrier}-m100--china--scale-{sequence:03d}"


def _target_set(execution_id: str) -> dict[str, object]:
    return {
        "executionId": execution_id,
        "selectionPolicy": "frozen",
        "sourceRef": "quwoquan_data/reference/travel/entities/china",
        "entityCatalogDigest": CATALOG_DIGEST,
        "targetCount": 1,
        "targetRefs": ["地点/景区/测试实体"],
        "targets": [{"name": "测试实体", "entityType": "地点/景区"}],
    }


def _manifest(
    execution_id: str,
    source_document: dict[str, object],
    *,
    retry_of: str | None,
) -> dict[str, object]:
    target = _target_set(execution_id)
    return {
        "executionId": execution_id,
        "familyRef": {"ref": "content/travel/test", "sha256": "c" * 64},
        "sourceDigest": source_document,
        "modelBinding": {
            "provider": "codex_sdk",
            "authorModel": "gpt-5.6-terra",
            "authorModelFamily": "gpt",
            "authorModelParameters": [],
            "reviewerModel": "gpt-5.6-terra",
            "reviewerModelFamily": "gpt",
            "reviewerModelParameters": [],
        },
        "runtimeProfileId": "semantic_agent_local_calibrated",
        "runtimeProfileDigest": runtime_profile_digest(
            "semantic_agent_local_calibrated"
        ),
        "semanticSelectionId": "default",
        "semanticRuntime": "local",
        "requestRef": "0.plan/request.json",
        "targetSetRef": "0.plan/target_set.json",
        "targetSetDigest": _digest(target, prefix=False),
        "retryOf": retry_of,
    }


def _published_refs(carrier: str) -> dict[str, list[str]]:
    if carrier == "homepage":
        return {"entities": ["地点/景区/homepage-001"], "posts": []}
    return {
        "entities": [],
        "posts": [f"{carrier}/测试/{carrier}-001/001"],
    }


def _scale_source_pool(
    output_root: Path,
    *,
    source_revision: str,
) -> tuple[dict[str, object], str, dict[str, dict[str, object]]]:
    evidence_root = output_root / "data/local/workspace/scale-source-pools/m100/evidence"
    candidates: list[dict[str, object]] = []
    object_refs = {
        "homepage": "entities/地点/景区/测试实体",
        "article": "posts/article/测试/article-001/001",
        "image": "posts/image/测试/image-001/001",
        "video": "posts/video/测试/video-001/001",
    }

    def evidence(carrier: str, kind: str) -> tuple[str, str, str]:
        ref = f"{carrier}/{kind}.json"
        document = {
            "schema": f"quwoquan_data.test_{kind}_evidence",
            "carrier": carrier,
            "objectRef": object_refs[carrier],
        }
        path = evidence_root / ref
        _write(path, document)
        return ref, _digest(document), _file_digest(path)

    for carrier in CARRIERS:
        source_unit = evidence(carrier, "source_unit")
        acquisition = evidence(carrier, "acquisition")
        rights = evidence(carrier, "rights")
        quality = evidence(carrier, "quality")
        playability = evidence(carrier, "playability") if carrier == "video" else None
        candidates.append(
            {
                "candidateId": f"{carrier}-candidate-001",
                "carrier": carrier,
                "objectRef": object_refs[carrier],
                "entityRef": "地点/景区/测试实体",
                "observedEntityRef": "地点/景区/测试实体",
                "sourceRevision": source_revision,
                "sourceDigest": SOURCE_DIGEST,
                "entityCatalogDigest": CATALOG_DIGEST,
                "sourceUnitRef": source_unit[0],
                "sourceUnitDigest": source_unit[1],
                "sourceUnitFileSha256": source_unit[2],
                "provider": "fixture_provider",
                "contentSha256": "sha256:" + {
                    "homepage": "1",
                    "article": "2",
                    "image": "3",
                    "video": "4",
                }[carrier]
                * 64,
                "acquisitionStatus": "acquired",
                "acquisitionRef": acquisition[0],
                "acquisitionDigest": acquisition[1],
                "acquisitionFileSha256": acquisition[2],
                "rightsStatus": "verified",
                "distributionDecision": "commercial_allowed",
                "rightsRef": rights[0],
                "rightsDigest": rights[1],
                "rightsFileSha256": rights[2],
                "qualityStatus": "passed",
                "qualityRef": quality[0],
                "qualityDigest": quality[1],
                "qualityFileSha256": quality[2],
                "generated": False,
                "playabilityRef": None if playability is None else playability[0],
                "playabilityDigest": None if playability is None else playability[1],
                "playabilityFileSha256": None if playability is None else playability[2],
                "videoReadiness": None
                if carrier != "video"
                else {
                    "playable": True,
                    "motion": True,
                    "premiumEligible": True,
                    "playCount": 100,
                    "likeCount": 20,
                    "commentCount": 5,
                    "shareCount": 3,
                    "favoriteCount": 7,
                    "observedAt": "2026-08-05T00:00:00+00:00",
                    "popularityPercentile": 0.9,
                    "comparisonBucket": {
                        "provider": "fixture_provider",
                        "topic": "fixture-topic",
                        "timeBucket": "2026-08-05",
                        "candidateCount": 2,
                    },
                },
            }
        )
    pool_stable: dict[str, object] = {
        "schema": "quwoquan_data.scale_source_pool",
        "poolId": "campaign-release-selector-m100-pool",
        "targetScale": "M100",
        "sourceRevision": source_revision,
        "sourceDigest": SOURCE_DIGEST,
        "entityCatalogDigest": CATALOG_DIGEST,
        "createdAt": "2026-08-05T00:00:00+00:00",
        "requiredNewCandidateCounts": [
            {"carrier": carrier, "minimumCandidateCount": 1}
            for carrier in CARRIERS
        ],
        "candidates": candidates,
    }
    pool = {**pool_stable, "planDigest": _digest(pool_stable)}
    assert_valid(pool, "source", "scale_source_pool", label="fixture scale source pool")
    pool_path = output_root / "data/local/workspace/scale-source-pools/m100/plan.json"
    _write(pool_path, pool)
    binding: dict[str, object] = {
        "poolId": pool["poolId"],
        "targetScale": pool["targetScale"],
        "sourceRevision": source_revision,
        "sourceDigest": SOURCE_DIGEST,
        "entityCatalogDigest": CATALOG_DIGEST,
        "planRef": pool_path.relative_to(output_root).as_posix(),
        "planDigest": pool["planDigest"],
        "planFileSha256": _file_digest(pool_path),
    }
    selections: dict[str, dict[str, object]] = {}
    for carrier in CARRIERS:
        stable = {
            "carrier": carrier,
            "candidateIds": [f"{carrier}-candidate-001"],
            "candidateCount": 1,
        }
        selections[carrier] = {**stable, "selectionDigest": _digest(stable)}
    return binding, evidence_root.relative_to(output_root).as_posix(), selections


def _fixture(tmp_path: Path) -> dict[str, object]:
    output_root = tmp_path / "output"
    _preflight_path, semantic_preflight_binding = ready_semantic_preflight(
        "default",
        output_root=output_root,
    )
    roots = CampaignReleaseRoots(
        output_root=output_root,
        campaigns_root=(
            output_root / "data/local/workspace/content-campaign-submissions"
        ),
        tasks_root=output_root / "data/tasks",
        publish_root=tmp_path / "publish",
        release_root=output_root / "data/releases",
    )
    execution_ids = {carrier: _execution_id(carrier) for carrier in CARRIERS}
    root_id = execution_ids["homepage"]
    campaign_root = roots.campaigns_root / root_id
    source_document: dict[str, object] = {
        "algorithm": "sha256",
        "digest": SOURCE_DIGEST,
        "inputs": ["quwoquan_data/reference/travel"],
    }
    source_revision = _digest(
        {
            "schema": "quwoquan_data.campaign_content_source_revision",
            "sourceDigest": SOURCE_DIGEST,
            "entityCatalogDigest": CATALOG_DIGEST,
        }
    )
    empty_external = _digest(
        {"schema": "quwoquan_data.campaign_external_input_set", "refs": []}
    )
    lane_inputs = {
        carrier: {
            "executionId": execution_ids[carrier],
            "externalInputRefs": [],
            "externalInputsDigest": empty_external,
        }
        for carrier in CARRIERS
    }
    pool_binding, pool_evidence_ref, pool_selections = _scale_source_pool(
        output_root,
        source_revision=source_revision,
    )
    submissions: dict[str, dict[str, object]] = {}
    older_image_id = _execution_id("image", 200)
    for carrier in CARRIERS:
        execution_id = execution_ids[carrier]
        retry_of = older_image_id if carrier == "image" else None
        stable: dict[str, object] = {
            "schema": "quwoquan_data.content_execution_submission",
            "scale": "M100",
            "rootExecutionId": root_id,
            "executionId": execution_id,
            "operation": f"{carrier}.generate",
            "carrier": carrier,
            "familyRef": "content/travel/test",
            "regionRef": "china",
            "selector": "auto",
            "quota": 1,
            "count": 1,
            "requiredWorkers": 1,
            "partitionCount": 16,
            "capacityPlanDigest": "sha256:" + "6" * 64,
            "topic": None,
            "targetNames": ["测试实体"],
            "sourceProviders": [],
            "semanticSelectionId": "default",
            "semanticPreflightReceipt": semantic_preflight_binding,
            "scaleSourcePool": pool_binding,
            "sourcePoolEvidenceRootRef": pool_evidence_ref,
            "sourcePoolSelection": pool_selections[carrier],
            "retryOf": retry_of,
            "gitBranch": "dev1.0",
            "gitCommitSha": "d" * 40,
            "sourceRevision": source_revision,
            "sourceDigest": source_document,
            "entityCatalogDigest": CATALOG_DIGEST,
            "externalInputRefs": [],
            "externalInputsDigest": empty_external,
        }
        submission = {
            **stable,
            "requestDigest": _digest(stable),
            "submittedAt": "2026-08-05T00:00:00+00:00",
        }
        submissions[carrier] = submission
        _write(campaign_root / "submissions" / f"{execution_id}.json", submission)
        target = _target_set(execution_id)
        _write(roots.tasks_root / execution_id / "0.plan/target_set.json", target)
        _write(
            roots.tasks_root / execution_id / "execution_manifest.json",
            _manifest(execution_id, source_document, retry_of=retry_of),
        )
    _write(
        roots.tasks_root / older_image_id / "0.plan/target_set.json",
        _target_set(older_image_id),
    )
    _write(
        roots.tasks_root / older_image_id / "execution_manifest.json",
        _manifest(older_image_id, source_document, retry_of=None),
    )
    plan_stable: dict[str, object] = {
        "schema": "quwoquan_data.content_campaign_plan",
        "rootExecutionId": root_id,
        "executionMode": "central",
        "scale": "M100",
        "gitBranch": "dev1.0",
        "gitCommitSha": "d" * 40,
        "sourceRevision": source_revision,
        "sourceDigest": SOURCE_DIGEST,
        "entityCatalogDigest": CATALOG_DIGEST,
        "semanticSelectionId": "default",
        "semanticPreflightReceipt": semantic_preflight_binding,
        "scaleSourcePool": pool_binding,
        "sourcePoolEvidenceRootRef": pool_evidence_ref,
        "laneSourcePoolSelections": pool_selections,
        "laneExternalInputs": lane_inputs,
        "externalInputsDigest": _digest(
            {
                "schema": "quwoquan_data.campaign_external_input_lanes",
                "lanes": lane_inputs,
            }
        ),
        "submissionDigests": {
            carrier: submissions[carrier]["requestDigest"] for carrier in CARRIERS
        },
        "executionIds": execution_ids,
        "frozenAt": "2026-08-05T00:00:00+00:00",
    }
    plan = {**plan_stable, "planDigest": _digest(plan_stable)}
    _write(campaign_root / "campaign_plan.json", plan)
    capsule_stable: dict[str, object] = {
        "schema": "quwoquan_data.content_campaign_source_capsule",
        "format": "source-snapshot-v1",
        "gitCommitSha": plan["gitCommitSha"],
        "sourceRevision": source_revision,
        "sourceDigest": SOURCE_DIGEST,
        "entityCatalogDigest": CATALOG_DIGEST,
        "roots": ["quwoquan_data"],
        "laneExternalInputs": {
            carrier: {
                "rootRef": f"external-inputs/{carrier}",
                "externalInputRefs": [],
                "externalInputsDigest": empty_external,
            }
            for carrier in CARRIERS
        },
        "externalInputsDigest": plan["externalInputsDigest"],
        "scaleSourcePool": pool_binding,
        "sourcePoolSnapshotRootRef": "scale-source-pool",
        "laneSourcePoolSelections": pool_selections,
    }
    capsule_digest = _digest(capsule_stable)
    capsule_root = (
        output_root
        / "data/local/cache/content-campaign-workspaces/content-addressed-capsules"
        / capsule_digest.removeprefix("sha256:")
    )
    pool_path = output_root / str(pool_binding["planRef"])
    _write(
        capsule_root / "scale-source-pool/plan.json",
        json.loads(pool_path.read_text(encoding="utf-8")),
    )
    _write(
        capsule_root / ".qwq_campaign_capsule.json",
        {
            **capsule_stable,
            "capsuleDigest": capsule_digest,
            "treeDigest": "sha256:" + "e" * 64,
        },
    )
    capsule_ref = capsule_root.relative_to(output_root).as_posix()
    _write(
        campaign_root / "campaign_report.json",
        {
            "schema": "quwoquan_data.content_campaign_report",
            "rootExecutionId": root_id,
            "campaignRunId": RUN_ID,
            "campaignGeneration": 3,
            "campaignFencingToken": FENCE,
            "status": "succeeded",
            "phase": "completed",
            "planDigest": plan["planDigest"],
            "gitBranch": plan["gitBranch"],
            "gitCommitSha": plan["gitCommitSha"],
            "sourceDigest": SOURCE_DIGEST,
            "entityCatalogDigest": CATALOG_DIGEST,
            "lanes": {
                carrier: {
                    "executionId": execution_ids[carrier],
                    "status": "finalized",
                    "phase": "publish",
                    "reviewReturnCode": 0,
                    "publishReturnCode": 0,
                    "sourceCapsuleRef": capsule_ref,
                    "sourceCapsuleDigest": capsule_digest,
                    "sourceCapsuleCommitSha": plan["gitCommitSha"],
                    "sourceCapsuleSourceDigest": SOURCE_DIGEST,
                    "sourceCapsuleReadOnly": True,
                    "executionRootRef": f"data/tasks/{execution_ids[carrier]}",
                    "cleanupStatus": "cleaned",
                    "approvedQuota": 1,
                    "qualifiedCount": 1,
                    "finalizedCount": 1,
                    "selectedCount": 1,
                    "discardedCount": 0,
                    "shortfallCount": 0,
                    "error": None,
                }
                for carrier in CARRIERS
            },
            "failure": None,
            "startedAt": "2026-08-05T00:00:00+00:00",
            "updatedAt": "2026-08-05T00:01:00+00:00",
        },
    )
    runtime = {
        "schema": "quwoquan_data.content_campaign_runtime_snapshot",
        "rootExecutionId": root_id,
        "runId": RUN_ID,
        "generation": 3,
        "fencingToken": FENCE,
        "status": "succeeded",
        "phase": "completed",
        "planDigest": plan["planDigest"],
        "failure": None,
    }
    _write(campaign_root / "runtime/snapshot.json", runtime)
    for carrier in CARRIERS:
        execution_id = execution_ids[carrier]
        _write(
            campaign_root / "runtime/lanes" / f"{carrier}.json",
            {
                "schema": "quwoquan_data.content_campaign_lane_checkpoint",
                "rootExecutionId": root_id,
                "runId": RUN_ID,
                "generation": 3,
                "fencingToken": FENCE,
                "carrier": carrier,
                "executionId": execution_id,
                "phase": "run",
                "status": "succeeded",
                "returnCode": 0,
                "executionRoot": str((roots.tasks_root / execution_id).resolve()),
            },
        )
        refs = _published_refs(carrier)
        publish_path = roots.tasks_root / execution_id / "publish_ref.json"
        _write(
            publish_path,
            {
                "schema": "quwoquan_data.execution_publish_ref",
                "executionId": execution_id,
                "canonicalPublishRoot": "quwoquan_data/publish",
                "publishedRefs": refs,
            },
        )
        kind = "entities" if carrier == "homepage" else "posts"
        ref = refs[kind][0]
        manifest: dict[str, object] = {
            "executionId": execution_id,
            "sourceDigest": source_document,
        }
        if kind == "posts":
            manifest["contentType"] = carrier
        _write(roots.publish_root / kind / ref / "manifest.json", manifest)
        _write(
            campaign_root / "receipts" / f"{carrier}-publish.json",
            {
                "schema": "quwoquan_data.content_campaign_lane_receipt",
                "rootExecutionId": root_id,
                "executionId": execution_id,
                "carrier": carrier,
                "phase": "publish",
                "status": "finalized",
                "approvedQuota": 1,
                "qualifiedCount": 1,
                "finalizedCount": 1,
                "selectedCount": 1,
                "discardedCount": 0,
                "shortfallCount": 0,
                "discards": [],
                "executionPublishRef": publish_path.relative_to(
                    roots.output_root
                ).as_posix(),
                "executionPublishSha256": _file_digest(publish_path),
                "campaignRunId": RUN_ID,
                "campaignGeneration": 3,
                "campaignFencingToken": FENCE,
            },
        )
    return {
        "roots": roots,
        "rootId": root_id,
        "campaignRoot": campaign_root,
        "executionIds": execution_ids,
        "olderImageId": older_image_id,
    }


def test_campaign_release__missing_publish_binding_fails_schema_before_aggregate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    campaign_root = fixture["campaignRoot"]
    assert isinstance(campaign_root, Path)
    receipt_path = campaign_root / "receipts/image-publish.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt.pop("executionPublishRef")
    _write(receipt_path, receipt)
    called = False

    def aggregate(**_kwargs: object) -> dict[str, object]:
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(campaign_release, "build_aggregate_release", aggregate)
    with pytest.raises(CampaignReleaseError) as caught:
        build_campaign_release(
            root_execution_id=str(fixture["rootId"]),
            release_id=RELEASE_ID,
            roots=fixture["roots"],
        )

    assert caught.value.code == "DATA.CAMPAIGN.RELEASE_PUBLISH_RECEIPT_INVALID"
    assert "executionPublishRef" in str(caught.value)
    assert called is False


def test_campaign_release__derives_four_lanes_and_retry_lineage__local_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    captured: list[list[str]] = []

    def aggregate(**kwargs: object) -> dict[str, object]:
        execution_ids = list(kwargs["execution_ids"])
        captured.append(execution_ids)
        release = Path(kwargs["release_root"]) / str(kwargs["release_id"])
        _write(release / "payload/release.json", {"releaseId": RELEASE_ID})
        return {
            "schema": "quwoquan_data.aggregate_release_result",
            "releaseId": RELEASE_ID,
            "releaseRoot": str(release),
            "executionIds": execution_ids,
            "canonicalMerkle": "sha256:" + "e" * 64,
            "idempotent": len(captured) > 1,
        }

    monkeypatch.setattr(campaign_release, "build_aggregate_release", aggregate)
    result = build_campaign_release(
        root_execution_id=str(fixture["rootId"]),
        release_id=RELEASE_ID,
        roots=fixture["roots"],
    )
    attestation_path = Path(result["campaignSelectionAttestation"])
    first_bytes = attestation_path.read_bytes()
    attestation = json.loads(first_bytes)

    assert "execution_ids" not in inspect.signature(build_campaign_release).parameters
    assert captured == [[fixture["executionIds"][carrier] for carrier in CARRIERS]]
    assert attestation["executionIds"] == fixture["executionIds"]
    assert attestation["retryLineage"]["image"] == [
        fixture["executionIds"]["image"],
        fixture["olderImageId"],
    ]
    assert attestation["campaignRun"] == {
        "runId": RUN_ID,
        "generation": 3,
        "fencingToken": FENCE,
    }
    assert result["manifestDigest"] == attestation["manifestDigest"]
    digest_input = {
        key: value for key, value in attestation.items() if key != "selectionDigest"
    }
    assert attestation["selectionDigest"] == _digest(digest_input)
    rerun = build_campaign_release(
        root_execution_id=str(fixture["rootId"]),
        release_id=RELEASE_ID,
        roots=fixture["roots"],
    )
    assert rerun["campaignSelectionDigest"] == result["campaignSelectionDigest"]
    assert attestation_path.read_bytes() == first_bytes


def test_campaign_release__conflicting_self_consistent_selection_blocks_before_aggregate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    roots = fixture["roots"]
    assert isinstance(roots, CampaignReleaseRoots)

    def initial_aggregate(**kwargs: object) -> dict[str, object]:
        release = Path(kwargs["release_root"]) / str(kwargs["release_id"])
        _write(release / "payload/release.json", {"releaseId": RELEASE_ID})
        return {
            "schema": "quwoquan_data.aggregate_release_result",
            "releaseId": RELEASE_ID,
            "releaseRoot": str(release),
            "executionIds": list(kwargs["execution_ids"]),
            "canonicalMerkle": "sha256:" + "e" * 64,
            "idempotent": False,
        }

    monkeypatch.setattr(campaign_release, "build_aggregate_release", initial_aggregate)
    initial = build_campaign_release(
        root_execution_id=str(fixture["rootId"]),
        release_id=RELEASE_ID,
        roots=roots,
    )
    selection_path = Path(initial["campaignSelectionAttestation"])
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    selection["releaseId"] = "conflicting-release-id"
    selection["selectionDigest"] = _digest(
        {key: value for key, value in selection.items() if key != "selectionDigest"}
    )
    _write(selection_path, selection)
    target_release = roots.release_root / RELEASE_ID
    shutil.rmtree(target_release)

    aggregate_calls = 0

    def forbidden_aggregate(**_kwargs: object) -> dict[str, object]:
        nonlocal aggregate_calls
        aggregate_calls += 1
        raise AssertionError("conflicting selection must block before aggregate")

    monkeypatch.setattr(
        campaign_release,
        "build_aggregate_release",
        forbidden_aggregate,
    )
    with pytest.raises(CampaignReleaseError) as caught:
        build_campaign_release(
            root_execution_id=str(fixture["rootId"]),
            release_id=RELEASE_ID,
            roots=roots,
        )

    assert caught.value.code == "DATA.CAMPAIGN.RELEASE_ATTESTATION_CONFLICT"
    assert aggregate_calls == 0
    assert not target_release.exists()


def test_campaign_release__selection_extra_field_blocks_before_aggregate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    roots = fixture["roots"]
    assert isinstance(roots, CampaignReleaseRoots)

    def initial_aggregate(**kwargs: object) -> dict[str, object]:
        release = Path(kwargs["release_root"]) / str(kwargs["release_id"])
        _write(release / "payload/release.json", {"releaseId": RELEASE_ID})
        return {
            "schema": "quwoquan_data.aggregate_release_result",
            "releaseId": RELEASE_ID,
            "releaseRoot": str(release),
            "executionIds": list(kwargs["execution_ids"]),
            "canonicalMerkle": "sha256:" + "e" * 64,
            "idempotent": False,
        }

    monkeypatch.setattr(campaign_release, "build_aggregate_release", initial_aggregate)
    initial = build_campaign_release(
        root_execution_id=str(fixture["rootId"]),
        release_id=RELEASE_ID,
        roots=roots,
    )
    selection_path = Path(initial["campaignSelectionAttestation"])
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    selection["unexpectedEvidence"] = {"accepted": True}
    selection["selectionDigest"] = _digest(
        {key: value for key, value in selection.items() if key != "selectionDigest"}
    )
    _write(selection_path, selection)
    target_release = roots.release_root / RELEASE_ID
    shutil.rmtree(target_release)

    aggregate_calls = 0

    def forbidden_aggregate(**_kwargs: object) -> dict[str, object]:
        nonlocal aggregate_calls
        aggregate_calls += 1
        raise AssertionError("selection with extra keys must block before aggregate")

    monkeypatch.setattr(
        campaign_release,
        "build_aggregate_release",
        forbidden_aggregate,
    )
    with pytest.raises(CampaignReleaseError) as caught:
        build_campaign_release(
            root_execution_id=str(fixture["rootId"]),
            release_id=RELEASE_ID,
            roots=roots,
        )

    assert caught.value.code == "DATA.CAMPAIGN.RELEASE_ATTESTATION_CONFLICT"
    assert aggregate_calls == 0
    assert not target_release.exists()


def test_campaign_release__existing_release_without_selection_backfills_attestation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    roots = fixture["roots"]
    assert isinstance(roots, CampaignReleaseRoots)
    target_release = roots.release_root / RELEASE_ID
    _write(target_release / "payload/release.json", {"releaseId": RELEASE_ID})
    aggregate_calls = 0

    def idempotent_aggregate(**kwargs: object) -> dict[str, object]:
        nonlocal aggregate_calls
        aggregate_calls += 1
        assert Path(kwargs["release_root"]) / str(kwargs["release_id"]) == target_release
        return {
            "schema": "quwoquan_data.aggregate_release_result",
            "releaseId": RELEASE_ID,
            "releaseRoot": str(target_release),
            "executionIds": list(kwargs["execution_ids"]),
            "canonicalMerkle": "sha256:" + "e" * 64,
            "idempotent": True,
        }

    monkeypatch.setattr(
        campaign_release,
        "build_aggregate_release",
        idempotent_aggregate,
    )
    result = build_campaign_release(
        root_execution_id=str(fixture["rootId"]),
        release_id=RELEASE_ID,
        roots=roots,
    )
    selection_path = Path(result["campaignSelectionAttestation"])
    selection = json.loads(selection_path.read_text(encoding="utf-8"))

    assert aggregate_calls == 1
    assert result["idempotent"] is True
    assert selection["releaseId"] == RELEASE_ID
    assert selection["manifestDigest"] == payload_digest(target_release)
    assert selection_path.is_file()


def test_campaign_release_accepts_audited_submission_only_predecessor_for_lineage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    roots = fixture["roots"]
    assert isinstance(roots, CampaignReleaseRoots)
    predecessor_image_id = str(fixture["olderImageId"])
    shutil.rmtree(roots.tasks_root / predecessor_image_id)
    predecessor_root_id = _execution_id("homepage", 200)
    predecessor_campaign = roots.campaigns_root / predecessor_root_id
    current_campaign = fixture["campaignRoot"]
    assert isinstance(current_campaign, Path)
    current_submissions = {
        carrier: json.loads(
            (
                current_campaign
                / "submissions"
                / f"{fixture['executionIds'][carrier]}.json"
            ).read_text(encoding="utf-8")
        )
        for carrier in CARRIERS
    }
    for carrier in CARRIERS:
        current = current_submissions[carrier]
        predecessor_id = _execution_id(carrier, 200)
        stable = {
            key: value
            for key, value in current.items()
            if key not in {"requestDigest", "submittedAt", "predecessorReconciliation"}
        }
        stable.update(
            {
                "rootExecutionId": predecessor_root_id,
                "executionId": predecessor_id,
                "retryOf": None,
            }
        )
        _write(
            predecessor_campaign / "submissions" / f"{predecessor_id}.json",
            {
                **stable,
                "requestDigest": _digest(stable),
                "submittedAt": "2026-08-05T00:00:00+00:00",
            },
        )
    blocker = roots.output_root / "data/local/cache/preflight.json"
    _write(
        blocker,
        {
            "ready": False,
            "semanticAgentStartup": {
                "provider": "codex_sdk",
                "checked": True,
                "ready": False,
                "issues": ["capacity rejected"],
            },
        },
    )
    source_document = current_submissions["image"]["sourceDigest"]
    monkeypatch.setattr(
        campaign_submission_reconciliation,
        "current_source_digest",
        lambda **_kwargs: SimpleNamespace(
            to_document=lambda: dict(source_document)
        ),
    )
    monkeypatch.setattr(
        campaign_submission_reconciliation,
        "entity_catalog_digest",
        lambda _ref: CATALOG_DIGEST,
    )
    _receipt, receipt_path = (
        campaign_submission_reconciliation.reconcile_submission_only_campaign(
            predecessor_root_id,
            reason="provider_rejected",
            blocker_evidence=blocker,
            repo_root=tmp_path,
            output_root=roots.output_root,
        )
    )
    reference = campaign_submission_reconciliation.reconciliation_reference(
        receipt_path,
        output_root=roots.output_root,
    )
    image_path = (
        current_campaign
        / "submissions"
        / f"{fixture['executionIds']['image']}.json"
    )
    image = json.loads(image_path.read_text(encoding="utf-8"))
    image_stable = {
        key: value for key, value in image.items() if key not in {"requestDigest", "submittedAt"}
    }
    image_stable["predecessorReconciliation"] = reference
    image = {
        **image_stable,
        "requestDigest": _digest(image_stable),
        "submittedAt": image["submittedAt"],
    }
    _write(image_path, image)
    plan_path = current_campaign / "campaign_plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan["submissionDigests"]["image"] = image["requestDigest"]
    plan_stable = {key: value for key, value in plan.items() if key != "planDigest"}
    plan["planDigest"] = _digest(plan_stable)
    _write(plan_path, plan)
    runtime_path = current_campaign / "runtime/snapshot.json"
    runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
    runtime["planDigest"] = plan["planDigest"]
    _write(runtime_path, runtime)

    def aggregate(**kwargs: object) -> dict[str, object]:
        release = Path(kwargs["release_root"]) / str(kwargs["release_id"])
        _write(release / "payload/release.json", {"releaseId": RELEASE_ID})
        return {
            "schema": "quwoquan_data.aggregate_release_result",
            "releaseId": RELEASE_ID,
            "releaseRoot": str(release),
            "executionIds": list(kwargs["execution_ids"]),
            "canonicalMerkle": "sha256:" + "e" * 64,
            "idempotent": False,
        }

    monkeypatch.setattr(campaign_release, "build_aggregate_release", aggregate)
    result = build_campaign_release(
        root_execution_id=str(fixture["rootId"]),
        release_id=RELEASE_ID,
        roots=roots,
    )
    attestation = json.loads(
        Path(result["campaignSelectionAttestation"]).read_text(encoding="utf-8")
    )

    assert attestation["retryLineage"]["image"] == [
        fixture["executionIds"]["image"],
        predecessor_image_id,
    ]
    assert set(attestation["executionIds"].values()) == set(
        fixture["executionIds"].values()
    )


def test_campaign_release__publish_ref_digest_tamper_blocks_aggregate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    image_id = fixture["executionIds"]["image"]
    roots = fixture["roots"]
    assert isinstance(roots, CampaignReleaseRoots)
    publish_path = roots.tasks_root / image_id / "publish_ref.json"
    publish = json.loads(publish_path.read_text(encoding="utf-8"))
    publish["publishedRefs"]["posts"].append("image/测试/injected/001")
    _write(publish_path, publish)

    monkeypatch.setattr(
        campaign_release,
        "build_aggregate_release",
        lambda **_kwargs: pytest.fail("aggregate must not run"),
    )
    with pytest.raises(CampaignReleaseError) as caught:
        build_campaign_release(
            root_execution_id=str(fixture["rootId"]),
            release_id=RELEASE_ID,
            roots=roots,
        )
    assert caught.value.code == "DATA.CAMPAIGN.RELEASE_PUBLISH_BINDING_DRIFT"


def test_campaign_release__stale_runtime_checkpoint_blocks_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    campaign_root = fixture["campaignRoot"]
    assert isinstance(campaign_root, Path)
    checkpoint_path = campaign_root / "runtime/lanes/video.json"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    checkpoint["generation"] = 2
    _write(checkpoint_path, checkpoint)
    monkeypatch.setattr(
        campaign_release,
        "build_aggregate_release",
        lambda **_kwargs: pytest.fail("aggregate must not run"),
    )

    with pytest.raises(CampaignReleaseError) as caught:
        build_campaign_release(
            root_execution_id=str(fixture["rootId"]),
            release_id=RELEASE_ID,
            roots=fixture["roots"],
        )
    assert caught.value.code == "DATA.CAMPAIGN.RELEASE_FENCE_DRIFT"
