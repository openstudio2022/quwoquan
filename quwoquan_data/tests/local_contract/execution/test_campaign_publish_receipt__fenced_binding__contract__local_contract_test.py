from __future__ import annotations

import fcntl
import hashlib
import inspect
import json
from pathlib import Path

import pytest
from content.execution.campaign.external_inputs import payload_digest
from content.execution.campaign.receipt import (
    CampaignReceiptError,
    lane_receipt_path,
    load_lane_receipt,
    project_publish_receipt_binding,
    write_publish_receipt,
)
from content.execution.campaign.workspace import (
    CampaignRuntimePaths,
    lane_execution_root,
)
from content.release.canonical.campaign_release_contract import CampaignReleaseRoots
from content.release.canonical.campaign_release_publish import validate_lane_publish
from core.io import read_json, write_json
from support.capacity_calibration_fixture import synthetic_capacity_source_binding
from support.semantic_preflight_fixture import ready_semantic_preflight

CARRIERS = ("homepage", "article", "image", "video")
WORKLOADS = {carrier: 1 for carrier in CARRIERS}
ROOT_ID = "20260805--travel-homepage-m100--china--scale-301"
EXECUTION_IDS = {
    carrier: (
        ROOT_ID
        if carrier == "homepage"
        else f"20260805--travel-{carrier}-m100--china--scale-301"
    )
    for carrier in CARRIERS
}
RUN_ID = "current-controller-run"
FENCING_TOKEN = "sha256:" + "f" * 64


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path) -> tuple[CampaignRuntimePaths, Path, Path]:
    output = tmp_path / "output"
    runtime = CampaignRuntimePaths(
        repo_root=tmp_path / "repo",
        output_root=output,
        publish_root=tmp_path / "publish",
        campaigns_root=(output / "data/local/workspace/content-campaign-submissions"),
        workspaces_root=output / "data/local/cache/content-campaign-workspaces",
    )
    _preflight_path, semantic_preflight_binding = ready_semantic_preflight(
        "default",
        output_root=runtime.output_root,
    )
    campaign = runtime.campaigns_root / ROOT_ID
    empty_external_digest = payload_digest(
        {"schema": "quwoquan_data.campaign_external_input_set", "refs": []}
    )
    lane_inputs = {
        carrier: {
            "executionId": EXECUTION_IDS[carrier],
            "externalInputRefs": [],
            "externalInputsDigest": empty_external_digest,
        }
        for carrier in CARRIERS
    }
    pool_stable = {
        "schema": "quwoquan_data.scale_source_pool",
        "poolId": "publish-receipt-m100-pool",
        "targetScale": "M100",
        "workloadMode": "milestone_preset",
        "activeCarriers": list(CARRIERS),
        "workloadTargets": WORKLOADS,
        "sourceRevision": "sha256:" + "b" * 64,
        "sourceDigest": "sha256:" + "c" * 64,
        "entityCatalogDigest": "sha256:" + "d" * 64,
        "candidates": [
            {"candidateId": f"{carrier}-candidate-001", "carrier": carrier}
            for carrier in CARRIERS
        ],
    }
    pool = {**pool_stable, "planDigest": payload_digest(pool_stable)}
    pool_path = output / "data/local/workspace/scale-source-pool/plan.json"
    write_json(pool_path, pool)
    evidence_root = output / "data/local/workspace/scale-source-pool/evidence"
    evidence_root.mkdir(parents=True)
    pool_binding = {
        "poolId": pool["poolId"],
        "targetScale": pool["targetScale"],
        "workloadMode": pool["workloadMode"],
        "activeCarriers": pool["activeCarriers"],
        "workloadTargets": pool["workloadTargets"],
        "sourceRevision": pool["sourceRevision"],
        "sourceDigest": pool["sourceDigest"],
        "entityCatalogDigest": pool["entityCatalogDigest"],
        "planRef": pool_path.relative_to(output).as_posix(),
        "planDigest": pool["planDigest"],
        "planFileSha256": _digest(pool_path),
    }
    pool_selections = {}
    for carrier in CARRIERS:
        selection = {
            "carrier": carrier,
            "candidateIds": [f"{carrier}-candidate-001"],
            "candidateCount": 1,
        }
        pool_selections[carrier] = {
            **selection,
            "selectionDigest": payload_digest(selection),
        }
    plan_stable = {
        "schema": "quwoquan_data.content_campaign_plan",
        "rootExecutionId": ROOT_ID,
        "executionMode": "central",
        "scale": "M100",
        "workloadMode": "milestone_preset",
        "activeCarriers": list(CARRIERS),
        "workloads": WORKLOADS,
        "capacityCalibration": synthetic_capacity_source_binding(),
        "gitBranch": "dev1.0",
        "gitCommitSha": "a" * 40,
        "sourceRevision": "sha256:" + "b" * 64,
        "sourceDigest": "sha256:" + "c" * 64,
        "executionBundle": {
            "algorithm": "sha256",
            "digest": "sha256:" + "e" * 64,
            "inputs": ["quwoquan_data/scripts"],
        },
        "entityCatalogDigest": "sha256:" + "d" * 64,
        "semanticSelectionId": "default",
        "semanticPreflightReceipt": semantic_preflight_binding,
        "scaleSourcePool": pool_binding,
        "sourcePoolEvidenceRootRef": evidence_root.relative_to(output).as_posix(),
        "laneSourcePoolSelections": pool_selections,
        "laneExternalInputs": lane_inputs,
        "externalInputsDigest": payload_digest(
            {
                "schema": "quwoquan_data.campaign_external_input_lanes",
                "lanes": lane_inputs,
            }
        ),
        "submissionDigests": {
            carrier: "sha256:" + str(index + 1) * 64
            for index, carrier in enumerate(CARRIERS)
        },
        "executionIds": EXECUTION_IDS,
        "frozenAt": "2026-08-05T00:00:00+00:00",
    }
    plan = {**plan_stable, "planDigest": payload_digest(plan_stable)}
    write_json(campaign / "campaign_plan.json", plan)
    write_json(
        lane_receipt_path(ROOT_ID, "image", "review", root=runtime.campaigns_root),
        {
            "schema": "quwoquan_data.content_campaign_lane_receipt",
            "rootExecutionId": ROOT_ID,
            "executionId": EXECUTION_IDS["image"],
            "carrier": "image",
            "phase": "review",
            "status": "qualified",
            "approvedQuota": 1,
            "qualifiedCount": 1,
            "finalizedCount": 0,
            "selectedCount": 1,
            "discardedCount": 0,
            "shortfallCount": 0,
            "discards": [],
        },
    )
    execution_root_path = lane_execution_root(runtime, EXECUTION_IDS["image"])
    publish_path = execution_root_path / "publish_ref.json"
    write_json(
        publish_path,
        {
            "schema": "quwoquan_data.execution_publish_ref",
            "executionId": EXECUTION_IDS["image"],
            "canonicalPublishRoot": "canonical-publish",
            "publishedRefs": {
                "entities": [],
                "posts": ["image/测试/image-001/001"],
            },
            "publishDiscards": [],
        },
    )
    write_json(
        campaign / "runtime/snapshot.json",
        {
            "schema": "quwoquan_data.content_campaign_runtime_snapshot",
            "rootExecutionId": ROOT_ID,
            "runId": RUN_ID,
            "generation": 4,
            "fencingToken": FENCING_TOKEN,
            "status": "active",
            "phase": "publish",
            "planDigest": plan["planDigest"],
            "lanes": {
                "image": {
                    "executionId": EXECUTION_IDS["image"],
                    "phase": "run",
                    "status": "running",
                }
            },
        },
    )
    checkpoint_path = campaign / "runtime/lanes/image.json"
    write_json(
        checkpoint_path,
        {
            "schema": "quwoquan_data.content_campaign_lane_checkpoint",
            "rootExecutionId": ROOT_ID,
            "runId": RUN_ID,
            "generation": 4,
            "fencingToken": FENCING_TOKEN,
            "carrier": "image",
            "executionId": EXECUTION_IDS["image"],
            "phase": "run",
            "status": "running",
            "executionRoot": str(execution_root_path),
            "returnCode": 0,
        },
    )
    return runtime, publish_path, checkpoint_path


