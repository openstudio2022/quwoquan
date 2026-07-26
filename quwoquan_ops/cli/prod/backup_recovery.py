#!/usr/bin/env python3
"""Validate fail-closed production backup/recovery evidence receipts."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


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
    issues: list[str] = []
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
    datasets = receipt.get("datasets")
    by_id = {
        item.get("id"): item
        for item in datasets
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    } if isinstance(datasets, list) else {}
    for required in plan.get("datasets") or []:
        if not isinstance(required, dict):
            issues.append("backup plan contains invalid dataset")
            continue
        dataset_id = required.get("id")
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
