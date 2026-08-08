"""Derive canonical resource-soak evidence from raw host and queue samples."""
from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path
from typing import Any

from content.release.canonical.campaign_scale_contract import (
    _TERMINAL_TIMING_EVENTS,
    CARRIERS,
    MAX_CONTROLLER_P95_RSS_BYTES,
    MAX_HEARTBEAT_AGE_SECONDS,
    MAX_NON_VIDEO_WORKER_P95_RSS_BYTES,
    MAX_OLDEST_READY_AGE_SECONDS,
    MAX_OPEN_FD_COUNT,
    MAX_PROGRESS_AGE_SECONDS,
    MAX_QUEUE_DEPTH,
    MAX_SAMPLE_GAP_SECONDS,
    MAX_TERMINAL_RESIDUAL_BYTES,
    MAX_TOTAL_P95_RSS_BYTES,
    MAX_TOTAL_RSS_BYTES,
    MAX_VIDEO_WORKER_P95_RSS_BYTES,
    MIN_SEMANTIC_JOBS_PER_LANE,
    MIN_SOAK_SAMPLES,
    MIN_SOAK_SECONDS,
    TEMPORARY_WORKSPACE_FIXED_ALLOWANCE_BYTES,
    CampaignScaleEvidenceError,
    _active_at,
    _assert_input_identity,
    _file_sha256,
    _load_plan,
    _safe_ref,
    _semantic_jobs,
    _timestamp,
    _validated,
    _write_create_once,
    campaign_source_revision,
)

_TERMINAL_JOB_STATES = frozenset({"blocked", "dead", "succeeded"})
_TERMINAL_EVENT_BY_STATE = {
    "blocked": "blocked",
    "dead": "failed",
    "succeeded": "succeeded",
}
_Interval = tuple[datetime, datetime]


def _nearest_rank_p95(values: list[int]) -> int:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]


def _release_payload_bytes(release_root: Path) -> int:
    payload_root = release_root / "payload"
    if release_root.is_symlink() or not payload_root.is_dir():
        raise CampaignScaleEvidenceError(
            f"resource soak release payload is missing: {payload_root}"
        )
    total = 0
    for path in payload_root.rglob("*"):
        if path.is_symlink():
            raise CampaignScaleEvidenceError(
                f"resource soak release payload contains symlink: {path}"
            )
        if path.is_file():
            total += path.stat().st_size
    return total


def _validate_sample_relationships(samples: list[dict[str, Any]]) -> None:
    for index, row in enumerate(samples):
        total = int(row["totalRssBytes"])
        lower_bound = max(
            int(row["controllerRssBytes"]),
            int(row["nonVideoWorkerMaxRssBytes"]),
            int(row["videoWorkerMaxRssBytes"]),
        )
        if total < lower_bound:
            raise CampaignScaleEvidenceError(
                f"resource sample[{index}].totalRssBytes is below a component RSS"
            )


def _active_intervals(
    timings: list[tuple[str, datetime]],
    *,
    label: str,
) -> list[_Interval]:
    intervals: list[_Interval] = []
    leased_at: datetime | None = None
    for event, captured_at in timings:
        if event == "leased":
            if leased_at is not None:
                raise CampaignScaleEvidenceError(
                    f"{label} has a second lease before the first lease terminated"
                )
            leased_at = captured_at
        elif event in _TERMINAL_TIMING_EVENTS and leased_at is not None:
            intervals.append((leased_at, captured_at))
            leased_at = None
    return intervals


def _merge_intervals(intervals: list[_Interval]) -> list[_Interval]:
    if not intervals:
        return []
    ordered = sorted(intervals)
    merged: list[_Interval] = [ordered[0]]
    for started_at, ended_at in ordered[1:]:
        prior_start, prior_end = merged[-1]
        if started_at <= prior_end:
            merged[-1] = (prior_start, max(prior_end, ended_at))
        else:
            merged.append((started_at, ended_at))
    return merged


def _intersect_intervals(left: list[_Interval], right: list[_Interval]) -> list[_Interval]:
    result: list[_Interval] = []
    left_index = 0
    right_index = 0
    while left_index < len(left) and right_index < len(right):
        started_at = max(left[left_index][0], right[right_index][0])
        ended_at = min(left[left_index][1], right[right_index][1])
        if started_at < ended_at:
            result.append((started_at, ended_at))
        if left[left_index][1] <= right[right_index][1]:
            left_index += 1
        else:
            right_index += 1
    return result