def test_publish_receipt_projects_publish_ref_and_fence_without_caller_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, publish_path, _checkpoint_path = _fixture(tmp_path)
    monkeypatch.setenv("QWQ_CAMPAIGN_RUN_ID", "forged-env-run")
    monkeypatch.setenv("QWQ_CAMPAIGN_GENERATION", "999")
    monkeypatch.setenv("QWQ_CAMPAIGN_FENCING_TOKEN", "sha256:" + "0" * 64)

    path = write_publish_receipt(
        root_execution_id=ROOT_ID,
        execution_id=EXECUTION_IDS["image"],
        runtime_paths=runtime,
    )
    receipt = read_json(path)

    assert receipt["executionPublishRef"] == (
        f"data/tasks/{EXECUTION_IDS['image']}/publish_ref.json"
    )
    assert receipt["executionPublishSha256"] == _digest(publish_path)
    assert receipt["campaignRunId"] == RUN_ID
    assert receipt["campaignGeneration"] == 4
    assert receipt["campaignFencingToken"] == FENCING_TOKEN
    assert project_publish_receipt_binding(
        root_execution_id=ROOT_ID,
        execution_id=EXECUTION_IDS["image"],
        runtime_paths=runtime,
    ) == {
        key: receipt[key]
        for key in (
            "executionPublishRef",
            "executionPublishSha256",
            "campaignRunId",
            "campaignGeneration",
            "campaignFencingToken",
        )
    }
    parameters = inspect.signature(write_publish_receipt).parameters
    assert not {
        "execution_publish_ref",
        "execution_publish_sha256",
        "campaign_run_id",
        "campaign_generation",
        "campaign_fencing_token",
    }.intersection(parameters)


