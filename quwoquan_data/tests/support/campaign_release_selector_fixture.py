"""campaign release selector 合约测试共享常量与 campaign fixture。

由 test_campaign_release__selector_* 场景组与
terminal_unpublished_partial_retry / mixed_terminal_retry 兄弟测试共享；
从原单体测试文件逐字下沉，不改变任何 fixture 逻辑。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from content.release.canonical.campaign_release import CampaignReleaseRoots
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
    evidence_root = (
        output_root / "data/local/workspace/scale-source-pools/m100/evidence"
    )
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
        candidate = {
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
            "contentSha256": "sha256:"
            + {
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
        if carrier in {"homepage", "article"}:
            candidate["sourceReadyEvidenceRootRef"] = "."
        candidates.append(candidate)
    pool_stable: dict[str, object] = {
        "schema": "quwoquan_data.scale_source_pool",
        "poolId": "campaign-release-selector-m100-pool",
        "targetScale": "M100",
        "sourceRevision": source_revision,
        "sourceDigest": SOURCE_DIGEST,
        "entityCatalogDigest": CATALOG_DIGEST,
        "createdAt": "2026-08-05T00:00:00+00:00",
        "waveCandidateCounts": [
            {"carrier": carrier, "minimumCandidateCount": 1} for carrier in CARRIERS
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
            "workerHostSetBinding": None,
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
