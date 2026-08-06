from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path

import pytest
from content.execution.campaign_external_inputs import payload_digest
from content.execution.campaign_receipt import (
    CampaignReceiptError,
    lane_receipt_path,
    load_lane_receipt,
    project_publish_receipt_binding,
    write_publish_receipt,
)
from content.execution.campaign_workspace import (
    CampaignRuntimePaths,
    lane_execution_root,
)
from core.io import read_json, write_json
from support.semantic_preflight_fixture import ready_semantic_preflight

CARRIERS = ("homepage", "article", "image", "video")
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
    plan_stable = {
        "schema": "quwoquan_data.content_campaign_plan",
        "rootExecutionId": ROOT_ID,
        "gitBranch": "dev1.0",
        "gitCommitSha": "a" * 40,
        "sourceRevision": "sha256:" + "b" * 64,
        "sourceDigest": "sha256:" + "c" * 64,
        "entityCatalogDigest": "sha256:" + "d" * 64,
        "semanticSelectionId": "default",
        "semanticPreflightReceipt": semantic_preflight_binding,
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
            "canonicalPublishRoot": "quwoquan_data/publish",
            "publishedRefs": {
                "entities": [],
                "posts": ["image/测试/image-001/001"],
            },
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
