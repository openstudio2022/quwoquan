#!/usr/bin/env python3
"""Validate fail-closed production backup/recovery evidence receipts."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml


_READBACK_FIELDS = frozenset(
    {
        "mapping",
        "documentCount",
        "canonicalDigest",
        "timeBoundary",
        "aggregateConsistency",
    }
)
_MEMBERSHIP_FIELDS = frozenset(
    {"resourceRef", "namespaces", "indexPatterns", "snapshotPolicyRef"}
)
_SAFE_MEMBER = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")
_SAFE_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}(?:-\*)?$")


def _normalized_memberships(dataset: dict[str, Any]) -> dict[str, Any]:
    return {
        "resourceRef": dataset.get("resourceRef"),
        "namespaces": dataset.get("namespaces"),
        "indexPatterns": dataset.get("indexPatterns"),
        "snapshotPolicyRef": dataset.get("snapshotPolicyRef"),
    }


def _validate_plan_datasets(plan: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    datasets = plan.get("datasets")
    if not isinstance(datasets, list) or not datasets:
        return ["backup plan datasets must be a non-empty list"]
    seen: set[str] = set()
    membership_owners: dict[tuple[str, str], set[str]] = {}
    for index, dataset in enumerate(datasets):
        label = f"backup plan datasets[{index}]"
        if not isinstance(dataset, dict):
            issues.append(f"{label} is invalid")
            continue
        dataset_id = str(dataset.get("id") or "").strip()
        if not dataset_id or _SAFE_MEMBER.fullmatch(dataset_id) is None:
            issues.append(f"{label}.id must be a safe non-empty ID")
        elif dataset_id in seen:
            issues.append(f"{label}.id is duplicated: {dataset_id}")
        seen.add(dataset_id)
        memberships = _normalized_memberships(dataset)
        resource_ref = memberships["resourceRef"]
        snapshot_ref = memberships["snapshotPolicyRef"]
        if not isinstance(resource_ref, str) or _SAFE_MEMBER.fullmatch(resource_ref) is None:
            issues.append(f"{dataset_id}: resourceRef is invalid")
        if not isinstance(snapshot_ref, str) or _SAFE_MEMBER.fullmatch(snapshot_ref) is None:
            issues.append(f"{dataset_id}: snapshotPolicyRef is invalid")
        namespaces = memberships["namespaces"]
        if (
            not isinstance(namespaces, list)
            or not namespaces
            or len(namespaces) != len(set(namespaces))
            or any(
                not isinstance(item, str) or _SAFE_MEMBER.fullmatch(item) is None
                for item in namespaces
            )
        ):
            issues.append(f"{dataset_id}: namespaces must be unique safe members")
            namespaces = []
        if isinstance(resource_ref, str):
            for namespace in namespaces:
                membership_owners.setdefault(
                    (resource_ref, namespace), set()
                ).add(dataset_id)
        patterns = memberships["indexPatterns"]
        if not isinstance(patterns, list) or len(patterns) != len(set(patterns)):
            issues.append(f"{dataset_id}: indexPatterns must be a unique list")
            patterns = []
        for pattern in patterns:
            if not isinstance(pattern, str) or _SAFE_PATTERN.fullmatch(pattern) is None:
                issues.append(f"{dataset_id}: index pattern is unsafe: {pattern!r}")
                continue
            covered = pattern[:-2] if pattern.endswith("-*") else pattern
            if covered not in namespaces:
                issues.append(
                    f"{dataset_id}: index pattern exceeds namespace membership: {pattern}"
                )
        readback = dataset.get("readback")
        if (
            not isinstance(readback, list)
            or not readback
            or len(readback) != len(set(readback))
            or not set(readback).issubset(_READBACK_FIELDS)
        ):
            issues.append(f"{dataset_id}: readback must use the supported closed set")
    for (resource_ref, namespace), owners in sorted(membership_owners.items()):
        if len(owners) > 1:
            issues.append(
                f"backup membership overlaps on {resource_ref}/{namespace}: "
                f"{sorted(owners)}"
            )
    return issues

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def _utc(value: object) -> dt.datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
            dt.timezone.utc
        )
    except ValueError:
        return None


def _digest(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _validate(plan: dict[str, Any], receipt: dict[str, Any]) -> list[str]:
    issues = _validate_plan_datasets(plan)
    if receipt.get("schema") != "quwoquan-prod-backup-recovery-receipt":
        issues.append("receipt schema is invalid")
    if receipt.get("planDigest") != _digest(plan):
        issues.append("receipt planDigest does not match the canonical backup plan")
    generated_at = _utc(receipt.get("generatedAt"))
    max_age = int(plan.get("receiptMaxAgeHours") or 0)
    if generated_at is None:
        issues.append("receipt generatedAt is invalid")
    elif max_age <= 0 or generated_at < dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=max_age):
        issues.append("receipt is stale")

    planned = {
        item.get("id"): item
        for item in plan.get("datasets") or []
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    datasets = receipt.get("datasets")
    receipt_items = datasets if isinstance(datasets, list) else []
    by_id: dict[str, dict[str, Any]] = {}
    for evidence in receipt_items:
        if not isinstance(evidence, dict) or not isinstance(evidence.get("id"), str):
            issues.append("receipt contains invalid dataset evidence")
            continue
        dataset_id = evidence["id"]
        if dataset_id in by_id:
            issues.append(f"{dataset_id}: receipt dataset is duplicated")
            continue
        by_id[dataset_id] = evidence
    extra_ids = sorted(set(by_id) - set(planned))
    if extra_ids:
        issues.append(f"receipt contains unplanned datasets: {extra_ids}")

    for dataset_id, required in planned.items():
        evidence = by_id.get(dataset_id)
        if not isinstance(evidence, dict):
            issues.append(f"{dataset_id}: receipt dataset is missing")
            continue
        for key in ("contentDigest", "kmsKeyVersion", "remoteCopyUri", "isolationTarget"):
            if not isinstance(evidence.get(key), str) or not evidence[key].strip():
                issues.append(f"{dataset_id}: {key} is missing")
        if evidence.get("encrypted") is not True:
            issues.append(f"{dataset_id}: encryption is not verified")
        if evidence.get("remoteCopyVerified") is not True:
            issues.append(f"{dataset_id}: remote copy is not verified")
        if evidence.get("restoreVerified") is not True:
            issues.append(f"{dataset_id}: isolated restore is not verified")
        if int(evidence.get("rpoMinutes") or -1) > int(required.get("rpoMinutes") or 0):
            issues.append(f"{dataset_id}: RPO exceeds plan")
        if int(evidence.get("restoreDurationMinutes") or -1) > int(required.get("rtoMinutes") or 0):
            issues.append(f"{dataset_id}: RTO exceeds plan")

        memberships = evidence.get("memberships")
        expected_memberships = _normalized_memberships(required)
        if (
            not isinstance(memberships, dict)
            or set(memberships) != _MEMBERSHIP_FIELDS
            or memberships != expected_memberships
        ):
            issues.append(
                f"{dataset_id}: receipt memberships do not exactly match the plan"
            )
        readback = evidence.get("readback")
        expected_readback = set(required.get("readback") or [])
        if not isinstance(readback, dict) or set(readback) != expected_readback:
            issues.append(
                f"{dataset_id}: receipt readback does not exactly match the plan"
            )
        else:
            for field in sorted(expected_readback):
                if readback.get(field) is not True:
                    issues.append(f"{dataset_id}: readback.{field} is not verified")

    capacity = receipt.get("capacityCost")
    if not isinstance(capacity, dict):
        return [*issues, "capacityCost evidence is missing"]
    policy = plan.get("capacityCost") or {}
    for key, limit in (
        ("sourceUsagePercent", policy.get("sourceUsagePercentMax")),
        ("replicaUsagePercent", policy.get("replicaUsagePercentMax")),
        ("monthlyCostCny", policy.get("monthlyCostBudgetCny")),
    ):
        if not isinstance(capacity.get(key), (int, float)):
            issues.append(f"capacityCost.{key} is missing")
        elif not isinstance(limit, (int, float)):
            issues.append(f"capacityCost policy for {key} is missing")
        elif capacity[key] > limit:
            issues.append(f"capacityCost.{key} exceeds plan")
    return issues


def main() -> int:
    args = _parse_args()
    try:
        plan = yaml.safe_load(args.plan.read_text(encoding="utf-8"))
        receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError, json.JSONDecodeError) as error:
        issues = [f"backup recovery evidence is unreadable: {error}"]
        plan, receipt = {}, {}
    if not isinstance(plan, dict) or plan.get("schema") != "quwoquan-prod-backup-recovery-plan":
        issues = ["backup recovery plan is invalid"]
    else:
        issues = _validate(plan, receipt if isinstance(receipt, dict) else {})
    payload = {
        "schema": "quwoquan-prod-backup-recovery-validation",
        "status": "ok" if not issues else "blocked",
        "planDigest": _digest(plan) if isinstance(plan, dict) else "",
        "receiptDigest": _digest(receipt) if isinstance(receipt, dict) else "",
        "issues": issues,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if issues:
        print("[backup-recovery] BLOCK: " + "; ".join(issues))
        return 2
    print("[backup-recovery] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
