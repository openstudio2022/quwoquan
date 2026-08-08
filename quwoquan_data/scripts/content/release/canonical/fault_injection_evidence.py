"""Derive canonical fault-injection recovery evidence from queue timelines."""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.release.canonical.campaign_scale_contract import (
    _FAULT_EVENTS,
    CARRIERS,
    CampaignScaleEvidenceError,
    _assert_input_identity,
    _file_sha256,
    _job_timings,
    _load_plan,
    _resolve_ref,
    _safe_ref,
    _semantic_jobs,
    _timestamp,
    _validated,
    _write_create_once,
    campaign_source_revision,
)

FAULT_TYPES = (
    "worker_termination",
    "lease_expiry",
    "redis_restart",
    "mongo_reconnect",
    "provider_timeout",
    "provider_rate_limit",
)


def _validate_injection_evidence(
    case: Mapping[str, Any],
    *,
    output_root: Path,
) -> None:
    evidence_path = _resolve_ref(
        str(case["injectionEvidenceRef"]),
        output_root=output_root,
        label=f"fault injection event:{case['caseId']}",
    )
    if _file_sha256(evidence_path) != case["injectionEvidenceSha256"]:
        raise CampaignScaleEvidenceError(
            f"fault injection event digest drift: {case['caseId']}"
        )
    event = _validated(
        evidence_path,
        "release",
        "fault_injection_event",
        label=f"fault injection event:{case['caseId']}",
    )
    expected = {
        "caseId": case["caseId"],
        "faultType": case["faultType"],
        "carrier": case["carrier"],
        "executionId": case["executionId"],
        "jobId": case["jobId"],
        "triggeredAt": case["faultEventAt"],
    }
    if any(event.get(key) != value for key, value in expected.items()):
        raise CampaignScaleEvidenceError(
            f"fault injection event identity drift: {case['caseId']}"
        )


def _fault_outcome(
    *,
    case: Mapping[str, Any],
    job: Mapping[str, Any],
) -> str:
    timings = _job_timings(job, label=f"fault job:{case['jobId']}")
    fault_at = _timestamp(case["faultEventAt"], label=f"fault case:{case['caseId']}")
    matching = [
        index
        for index, (event, at) in enumerate(timings)
        if at == fault_at and event in _FAULT_EVENTS[str(case["faultType"])]
    ]
    if len(matching) != 1:
        raise CampaignScaleEvidenceError(
            f"fault case {case['caseId']} has no exact queue timing event"
        )
    after = timings[matching[0] + 1 :]
    succeeded = any(event == "succeeded" for event, _at in after)
    recovered = any(event in {"leased", "requeued", "revived"} for event, _at in after)
    if not succeeded or not recovered:
        return "unrecovered"
    return "manual" if any(event == "revived" for event, _at in after) else "automatic"


def write_fault_injection_evidence(
    *,
    evidence_id: str,
    campaign_plan_path: Path,
    raw_cases_path: Path,
    tasks_root: Path,
    output_root: Path,
    evidence_root: Path,
) -> tuple[dict[str, Any], Path]:
    plan = _load_plan(campaign_plan_path)
    raw = _validated(
        raw_cases_path,
        "release",
        "fault_injection_cases",
        label="raw campaign fault injection cases",
    )
    source_revision = campaign_source_revision(plan)
    _assert_input_identity(
        raw,
        plan=plan,
        source_revision=source_revision,
        label="fault injection",
    )
    jobs = _semantic_jobs(plan=plan, tasks_root=tasks_root)
    seen_case_ids: set[str] = set()
    seen_events: set[tuple[str, str]] = set()
    derived_cases: list[dict[str, Any]] = []
    for case in raw["cases"]:
        _validate_injection_evidence(case, output_root=output_root)
        case_id = str(case["caseId"])
        carrier = str(case["carrier"])
        execution_id = str(case["executionId"])
        job_id = str(case["jobId"])
        event_key = (job_id, str(case["faultEventAt"]))
        if case_id in seen_case_ids or event_key in seen_events:
            raise CampaignScaleEvidenceError("fault cases must have unique case/event identities")
        seen_case_ids.add(case_id)
        seen_events.add(event_key)
        if execution_id != plan["executionIds"][carrier]:
            raise CampaignScaleEvidenceError(f"fault case execution lane drift: {case_id}")
        job_row = jobs[carrier].get(job_id)
        if job_row is None:
            raise CampaignScaleEvidenceError(f"fault case semantic job is missing: {case_id}")
        outcome = _fault_outcome(case=case, job=job_row["job"])
        derived_cases.append(
            {
                "caseId": case_id,
                "faultType": case["faultType"],
                "carrier": carrier,
                "executionId": execution_id,
                "jobId": job_id,
                "faultEventAt": case["faultEventAt"],
                "injectionEvidenceRef": case["injectionEvidenceRef"],
                "injectionEvidenceSha256": case["injectionEvidenceSha256"],
                "outcome": outcome,
            }
        )
    eligible = len(derived_cases)
    automatic = sum(row["outcome"] == "automatic" for row in derived_cases)
    manual = sum(row["outcome"] == "manual" for row in derived_cases)
    unrecovered = eligible - automatic - manual
    status = "NOT_EXERCISED" if eligible == 0 else "MEASURED"
    rate = round(automatic / eligible, 6) if eligible else None
    counts = Counter(str(row["carrier"]) for row in derived_cases)
    fault_counts = Counter(str(row["faultType"]) for row in derived_cases)
    lane_rows = [
        {"carrier": carrier, "recoveryEligibleCount": counts[carrier]}
        for carrier in CARRIERS
    ]
    fault_type_rows = [
        {
            "faultType": fault_type,
            "recoveryEligibleCount": fault_counts[fault_type],
        }
        for fault_type in FAULT_TYPES
    ]
    stable = {
        "schema": "quwoquan_data.fault_injection_evidence",
        "evidenceId": evidence_id,
        "rootExecutionId": plan["rootExecutionId"],
        "runtimeSessionId": raw["runtimeSessionId"],
        "runtimeSessionRef": raw["runtimeSessionRef"],
        "runtimeSessionDigest": raw["runtimeSessionDigest"],
        "runId": raw["runId"],
        "generation": raw["generation"],
        "fencingToken": raw["fencingToken"],
        "status": "passed",
        "sourceRevision": source_revision,
        "sourceDigest": plan["sourceDigest"],
        "entityCatalogDigest": plan["entityCatalogDigest"],
        "rawCasesRef": _safe_ref(
            raw_cases_path,
            output_root=output_root,
            label="fault injection cases",
        ),
        "rawCasesSha256": _file_sha256(raw_cases_path),
        "automaticRecoveryStatus": status,
        "recoveryEligibleCount": eligible,
        "automaticRecoveredCount": automatic,
        "manualRecoveredCount": manual,
        "unrecoveredCount": unrecovered,
        "automaticRecoveryRate": rate,
        "casesByLane": lane_rows,
        "casesByFaultType": fault_type_rows,
        "cases": derived_cases,
    }
    return _write_create_once(
        path=evidence_root / "fault-injection.json",
        stable=stable,
        schema_name="fault_injection_evidence",
    )
