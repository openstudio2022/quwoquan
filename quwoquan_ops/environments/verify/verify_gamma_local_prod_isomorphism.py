#!/usr/bin/env python3
"""Verify gamma/prod share one service baseline and differ only at env entries."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.environment_topology import load_environment_topology


def main() -> int:
    errors: list[str] = []
    topology = load_environment_topology()
    environments = topology["environments"]
    targets = topology["targets"]

    for section in ("publicBases", "serviceAliases", "subnets"):
        gamma_keys = set((environments["gamma"].get(section) or {}).keys())
        prod_keys = set((environments["prod"].get(section) or {}).keys())
        if gamma_keys != prod_keys:
            errors.append(
                f"gamma/prod {section} keys differ: gamma={sorted(gamma_keys)} prod={sorted(prod_keys)}"
            )

    if (targets.get("gamma-local") or {}).get("env") != "gamma":
        errors.append("gamma-local must belong to gamma")
    if (targets.get("prod-hosted") or {}).get("env") != "prod":
        errors.append("prod-hosted must belong to prod")

    service_root = ROOT / "quwoquan_service" / "services"
    services = sorted(path for path in service_root.iterdir() if path.is_dir())
    for service in services:
        baseline = service / "deploy" / "base" / "kustomization.yaml"
        gamma_entry = service / "environments" / "gamma" / "deploy" / "kustomization.yaml"
        prod_entry = service / "environments" / "prod" / "deploy" / "kustomization.yaml"
        for required in (baseline, gamma_entry, prod_entry):
            if not required.is_file():
                errors.append(f"missing deployment contract: {required.relative_to(ROOT)}")
        for entry in (gamma_entry, prod_entry):
            if entry.is_file() and "../../../deploy/base" not in entry.read_text(encoding="utf-8"):
                errors.append(f"{entry.relative_to(ROOT)} must reference the shared deploy/base")

    for environment in ("gamma", "prod"):
        result = subprocess.run(
            [
                "kustomize",
                "build",
                "--load-restrictor",
                "LoadRestrictionsNone",
                str(ROOT / "quwoquan_ops" / "environments" / environment),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            errors.append(f"{environment} assembly does not build: {result.stderr.strip()}")

    if errors:
        print("FAIL: gamma/prod environment autonomy validation")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(f"PASS: gamma/prod share {len(services)} service baselines and build independently")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
