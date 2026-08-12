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
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping


REQUIRED_RUNS = 5
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
    rows: list[Mapping[str, Any]] = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError(f"{label} report must be an object: {path}")
        if payload.get("status") != "passed" or payload.get("baselineEligible") is not True:
            raise ValueError(f"{label} report is not a completed green run: {path}")
        rows.append(payload)
    _require_comparable(tuple(rows), label)
    return tuple(rows)


def _require_comparable(rows: tuple[Mapping[str, Any], ...], label: str) -> None:
    for field in (
        "target",
        "environment",
        "candidateBindingDigest",
        "requestDigest",
        "machineFingerprint",
    ):
        values = {str(row.get(field) or "") for row in rows}
        if "" in values or len(values) != 1:
            raise ValueError(f"{label} reports have mixed or missing {field}")


def _preparation_ms(row: Mapping[str, Any]) -> int:
    measured = int(row.get("dataPreparationMs") or 0)
    if measured > 0:
        return measured
    return sum(int(row.get(field) or 0) for field in PREPARATION_FIELDS)


def _capability_p95(rows: tuple[Mapping[str, Any], ...]) -> dict[str, int]:
    values: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        timings = row.get("capabilityTimings")
        if not isinstance(timings, list):
            raise ValueError("capabilityTimings must be present in every report")
        per_run: dict[str, int] = defaultdict(int)
        for item in timings:
            if not isinstance(item, Mapping):
                continue
            key = str(item.get("capabilityKey") or "")
            if not key:
                raise ValueError("capability timing misses capabilityKey")
            per_run[key] += sum(
                int(item.get(field) or 0)
                for field in ("provisionMs", "readbackMs", "cleanupMs")
            )
        for key, value in per_run.items():
            values[key].append(value)
    if any(len(samples) != REQUIRED_RUNS for samples in values.values()):
        raise ValueError("capability timing sets differ between comparable runs")
    return {key: max(samples) for key, samples in values.items()}


def compare(
    baseline: tuple[Mapping[str, Any], ...],
    candidate: tuple[Mapping[str, Any], ...],
) -> list[str]:
    issues: list[str] = []
    identity_fields = (
        "target",
        "environment",
        "candidateBindingDigest",
        "requestDigest",
        "machineFingerprint",
    )
    for field in identity_fields:
        if baseline[0].get(field) != candidate[0].get(field):
            issues.append(f"baseline/candidate {field} mismatch")
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
            if baseline_p95[key] > 0 and candidate_p95[key] > baseline_p95[key] * 1.20:
                issues.append(f"capability p95 regressed by more than 20%: {key}")
    return issues


def main() -> int:
    args = _parser().parse_args()
    try:
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
