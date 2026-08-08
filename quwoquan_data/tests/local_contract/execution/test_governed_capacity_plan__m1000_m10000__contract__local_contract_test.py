from __future__ import annotations

from datetime import datetime, timezone

import pytest

from content.execution.preflight.receipt import build_semantic_preflight_receipt
from content.execution.preflight.selection import (
    bind_semantic_preflight_selection,
    resolve_semantic_preflight_selection,
)
from content.execution.scale.capacity_plan import (
    CAPACITY_PLAN_INVALID,
    CAPACITY_SHORTFALL,
    PREDECESSOR_IDENTITY_DRIFT,
    GovernedCapacityPlanError,
    build_governed_capacity_plan,
    throughput_basis_digest,
)
from core.schema import assert_valid


CARRIERS = ("homepage", "article", "image", "video")


def _preflight(*, effective_concurrency: int = 8) -> dict[str, object]:
    selection = resolve_semantic_preflight_selection("cursor_auto")
    preflight = {
        "provider": "cursor_sdk",
        "semanticAgentStartup": {
            "checked": True,
            "ready": True,
            "provider": "cursor_sdk",
            "model": "auto",
            "runtime": "local",
        },
        "reliableTaskFleet": {
            "checked": True,
            "ready": True,
            "target": "local-contract",
            "mongo": True,
            "redis": True,
            "owned": True,
            "issues": [],
        },
        "ready": True,
        "issues": [],
    }
    bind_semantic_preflight_selection(preflight, selection)
    report = {
        **selection.document(),
        "selectionDigest": selection.selection_digest,
        "fallbackPolicy": "forbidden",
        "preflight": preflight,
        "semanticAgentStartup": preflight["semanticAgentStartup"],
        "capacitySoak": {
            **selection.document(),
            "selectionDigest": selection.selection_digest,
            "ready": True,
            "attempts": effective_concurrency,
            "successCount": effective_concurrency,
            "effectiveConcurrency": effective_concurrency,
            "bridgeDisconnectCount": 0,
            "issues": [],
        },
        "startupRequested": True,
        "soakRequested": True,
        "workspaceSmokeRequested": False,
        "ready": True,
    }
    return build_semantic_preflight_receipt(selection=selection, report=report)


def _promotion(*, target_scale: str = "M100") -> dict[str, object]:
    identity = {
        "sourceRevision": "sha256:" + "1" * 64,
        "sourceDigest": "sha256:" + "2" * 64,
        "entityCatalogDigest": "sha256:" + "3" * 64,
    }
    rows: list[dict[str, object]] = []
    resource_ref = f"data/promotions/{target_scale}/resource-soak.json"
    resource_digest = "sha256:" + "5" * 64
    for index, carrier in enumerate(CARRIERS, start=1):
        row = {
            "carrier": carrier,
            "measuredScale": target_scale,
            **identity,
            "throughputUnit": "objects_per_second_per_slot",
            "perSlotThroughputSamples": [0.005 * index, 0.01 * index, 0.02 * index],
            "evidenceRef": resource_ref,
            "evidenceDigest": resource_digest,
        }
        row["throughputBasisDigest"] = throughput_basis_digest(row)
        rows.append(row)
    return {
        "schema": "quwoquan_data.research_scale_promotion",
        "promotionId": f"promotion-{target_scale.lower()}",
        "releaseId": f"release-{target_scale.lower()}",
        "releaseClass": "research",
        "productLifecycleState": "research",
        "manifestDigest": "sha256:" + "4" * 64,
        **identity,
        "targetScale": target_scale,
        "nextScaleEligible": "M1000" if target_scale == "M100" else "M10000",
        "resourceSoakEvidenceRef": resource_ref,
        "resourceSoakEvidenceDigest": resource_digest,
        "capacityThroughputByCarrier": rows,
    }


def test_m1000_plan_uses_nearest_rank_p10_and_deterministic_partitions() -> None:
    receipt = _preflight(effective_concurrency=8)
    now = datetime.now(timezone.utc)
    plan = build_governed_capacity_plan(
        predecessor_promotion=_promotion(),
        target_scale="M1000",
        carrier_deltas={
            "homepage": 2_000,
            "article": 900,
            "image": 900,
            "video": 900,
        },
        preflight_receipt=receipt,
        now=now,
    )

    assert plan["budgetSeconds"] == 259_200
    assert plan["capacityUtilizationFactor"] == 0.8
    assert plan["requiredSlots"] == 5
    assert plan["availableSlots"] == 8
    assert plan["capacityHeadroomSlots"] == 3
    assert [row["carrier"] for row in plan["carrierPlans"]] == list(CARRIERS)
    assert [row["partitionCount"] for row in plan["carrierPlans"]] == [16] * 4
    assert plan["carrierPlans"][0]["p10PerSlotThroughput"] == 0.005
    assert plan["carrierPlans"][0]["requiredWorkers"] == 2
    assert plan["carrierPlans"][0]["throughputSampleCount"] == 3
    assert_valid(plan, "execution", "governed_capacity_plan")

    repeated = build_governed_capacity_plan(
        predecessor_promotion=_promotion(),
        target_scale="M1000",
        carrier_deltas={
            "homepage": 2_000,
            "article": 900,
            "image": 900,
            "video": 900,
        },
        preflight_receipt=receipt,
        now=now,
    )
    assert repeated == plan


