# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-004
from __future__ import annotations

import copy
import hashlib
import json

import pytest
from content.execution.campaign.plan_source_pool import aggregate_plan_source_pool
from content.execution.planning.source_pool_policy import (
    allows_scale_source_pool,
    requires_scale_source_pool,
    source_pool_policy_fields,
)
from content.execution.request import RuntimeExecutionRequest
from core.schema import assert_valid
from core.source_digest import ExecutionBundleIdentity
from support.capacity_calibration_fixture import synthetic_capacity_source_binding

DIGEST = "sha256:" + "a" * 64
BINDING = {
    "poolId": "pool-m100",
    "targetScale": "WORKLOAD",
    "workloadMode": "explicit",
    "activeCarriers": ["homepage", "article", "image", "video"],
    "workloadTargets": {
        "homepage": 2,
        "article": 2,
        "image": 2,
        "video": 2,
    },
    "sourceRevision": DIGEST,
    "sourceDigest": "sha256:" + "b" * 64,
    "entityCatalogDigest": "sha256:" + "c" * 64,
    "planRef": "data/local/workspace/source-pool/plan.json",
    "planDigest": "sha256:" + "d" * 64,
    "planFileSha256": "sha256:" + "e" * 64,
}
EXECUTION_BUNDLE = ExecutionBundleIdentity(DIGEST).to_document()


def _selection(carrier: str, count: int = 2) -> dict[str, object]:
    stable = {
        "carrier": carrier,
        "candidateIds": [f"{carrier}-{index}" for index in range(count)],
        "candidateCount": count,
    }
    encoded = json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()
    return {**stable, "selectionDigest": "sha256:" + hashlib.sha256(encoded).hexdigest()}


def _submissions() -> dict[str, dict[str, object]]:
    return {
        carrier: {
            "scaleSourcePool": copy.deepcopy(BINDING),
            "sourcePoolEvidenceRootRef": "data/local/workspace/source-pool/evidence",
            "sourcePoolSelection": _selection(carrier),
        }
        for carrier in ("homepage", "article", "image", "video")
    }


def test_plan_aggregates_one_binding_and_exact_carrier_closed_selections() -> None:
    binding, evidence_ref, selections = aggregate_plan_source_pool(_submissions())

    assert binding == BINDING
    assert evidence_ref == "data/local/workspace/source-pool/evidence"
    assert selections is not None
    assert set(selections) == {"homepage", "article", "image", "video"}
    assert selections["video"]["candidateIds"] == ["video-0", "video-1"]


def test_plan_rejects_cross_lane_pool_or_selection_drift() -> None:
    submissions = _submissions()
    submissions["video"]["scaleSourcePool"]["planDigest"] = "sha256:" + "1" * 64
    with pytest.raises(ValueError, match="POOL_SHORTFALL.*binding drift"):
        aggregate_plan_source_pool(submissions)

    submissions = _submissions()
    submissions["video"]["sourcePoolSelection"]["carrier"] = "image"
    with pytest.raises(ValueError, match="POOL_SHORTFALL.*video pool selection drift"):
        aggregate_plan_source_pool(submissions)


def test_runtime_request_round_trip_preserves_source_pool_exactly() -> None:
    request = RuntimeExecutionRequest.from_document(
        {
            "familyRef": "content/travel/video/base",
            "regionRef": "china",
            "selector": "source-ready-priority",
            "count": 2,
            "quota": 1,
            "capacityCalibration": synthetic_capacity_source_binding(),
            "workerHostSetBinding": None,
            "topic": None,
            "sourceProviders": [],
            "targetNames": [],
            "scaleSourcePool": BINDING,
            "sourcePoolEvidenceRootRef": "data/local/workspace/source-pool/evidence",
            "sourcePoolSelection": _selection("video"),
        }
    )

    assert request.to_document()["scaleSourcePool"] == BINDING
    assert request.to_document()["sourcePoolSelection"] == _selection("video")