def test_publish_receipt_projects_distributed_lane_claim(
    tmp_path: Path,
) -> None:
    runtime, publish_path, _checkpoint_path = _fixture(tmp_path)
    campaign = runtime.campaigns_root / ROOT_ID
    plan_path = campaign / "campaign_plan.json"
    plan = read_json(plan_path)
    stable = {key: value for key, value in plan.items() if key != "planDigest"}
    stable["executionMode"] = "distributed"
    stable["distributedRun"] = {
        "campaignRunId": "distributed-campaign-run",
        "campaignGeneration": 1,
        "campaignFencingToken": "sha256:" + "7" * 64,
    }
    write_json(plan_path, {**stable, "planDigest": payload_digest(stable)})
    write_json(
        campaign / "claims/image.json",
        {
            "schema": "quwoquan_data.content_campaign_lane_claim",
            "rootExecutionId": ROOT_ID,
            "planDigest": payload_digest(stable),
            "campaignRunId": "distributed-campaign-run",
            "campaignGeneration": 1,
            "campaignFencingToken": "sha256:" + "7" * 64,
            "carrier": "image",
            "executionId": EXECUTION_IDS["image"],
            "claimId": "sha256:" + "8" * 64,
            "claimAttempt": 1,
            "status": "running",
            "phase": "run",
            "capsuleRef": "data/local/cache/capsule",
            "executionRoot": str(lane_execution_root(runtime, EXECUTION_IDS["image"])),
            "pid": 123,
            "pgid": 123,
            "returnCode": None,
            "error": None,
            "acquiredAt": "2026-08-05T00:00:00+00:00",
            "heartbeatAt": "2026-08-05T00:00:01+00:00",
            "updatedAt": "2026-08-05T00:00:01+00:00",
            "finishedAt": None,
        },
    )

    lock_path = campaign / "claims/.image.lock"
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        path = write_publish_receipt(
            root_execution_id=ROOT_ID,
            execution_id=EXECUTION_IDS["image"],
            runtime_paths=runtime,
        )
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    receipt = read_json(path)

    assert receipt["executionPublishSha256"] == _digest(publish_path)
    assert receipt["campaignRunId"] == "distributed-campaign-run"
    assert receipt["campaignGeneration"] == 1
    assert receipt["campaignFencingToken"] == "sha256:" + "7" * 64


