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


def main() -> int:
    manifest = load_environment_topology()
    issues = validate_environment_topology(manifest)
    if issues:
        print("[verify_environment_topology_manifest] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1

    summary = {
        "environments": sorted((manifest.get("environments") or {}).keys()),
        "targets": sorted((manifest.get("targets") or {}).keys()),
    }
    print("[verify_environment_topology_manifest] OK")
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
