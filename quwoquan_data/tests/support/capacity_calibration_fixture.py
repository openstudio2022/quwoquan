"""Synthetic capacity bindings for control-logic tests only.

这些值不代表主机容量、吞吐或稳态结论。local_contract 只用它们证明 receipt
绑定、wave 推导与 deadline 传播；生产数值只能来自受治理 M100 soak receipt。
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.execution.planning.capacity_calibration import (
    current_host_class,
    freeze_capacity_source_binding,
)

SYNTHETIC_FROZEN_AT_EPOCH_SECONDS = 2_000_000_000


def synthetic_capacity_source_binding(
    *,
    provider_tier: str = "default",
) -> dict[str, Any]:
    return {
        "calibrationId": "local-contract-capacity",
        "calibrationReceiptRef": (
            "data/local/tests/capacity/local-contract-capacity.json"
        ),
        "calibrationReceiptDigest": "sha256:" + "c" * 64,
        "applicability": {
            "hostClass": "local-contract-host",
            "providerTier": provider_tier,
        },
        "frozenCapacity": {
            "autoResearchMaxConcurrentWorkers": 4,
            "fleetMaxConcurrentWorkers": 2,
            "objectWallClockSeconds": 900,
            "completionGraceSeconds": 300,
        },
        # 存活阈值与容量上限分块：这里的取值同样只用于控制逻辑断言，
        # 不代表任何主机上实测的心跳写入开销或单实体耗时分布。
        "frozenLiveness": {
            "sourceDiscoveryHeartbeatIntervalSeconds": 5,
            "sourceDiscoveryHeartbeatStaleAfterSeconds": 15,
        },
    }


def _digest_document(document: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(document),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _digest_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def write_synthetic_capacity_receipt(
    path: Path,
    *,
    provider_tier: str = "default",
) -> Path:
    path = path.resolve()
    parts = path.parts
    if "data" not in parts:
        raise ValueError("synthetic capacity receipt must live under data/**")
    data_index = parts.index("data")
    owner_root = Path(*parts[:data_index])
    base = path.parent
    base.mkdir(parents=True, exist_ok=True)

    bound_paths = {
        "provider": base / "synthetic-provider.json",
        "resource": base / "synthetic-resource.json",
        "fleet": base / "synthetic-fleet.json",
        "timing": base / "synthetic-timing.json",
    }
    for name, bound_path in bound_paths.items():
        bound_path.write_text(
            json.dumps({"schema": f"synthetic.{name}"}),
            encoding="utf-8",
        )

    def ref(bound_path: Path) -> str:
        return bound_path.relative_to(owner_root).as_posix()

    source = synthetic_capacity_source_binding(provider_tier=provider_tier)
    decision = dict(source["frozenCapacity"])
    liveness = dict(source["frozenLiveness"])
    evidence_stable = {
        "schema": "quwoquan_data.governed_capacity_calibration_evidence",
        "calibrationId": source["calibrationId"],
        "workloadScale": "M100",
        "hostClass": current_host_class(),
        "providerTier": provider_tier,
        "providerEvidenceCalibrationId": source["calibrationId"],
        "providerCandidates": [
            {
                "reportRef": ref(bound_paths["provider"]),
                "reportDigest": _digest_file(bound_paths["provider"]),
                "resourceSamplesRef": ref(bound_paths["resource"]),
                "resourceSamplesDigest": _digest_file(bound_paths["resource"]),
                "attempts": 100,
                "requestedConcurrency": 4,
                "effectiveConcurrency": 4,
                "successCount": 100,
                "provider429Count": 0,
                "authFailureCount": 0,
                "true5xxCount": 0,
                "startupTimeoutCount": 0,
                "bridgeDisconnectCount": 0,
                "startupLatencyP95Seconds": 1.0,
                "admitted": True,
            }
        ],
        "resourcePeaks": {
            "sampleCount": 1,
            "rssBytes": 1,
            "cpuPercent": 0.0,
            "cursorBridgeProcessCount": 0,
        },
        "fleetObservations": [
            {
                "executionId": "synthetic-execution",
                "reportRef": ref(bound_paths["fleet"]),
                "reportDigest": _digest_file(bound_paths["fleet"]),
                "total": 1,
                "fleetPeakConcurrentWorkers": 1,
                "fleetWallClockMilliseconds": 1,
            }
        ],
        "objectTimingObservations": [
            {
                "executionId": "synthetic-execution",
                "stateRef": ref(bound_paths["timing"]),
                "stateDigest": _digest_file(bound_paths["timing"]),
                "sampleCount": 1,
                "p95Seconds": 1.0,
                "maxSeconds": 1.0,
            }
        ],
        "heartbeatWriteObservations": [
            {"sampleCount": 1, "p95Seconds": 0.01, "maxSeconds": 0.01}
        ],
        "decision": {
            **decision,
            "rule": (
                "zero-provider-failure-candidate+observed-fleet-peak+"
                "minute-ceiling"
            ),
            **liveness,
            "missedHeartbeatTolerance": 3,
            "livenessRule": (
                "heartbeat-write-cost-ceiling+object-duration-detection-floor+"
                "declared-missed-beat-tolerance"
            ),
        },
        "recordedAt": "2026-08-16T00:00:00Z",
    }
    evidence = {
        **evidence_stable,
        "evidenceDigest": _digest_document(evidence_stable),
    }
    evidence_path = base / "synthetic-soak.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    receipt = {
        "schema": "quwoquan_data.governed_capacity_calibration_receipt",
        "calibrationId": source["calibrationId"],
        "supersedesCalibrationId": None,
        "soakEvidenceRef": ref(evidence_path),
        "soakEvidenceDigest": evidence["evidenceDigest"],
        "applicability": {
            "hostClass": current_host_class(),
            "providerTier": provider_tier,
        },
        "frozenCapacity": decision,
        "frozenLiveness": liveness,
        "calibratedAt": "2026-08-16T00:00:00Z",
    }
    receipt["receiptDigest"] = _digest_document(receipt)
    path.write_text(json.dumps(receipt, ensure_ascii=False), encoding="utf-8")
    return path


def synthetic_governed_execution_authority(
    *,
    provider_tier: str = "default",
) -> dict[str, Any]:
    """One governed executionAuthority wrapping the synthetic source binding."""
    return {
        "mode": "governed_calibration",
        "calibration": synthetic_capacity_source_binding(
            provider_tier=provider_tier
        ),
    }


def synthetic_capacity_execution_binding(
    *,
    work_unit_count: int,
    source_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return freeze_capacity_source_binding(
        source_binding or synthetic_capacity_source_binding(),
        work_unit_count=work_unit_count,
        frozen_at_epoch_seconds=SYNTHETIC_FROZEN_AT_EPOCH_SECONDS,
    )


__all__ = [
    "SYNTHETIC_FROZEN_AT_EPOCH_SECONDS",
    "synthetic_capacity_execution_binding",
    "synthetic_capacity_source_binding",
    "synthetic_governed_execution_authority",
    "write_synthetic_capacity_receipt",
]