def test_publish_receipt_freezes_review_count_and_per_object_publish_discards(
    tmp_path: Path,
) -> None:
    runtime, publish_path, _checkpoint_path = _fixture(tmp_path)
    review_path = lane_receipt_path(
        ROOT_ID,
        "image",
        "review",
        root=runtime.campaigns_root,
    )
    review = read_json(review_path)
    review.update(
        {
            "approvedQuota": 3,
            "qualifiedCount": 3,
            "selectedCount": 3,
            "shortfallCount": 0,
        }
    )
    write_json(review_path, review)
    publish = read_json(publish_path)
    publish["publishedRefs"]["posts"] = [
        "image/测试/image-001/001",
        "image/测试/image-002/001",
    ]
    publish["publishDiscards"] = [
        {
            "objectRef": "image/测试/image-003/001",
            "issues": ["DATA.PUBLISH.OBJECT_APPLY_FAILED"],
        }
    ]
    write_json(publish_path, publish)

    path = write_publish_receipt(
        root_execution_id=ROOT_ID,
        execution_id=EXECUTION_IDS["image"],
        runtime_paths=runtime,
    )
    receipt = read_json(path)

    assert receipt["status"] == "partial"
    assert receipt["reviewQualifiedCount"] == receipt["qualifiedCount"] == 3
    assert receipt["finalizedCount"] == 2
    assert receipt["publishDiscards"] == publish["publishDiscards"]


def test_partial_publish_receipt_closes_campaign_release_with_success_refs_only(
    tmp_path: Path,
) -> None:
    runtime, publish_path, _checkpoint_path = _fixture(tmp_path)
    campaign = runtime.campaigns_root / ROOT_ID
    review_path = lane_receipt_path(
        ROOT_ID, "image", "review", root=runtime.campaigns_root
    )
    review = read_json(review_path)
    review.update(
        {
            "approvedQuota": 3,
            "qualifiedCount": 3,
            "selectedCount": 3,
            "shortfallCount": 0,
        }
    )
    write_json(review_path, review)
    succeeded = [
        "image/测试/image-001/001",
        "image/测试/image-002/001",
    ]
    publish = read_json(publish_path)
    publish["publishedRefs"]["posts"] = succeeded
    publish["publishDiscards"] = [
        {
            "objectRef": "image/测试/image-003/001",
            "issues": ["DATA.PUBLISH.OBJECT_APPLY_FAILED"],
        }
    ]
    write_json(publish_path, publish)
    receipt_path = write_publish_receipt(
        root_execution_id=ROOT_ID,
        execution_id=EXECUTION_IDS["image"],
        runtime_paths=runtime,
    )
    source_digest = {"algorithm": "sha256", "digest": "c" * 64}
    for ref in succeeded:
        write_json(
            runtime.publish_root / "posts" / ref / "manifest.json",
            {
                "executionId": EXECUTION_IDS["image"],
                "sourceDigest": source_digest,
                "contentType": "image",
            },
        )
    plan = read_json(campaign / "campaign_plan.json")
    runtime_snapshot = read_json(campaign / "runtime/snapshot.json")
    roots = CampaignReleaseRoots(
        output_root=runtime.output_root,
        campaigns_root=runtime.campaigns_root,
        tasks_root=runtime.output_root / "data/tasks",
        publish_root=runtime.publish_root,
        release_root=runtime.output_root / "data/releases",
    )

    closure = validate_lane_publish(
        ROOT_ID,
        "image",
        plan,
        {"quota": 3, "sourceDigest": source_digest},
        runtime_snapshot,
        roots=roots,
    )

    assert closure["finalizedCount"] == 2
    assert closure["reviewQualifiedCount"] == 3
    assert closure["publishDiscardedCount"] == 1
    assert closure["publishReceiptSha256"] == _digest(receipt_path)