def _interval_document(interval: _Interval) -> dict[str, Any]:
    started_at, ended_at = interval
    return {
        "startedAt": started_at.isoformat(),
        "endedAt": ended_at.isoformat(),
        "durationSeconds": int((ended_at - started_at).total_seconds()),
    }


def _lane_timeline_rows(
    jobs: dict[str, dict[str, dict[str, Any]]],
    *,
    execution_ids: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, list[_Interval]], datetime | None]:
    lane_rows: list[dict[str, Any]] = []
    lane_intervals: dict[str, list[_Interval]] = {}
    terminal_instants: list[datetime] = []
    for carrier in CARRIERS:
        succeeded_ids: list[str] = []
        per_slot_throughput_samples: list[float] = []
        terminal_ids: list[str] = []
        intervals: list[_Interval] = []
        for job_id, row in jobs[carrier].items():
            job = row["job"]
            timings = row["timings"]
            job_intervals = _active_intervals(
                timings, label=f"semantic job:{job_id}"
            )
            intervals.extend(job_intervals)
            state = str(job.get("state") or "")
            expected_terminal = _TERMINAL_EVENT_BY_STATE.get(state)
            if (
                state in _TERMINAL_JOB_STATES
                and timings
                and timings[-1][0] == expected_terminal
            ):
                terminal_ids.append(job_id)
                terminal_instants.append(timings[-1][1])
                if state == "succeeded":
                    active_seconds = sum(
                        (ended_at - started_at).total_seconds()
                        for started_at, ended_at in job_intervals
                    )
                    if active_seconds <= 0:
                        raise CampaignScaleEvidenceError(
                            f"semantic job:{job_id} has no positive active duration"
                        )
                    succeeded_ids.append(job_id)
                    per_slot_throughput_samples.append(
                        round(1.0 / active_seconds, 12)
                    )
        merged = _merge_intervals(intervals)
        lane_intervals[carrier] = merged
        all_ids = sorted(jobs[carrier])
        lane_rows.append(
            {
                "carrier": carrier,
                "executionId": str(execution_ids[carrier]),
                "semanticJobCount": len(all_ids),
                "semanticJobSucceededCount": len(succeeded_ids),
                "semanticJobTerminalCount": len(terminal_ids),
                "semanticJobIds": all_ids,
                "semanticJobSucceededIds": sorted(succeeded_ids),
                "semanticJobTerminalIds": sorted(terminal_ids),
                "perSlotThroughputSamples": sorted(
                    per_slot_throughput_samples
                ),
                "activeDurationSeconds": sum(
                    int((ended_at - started_at).total_seconds())
                    for started_at, ended_at in merged
                ),
                "activeIntervals": [_interval_document(interval) for interval in merged],
            }
        )
    all_terminal = all(
        row["semanticJobCount"] > 0
        and row["semanticJobTerminalCount"] == row["semanticJobCount"]
        for row in lane_rows
    )
    all_terminal_at = max(terminal_instants) if all_terminal else None
    return lane_rows, lane_intervals, all_terminal_at


def _four_lane_overlap(
    lane_intervals: dict[str, list[_Interval]],
) -> list[_Interval]:
    overlap = list(lane_intervals[CARRIERS[0]])
    for carrier in CARRIERS[1:]:
        overlap = _intersect_intervals(overlap, lane_intervals[carrier])
    return overlap