def test_m10000_uses_seven_day_budget_and_m1000_predecessor() -> None:
    plan = build_governed_capacity_plan(
        predecessor_promotion=_promotion(target_scale="M1000"),
        target_scale="M10000",
        carrier_deltas={carrier: 9_000 for carrier in CARRIERS},
        preflight_receipt=_preflight(effective_concurrency=16),
    )

    assert plan["budgetSeconds"] == 604_800
    assert plan["predecessorPromotion"]["targetScale"] == "M1000"
    assert plan["requiredSlots"] == 9


def test_capacity_shortfall_is_typed_and_does_not_emit_a_plan() -> None:
    promotion = _promotion()
    for row in promotion["capacityThroughputByCarrier"]:
        row["perSlotThroughputSamples"] = [0.000001]
        row["throughputBasisDigest"] = throughput_basis_digest(row)

    with pytest.raises(GovernedCapacityPlanError) as captured:
        build_governed_capacity_plan(
            predecessor_promotion=promotion,
            target_scale="M1000",
            carrier_deltas={carrier: 1_000 for carrier in CARRIERS},
            preflight_receipt=_preflight(effective_concurrency=8),
        )

    assert captured.value.code == CAPACITY_SHORTFALL
    assert "requiredSlots=" in str(captured.value)


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("missing_samples", CAPACITY_PLAN_INVALID),
        ("zero_sample", CAPACITY_PLAN_INVALID),
        ("evidence_digest_drift", PREDECESSOR_IDENTITY_DRIFT),
        ("throughput_basis_digest_drift", CAPACITY_PLAN_INVALID),
        ("source_identity_drift", PREDECESSOR_IDENTITY_DRIFT),
        ("predecessor_scale_drift", PREDECESSOR_IDENTITY_DRIFT),
        ("expired_preflight", CAPACITY_PLAN_INVALID),
    ],
)
def test_missing_zero_and_drift_inputs_fail_closed(
    mutation: str, expected_code: str
) -> None:
    promotion = _promotion()
    receipt = _preflight()
    now = datetime.now(timezone.utc)
    if mutation == "missing_samples":
        promotion["capacityThroughputByCarrier"][0]["perSlotThroughputSamples"] = []
    elif mutation == "zero_sample":
        promotion["capacityThroughputByCarrier"][0]["perSlotThroughputSamples"] = [0]
    elif mutation == "evidence_digest_drift":
        promotion["capacityThroughputByCarrier"][0]["evidenceDigest"] = "sha256:" + "f" * 64
    elif mutation == "throughput_basis_digest_drift":
        promotion["capacityThroughputByCarrier"][0]["throughputBasisDigest"] = (
            "sha256:" + "f" * 64
        )
    elif mutation == "source_identity_drift":
        promotion["capacityThroughputByCarrier"][0]["sourceDigest"] = "sha256:" + "a" * 64
    elif mutation == "predecessor_scale_drift":
        promotion["targetScale"] = "M1000"
    elif mutation == "expired_preflight":
        now = datetime(2100, 1, 1, tzinfo=timezone.utc)

    with pytest.raises(GovernedCapacityPlanError) as captured:
        build_governed_capacity_plan(
            predecessor_promotion=promotion,
            target_scale="M1000",
            carrier_deltas={carrier: 900 for carrier in CARRIERS},
            preflight_receipt=receipt,
            now=now,
        )

    assert captured.value.code == expected_code


def test_partition_count_is_power_of_two_and_capped_at_256() -> None:
    promotion = _promotion()
    promotion["capacityThroughputByCarrier"][0]["perSlotThroughputSamples"] = [0.00001]
    promotion["capacityThroughputByCarrier"][0]["throughputBasisDigest"] = throughput_basis_digest(
        promotion["capacityThroughputByCarrier"][0]
    )
    plan = build_governed_capacity_plan(
        predecessor_promotion=promotion,
        target_scale="M1000",
        carrier_deltas={"homepage": 1_000, "article": 1, "image": 1, "video": 1},
        preflight_receipt=_preflight(effective_concurrency=500),
    )

    homepage = plan["carrierPlans"][0]
    assert homepage["requiredWorkers"] == 483
    assert homepage["partitionCount"] == 256