def test_publish_receipt_freezes_zero_success_as_blocked_not_partial(
    tmp_path: Path,
) -> None:
    runtime, publish_path, _checkpoint_path = _fixture(tmp_path)
    publish = read_json(publish_path)
    publish["publishedRefs"]["posts"] = []
    publish["publishDiscards"] = [
        {
            "objectRef": "image/测试/image-001/001",
            "issues": ["DATA.PUBLISH.OBJECT_APPLY_FAILED"],
        }
    ]
    write_json(publish_path, publish)

    receipt = read_json(
        write_publish_receipt(
            root_execution_id=ROOT_ID,
            execution_id=EXECUTION_IDS["image"],
            runtime_paths=runtime,
        )
    )

    assert receipt["status"] == "blocked"
    assert receipt["reviewQualifiedCount"] == receipt["qualifiedCount"] == 1
    assert receipt["finalizedCount"] == 0
    assert len(receipt["publishDiscards"]) == 1


def test_publish_receipt_blocks_stale_checkpoint_before_writing(tmp_path: Path) -> None:
    runtime, _publish_path, checkpoint_path = _fixture(tmp_path)
    checkpoint = read_json(checkpoint_path)
    checkpoint["generation"] = 3
    write_json(checkpoint_path, checkpoint)

    with pytest.raises(CampaignReceiptError) as caught:
        write_publish_receipt(
            root_execution_id=ROOT_ID,
            execution_id=EXECUTION_IDS["image"],
            runtime_paths=runtime,
        )

    assert caught.value.code == "DATA.CAMPAIGN.RECEIPT_CHECKPOINT_DRIFT"
    assert not lane_receipt_path(
        ROOT_ID,
        "image",
        "publish",
        root=runtime.campaigns_root,
    ).exists()


def test_publish_receipt_create_once_detects_publish_ref_byte_drift(
    tmp_path: Path,
) -> None:
    runtime, publish_path, _checkpoint_path = _fixture(tmp_path)
    path = write_publish_receipt(
        root_execution_id=ROOT_ID,
        execution_id=EXECUTION_IDS["image"],
        runtime_paths=runtime,
    )
    publish = read_json(publish_path)
    publish_path.write_text(
        json.dumps(publish, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(CampaignReceiptError) as caught:
        write_publish_receipt(
            root_execution_id=ROOT_ID,
            execution_id=EXECUTION_IDS["image"],
            runtime_paths=runtime,
        )

    assert caught.value.code == "DATA.CAMPAIGN.RECEIPT_IMMUTABLE_COLLISION"
    assert read_json(path)["executionPublishSha256"] != _digest(publish_path)


def test_lane_receipt_contract_requires_publish_binding_and_forbids_it_on_review(
    tmp_path: Path,
) -> None:
    campaigns_root = tmp_path / "campaigns"
    base = {
        "schema": "quwoquan_data.content_campaign_lane_receipt",
        "rootExecutionId": ROOT_ID,
        "executionId": EXECUTION_IDS["image"],
        "carrier": "image",
        "phase": "publish",
        "status": "finalized",
        "approvedQuota": 1,
        "qualifiedCount": 1,
        "finalizedCount": 1,
        "selectedCount": 1,
        "discardedCount": 0,
        "shortfallCount": 0,
        "discards": [],
    }
    publish_path = lane_receipt_path(
        ROOT_ID,
        "image",
        "publish",
        root=campaigns_root,
    )
    write_json(publish_path, base)
    with pytest.raises(CampaignReceiptError) as missing:
        load_lane_receipt(
            ROOT_ID,
            "image",
            "publish",
            root=campaigns_root,
        )
    assert missing.value.code == "DATA.CAMPAIGN.RECEIPT_PUBLISH_BINDING_MISSING"

    review = {
        **base,
        "phase": "review",
        "status": "qualified",
        "finalizedCount": 0,
        "executionPublishRef": "data/tasks/example/publish_ref.json",
    }
    review_path = lane_receipt_path(
        ROOT_ID,
        "image",
        "review",
        root=campaigns_root,
    )
    write_json(review_path, review)
    with pytest.raises(CampaignReceiptError) as forbidden:
        load_lane_receipt(
            ROOT_ID,
            "image",
            "review",
            root=campaigns_root,
        )
    assert forbidden.value.code == "DATA.CAMPAIGN.RECEIPT_REVIEW_BINDING_FORBIDDEN"
