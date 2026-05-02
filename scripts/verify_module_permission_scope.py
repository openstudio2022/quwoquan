#!/usr/bin/env python3
"""Validate module store/queue permissions stay inside domain scope."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "deploy/shared/reliable_task_module_catalog.yaml"

SHARED_STORE_PREFIXES = ("reliabletask.",)
SHARED_QUEUE_PREFIXES = ("reliabletask.",)


def fail(message: str) -> None:
    print(f"[verify] FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_yaml(path: Path) -> dict:
    if not path.exists():
        fail(f"missing {path.relative_to(ROOT)}")
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def is_allowed_ref(ref: str, domain: str, shared_prefixes: tuple[str, ...]) -> bool:
    if not ref:
        return False
    if ref.startswith(shared_prefixes):
        return True
    if "." not in ref:
        return True
    return ref.split(".", 1)[0] == domain


def main() -> None:
    catalog = load_yaml(CATALOG)
    modules = catalog.get("modules")
    if not isinstance(modules, dict) or not modules:
        fail("catalog.modules must be a non-empty map")

    for module_name, module in modules.items():
        domain = module.get("domain")
        if not domain:
            fail(f"{module_name}.domain is required")
        for store in module.get("requiredStores", []):
            if not is_allowed_ref(str(store), domain, SHARED_STORE_PREFIXES):
                fail(f"{module_name} cannot access store '{store}' outside domain '{domain}'")
        for queue in module.get("requiredQueues", []):
            if not is_allowed_ref(str(queue), domain, SHARED_QUEUE_PREFIXES):
                fail(f"{module_name} cannot access queue '{queue}' outside domain '{domain}'")

    print("[verify] OK: module permission scope validated")


if __name__ == "__main__":
    main()
