"""Stable authority material and identifier derivation for acceptance facts."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any, Callable

from quwoquan_ops.cli.lib.environment_acceptance_fact_contract import _FINALIZATION_KEYS


def _fact_id_material(fact: Mapping[str, Any]) -> dict[str, Any]:
    target_bindings = fact.get("targetBindingRefs")
    raw_results = fact.get("requiredRawResults")
    material: dict[str, Any] = {
        "schema": fact.get("schema"),
        "acceptanceProfile": fact.get("acceptanceProfile"),
        "environment": fact.get("environment"),
        "target": fact.get("target"),
        "releaseId": fact.get("releaseId"),
        "releaseDigest": fact.get("releaseDigest"),
        "manifestDigest": fact.get("manifestDigest"),
        "importRunId": fact.get("importRunId"),
        "verifyRunId": fact.get("verifyRunId"),
        "samplePlanDigest": fact.get("samplePlanDigest"),
        "requiredRawDigests": sorted(
            (
                {"digest": item.get("digest"), "slotId": item.get("slotId")}
                for item in raw_results
                if isinstance(item, Mapping)
            ),
            key=lambda item: (str(item["slotId"]), str(item["digest"])),
        )
        if isinstance(raw_results, list)
        else raw_results,
        "dataReadinessDigest": (fact.get("dataReadiness") or {}).get("digest")
        if isinstance(fact.get("dataReadiness"), Mapping)
        else None,
        "sourceFingerprint": fact.get("sourceFingerprint"),
    }
    if fact.get("acceptanceProfile") == "m1_api_consumer":
        material["consumerHealthDigest"] = (
            (fact.get("consumerHealth") or {}).get("digest")
            if isinstance(fact.get("consumerHealth"), Mapping)
            else None
        )
        return material

    material.pop("manifestDigest", None)
    finalization = fact.get("resourceFinalization")
    prod = fact.get("prodReleaseFacts")
    predecessor = fact.get("predecessorAcceptance")
    material.update(
        {
            "targetBindingDigests": sorted(
                (
                    {
                        "digest": item.get("digest"),
                        "platform": item.get("platform"),
                        "deviceProfile": item.get("deviceProfile"),
                    }
                    for item in target_bindings
                    if isinstance(item, Mapping)
                ),
                key=lambda item: (
                    str(item["platform"]),
                    str(item["deviceProfile"]),
                    str(item["digest"]),
                ),
            )
            if isinstance(target_bindings, list)
            else target_bindings,
            "activeCas": {
                field: (fact.get("activeCas") or {}).get(field)
                for field in ("digest", "readbackDigest", "releaseId", "releaseDigest")
            }
            if isinstance(fact.get("activeCas"), Mapping)
            else fact.get("activeCas"),
            "lifecycleExitDigest": (fact.get("lifecycleExit") or {}).get("digest")
            if isinstance(fact.get("lifecycleExit"), Mapping)
            else None,
            "providerReadinessDigest": (fact.get("providerReadiness") or {}).get(
                "digest"
            )
            if isinstance(fact.get("providerReadiness"), Mapping)
            else None,
            "observabilityReadinessDigest": (
                fact.get("observabilityReadiness") or {}
            ).get("digest")
            if isinstance(fact.get("observabilityReadiness"), Mapping)
            else None,
            "rollbackReadinessDigest": (fact.get("rollbackReadiness") or {}).get(
                "digest"
            )
            if isinstance(fact.get("rollbackReadiness"), Mapping)
            else None,
            "predecessorAcceptance": {
                field: predecessor.get(field)
                for field in ("environment", "factId", "digest")
            }
            if isinstance(predecessor, Mapping)
            else predecessor,
            "resourceFinalizationDigests": {
                field: sorted(
                    str(item.get("digest"))
                    for item in finalization.get(field, [])
                    if isinstance(item, Mapping)
                )
                for field in _FINALIZATION_KEYS
            }
            if isinstance(finalization, Mapping)
            else finalization,
            "prodReleaseFacts": {
                "engineeringEligibilityDigest": (
                    prod.get("engineeringEligibility") or {}
                ).get("digest"),
                "durableApprovalDigest": (prod.get("durableApproval") or {}).get(
                    "digest"
                ),
                "rolloutStageDigests": [
                    {"stage": item.get("stage"), "digest": item.get("digest")}
                    for item in prod.get("rolloutStages", [])
                    if isinstance(item, Mapping)
                ],
                "rollbackReadinessDigest": (prod.get("rollbackReadiness") or {}).get(
                    "digest"
                ),
            }
            if isinstance(prod, Mapping)
            else prod,
        }
    )
    return material


def derive_fact_id(
    fact: Mapping[str, Any],
    *,
    canonical_fact_bytes: Callable[[Mapping[str, Any]], bytes],
) -> str:
    return (
        "sha256:"
        + hashlib.sha256(canonical_fact_bytes(_fact_id_material(fact))).hexdigest()
    )


__all__ = ["derive_fact_id"]
