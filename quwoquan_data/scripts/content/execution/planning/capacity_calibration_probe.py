"""Measure this host and freeze each capacity calibration observation exactly once.

`DEC-006` requires every frozen ceiling to trace back to an observation made on
the host that will run the workload. This module owns the measuring end: the
Provider concurrency probe and its resource samples, the fleet peak and object
timing snapshots read out of real run reports, and the heartbeat write cost.

Each observation is written create-once under the calibration's own output
directory, so re-running one calibration reads the frozen observation back
instead of re-timing it. Turning observations into a receipt belongs to
`capacity_calibration_writer`.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import time
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.paths import OUTPUT_ROOT, REPO_ROOT
from core.runtime_policy import active_runtime_policy
from core.schema import assert_valid

from content.execution.preflight.selection import resolve_semantic_preflight_selection
from content.execution.preflight.semantic_provider import semantic_agent_probe_suite
from content.execution.runtime_evidence.contract import canonical_digest

_PROBE_ATTEMPTS = 100
_SAMPLE_INTERVAL_SECONDS = 0.5
_HEARTBEAT_WRITE_SAMPLES = 64


class CapacityCalibrationRunError(RuntimeError):
    """The live calibration inputs are incomplete or no candidate is admitted."""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def file_digest(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise CapacityCalibrationRunError(
            f"capacity calibration evidence is missing or unsafe: {path}"
        )
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def nearest_rank_p95(values: Sequence[float]) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]


def evidence_ref(path: Path) -> str:
    resolved = path.expanduser().resolve()
    for root in (OUTPUT_ROOT.resolve(), REPO_ROOT.resolve()):
        try:
            return resolved.relative_to(root).as_posix()
        except ValueError:
            continue
    raise CapacityCalibrationRunError(
        f"capacity calibration evidence escapes governed roots: {path}"
    )


def copy_exact_once(source: Path, target: Path) -> None:
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


def write_exact_once(path: Path, payload: Mapping[str, Any]) -> None:
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
        "capturedAt": now_iso(),
        "rssBytes": sum(row[1] for row in measured),
        "cpuPercent": round(sum(row[2] for row in measured), 3),
        "cursorBridgeProcessCount": sum(
            1 for row in measured if "cursor-sdk-bridge" in row[3]
        ),
    }


def candidate_summary(
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
        "reportRef": evidence_ref(report_path),
        "reportDigest": file_digest(report_path),
        "resourceSamplesRef": evidence_ref(samples_path),
        "resourceSamplesDigest": file_digest(samples_path),
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


def run_probe_candidate(
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
        return candidate_summary(
            candidate=candidate,
            report_path=report_path,
            samples_path=samples_path,
        )
    selection = resolve_semantic_preflight_selection(semantic_selection_id)
    started_at = now_iso()
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
    finished_at = now_iso()
    write_exact_once(report_path, report)
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
    write_exact_once(samples_path, samples_document)
    return candidate_summary(
        candidate=candidate,
        report_path=report_path,
        samples_path=samples_path,
    )

def fleet_observation(
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
        "sourceDigest": file_digest(path),
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
    write_exact_once(snapshot_path, snapshot)
    return {
        "executionId": snapshot["executionId"],
        "reportRef": evidence_ref(snapshot_path),
        "reportDigest": file_digest(snapshot_path),
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

def object_timing_observation(
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
        "sourceDigest": file_digest(path),
        "executionId": str(payload.get("executionId") or "").strip(),
        "sampleCount": len(values),
        "p95Seconds": round(nearest_rank_p95(values), 3),
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
    write_exact_once(snapshot_path, snapshot)
    return {
        "executionId": snapshot["executionId"],
        "stateRef": evidence_ref(snapshot_path),
        "stateDigest": file_digest(snapshot_path),
        "sampleCount": snapshot["sampleCount"],
        "p95Seconds": snapshot["p95Seconds"],
        "maxSeconds": snapshot["maxSeconds"],
    }

def heartbeat_write_observation(output_dir: Path) -> dict[str, Any]:
    """Measure what one heartbeat write actually costs on this host.

    观测结果与 provider probe 一样落成本次标定的 create-once 证据：同一 calibration
    重跑时读回已冻结的那一次观测，而不是重新计时。否则同一身份的 evidence 会因为两次
    计时不同而互相冲突。
    """
    from content.source.research.stage_liveness import (
        StageStatus,
        write_source_discovery_progress,
    )

    observation_path = output_dir / "heartbeat-write-observation.json"
    if observation_path.is_file() and not observation_path.is_symlink():
        frozen = json.loads(observation_path.read_text(encoding="utf-8"))
        return {
            "sampleCount": int(frozen["sampleCount"]),
            "p95Seconds": float(frozen["p95Seconds"]),
            "maxSeconds": float(frozen["maxSeconds"]),
        }
    probe_path = output_dir / "heartbeat-write-probe.json"
    durations: list[float] = []
    for index in range(_HEARTBEAT_WRITE_SAMPLES):
        started = time.perf_counter()
        write_source_discovery_progress(
            "calibration-heartbeat-write-probe",
            status=StageStatus.RUNNING,
            candidate_entity_count=_HEARTBEAT_WRITE_SAMPLES,
            terminal_entity_count=index,
            running_entity_ids=(f"probe-{index:03d}",),
            frozen_max_concurrent_workers=1,
            heartbeat_interval_seconds=1,
            heartbeat_stale_after_seconds=2,
            elapsed_seconds=float(index + 1),
            now_epoch_seconds=int(time.time()),
            path=probe_path,
        )
        durations.append(max(time.perf_counter() - started, 1e-6))
    probe_path.unlink(missing_ok=True)
    observation = {
        "sampleCount": len(durations),
        "p95Seconds": round(nearest_rank_p95(durations), 6),
        "maxSeconds": round(max(durations), 6),
    }
    observation_path.write_text(json.dumps(observation), encoding="utf-8")
    return observation


__all__ = [
    "CapacityCalibrationRunError",
    "candidate_summary",
    "copy_exact_once",
    "evidence_ref",
    "file_digest",
    "fleet_observation",
    "heartbeat_write_observation",
    "nearest_rank_p95",
    "now_iso",
    "object_timing_observation",
    "run_probe_candidate",
]
