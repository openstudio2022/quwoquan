#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.environment_topology import (
    load_environment_topology,
    validate_environment_topology,
)
from quwoquan_ops.cli.lib.content_release_readiness import (
    load_content_release_readiness_policy,
)


def main() -> int:
    manifest = load_environment_topology()
    issues = validate_environment_topology(manifest)
    try:
        content_readiness = load_content_release_readiness_policy()
    except ValueError as exc:
        issues.append(f"content release readiness policy invalid: {exc}")
        content_readiness = None
    if issues:
        print("[verify_environment_topology_manifest] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1

    summary = {
        "environments": sorted((manifest.get("environments") or {}).keys()),
        "targets": sorted((manifest.get("targets") or {}).keys()),
        "contentReleaseReadiness": (
            {
                "policyId": content_readiness.policy_id,
                "requirements": [
                    f"{requirement.phase.value}/{requirement.environment}:{requirement.target}"
                    for requirement in content_readiness.requirements
                ],
            }
            if content_readiness is not None
            else None
        ),
    }
    print("[verify_environment_topology_manifest] OK")
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
