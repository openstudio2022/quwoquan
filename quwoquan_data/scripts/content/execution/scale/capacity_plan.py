"""Pure, fail-closed capacity planning for governed M1000/M10000 runs."""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING
from typing import Any

from content.execution.preflight.receipt import (
    validate_semantic_preflight_receipt,
)
from content.execution.queue.partition import partition_count
from core.schema import assert_valid


CARRIERS = ("homepage", "article", "image", "video")
CAPACITY_SHORTFALL = "DATA.AGENT.CAPACITY_SHORTFALL"
CAPACITY_PLAN_INVALID = "DATA.SCALE.CAPACITY_PLAN_INVALID"
PREDECESSOR_IDENTITY_DRIFT = "DATA.SCALE.PREDECESSOR_IDENTITY_DRIFT"

_TARGET_POLICY = {
    "M1000": {"predecessor": "M100", "budgetSeconds": 259_200},
    "M10000": {"predecessor": "M1000", "budgetSeconds": 604_800},
}
_UTILIZATION_FACTOR = Decimal("0.8")
_DIGEST_PREFIX = "sha256:"


class GovernedCapacityPlanError(RuntimeError):
    """Typed fail-closed capacity-plan rejection."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def _canonical_digest(value: Mapping[str, Any]) -> str:
    body = json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _DIGEST_PREFIX + hashlib.sha256(body).hexdigest()


def throughput_basis_document(row: Mapping[str, Any]) -> dict[str, Any]:
    """Return the exact document whose digest binds one carrier's samples."""

    return {
        "schema": "quwoquan_data.capacity_throughput_basis",
        "carrier": row.get("carrier"),
        "measuredScale": row.get("measuredScale"),
        "sourceRevision": row.get("sourceRevision"),
        "sourceDigest": row.get("sourceDigest"),
        "entityCatalogDigest": row.get("entityCatalogDigest"),
        "throughputUnit": row.get("throughputUnit"),
        "perSlotThroughputSamples": list(
            row.get("perSlotThroughputSamples") or []
        ),
    }


def throughput_basis_digest(row: Mapping[str, Any]) -> str:
    """Digest the governed per-slot throughput evidence projection."""

    return _canonical_digest(throughput_basis_document(row))


def _invalid(message: str) -> GovernedCapacityPlanError:
    return GovernedCapacityPlanError(CAPACITY_PLAN_INVALID, message)


def _identity_drift(message: str) -> GovernedCapacityPlanError:
    return GovernedCapacityPlanError(PREDECESSOR_IDENTITY_DRIFT, message)


