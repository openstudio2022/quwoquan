# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-009
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/source-discovery-scale-reliability/spec.md#gwt-002.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/source-discovery-scale-reliability/spec.md#gwt-002.t7
"""Capacity writer derives values from measured evidence and resumes create-once."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from content.execution.planning import capacity_calibration_probe as probe
from content.execution.planning import capacity_calibration_writer as writer
from content.execution.planning.capacity_calibration import (
    load_capacity_calibration_receipt,
)
from content.execution.runtime_evidence.contract import canonical_digest
from core import paths as core_paths
from support.capacity_calibration_fixture import (
    SYNTHETIC_FROZEN_AT_EPOCH_SECONDS,
)


def _probe_report(concurrency: int, *, admitted: bool) -> dict[str, object]:
    failures = 0 if admitted else 1
    return {
        "attempts": 100,
        "effectiveConcurrency": concurrency,
        "successCount": 100 - failures,
        "authFailures": 0,
        "true5xxCount": failures,
        "startupTimeoutCount": 0,
        "bridgeDisconnectCount": 0,
        "startupLatencyP95": 11.2,
        "results": [
            {
                "attempt": index,
                "ready": admitted or index != 1,
                "httpStatus": 500 if not admitted and index == 1 else None,
            }
            for index in range(1, 101)
        ],
    }


def _fleet_report(path: Path) -> Path:
    payload = {
        "passed": True,
        "executionId": "20260817--travel-homepage-closure--china-sichuan--pilot-001",
        "total": 3,
        "fleetPeakConcurrentWorkers": 3,
        "fleetWallClockMilliseconds": 61_001,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _execution_state(path: Path) -> Path:
    payload = {
        "executionId": "20260816--travel-article-g1--china-sichuan--pilot-011",
        "outcomes": [
            {
                "runId": "run-a",
                "timing": {"durationSeconds": 541.748},
            },
            {
                "runId": "run-b",
                "timing": {"durationSeconds": 659.564},
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_writer_selects_highest_zero_failure_candidate_and_freezes_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(core_paths, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(core_paths, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(probe, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(probe, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(writer, "_candidate_concurrencies", lambda: (8, 4, 2, 1))
    calls: list[int] = []

    def probe_candidate(
        *,
        calibration_id: str,
        candidate: int,
        semantic_selection_id: str,
        output_dir: Path,
    ) -> tuple[dict[str, object], list[dict[str, object]]]:
        calls.append(candidate)
        report_path = output_dir / f"provider-probe-concurrency-{candidate}.json"
        samples_path = output_dir / f"resource-samples-concurrency-{candidate}.json"
        output_dir.mkdir(parents=True, exist_ok=True)
        report = _probe_report(candidate, admitted=candidate <= 4)
        report_path.write_text(json.dumps(report), encoding="utf-8")
        samples_stable = {
            "schema": "quwoquan_data.governed_capacity_probe_resource_samples",
            "calibrationId": calibration_id,
            "requestedConcurrency": candidate,
            "startedAt": "2026-08-16T00:00:00Z",
            "finishedAt": "2026-08-16T00:01:00Z",
            "samples": [
                {
                    "capturedAt": "2026-08-16T00:00:30Z",
                    "rssBytes": candidate * 100,
                    "cpuPercent": candidate * 10.0,
                    "cursorBridgeProcessCount": candidate,
                }
            ],
        }
        samples = {
            **samples_stable,
            "samplesDigest": canonical_digest(samples_stable),
        }
        samples_path.write_text(json.dumps(samples), encoding="utf-8")
        return probe.candidate_summary(
            candidate=candidate,
            report_path=report_path,
            samples_path=samples_path,
        )

    monkeypatch.setattr(writer, "run_probe_candidate", probe_candidate)
    output = (
        tmp_path
        / "quwoquan_data/control_plane/_shared/capacity_calibration/test-run"
    )
    fleet = _fleet_report(tmp_path / "fleet.json")
    state = _execution_state(tmp_path / "execution-state.json")

    receipt, path = writer.run_capacity_calibration(
        calibration_id="test-run",
        semantic_selection_id="default",
        fleet_report_paths=(fleet,),
        execution_state_paths=(state,),
        output_dir=output,
        missed_heartbeat_tolerance=3,
    )

    assert calls == [8, 4]
    assert receipt["frozenCapacity"] == {
        "autoResearchMaxConcurrentWorkers": 4,
        "fleetMaxConcurrentWorkers": 3,
        "objectWallClockSeconds": 660,
        "completionGraceSeconds": 120,
    }
    assert load_capacity_calibration_receipt(path) == receipt
    evidence = json.loads((output / "evidence.json").read_text())

    # 心跳间隔与过期阈值来自本次标定的实测心跳写入开销与实测单实体耗时，
    # 不是默认常量，也不从容量上限或单对象 wall-clock 挪用。
    liveness = receipt["frozenLiveness"]
    interval = liveness["sourceDiscoveryHeartbeatIntervalSeconds"]
    stale_after = liveness["sourceDiscoveryHeartbeatStaleAfterSeconds"]
    assert interval >= 1
    assert stale_after == interval * 3
    assert stale_after > interval
    assert interval not in {
        receipt["frozenCapacity"]["autoResearchMaxConcurrentWorkers"],
        receipt["frozenCapacity"]["objectWallClockSeconds"],
        receipt["frozenCapacity"]["completionGraceSeconds"],
    }
    assert stale_after not in {
        receipt["frozenCapacity"]["objectWallClockSeconds"],
        receipt["frozenCapacity"]["completionGraceSeconds"],
    }
    write_observations = evidence["heartbeatWriteObservations"]
    assert write_observations
    write_cost = max(float(row["maxSeconds"]) for row in write_observations)
    detection_ceiling = (
        min(float(row["p95Seconds"]) for row in evidence["objectTimingObservations"])
        / 10
    )
    # 下界来自实测写入开销，上界来自实测单实体耗时；两端都能指回一处证据。
    assert interval >= write_cost
    assert interval <= detection_ceiling
    assert evidence["decision"]["missedHeartbeatTolerance"] == 3
    assert evidence["decision"]["sourceDiscoveryHeartbeatIntervalSeconds"] == interval
    assert (
        evidence["decision"]["sourceDiscoveryHeartbeatStaleAfterSeconds"] == stale_after
    )
    assert evidence["decision"]["livenessRule"] == writer._LIVENESS_RULE
    assert evidence["providerEvidenceCalibrationId"] == "test-run"
    assert [row["admitted"] for row in evidence["providerCandidates"]] == [
        False,
        True,
    ]
    assert evidence["resourcePeaks"] == {
        "sampleCount": 1,
        "rssBytes": 400,
        "cpuPercent": 40.0,
        "cursorBridgeProcessCount": 4,
    }

    repeated, repeated_path = writer.run_capacity_calibration(
        calibration_id="test-run",
        semantic_selection_id="default",
        fleet_report_paths=(fleet,),
        execution_state_paths=(state,),
        output_dir=output,
        missed_heartbeat_tolerance=3,
    )
    assert repeated == receipt
    assert repeated_path == path

    copied_output = (
        tmp_path
        / "quwoquan_data/control_plane/_shared/capacity_calibration/test-run-copy"
    )
    copied, copied_path = writer.run_capacity_calibration(
        calibration_id="test-run-copy",
        semantic_selection_id="default",
        fleet_report_paths=(fleet,),
        execution_state_paths=(state,),
        output_dir=copied_output,
        missed_heartbeat_tolerance=3,
        provider_evidence_dir=output,
        provider_evidence_calibration_id="test-run",
    )
    copied_evidence = json.loads((copied_output / "evidence.json").read_text())
    assert copied_evidence["providerEvidenceCalibrationId"] == "test-run"
    assert copied_evidence["providerCandidates"][1]["reportRef"].startswith(
        "quwoquan_data/control_plane/_shared/capacity_calibration/test-run-copy/"
    )
    assert (copied_output / "provider-probe-concurrency-4.json").read_bytes() == (
        output / "provider-probe-concurrency-4.json"
    ).read_bytes()
    assert load_capacity_calibration_receipt(copied_path) == copied


def test_writer_rejects_fleet_observation_without_measured_peak(
    tmp_path: Path,
) -> None:
    path = tmp_path / "fleet.json"
    path.write_text(
        json.dumps(
            {
                "passed": True,
                "executionId": "execution",
                "total": 1,
                "fleetWallClockMilliseconds": 1,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(probe.CapacityCalibrationRunError, match="measured capacity"):
        probe.fleet_observation(
            path,
            output_dir=tmp_path / "snapshots",
            ordinal=1,
        )


def test_minute_ceiling_is_monotonic() -> None:
    assert writer._minute_ceiling(1) == 60
    assert writer._minute_ceiling(60) == 60
    assert writer._minute_ceiling(60.001) == 120
    assert writer._minute_ceiling(SYNTHETIC_FROZEN_AT_EPOCH_SECONDS) > 120
