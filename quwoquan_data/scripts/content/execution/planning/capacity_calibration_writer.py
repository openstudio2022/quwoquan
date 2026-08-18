"""Run and freeze one governed capacity calibration."""
from __future__ import annotations

import json
import math
import os
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from content.execution.planning.capacity_calibration import current_host_class
from content.execution.preflight.selection import resolve_semantic_preflight_selection
from content.execution.preflight.semantic_provider import semantic_agent_probe_suite
from content.execution.runtime_evidence.contract import canonical_digest, write_create_once
from core.paths import OUTPUT_ROOT, REPO_ROOT
from core.runtime_policy import active_runtime_policy
from core.schema import assert_valid

_PROBE_ATTEMPTS = 100
_SAMPLE_INTERVAL_SECONDS = 0.5
_DECISION_RULE = (
    "zero-provider-failure-candidate+observed-fleet-peak+minute-ceiling"
)


class CapacityCalibrationRunError(RuntimeError):
    """The live calibration inputs are incomplete or no candidate is admitted."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _file_digest(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise CapacityCalibrationRunError(
            f"capacity calibration evidence is missing or unsafe: {path}"
        )
    import hashlib

    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _evidence_ref(path: Path) -> str:
    resolved = path.expanduser().resolve()
    for root in (OUTPUT_ROOT.resolve(), REPO_ROOT.resolve()):
        try:
            return resolved.relative_to(root).as_posix()
        except ValueError:
            continue
    raise CapacityCalibrationRunError(
        f"capacity calibration evidence escapes governed roots: {path}"
    )


def _copy_exact_once(source: Path, target: Path) -> None:
    if source.is_symlink() or not source.is_file():
        raise CapacityCalibrationRunError(
            f"capacity calibration source evidence is missing or unsafe: {source}"
        )
    payload = source.read_bytes()
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if target.is_symlink() or target.read_bytes() != payload:
            raise CapacityCalibrationRunError(
                f"capacity calibration create-once collision: {target}"
            )
        return
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _write_exact_once(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing != dict(payload):
            raise CapacityCalibrationRunError(
                f"capacity calibration create-once collision: {path}"
            )
        return
    path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, indent=2)
        + "\n",
        encoding="utf-8",
    )


def _candidate_concurrencies() -> tuple[int, ...]:
    logical_cpu = os.cpu_count()
    if isinstance(logical_cpu, bool) or not isinstance(logical_cpu, int):
        raise CapacityCalibrationRunError("logical CPU count is unavailable")
    highest = 1 << max(0, logical_cpu.bit_length() - 1)
    return tuple(
        value for value in (highest >> offset for offset in range(highest.bit_length()))
        if value >= 1
    )


def _process_sample(root_pid: int) -> dict[str, Any]:
    result = subprocess.run(
        ["ps", "-ax", "-o", "pid=", "-o", "ppid=", "-o", "rss=", "-o", "%cpu=", "-o", "command="],
        check=False,
        capture_output=True,
        text=True,
        timeout=active_runtime_policy().runtime_evidence.process_inspection_timeout_seconds,
    )
    if result.returncode != 0:
        raise CapacityCalibrationRunError(
            f"capacity process observation failed: exit={result.returncode}"
        )
    rows: dict[int, tuple[int, int, float, str]] = {}
    for line in result.stdout.splitlines():
        fields = line.strip().split(maxsplit=4)
        if len(fields) != 5:
            continue
        try:
            pid, ppid, rss_kib = (int(fields[index]) for index in range(3))
            cpu_percent = float(fields[3])
        except ValueError:
            continue
        rows[pid] = (ppid, rss_kib * 1024, cpu_percent, fields[4])
    descendants = {root_pid}
    changed = True
    while changed:
        changed = False
        for pid, (ppid, _rss, _cpu, _command) in rows.items():
            if ppid in descendants and pid not in descendants:
                descendants.add(pid)
                changed = True
    measured = [rows[pid] for pid in descendants if pid in rows]
    if not measured:
        raise CapacityCalibrationRunError(
            "capacity process observation did not include the runner"
        )
    return {
        "capturedAt": _now(),
        "rssBytes": sum(row[1] for row in measured),
        "cpuPercent": round(sum(row[2] for row in measured), 3),
        "cursorBridgeProcessCount": sum(
            1 for row in measured if "cursor-sdk-bridge" in row[3]
        ),
    }


def _candidate_summary(
    *,
    candidate: int,
    report_path: Path,
    samples_path: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    samples_document = json.loads(samples_path.read_text(encoding="utf-8"))
    samples = list(samples_document.get("samples") or [])
    if not isinstance(report, dict) or not samples:
        raise CapacityCalibrationRunError(
            "capacity probe candidate evidence is incomplete"
        )
    provider_429_count = sum(
        1
        for row in report.get("results") or []
        if isinstance(row, Mapping)
        and (
            row.get("httpStatus") == 429
            or "429" in str(row.get("errorCode") or "")
            or "RATE_LIMIT" in str(row.get("errorCode") or "").upper()
        )
    )
    summary = {
        "reportRef": _evidence_ref(report_path),
        "reportDigest": _file_digest(report_path),
        "resourceSamplesRef": _evidence_ref(samples_path),
        "resourceSamplesDigest": _file_digest(samples_path),
        "attempts": int(report.get("attempts") or 0),
        "requestedConcurrency": candidate,
        "effectiveConcurrency": int(report.get("effectiveConcurrency") or 0),
        "successCount": int(report.get("successCount") or 0),
        "provider429Count": provider_429_count,
        "authFailureCount": int(report.get("authFailures") or 0),
        "true5xxCount": int(report.get("true5xxCount") or 0),
        "startupTimeoutCount": int(report.get("startupTimeoutCount") or 0),
        "bridgeDisconnectCount": int(report.get("bridgeDisconnectCount") or 0),
        "startupLatencyP95Seconds": float(report.get("startupLatencyP95") or 0),
    }
    summary["admitted"] = (
        summary["attempts"] == _PROBE_ATTEMPTS
        and summary["successCount"] == _PROBE_ATTEMPTS
        and summary["effectiveConcurrency"] == candidate
        and all(
            summary[field] == 0
            for field in (
                "provider429Count",
                "authFailureCount",
                "true5xxCount",
                "startupTimeoutCount",
                "bridgeDisconnectCount",
            )
        )
    )
    return summary, samples


def _run_probe_candidate(
    *,
    calibration_id: str,
    candidate: int,
    semantic_selection_id: str,
    output_dir: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    report_path = output_dir / f"provider-probe-concurrency-{candidate}.json"
    samples_path = output_dir / f"resource-samples-concurrency-{candidate}.json"
    if report_path.is_file() or samples_path.is_file():
        if not report_path.is_file() or not samples_path.is_file():
            raise CapacityCalibrationRunError(
                "capacity probe candidate has a partial create-once checkpoint"
            )
        return _candidate_summary(
            candidate=candidate,
            report_path=report_path,
            samples_path=samples_path,
        )
    selection = resolve_semantic_preflight_selection(semantic_selection_id)
    started_at = _now()
    with ThreadPoolExecutor() as executor:
        future = executor.submit(
            semantic_agent_probe_suite,
            provider=selection.provider,
            model=selection.model_selection,
            runtime=selection.runtime.value,
            attempts=_PROBE_ATTEMPTS,
            concurrency=candidate,
            timeout_seconds=active_runtime_policy().startup_timeout_seconds,
            cwd=REPO_ROOT,
        )
        samples: list[dict[str, Any]] = []
        while not future.done():
            samples.append(_process_sample(os.getpid()))
            time.sleep(_SAMPLE_INTERVAL_SECONDS)
        report = dict(future.result())
    samples.append(_process_sample(os.getpid()))
    finished_at = _now()
    _write_exact_once(report_path, report)
    samples_stable = {
        "schema": "quwoquan_data.governed_capacity_probe_resource_samples",
        "calibrationId": calibration_id,
        "requestedConcurrency": candidate,
        "startedAt": started_at,
        "finishedAt": finished_at,
        "samples": samples,
    }
    samples_document = {
        **samples_stable,
        "samplesDigest": canonical_digest(samples_stable),
    }
    assert_valid(
        samples_document,
        "execution",
        "governed_capacity_probe_resource_samples",
        label="capacity probe resource samples",
    )
    _write_exact_once(samples_path, samples_document)
    return _candidate_summary(
        candidate=candidate,
        report_path=report_path,
        samples_path=samples_path,
    )


def _fleet_observation(
    path: Path,
    *,
    output_dir: Path,
    ordinal: int,
) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("passed") is not True:
        raise CapacityCalibrationRunError(
            f"fleet calibration input is not a passed report: {path}"
        )
    peak = payload.get("fleetPeakConcurrentWorkers")
    total = payload.get("total")
    wall = payload.get("fleetWallClockMilliseconds")
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 1
        for value in (peak, total, wall)
    ):
        raise CapacityCalibrationRunError(
            f"fleet calibration input lacks measured capacity: {path}"
        )
    snapshot_stable = {
        "schema": "quwoquan_data.governed_capacity_fleet_observation",
        "sourceDigest": _file_digest(path),
        "executionId": str(payload.get("executionId") or "").strip(),
        "total": total,
        "fleetPeakConcurrentWorkers": peak,
        "fleetWallClockMilliseconds": wall,
    }
    snapshot = {
        **snapshot_stable,
        "snapshotDigest": canonical_digest(snapshot_stable),
    }
    snapshot_path = output_dir / f"fleet-observation-{ordinal:03d}.json"
    assert_valid(
        snapshot,
        "execution",
        "governed_capacity_fleet_observation",
        label="capacity fleet observation",
    )
    _write_exact_once(snapshot_path, snapshot)
    return {
        "executionId": snapshot["executionId"],
        "reportRef": _evidence_ref(snapshot_path),
        "reportDigest": _file_digest(snapshot_path),
        "total": total,
        "fleetPeakConcurrentWorkers": peak,
        "fleetWallClockMilliseconds": wall,
    }


def _timing_durations(value: object, found: dict[str, float]) -> None:
    if isinstance(value, Mapping):
        timing = value.get("timing")
        run_id = str(value.get("runId") or "").strip()
        if isinstance(timing, Mapping) and run_id:
            duration = timing.get("durationSeconds")
            if (
                not isinstance(duration, bool)
                and isinstance(duration, (int, float))
                and duration > 0
            ):
                found[run_id] = float(duration)
        for child in value.values():
            _timing_durations(child, found)
    elif isinstance(value, list):
        for child in value:
            _timing_durations(child, found)


def _nearest_rank_p95(values: Sequence[float]) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]


def _object_timing_observation(
    path: Path,
    *,
    output_dir: Path,
    ordinal: int,
) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    durations: dict[str, float] = {}
    _timing_durations(payload, durations)
    if not durations:
        raise CapacityCalibrationRunError(
            f"execution state has no object timing observations: {path}"
        )
    values = tuple(durations.values())
    snapshot_stable = {
        "schema": "quwoquan_data.governed_capacity_object_timing_observation",
        "sourceDigest": _file_digest(path),
        "executionId": str(payload.get("executionId") or "").strip(),
        "sampleCount": len(values),
        "p95Seconds": round(_nearest_rank_p95(values), 3),
        "maxSeconds": round(max(values), 3),
        "samples": [
            {"runId": run_id, "durationSeconds": duration}
            for run_id, duration in sorted(durations.items())
        ],
    }
    snapshot = {
        **snapshot_stable,
        "snapshotDigest": canonical_digest(snapshot_stable),
    }
    snapshot_path = output_dir / f"object-timing-{ordinal:03d}.json"
    assert_valid(
        snapshot,
        "execution",
        "governed_capacity_object_timing_observation",
        label="capacity object timing observation",
    )
    _write_exact_once(snapshot_path, snapshot)
    return {
        "executionId": snapshot["executionId"],
        "stateRef": _evidence_ref(snapshot_path),
        "stateDigest": _file_digest(snapshot_path),
        "sampleCount": snapshot["sampleCount"],
        "p95Seconds": snapshot["p95Seconds"],
        "maxSeconds": snapshot["maxSeconds"],
    }


def _minute_ceiling(seconds: float) -> int:
    return max(60, math.ceil(seconds / 60) * 60)


def run_capacity_calibration(
    *,
    calibration_id: str,
    semantic_selection_id: str,
    fleet_report_paths: Sequence[Path],
    execution_state_paths: Sequence[Path],
    output_dir: Path,
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
        row, samples = _run_probe_candidate(
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
                _copy_exact_once(probe_dir / name, output_dir / name)
            row, samples = _candidate_summary(
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
        _fleet_observation(
            path.resolve(),
            output_dir=output_dir,
            ordinal=index,
        )
        for index, path in enumerate(fleet_report_paths, start=1)
    ]
    timing_rows = [
        _object_timing_observation(
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
    decision = {
        "autoResearchMaxConcurrentWorkers": int(
            admitted["requestedConcurrency"]
        ),
        "fleetMaxConcurrentWorkers": fleet_peak,
        "objectWallClockSeconds": object_wall,
        "completionGraceSeconds": completion_grace,
        "rule": _DECISION_RULE,
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
        "soakEvidenceRef": _evidence_ref(evidence_path),
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
