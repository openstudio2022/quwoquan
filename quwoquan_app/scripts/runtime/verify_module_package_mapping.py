#!/usr/bin/env python3
"""Validate deployment package to runtime module mapping."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
PROCESS_MAPPING = ROOT / "deploy/shared/process_domain_mapping.yaml"
MODULE_MAPPING = ROOT / "deploy/shared/module_package_mapping.yaml"
MODULE_CATALOG = ROOT / "deploy/shared/reliable_task_module_catalog.yaml"


def fail(message: str) -> None:
    print(f"[verify] FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_yaml(path: Path) -> dict:
    if not path.exists():
        fail(f"missing {path.relative_to(ROOT)}")
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def normalize_env(env_cfg: dict) -> dict:
    normalized: dict[str, dict[str, list[str]]] = {}
    for process_name, process_cfg in sorted(env_cfg.items()):
        domains = sorted(str(item) for item in process_cfg.get("domains", []))
        modules = sorted(str(item) for item in process_cfg.get("modules", []))
        normalized[process_name] = {"domains": domains, "modules": modules}
    return normalized


def main() -> None:
    process_data = load_yaml(PROCESS_MAPPING)
    module_data = load_yaml(MODULE_MAPPING)
    catalog_data = load_yaml(MODULE_CATALOG)

    process_envs = process_data.get("environments")
    module_envs = module_data.get("environments")
    catalog_modules = set((catalog_data.get("modules") or {}).keys())

    if not isinstance(process_envs, dict) or not process_envs:
        fail("process_domain_mapping.environments must be a non-empty map")
    if not isinstance(module_envs, dict) or not module_envs:
        fail("module_package_mapping.environments must be a non-empty map")

    required_envs = ["alpha", "beta", "gamma", "prod-gray", "prod"]
    for env in required_envs:
        if env not in module_envs:
            fail(f"module_package_mapping missing environments.{env}")

    for env, packages in module_envs.items():
        if env not in process_envs:
            fail(f"module_package_mapping contains unknown environment {env}")
        if not isinstance(packages, dict) or not packages:
            fail(f"module_package_mapping.environments.{env} must be a non-empty map")

        process_cfg = process_envs[env]
        for process_name, package_cfg in packages.items():
            if process_name not in process_cfg:
                fail(f"{env}.{process_name} not found in process_domain_mapping")

            process_domains = set(str(item) for item in process_cfg[process_name].get("domains", []))
            package_domains = set(str(item) for item in package_cfg.get("domains", []))
            modules = [str(item) for item in package_cfg.get("modules", [])]

            if not package_domains:
                fail(f"{env}.{process_name}.domains cannot be empty")
            if package_domains != process_domains:
                fail(
                    f"{env}.{process_name}.domains must match process_domain_mapping "
                    f"(expected {sorted(process_domains)}, got {sorted(package_domains)})"
                )
            if not modules:
                fail(f"{env}.{process_name}.modules cannot be empty")

            for module in modules:
                if "." not in module:
                    fail(f"{env}.{process_name} module '{module}' must use domain.capability")
                module_domain = module.split(".", 1)[0]
                if module_domain not in package_domains:
                    fail(f"{env}.{process_name} module '{module}' domain not owned by package")
                if module not in catalog_modules:
                    fail(f"{env}.{process_name} module '{module}' missing from reliable_task_module_catalog.modules")

    beta_norm = normalize_env(module_envs["beta"])
    for env in ["gamma", "prod-gray", "prod"]:
        if normalize_env(module_envs[env]) != beta_norm:
            fail("beta, gamma, prod-gray and prod module-package mapping must be identical")

    print("[verify] OK: module package mapping validated")


if __name__ == "__main__":
    main()
