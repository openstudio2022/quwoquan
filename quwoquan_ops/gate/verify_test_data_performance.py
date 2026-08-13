#!/usr/bin/env python3
"""Compare five green test-data runs without accepting early-failure timings.

Usage is evidence driven: callers pass five comparable legacy/baseline reports
and five candidate reports.  The gate never discovers or records a test
inventory, and it refuses mixed target, request, candidate or machine identity.

spec_ref: specs/feature-tree/runtime/runtime-testinfra/spec.md#sit-002.t3
spec_ref: specs/feature-tree/runtime/runtime-testinfra/test-data-provisioning-and-isolation/spec.md#gwt-001
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping


REQUIRED_RUNS = 5
CASE_RESULT_SCHEMA = "qwq.case_result"
_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}")
PREPARATION_FIELDS = (
    "requestCollectionMs",
    "providerDiscoveryMs",
    "planningMs",
    "actorProvisionMs",
    "criticalPathMs",
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", action="append", required=True, type=Path)
    parser.add_argument("--candidate", action="append", required=True, type=Path)
    return parser


def _load(paths: list[Path], label: str) -> tuple[Mapping[str, Any], ...]:
    if len(paths) != REQUIRED_RUNS:
        raise ValueError(f"{label} requires exactly five reports")
    resolved_paths = [path.expanduser().resolve() for path in paths]
    if len(resolved_paths) != len(set(resolved_paths)):
        raise ValueError(f"{label} requires five independent report paths")
    rows: list[Mapping[str, Any]] = []
    for path in resolved_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError(f"{label} report must be an object: {path}")
        if payload.get("status") != "passed" or payload.get("baselineEligible") is not True:
            raise ValueError(f"{label} report is not a completed green run: {path}")
        rows.append(payload)
    _require_comparable(tuple(rows), label)
    return tuple(rows)


def require_independent_report_paths(
    baseline_paths: list[Path],
    candidate_paths: list[Path],
) -> None:
    if len(baseline_paths) != REQUIRED_RUNS or len(candidate_paths) != REQUIRED_RUNS:
        raise ValueError("baseline and candidate each require exactly five reports")
    baseline = [path.expanduser().resolve() for path in baseline_paths]
    candidate = [path.expanduser().resolve() for path in candidate_paths]
    if len(baseline) != len(set(baseline)):
        raise ValueError("baseline requires five independent report paths")
    if len(candidate) != len(set(candidate)):
        raise ValueError("candidate requires five independent report paths")
    if set(baseline) & set(candidate):
        raise ValueError("baseline/candidate report paths must be independent")


def _require_comparable(rows: tuple[Mapping[str, Any], ...], label: str) -> None:
    if len(rows) != REQUIRED_RUNS:
        raise ValueError(f"{label} requires exactly five reports")
    run_ids = [str(row.get("runId") or "").strip() for row in rows]
    if any(not run_id for run_id in run_ids) or len(run_ids) != len(set(run_ids)):
        raise ValueError(f"{label} reports must have independent run identities")
    for field in (
        "target",
        "environment",
        "candidateBindingDigest",
        "requestDigest",
        "evidenceDigest",
        "handoffDigest",
        "sourceRevision",
        "packageDigest",
        "runtimeConfigDigest",
        "releaseId",
        "manifestDigest",
        "importRunId",
        "readinessReceiptDigest",
        "machineFingerprint",
    ):
        values = {str(row.get(field) or "") for row in rows}
        if "" in values or len(values) != 1:
            raise ValueError(f"{label} reports have mixed or missing {field}")
    for field in (
        "candidateBindingDigest",
        "requestDigest",
        "evidenceDigest",
        "handoffDigest",
        "packageDigest",
        "runtimeConfigDigest",
        "manifestDigest",
        "readinessReceiptDigest",
        "machineFingerprint",
    ):
        if not _canonical_digest(rows[0].get(field)):
            raise ValueError(f"{label} reports have non-canonical {field}")
    operation_sets = {
        tuple(sorted(str(item) for item in (row.get("executedOperationIds") or [])))
        for row in rows
    }
    if len(operation_sets) != 1 or not next(iter(operation_sets), ()):
        raise ValueError(f"{label} reports have mixed or missing executed operations")
    case_sets: set[tuple[str, ...]] = set()
    provider_sets: set[tuple[str, ...]] = set()
    required_provider_sets: set[tuple[str, ...]] = set()
    capability_sets: set[tuple[str, ...]] = set()
    for row in rows:
        if (
            row.get("schema") != CASE_RESULT_SCHEMA
            or row.get("status") != "passed"
            or row.get("preparationStatus") != "passed"
            or int(row.get("executed") or 0) <= 0
            or int(row.get("skipped") or 0) != 0
            or row.get("baselineEligible") is not True
        ):
            raise ValueError(f"{label} report schema or lifecycle is not fully green")
        for field in (
            "rootWorkerCount",
            "maxObservedConcurrency",
            "operationCount",
            "dataPreparationMs",
            "totalMs",
            "receiptWriteMs",
            "controlPlaneOverheadMs",
            *PREPARATION_FIELDS,
        ):
            value = row.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{label} report has invalid {field}")
        case_results = row.get("caseResults")
        if not isinstance(case_results, list) or len(case_results) != int(
            row.get("executed") or 0
        ):
            raise ValueError(f"{label} report has an incomplete business-case set")
        case_ids = tuple(
            sorted(
                str(item.get("caseId") or "")
                for item in case_results
                if isinstance(item, Mapping)
            )
        )
        if (
            len(case_ids) != len(case_results)
            or not case_ids
            or "" in case_ids
            or len(case_ids) != len(set(case_ids))
            or any(
                not isinstance(item, Mapping) or item.get("status") != "passed"
                for item in case_results
            )
        ):
            raise ValueError(f"{label} report has invalid business-case evidence")
        for item in case_results:
            assert isinstance(item, Mapping)
            execution = item.get("testExecution")
            if (
                not isinstance(execution, Mapping)
                or execution.get("executed") != 1
                or execution.get("failed") != 0
                or execution.get("skipped") != 0
                or not _canonical_digest(item.get("provisionReceiptDigest"))
                or not _canonical_digest(item.get("testBodyReceiptDigest"))
                or not _digest_list(item.get("readbackReceiptDigests"))
                or not _digest_list(item.get("cleanupReceiptDigests"))
            ):
                raise ValueError(
                    f"{label} report has incomplete case lifecycle evidence"
                )
        case_sets.add(case_ids)
        loaded = tuple(sorted(str(item) for item in (row.get("loadedProviders") or [])))
        required = tuple(
            sorted(str(item) for item in (row.get("requiredProviders") or []))
        )
        if not loaded or not required:
            raise ValueError(f"{label} report Provider closure is incomplete")
        provider_sets.add(loaded)
        required_provider_sets.add(required)
        operation_count = int(row.get("operationCount") or 0)
        if operation_count < len(row.get("executedOperationIds") or []):
            raise ValueError(f"{label} report operation receipts are incomplete")
        timings = row.get("capabilityTimings")
        if not isinstance(timings, list) or not timings:
            raise ValueError(f"{label} report has no capability timing evidence")
        capability_rows: list[str] = []
        owner_services: set[str] = set()
        request_ids: set[str] = set()
        for item in timings:
            if not isinstance(item, Mapping):
                raise ValueError(
                    f"{label} report capability timing item must be an object"
                )
            key = str(item.get("capabilityKey") or "").strip()
            owner = str(item.get("ownerService") or "").strip()
            request_id = str(item.get("requestId") or "").strip()
            if not key or not owner or not request_id or request_id in request_ids:
                raise ValueError(f"{label} report has invalid capability timing identity")
            request_ids.add(request_id)
            owner_services.add(owner)
            for field in ("provisionMs", "readbackMs", "cleanupMs", "operationCount"):
                value = item.get(field)
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise ValueError(
                        f"{label} report has invalid capability timing {field}"
                    )
            capability_rows.append(f"{owner}\0{key}")
        if owner_services != set(required):
            raise ValueError(
                f"{label} report capability timings do not cover Provider closure"
            )
        if sum(int(item["operationCount"]) for item in timings) > operation_count:
            raise ValueError(
                f"{label} report capability operation counts exceed lifecycle receipts"
            )
        capability_sets.add(tuple(sorted(capability_rows)))
    if len(case_sets) != 1:
        raise ValueError(f"{label} reports have mixed business-case sets")
    if len(provider_sets) != 1:
        raise ValueError(f"{label} reports have mixed Provider closures")
    if len(required_provider_sets) != 1:
        raise ValueError(f"{label} reports have mixed required Provider closures")
    if len(capability_sets) != 1:
        raise ValueError(f"{label} reports have mixed capability timing sets")


def _preparation_ms(row: Mapping[str, Any]) -> int:
    measured = int(row.get("dataPreparationMs") or 0)
    if measured > 0:
        return measured
    return sum(int(row.get(field) or 0) for field in PREPARATION_FIELDS)


def _canonical_digest(value: object) -> bool:
    return isinstance(value, str) and _DIGEST_RE.fullmatch(value) is not None


def _digest_list(value: object) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and len(value) == len(set(value))
        and all(_canonical_digest(item) for item in value)
    )


def _capability_p95(rows: tuple[Mapping[str, Any], ...]) -> dict[str, int]:
    values: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        timings = row.get("capabilityTimings")
        if not isinstance(timings, list):
            raise ValueError("capabilityTimings must be present in every report")
        per_run: dict[str, int] = defaultdict(int)
        for item in timings:
            if not isinstance(item, Mapping):
                raise ValueError("capability timing item must be an object")
            key = str(item.get("capabilityKey") or "")
            if not key:
                raise ValueError("capability timing misses capabilityKey")
            per_run[key] += sum(
                int(item.get(field) or 0)
                for field in ("provisionMs", "readbackMs", "cleanupMs")
            )
        for key, value in per_run.items():
            values[key].append(value)
    if not values:
        raise ValueError("capability timing evidence must not be empty")
    if any(len(samples) != REQUIRED_RUNS for samples in values.values()):
        raise ValueError("capability timing sets differ between comparable runs")
    return {key: max(samples) for key, samples in values.items()}


def _p95(rows: tuple[Mapping[str, Any], ...], field: str) -> int:
    values = sorted(int(row.get(field) or 0) for row in rows)
    if len(values) != REQUIRED_RUNS:
        raise ValueError(f"{field} requires exactly five samples")
    return values[-1]


def compare(
    baseline: tuple[Mapping[str, Any], ...],
    candidate: tuple[Mapping[str, Any], ...],
) -> list[str]:
    _require_comparable(baseline, "baseline")
    _require_comparable(candidate, "candidate")
    issues: list[str] = []
    baseline_run_ids = {str(row.get("runId")) for row in baseline}
    candidate_run_ids = {str(row.get("runId")) for row in candidate}
    if baseline_run_ids & candidate_run_ids:
        issues.append("baseline/candidate run identities must be independent")
    if any(
        row.get("benchmarkPolicy") != "serial-no-cache"
        or row.get("benchmarkOnly") is not True
        or int(row.get("rootWorkerCount") or 0) != 1
        or int(row.get("maxObservedConcurrency") or 0) != 1
        for row in baseline
    ):
        issues.append(
            "baseline runs must use the serial-no-cache benchmark-only policy"
        )
    if any(
        row.get("benchmarkPolicy") != "normal"
        or row.get("benchmarkOnly") is not False
        or int(row.get("rootWorkerCount") or 0) < 2
        or int(row.get("maxObservedConcurrency") or 0) < 2
        or int(row.get("maxObservedConcurrency") or 0)
        > int(row.get("rootWorkerCount") or 0)
        for row in candidate
    ):
        issues.append("candidate runs must use the normal execution policy")
    identity_fields = (
        "target",
        "environment",
        "candidateBindingDigest",
        "requestDigest",
        "evidenceDigest",
        "handoffDigest",
        "sourceRevision",
        "packageDigest",
        "runtimeConfigDigest",
        "releaseId",
        "manifestDigest",
        "importRunId",
        "readinessReceiptDigest",
        "machineFingerprint",
    )
    for field in identity_fields:
        if baseline[0].get(field) != candidate[0].get(field):
            issues.append(f"baseline/candidate {field} mismatch")
    if sorted(baseline[0].get("executedOperationIds") or []) != sorted(
        candidate[0].get("executedOperationIds") or []
    ):
        issues.append("baseline/candidate executed operation closure mismatch")
    baseline_case_ids = sorted(
        str(item.get("caseId") or "")
        for item in (baseline[0].get("caseResults") or [])
        if isinstance(item, Mapping)
    )
    candidate_case_ids = sorted(
        str(item.get("caseId") or "")
        for item in (candidate[0].get("caseResults") or [])
        if isinstance(item, Mapping)
    )
    if baseline_case_ids != candidate_case_ids:
        issues.append("baseline/candidate business-case closure mismatch")
    if sorted(baseline[0].get("loadedProviders") or []) != sorted(
        candidate[0].get("loadedProviders") or []
    ):
        issues.append("baseline/candidate Provider closure mismatch")
    if sorted(baseline[0].get("requiredProviders") or []) != sorted(
        candidate[0].get("requiredProviders") or []
    ):
        issues.append("baseline/candidate required Provider closure mismatch")
    baseline_capability_closure = sorted(
        (
            str(item.get("ownerService") or ""),
            str(item.get("capabilityKey") or ""),
        )
        for item in baseline[0].get("capabilityTimings") or []
        if isinstance(item, Mapping)
    )
    candidate_capability_closure = sorted(
        (
            str(item.get("ownerService") or ""),
            str(item.get("capabilityKey") or ""),
        )
        for item in candidate[0].get("capabilityTimings") or []
        if isinstance(item, Mapping)
    )
    if baseline_capability_closure != candidate_capability_closure:
        issues.append("baseline/candidate capability timing closure mismatch")
    baseline_preparation = statistics.median(_preparation_ms(row) for row in baseline)
    candidate_preparation = statistics.median(_preparation_ms(row) for row in candidate)
    baseline_total = statistics.median(int(row.get("totalMs") or 0) for row in baseline)
    candidate_total = statistics.median(int(row.get("totalMs") or 0) for row in candidate)
    if baseline_preparation <= 0 or candidate_preparation > baseline_preparation * 0.50:
        issues.append(
            "candidate data-preparation median did not decrease by at least 50%"
        )
    if baseline_total <= 0 or candidate_total > baseline_total * 0.70:
        issues.append("candidate total median did not decrease by at least 30%")
    discovery_planning_p95 = max(
        int(row.get("providerDiscoveryMs") or 0)
        + int(row.get("planningMs") or 0)
        for row in candidate
    )
    if discovery_planning_p95 > 500:
        issues.append(
            "candidate discovery+planning p95 exceeds 500ms"
        )
    if _p95(candidate, "controlPlaneOverheadMs") > 1000:
        issues.append(
            "candidate no-mutation control-plane p95 exceeds 1s"
        )
    for row in candidate:
        preparation = _preparation_ms(row)
        receipt = int(row.get("receiptWriteMs") or 0)
        if receipt > preparation * 0.05 and not any(
            "receipt write cost" in issue for issue in issues
        ):
            issues.append("candidate receipt write cost exceeds 5% of preparation time")
        if sorted(row.get("loadedProviders") or []) != sorted(
            row.get("requiredProviders") or []
        ) and not any("loaded Providers" in issue for issue in issues):
            issues.append("candidate loaded Providers exceed the requested closure")
    baseline_p95 = _capability_p95(baseline)
    candidate_p95 = _capability_p95(candidate)
    if set(baseline_p95) != set(candidate_p95):
        issues.append("baseline/candidate capability sets differ")
    else:
        for key in sorted(candidate_p95):
            if (
                baseline_p95[key] == 0
                and candidate_p95[key] > 0
                or baseline_p95[key] > 0
                and candidate_p95[key] > baseline_p95[key] * 1.20
            ):
                issues.append(f"capability p95 regressed by more than 20%: {key}")
    return issues


def main() -> int:
    args = _parser().parse_args()
    try:
        require_independent_report_paths(args.baseline, args.candidate)
        baseline = _load(args.baseline, "baseline")
        candidate = _load(args.candidate, "candidate")
        issues = compare(baseline, candidate)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        issues = [str(exc)]
    if issues:
        print("GATE_BLOCK: test-data performance evidence is not acceptable")
        for issue in issues:
            print(f"- {issue}")
        return 1
    print("PASS: test-data performance budgets are proven by five comparable green runs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