def test_campaign_plan_scale_pool_matches_frozen_active_workload() -> None:
    execution_ids = {
        carrier: f"20260808--travel-{carrier}-m100--china--scale-001"
        for carrier in ("homepage", "article", "image", "video")
    }
    lane_inputs = {
        carrier: {
            "executionId": execution_id,
            "externalInputRefs": [],
            "externalInputsDigest": DIGEST,
        }
        for carrier, execution_id in execution_ids.items()
    }
    plan = {
        "schema": "quwoquan_data.content_campaign_plan",
        "rootExecutionId": execution_ids["homepage"],
        "executionMode": "central",
        "scale": "M100",
        "workloadMode": "explicit",
        "activeCarriers": list(execution_ids),
        "workloads": dict(BINDING["workloadTargets"]),
        "gitBranch": "dev1.0",
        "gitCommitSha": "a" * 40,
        "sourceRevision": DIGEST,
        "sourceDigest": BINDING["sourceDigest"],
        "executionBundle": EXECUTION_BUNDLE,
        "entityCatalogDigest": BINDING["entityCatalogDigest"],
        "semanticSelectionId": "not_applicable",
        "capacityCalibration": synthetic_capacity_source_binding(),
        "scaleSourcePool": BINDING,
        "sourcePoolEvidenceRootRef": "data/local/workspace/source-pool/evidence",
        "laneSourcePoolSelections": {
            carrier: _selection(carrier) for carrier in execution_ids
        },
        "laneExternalInputs": lane_inputs,
        "externalInputsDigest": DIGEST,
        "submissionDigests": {carrier: DIGEST for carrier in execution_ids},
        "executionIds": execution_ids,
        "frozenAt": "2026-08-08T00:00:00Z",
        "planDigest": DIGEST,
    }
    assert_valid(plan, "execution", "content_campaign_plan", label="canonical M100 plan")


def test_source_pool_policy_uses_frozen_workload_instead_of_execution_intent() -> None:
    assert allows_scale_source_pool(workload_mode="explicit", scale="M1")
    assert allows_scale_source_pool(workload_mode="explicit", scale="M1000")
    assert not requires_scale_source_pool(workload_mode="explicit", scale="M10000")
    assert not requires_scale_source_pool(
        workload_mode="milestone_preset",
        scale="M1000",
    )
    assert requires_scale_source_pool(
        workload_mode="milestone_preset",
        scale="M10000",
    )
    assert source_pool_policy_fields(
        binding=None,
        evidence_root_ref=None,
        selection=None,
    ) == {}
    fields = source_pool_policy_fields(
        binding=BINDING,
        evidence_root_ref="data/local/workspace/source-pool/evidence",
        selection=_selection("video"),
    )
    assert fields["scaleSourcePool"] == BINDING


def test_explicit_plan_allows_no_pool_but_m10000_preset_requires_one() -> None:
    execution_ids = {
        carrier: f"20260808--travel-{carrier}-m100--china--scale-002"
        for carrier in ("homepage", "article", "image", "video")
    }
    lane_inputs = {
        carrier: {
            "executionId": execution_id,
            "externalInputRefs": [],
            "externalInputsDigest": DIGEST,
        }
        for carrier, execution_id in execution_ids.items()
    }
    plan = {
        "schema": "quwoquan_data.content_campaign_plan",
        "rootExecutionId": execution_ids["homepage"],
        "executionMode": "central",
        "scale": "M100",
        "workloadMode": "explicit",
        "activeCarriers": list(execution_ids),
        "workloads": {carrier: 1 for carrier in execution_ids},
        "gitBranch": "dev1.0",
        "gitCommitSha": "a" * 40,
        "sourceRevision": DIGEST,
        "sourceDigest": "sha256:" + "b" * 64,
        "executionBundle": EXECUTION_BUNDLE,
        "entityCatalogDigest": "sha256:" + "c" * 64,
        "semanticSelectionId": "not_applicable",
        "capacityCalibration": synthetic_capacity_source_binding(),
        "laneExternalInputs": lane_inputs,
        "externalInputsDigest": DIGEST,
        "submissionDigests": {carrier: DIGEST for carrier in execution_ids},
        "executionIds": execution_ids,
        "frozenAt": "2026-08-08T00:00:00Z",
        "planDigest": DIGEST,
    }
    assert_valid(plan, "execution", "content_campaign_plan")
    plan["workloadMode"] = "milestone_preset"
    plan["scale"] = "M10000"
    with pytest.raises(ValueError, match="scaleSourcePool"):
        assert_valid(plan, "execution", "content_campaign_plan")
