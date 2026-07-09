#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = [
    ROOT / ".github" / "workflows" / "deploy-prod-gray.yml",
    ROOT / ".github" / "workflows" / "deploy-prod-auto.yml",
]


def main() -> int:
    issues: list[str] = []
    for path in WORKFLOWS:
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(ROOT)
        if "quwoquan_ops/cli/stackctl.py deploy" not in text:
            issues.append(f"{rel} must call stackctl.py deploy")
        if "--target prod-hosted" not in text:
            issues.append(f"{rel} must deploy prod-hosted through stackctl")
        for token in ("--error-rate", "--p95-ms", "--redis-error-rate"):
            if token not in text:
                issues.append(f"{rel} missing {token} passthrough")
        for forbidden in (
            "make config-gray-rollout",
            "make config-slo-gate",
            "make config-rollback",
            "bash quwoquan_ops/cli/prod/deploy_to_prod.sh",
        ):
            if forbidden in text:
                issues.append(f"{rel} still contains legacy rollout entry: {forbidden}")

    if issues:
        print("[verify_prod_rollout_stackctl_contract] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1

    print("[verify_prod_rollout_stackctl_contract] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
