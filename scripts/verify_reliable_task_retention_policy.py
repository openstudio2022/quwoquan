#!/usr/bin/env python3
"""Validate reliable task retention and rate limit policies."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
RETENTION = ROOT / "deploy/shared/reliable_task_retention_policy.yaml"
CATALOG = ROOT / "deploy/shared/reliable_task_module_catalog.yaml"


def fail(message: str) -> None:
    print(f"[verify] FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_yaml(path: Path) -> dict:
    if not path.exists():
        fail(f"missing {path.relative_to(ROOT)}")
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def require_ttl(policy_name: str, section_name: str, section: dict, keys: list[str]) -> None:
    if not isinstance(section, dict):
        fail(f"{policy_name}.{section_name} must be a map")
    for key in keys:
        if key not in section or not str(section[key]).strip():
            fail(f"{policy_name}.{section_name}.{key} is required")


def main() -> None:
    retention = load_yaml(RETENTION)
    catalog = load_yaml(CATALOG)
    policies = retention.get("policies")
    rate_limits = retention.get("rateLimits")

    if not isinstance(policies, dict) or not policies:
        fail("retention policies must be a non-empty map")
    if not isinstance(rate_limits, dict) or not rate_limits:
        fail("rateLimits must be a non-empty map")

    for policy_name, policy in policies.items():
        require_ttl(policy_name, "outbox", policy.get("outbox"), ["dispatchedTtl", "failedTtl", "archiveAfter"])
        require_ttl(policy_name, "task", policy.get("task"), ["doneTtl", "deadTtl", "archiveAfter"])
        require_ttl(policy_name, "notification", policy.get("notification"), ["dispatchedTtl", "failedTtl", "archiveAfter"])
        require_ttl(policy_name, "dlq", policy.get("dlq"), ["ttl"])
        if policy["dlq"].get("requiresManualRecoveryPlan") is not True:
            fail(f"{policy_name}.dlq.requiresManualRecoveryPlan must be true")

    for rate_name, rate in rate_limits.items():
        for key in ["dispatchPerSecond", "claimPerSecond", "retryPerSecond", "priority"]:
            if key not in rate:
                fail(f"{rate_name}.{key} is required")
        if rate["priority"] not in {"high", "normal", "low"}:
            fail(f"{rate_name}.priority must be high, normal or low")

    catalog_tasks = catalog.get("tasks") or {}
    for task_type, task in catalog_tasks.items():
        if task.get("retentionPolicyRef") not in policies:
            fail(f"{task_type}.retentionPolicyRef missing from retention policies")
        if task.get("rateLimitPolicyRef") not in rate_limits:
            fail(f"{task_type}.rateLimitPolicyRef missing from rate limits")

    print("[verify] OK: reliable task retention policies validated")


if __name__ == "__main__":
    main()
