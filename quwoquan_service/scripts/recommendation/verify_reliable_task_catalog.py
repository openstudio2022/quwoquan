#!/usr/bin/env python3
"""Validate reliable task module and task routing catalog."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
CATALOG = ROOT / "deploy/shared/reliable_task_module_catalog.yaml"
RETENTION = ROOT / "deploy/shared/reliable_task_retention_policy.yaml"

MODULE_RE = re.compile(r"^[a-z][a-z0-9-]*\.[a-z][a-z0-9_]*$")


def fail(message: str) -> None:
    print(f"[verify] FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_yaml(path: Path) -> dict:
    if not path.exists():
        fail(f"missing {path.relative_to(ROOT)}")
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def main() -> None:
    catalog = load_yaml(CATALOG)
    retention = load_yaml(RETENTION)

    modules = catalog.get("modules")
    tasks = catalog.get("tasks")
    policies = set((retention.get("policies") or {}).keys())
    rate_limits = set((retention.get("rateLimits") or {}).keys())

    if not catalog.get("compatibleRuntimeVersion"):
        fail("catalog.compatibleRuntimeVersion is required")
    if not catalog.get("schemaVersion"):
        fail("catalog.schemaVersion is required")
    if not isinstance(modules, dict) or not modules:
        fail("catalog.modules must be a non-empty map")
    if not isinstance(tasks, dict) or not tasks:
        fail("catalog.tasks must be a non-empty map")

    for module_name, module_cfg in modules.items():
        if not MODULE_RE.match(module_name):
            fail(f"invalid module name '{module_name}'")
        domain = module_name.split(".", 1)[0]
        if module_cfg.get("domain") != domain:
            fail(f"{module_name}.domain must equal module prefix '{domain}'")
        capabilities = module_cfg.get("capabilities")
        if not isinstance(capabilities, list) or not capabilities:
            fail(f"{module_name}.capabilities must be a non-empty array")
        for key in ["requiredStores", "requiredQueues", "planes"]:
            if key not in module_cfg or not isinstance(module_cfg[key], list):
                fail(f"{module_name}.{key} must be an array")

    dispatch_caps = {"outbox_dispatch", "notification_dispatch"}
    worker_caps = {"task_worker", "notification_fanout", "notification_retry"}
    required_task_keys = [
        "ownerDomain",
        "dispatcherModule",
        "workerModule",
        "queue",
        "partitionKey",
        "payloadAllowlist",
        "mergePolicy",
        "retryPolicy",
        "retentionPolicyRef",
        "rateLimitPolicyRef",
        "runtimeFailureModule",
    ]

    for task_type, task_cfg in tasks.items():
        for key in required_task_keys:
            if key not in task_cfg:
                fail(f"{task_type}.{key} is required")

        owner_domain = task_cfg["ownerDomain"]
        if "." not in task_type:
            fail(f"taskType '{task_type}' must be namespaced")
        if task_type.split(".", 1)[0] != owner_domain:
            fail(f"{task_type}.ownerDomain must match taskType prefix")

        dispatcher = task_cfg["dispatcherModule"]
        worker = task_cfg["workerModule"]
        if dispatcher not in modules:
            fail(f"{task_type}.dispatcherModule '{dispatcher}' missing from modules")
        if worker not in modules:
            fail(f"{task_type}.workerModule '{worker}' missing from modules")

        dispatcher_caps = set(modules[dispatcher].get("capabilities", []))
        worker_caps_actual = set(modules[worker].get("capabilities", []))
        if not dispatcher_caps.intersection(dispatch_caps):
            fail(f"{task_type}.dispatcherModule '{dispatcher}' has no dispatch capability")
        if not worker_caps_actual.intersection(worker_caps):
            fail(f"{task_type}.workerModule '{worker}' has no worker capability")

        if modules[dispatcher].get("domain") != owner_domain:
            fail(f"{task_type}.dispatcherModule domain must match ownerDomain")
        if modules[worker].get("domain") != owner_domain:
            fail(f"{task_type}.workerModule domain must match ownerDomain")

        payload = task_cfg.get("payloadAllowlist")
        if not isinstance(payload, list) or not payload:
            fail(f"{task_type}.payloadAllowlist must be non-empty")
        retry = task_cfg.get("retryPolicy")
        if not isinstance(retry, dict) or "maxAttempts" not in retry or "backoff" not in retry:
            fail(f"{task_type}.retryPolicy must include maxAttempts and backoff")
        if task_cfg["retentionPolicyRef"] not in policies:
            fail(f"{task_type}.retentionPolicyRef missing from retention policies")
        if task_cfg["rateLimitPolicyRef"] not in rate_limits:
            fail(f"{task_type}.rateLimitPolicyRef missing from rateLimits")

    print("[verify] OK: reliable task catalog validated")


if __name__ == "__main__":
    main()
