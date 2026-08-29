"""Freeze one governed capacity calibration into a create-once receipt."""
from __future__ import annotations

import math
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from content.execution.planning.capacity_calibration import current_host_class
from content.execution.planning.capacity_calibration_probe import (
    CapacityCalibrationRunError,
    candidate_summary,
    copy_exact_once,
    evidence_ref,
    fleet_observation,
    heartbeat_write_observation,
    object_timing_observation,
    run_probe_candidate,
)
from content.execution.runtime_evidence.contract import write_create_once

_DECISION_RULE = (
    "zero-provider-failure-candidate+observed-fleet-peak+minute-ceiling"
)
_LIVENESS_RULE = (
    "heartbeat-write-cost-ceiling+object-duration-detection-floor+"
    "declared-missed-beat-tolerance"
)
_HEARTBEAT_WRITE_SAMPLES = 64
# 心跳写入占比上限：间隔至少要让一次写入的开销落到 1% 以内。
_HEARTBEAT_WRITE_DUTY_DIVISOR = 100
# 探测下限：间隔至少要比单实体耗时短一个量级，否则一个实体尚未得出终态时
# 的静默与「进程已死」仍然无法区分。
_HEARTBEAT_DETECTION_DIVISOR = 10


def _candidate_concurrencies() -> tuple[int, ...]:
    logical_cpu = os.cpu_count()
    if isinstance(logical_cpu, bool) or not isinstance(logical_cpu, int):
        raise CapacityCalibrationRunError("logical CPU count is unavailable")
    highest = 1 << max(0, logical_cpu.bit_length() - 1)
    return tuple(
        value for value in (highest >> offset for offset in range(highest.bit_length()))
        if value >= 1
    )


def _minute_ceiling(seconds: float) -> int:
    return max(60, math.ceil(seconds / 60) * 60)


def _freeze_liveness(
    *,
    heartbeat_rows: Sequence[Mapping[str, Any]],
    timing_rows: Sequence[Mapping[str, Any]],
    missed_heartbeat_tolerance: int,
) -> dict[str, int]:
    """Derive the two liveness thresholds from their own measured basis.

    容量上限与单对象 wall-clock 不是本推导的输入：间隔的下界来自实测心跳写入
    开销，上界来自实测单实体耗时分布，漏拍容忍数由标定者显式声明。
    """
    if (
        isinstance(missed_heartbeat_tolerance, bool)
        or not isinstance(missed_heartbeat_tolerance, int)
        or missed_heartbeat_tolerance < 2
    ):
        raise CapacityCalibrationRunError(
            "capacity calibration requires an explicitly declared missed "
            "heartbeat tolerance of at least two beats"
        )
    write_cost = max(float(row["maxSeconds"]) for row in heartbeat_rows)
    interval = max(1, math.ceil(write_cost * _HEARTBEAT_WRITE_DUTY_DIVISOR))
    detection_ceiling = (
        min(float(row["p95Seconds"]) for row in timing_rows)
        / _HEARTBEAT_DETECTION_DIVISOR
    )
    if interval > detection_ceiling:
        raise CapacityCalibrationRunError(
            "measured heartbeat write cost leaves no interval below the "
            f"observed single-entity detection floor of {detection_ceiling:.3f}s"
        )
    return {
        "sourceDiscoveryHeartbeatIntervalSeconds": interval,
        "sourceDiscoveryHeartbeatStaleAfterSeconds": (
            interval * missed_heartbeat_tolerance
        ),
    }