def _derive_resource_soak_stable(
    *,
    evidence_id: str,
    campaign_plan_path: Path,
    raw_samples_path: Path,
    tasks_root: Path,
    release_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    plan = _load_plan(campaign_plan_path)
    raw = _validated(
        raw_samples_path,
        "release",
        "resource_soak_samples",
        label="raw campaign resource soak samples",
    )
    source_revision = campaign_source_revision(plan)
    _assert_input_identity(
        raw,
        plan=plan,
        source_revision=source_revision,
        label="resource soak",
    )
    samples = list(raw["samples"])
    _validate_sample_relationships(samples)
    instants = [
        _timestamp(row["capturedAt"], label=f"resource sample[{index}].capturedAt")
        for index, row in enumerate(samples)
    ]
    if len(set(instants)) != len(instants) or any(
        instants[index] <= instants[index - 1] for index in range(1, len(instants))
    ):
        raise CampaignScaleEvidenceError("resource samples must be unique and chronological")
    duration_seconds = int((instants[-1] - instants[0]).total_seconds())
    gaps = [
        int((instants[index] - instants[index - 1]).total_seconds())
        for index in range(1, len(instants))
    ]
    max_gap = max(gaps, default=0)
    jobs = _semantic_jobs(plan=plan, tasks_root=tasks_root)
    lane_rows, lane_intervals, all_terminal_at = _lane_timeline_rows(
        jobs,
        execution_ids=dict(plan["executionIds"]),
    )
    overlap_intervals = _intersect_intervals(
        _four_lane_overlap(lane_intervals),
        [(instants[0], instants[-1])],
    )
    overlap_durations = [
        int((ended_at - started_at).total_seconds())
        for started_at, ended_at in overlap_intervals
    ]
    overlap_duration_seconds = sum(overlap_durations)
    longest_continuous_overlap_seconds = max(overlap_durations, default=0)
    overlap_samples = 0
    for instant in instants:
        active_lanes: set[str] = set()
        for carrier in CARRIERS:
            active_jobs = {
                job_id
                for job_id, row in jobs[carrier].items()
                if _active_at(row["timings"], instant)
            }
            if active_jobs:
                active_lanes.add(carrier)
        if active_lanes == set(CARRIERS):
            overlap_samples += 1
    all_terminal = all_terminal_at is not None
    terminal_sample_after_all_jobs = bool(
        all_terminal_at is not None and instants[-1] > all_terminal_at
    )

    release_payload_bytes = _release_payload_bytes(release_root)
    temporary_workspace_budget = (
        2 * release_payload_bytes + TEMPORARY_WORKSPACE_FIXED_ALLOWANCE_BYTES
    )
    peaks = {
        "controllerP95RssBytes": _nearest_rank_p95(
            [int(row["controllerRssBytes"]) for row in samples]
        ),
        "nonVideoWorkerP95RssBytes": _nearest_rank_p95(
            [int(row["nonVideoWorkerMaxRssBytes"]) for row in samples]
        ),
        "videoWorkerP95RssBytes": _nearest_rank_p95(
            [int(row["videoWorkerMaxRssBytes"]) for row in samples]
        ),
        "totalP95RssBytes": _nearest_rank_p95(
            [int(row["totalRssBytes"]) for row in samples]
        ),
        "totalMaxRssBytes": max(int(row["totalRssBytes"]) for row in samples),
        "temporaryWorkspaceMaxBytes": max(
            int(row["temporaryWorkspaceBytes"]) for row in samples
        ),
        "terminalResidualBytes": int(samples[-1]["terminalResidualBytes"]),
        "openFdCount": max(int(row["openFdCount"]) for row in samples),
        "queueDepth": max(int(row["queueDepth"]) for row in samples),
        "oldestReadyAgeSeconds": max(
            int(row["oldestReadyAgeSeconds"]) for row in samples
        ),
        "progressAgeSeconds": max(int(row["progressAgeSeconds"]) for row in samples),
        "heartbeatAgeSeconds": max(
            int(row["heartbeatAgeSeconds"]) for row in samples
        ),
    }
    budgets = {
        "maxControllerP95RssBytes": MAX_CONTROLLER_P95_RSS_BYTES,
        "maxNonVideoWorkerP95RssBytes": MAX_NON_VIDEO_WORKER_P95_RSS_BYTES,
        "maxVideoWorkerP95RssBytes": MAX_VIDEO_WORKER_P95_RSS_BYTES,
        "maxTotalP95RssBytes": MAX_TOTAL_P95_RSS_BYTES,
        "maxTotalRssBytes": MAX_TOTAL_RSS_BYTES,
        "maxTemporaryWorkspaceBytes": temporary_workspace_budget,
        "maxTerminalResidualBytes": MAX_TERMINAL_RESIDUAL_BYTES,
        "maxOpenFdCount": MAX_OPEN_FD_COUNT,
        "maxQueueDepth": MAX_QUEUE_DEPTH,
        "maxOldestReadyAgeSeconds": MAX_OLDEST_READY_AGE_SECONDS,
        "maxProgressAgeSeconds": MAX_PROGRESS_AGE_SECONDS,
        "maxHeartbeatAgeSeconds": MAX_HEARTBEAT_AGE_SECONDS,
    }
    budget_breaches = [
        metric
        for metric, budget_key in (
            ("controllerP95RssBytes", "maxControllerP95RssBytes"),
            ("nonVideoWorkerP95RssBytes", "maxNonVideoWorkerP95RssBytes"),
            ("videoWorkerP95RssBytes", "maxVideoWorkerP95RssBytes"),
            ("totalP95RssBytes", "maxTotalP95RssBytes"),
            ("totalMaxRssBytes", "maxTotalRssBytes"),
            ("temporaryWorkspaceMaxBytes", "maxTemporaryWorkspaceBytes"),
            ("terminalResidualBytes", "maxTerminalResidualBytes"),
            ("openFdCount", "maxOpenFdCount"),
            ("queueDepth", "maxQueueDepth"),
            ("oldestReadyAgeSeconds", "maxOldestReadyAgeSeconds"),
            ("progressAgeSeconds", "maxProgressAgeSeconds"),
            ("heartbeatAgeSeconds", "maxHeartbeatAgeSeconds"),
        )
        if peaks[metric] > budgets[budget_key]
    ]
    passed = (
        duration_seconds >= MIN_SOAK_SECONDS
        and len(samples) >= MIN_SOAK_SAMPLES
        and max_gap <= MAX_SAMPLE_GAP_SECONDS
        and all(
            row["semanticJobSucceededCount"] >= MIN_SEMANTIC_JOBS_PER_LANE
            and row["semanticJobTerminalCount"] == row["semanticJobCount"]
            for row in lane_rows
        )
        and longest_continuous_overlap_seconds >= MIN_SOAK_SECONDS
        and terminal_sample_after_all_jobs
        and not budget_breaches
    )
    return {
        "schema": "quwoquan_data.resource_soak_evidence",
        "evidenceId": evidence_id,
        "rootExecutionId": plan["rootExecutionId"],
        "runtimeSessionId": raw["runtimeSessionId"],
        "runtimeSessionRef": raw["runtimeSessionRef"],
        "runtimeSessionDigest": raw["runtimeSessionDigest"],
        "runId": raw["runId"],
        "generation": raw["generation"],
        "fencingToken": raw["fencingToken"],
        "status": "passed" if passed else "failed",
        "sourceRevision": source_revision,
        "sourceDigest": plan["sourceDigest"],
        "entityCatalogDigest": plan["entityCatalogDigest"],
        "rawSamplesRef": _safe_ref(
            raw_samples_path,
            output_root=output_root,
            label="resource soak samples",
        ),
        "rawSamplesSha256": _file_sha256(raw_samples_path),
        "soakStartedAt": samples[0]["capturedAt"],
        "soakEndedAt": samples[-1]["capturedAt"],
        "durationSeconds": duration_seconds,
        "sampleCount": len(samples),
        "maxSampleGapSeconds": max_gap,
        "semanticJobsByLane": lane_rows,
        "fourLaneOverlapSampleCount": overlap_samples,
        "fourLaneOverlapIntervals": [
            _interval_document(interval) for interval in overlap_intervals
        ],
        "fourLaneOverlapDurationSeconds": overlap_duration_seconds,
        "fourLaneLongestContinuousOverlapSeconds": (
            longest_continuous_overlap_seconds
        ),
        "allSemanticJobsTerminal": all_terminal,
        "allSemanticJobsTerminalAt": (
            all_terminal_at.isoformat() if all_terminal_at is not None else None
        ),
        "terminalResidualSampleAt": samples[-1]["capturedAt"],
        "terminalResidualMeasuredAfterAllJobs": terminal_sample_after_all_jobs,
        "releasePayloadBytes": release_payload_bytes,
        "budgets": budgets,
        "observedPeaks": peaks,
        "budgetBreaches": budget_breaches,
    }


def write_resource_soak_evidence(
    *,
    evidence_id: str,
    campaign_plan_path: Path,
    raw_samples_path: Path,
    tasks_root: Path,
    release_root: Path,
    output_root: Path,
    evidence_root: Path,
) -> tuple[dict[str, Any], Path]:
    stable = _derive_resource_soak_stable(
        evidence_id=evidence_id,
        campaign_plan_path=campaign_plan_path,
        raw_samples_path=raw_samples_path,
        tasks_root=tasks_root,
        release_root=release_root,
        output_root=output_root,
    )
    return _write_create_once(
        path=evidence_root / "resource-soak.json",
        stable=stable,
        schema_name="resource_soak_evidence",
    )


__all__ = ["_derive_resource_soak_stable", "write_resource_soak_evidence"]