def _positive_decimal(value: object, *, label: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _invalid(f"{label} must be a JSON number")
    parsed = Decimal(str(value))
    if not parsed.is_finite() or parsed <= 0:
        raise _invalid(f"{label} must be finite and greater than zero")
    return parsed


def _require_digest(value: object, *, label: str) -> str:
    text = str(value or "")
    if (
        len(text) != len(_DIGEST_PREFIX) + 64
        or not text.startswith(_DIGEST_PREFIX)
        or any(character not in "0123456789abcdef" for character in text[7:])
    ):
        raise _identity_drift(f"{label} is not a canonical sha256 digest")
    return text


def _require_safe_ref(value: object, *, label: str) -> str:
    text = str(value or "").strip()
    if not text or text.startswith("/") or ".." in text.split("/"):
        raise _invalid(f"{label} must be a safe relative evidence reference")
    return text


def _validate_predecessor(
    promotion: Mapping[str, Any], *, target_scale: str
) -> tuple[dict[str, str], list[Mapping[str, Any]]]:
    policy = _TARGET_POLICY[target_scale]
    expected_predecessor = str(policy["predecessor"])
    if (
        promotion.get("schema") != "quwoquan_data.research_scale_promotion"
        or promotion.get("releaseClass") != "research"
        or promotion.get("productLifecycleState") != "research"
        or promotion.get("targetScale") != expected_predecessor
        or promotion.get("nextScaleEligible") != target_scale
    ):
        raise _identity_drift(
            f"{target_scale} requires an eligible {expected_predecessor} research promotion"
        )
    identity = {
        "promotionId": str(promotion.get("promotionId") or ""),
        "releaseId": str(promotion.get("releaseId") or ""),
        "manifestDigest": _require_digest(
            promotion.get("manifestDigest"), label="manifestDigest"
        ),
        "sourceRevision": _require_digest(
            promotion.get("sourceRevision"), label="sourceRevision"
        ),
        "sourceDigest": _require_digest(
            promotion.get("sourceDigest"), label="sourceDigest"
        ),
        "entityCatalogDigest": _require_digest(
            promotion.get("entityCatalogDigest"), label="entityCatalogDigest"
        ),
        "resourceSoakEvidenceRef": _require_safe_ref(
            promotion.get("resourceSoakEvidenceRef"),
            label="resourceSoakEvidenceRef",
        ),
        "resourceSoakEvidenceDigest": _require_digest(
            promotion.get("resourceSoakEvidenceDigest"),
            label="resourceSoakEvidenceDigest",
        ),
        "targetScale": expected_predecessor,
    }
    if not identity["promotionId"] or not identity["releaseId"]:
        raise _identity_drift("predecessor promotion identity is incomplete")
    rows = promotion.get("capacityThroughputByCarrier")
    if not isinstance(rows, list) or len(rows) != len(CARRIERS):
        raise _invalid("capacityThroughputByCarrier must contain exactly four rows")
    return identity, rows


def _validate_deltas(carrier_deltas: Mapping[str, int]) -> dict[str, int]:
    if set(carrier_deltas) != set(CARRIERS):
        raise _invalid("carrier deltas must contain exactly homepage/article/image/video")
    result: dict[str, int] = {}
    for carrier in CARRIERS:
        value = carrier_deltas[carrier]
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise _invalid(f"{carrier} delta must be a positive integer")
        result[carrier] = value
    return result


def _validate_preflight(
    receipt: Mapping[str, Any], *, now: datetime | None
) -> tuple[int, Mapping[str, Any]]:
    observed_now = now or datetime.now(timezone.utc)
    try:
        validate_semantic_preflight_receipt(
            receipt,
            require_execution_admission=True,
            now=observed_now,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise _invalid(f"fresh semantic preflight receipt is invalid: {exc}") from exc
    evidence = receipt.get("evidence")
    capacity = (
        evidence.get("capacitySoak")
        if isinstance(evidence, Mapping)
        and isinstance(evidence.get("capacitySoak"), Mapping)
        else None
    )
    if capacity is None:
        raise _invalid("preflight capacitySoak evidence is missing")
    effective = capacity.get("effectiveConcurrency")
    success_count = capacity.get("successCount")
    attempts = capacity.get("attempts")
    disconnects = capacity.get("bridgeDisconnectCount")
    if isinstance(effective, bool) or not isinstance(effective, int) or effective <= 0:
        raise _invalid("preflight effectiveConcurrency must be a positive integer")
    if (
        isinstance(success_count, bool)
        or not isinstance(success_count, int)
        or success_count < effective
        or isinstance(attempts, bool)
        or not isinstance(attempts, int)
        or attempts < success_count
        or isinstance(disconnects, bool)
        or not isinstance(disconnects, int)
        or disconnects != 0
    ):
        raise _invalid("preflight capacity evidence is incomplete or unhealthy")
    return effective, capacity


def _nearest_rank_p10(samples: Sequence[Decimal]) -> Decimal:
    ordered = sorted(samples)
    rank = max(1, math.ceil(len(ordered) * 0.1))
    return ordered[rank - 1]


def _carrier_rows(
    *,
    rows: list[Mapping[str, Any]],
    identity: Mapping[str, str],
    deltas: Mapping[str, int],
    budget_seconds: int,
) -> list[dict[str, Any]]:
    indexed: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise _invalid("capacity throughput row must be an object")
        carrier = str(row.get("carrier") or "")
        if carrier not in CARRIERS or carrier in indexed:
            raise _invalid("capacity throughput carriers are duplicated or invalid")
        indexed[carrier] = row
    if set(indexed) != set(CARRIERS):
        raise _invalid("capacity throughput carriers are incomplete")

    plans: list[dict[str, Any]] = []
    for carrier in CARRIERS:
        row = indexed[carrier]
        if row.get("measuredScale") != identity["targetScale"]:
            raise _identity_drift(f"{carrier} throughput measuredScale drift")
        for field in ("sourceRevision", "sourceDigest", "entityCatalogDigest"):
            _require_digest(row.get(field), label=f"{carrier}.{field}")
            if row.get(field) != identity[field]:
                raise _identity_drift(f"{carrier} throughput {field} drift")
        if row.get("throughputUnit") != "objects_per_second_per_slot":
            raise _invalid(f"{carrier} throughput unit is invalid")
        raw_samples = row.get("perSlotThroughputSamples")
        if not isinstance(raw_samples, list) or not raw_samples:
            raise _invalid(f"{carrier} per-slot throughput samples are missing")
        samples = [
            _positive_decimal(value, label=f"{carrier} throughput sample")
            for value in raw_samples
        ]
        evidence_ref = _require_safe_ref(
            row.get("evidenceRef"), label=f"{carrier}.evidenceRef"
        )
        evidence_digest = _require_digest(
            row.get("evidenceDigest"), label=f"{carrier}.evidenceDigest"
        )
        if (
            evidence_ref != identity["resourceSoakEvidenceRef"]
            or evidence_digest != identity["resourceSoakEvidenceDigest"]
        ):
            raise _identity_drift(
                f"{carrier} throughput resource evidence binding drift"
            )
        basis_digest = _require_digest(
            row.get("throughputBasisDigest"),
            label=f"{carrier}.throughputBasisDigest",
        )
        if basis_digest != throughput_basis_digest(row):
            raise _invalid(f"{carrier} throughputBasisDigest drift")
        p10 = _nearest_rank_p10(samples)
        denominator = Decimal(budget_seconds) * p10 * _UTILIZATION_FACTOR
        workers = int(
            (Decimal(deltas[carrier]) / denominator).to_integral_value(
                rounding=ROUND_CEILING
            )
        )
        plans.append(
            {
                "carrier": carrier,
                "delta": deltas[carrier],
                "requiredWorkers": workers,
                "partitionCount": partition_count(workers),
                "p10PerSlotThroughput": float(p10),
                "throughputUnit": "objects_per_second_per_slot",
                "perSlotThroughputSamples": [float(value) for value in samples],
                "throughputSampleCount": len(samples),
                "throughputEvidenceRef": evidence_ref,
                "throughputEvidenceDigest": evidence_digest,
                "throughputBasisDigest": basis_digest,
            }
        )
    return plans


def build_governed_capacity_plan(
    *,
    predecessor_promotion: Mapping[str, Any],
    target_scale: str,
    carrier_deltas: Mapping[str, int],
    preflight_receipt: Mapping[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build a deterministic M1000/M10000 plan or raise a typed blocker."""

    if target_scale not in _TARGET_POLICY:
        raise _invalid("targetScale must be M1000 or M10000")
    identity, throughput_rows = _validate_predecessor(
        predecessor_promotion, target_scale=target_scale
    )
    deltas = _validate_deltas(carrier_deltas)
    effective_concurrency, _capacity = _validate_preflight(
        preflight_receipt, now=now
    )
    budget_seconds = int(_TARGET_POLICY[target_scale]["budgetSeconds"])
    carrier_plans = _carrier_rows(
        rows=throughput_rows,
        identity=identity,
        deltas=deltas,
        budget_seconds=budget_seconds,
    )
    required_slots = sum(row["requiredWorkers"] for row in carrier_plans)
    if required_slots > effective_concurrency:
        raise GovernedCapacityPlanError(
            CAPACITY_SHORTFALL,
            f"requiredSlots={required_slots} exceeds effectiveConcurrency={effective_concurrency}",
        )
    stable: dict[str, Any] = {
        "schema": "quwoquan_data.governed_capacity_plan",
        "targetScale": target_scale,
        "predecessorPromotion": identity,
        "predecessorPromotionDigest": _canonical_digest(predecessor_promotion),
        "sourceRevision": identity["sourceRevision"],
        "sourceDigest": identity["sourceDigest"],
        "entityCatalogDigest": identity["entityCatalogDigest"],
        "budgetSeconds": budget_seconds,
        "capacityUtilizationFactor": float(_UTILIZATION_FACTOR),
        "preflight": {
            "receiptId": preflight_receipt["receiptId"],
            "selectionDigest": preflight_receipt["selectionDigest"],
            "provider": preflight_receipt["provider"],
            "model": preflight_receipt["model"],
            "runtimeProfileDigest": preflight_receipt["runtimeProfileDigest"],
            "validUntil": preflight_receipt["validUntil"],
            "effectiveConcurrency": effective_concurrency,
        },
        "carrierPlans": carrier_plans,
        "requiredSlots": required_slots,
        "availableSlots": effective_concurrency,
        "capacityHeadroomSlots": effective_concurrency - required_slots,
    }
    document = {**stable, "planDigest": _canonical_digest(stable)}
    assert_valid(
        document,
        "execution",
        "governed_capacity_plan",
        label=f"governed {target_scale} capacity plan",
    )
    return document


__all__ = [
    "CAPACITY_PLAN_INVALID",
    "CAPACITY_SHORTFALL",
    "PREDECESSOR_IDENTITY_DRIFT",
    "GovernedCapacityPlanError",
    "build_governed_capacity_plan",
    "throughput_basis_digest",
    "throughput_basis_document",
]