def run_capacity_calibration(
    *,
    calibration_id: str,
    semantic_selection_id: str,
    fleet_report_paths: Sequence[Path],
    execution_state_paths: Sequence[Path],
    output_dir: Path,
    missed_heartbeat_tolerance: int,
    supersedes_calibration_id: str | None = None,
    provider_evidence_dir: Path | None = None,
    provider_evidence_calibration_id: str | None = None,
) -> tuple[dict[str, Any], Path]:
    if not calibration_id or not fleet_report_paths or not execution_state_paths:
        raise CapacityCalibrationRunError(
            "capacity calibration requires identity, fleet reports, and object timings"
        )
    output_dir = output_dir.expanduser().resolve()
    probe_dir = (
        provider_evidence_dir.expanduser().resolve()
        if provider_evidence_dir is not None
        else output_dir
    )
    provider_evidence_id = str(
        provider_evidence_calibration_id or calibration_id
    ).strip()
    if not provider_evidence_id:
        raise CapacityCalibrationRunError(
            "capacity calibration provider evidence identity is missing"
        )
    candidate_rows: list[dict[str, Any]] = []
    candidate_samples: dict[int, list[dict[str, Any]]] = {}
    admitted: dict[str, Any] | None = None
    for candidate in _candidate_concurrencies():
        row, samples = run_probe_candidate(
            calibration_id=calibration_id,
            candidate=candidate,
            semantic_selection_id=semantic_selection_id,
            output_dir=probe_dir,
        )
        if probe_dir != output_dir:
            for name in (
                f"provider-probe-concurrency-{candidate}.json",
                f"resource-samples-concurrency-{candidate}.json",
            ):
                copy_exact_once(probe_dir / name, output_dir / name)
            row, samples = candidate_summary(
                candidate=candidate,
                report_path=output_dir / f"provider-probe-concurrency-{candidate}.json",
                samples_path=output_dir / f"resource-samples-concurrency-{candidate}.json",
            )
        candidate_rows.append(row)
        candidate_samples[candidate] = samples
        if row["admitted"]:
            admitted = row
            break
    if admitted is None:
        raise CapacityCalibrationRunError(
            "no provider concurrency candidate completed 100 attempts without failure"
        )
    fleet_rows = [
        fleet_observation(
            path.resolve(),
            output_dir=output_dir,
            ordinal=index,
        )
        for index, path in enumerate(fleet_report_paths, start=1)
    ]
    timing_rows = [
        object_timing_observation(
            path.resolve(),
            output_dir=output_dir,
            ordinal=index,
        )
        for index, path in enumerate(execution_state_paths, start=1)
    ]
    admitted_samples = candidate_samples[int(admitted["requestedConcurrency"])]
    fleet_peak = max(int(row["fleetPeakConcurrentWorkers"]) for row in fleet_rows)
    object_wall = _minute_ceiling(
        max(float(row["maxSeconds"]) for row in timing_rows)
    )
    completion_grace = _minute_ceiling(
        max(
            float(admitted["startupLatencyP95Seconds"]),
            max(
                int(row["fleetWallClockMilliseconds"]) / 1000
                for row in fleet_rows
            ),
        )
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    heartbeat_rows = [heartbeat_write_observation(output_dir)]
    liveness = _freeze_liveness(
        heartbeat_rows=heartbeat_rows,
        timing_rows=timing_rows,
        missed_heartbeat_tolerance=missed_heartbeat_tolerance,
    )
    decision = {
        "autoResearchMaxConcurrentWorkers": int(
            admitted["requestedConcurrency"]
        ),
        "fleetMaxConcurrentWorkers": fleet_peak,
        "objectWallClockSeconds": object_wall,
        "completionGraceSeconds": completion_grace,
        "rule": _DECISION_RULE,
        **liveness,
        "missedHeartbeatTolerance": missed_heartbeat_tolerance,
        "livenessRule": _LIVENESS_RULE,
    }
    evidence_stable = {
        "schema": "quwoquan_data.governed_capacity_calibration_evidence",
        "calibrationId": calibration_id,
        "workloadScale": "M100",
        "hostClass": current_host_class(),
        "providerTier": semantic_selection_id,
        "providerEvidenceCalibrationId": provider_evidence_id,
        "providerCandidates": candidate_rows,
        "resourcePeaks": {
            "sampleCount": len(admitted_samples),
            "rssBytes": max(int(row["rssBytes"]) for row in admitted_samples),
            "cpuPercent": max(float(row["cpuPercent"]) for row in admitted_samples),
            "cursorBridgeProcessCount": max(
                int(row["cursorBridgeProcessCount"])
                for row in admitted_samples
            ),
        },
        "fleetObservations": fleet_rows,
        "objectTimingObservations": timing_rows,
        "heartbeatWriteObservations": heartbeat_rows,
        "decision": decision,
    }
    evidence_path = output_dir / "evidence.json"
    evidence = write_create_once(
        evidence_path,
        stable=evidence_stable,
        schema_name="governed_capacity_calibration_evidence",
        digest_field="evidenceDigest",
        recorded_at_field="recordedAt",
    )
    receipt_stable = {
        "schema": "quwoquan_data.governed_capacity_calibration_receipt",
        "calibrationId": calibration_id,
        "supersedesCalibrationId": supersedes_calibration_id,
        "soakEvidenceRef": evidence_ref(evidence_path),
        "soakEvidenceDigest": evidence["evidenceDigest"],
        "applicability": {
            "hostClass": current_host_class(),
            "providerTier": semantic_selection_id,
        },
        "frozenCapacity": {
            key: decision[key]
            for key in (
                "autoResearchMaxConcurrentWorkers",
                "fleetMaxConcurrentWorkers",
                "objectWallClockSeconds",
                "completionGraceSeconds",
            )
        },
        "frozenLiveness": dict(liveness),
    }
    receipt_path = output_dir / "receipt.json"
    receipt = write_create_once(
        receipt_path,
        stable=receipt_stable,
        schema_name="governed_capacity_calibration_receipt",
        digest_field="receiptDigest",
        recorded_at_field="calibratedAt",
    )
    return receipt, receipt_path


__all__ = ["CapacityCalibrationRunError", "run_capacity_calibration"]
