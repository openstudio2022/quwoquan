#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.port_manifest import (
    load_port_manifest,
    profile_ports,
    validate_port_manifest,
)


def main() -> int:
    manifest = load_port_manifest()
    issues = validate_port_manifest(manifest)
    if issues:
        print("[verify_local_env_port_manifest] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1

    preview = {
        profile: profile_ports(manifest, profile)
        for profile in ("alpha-local", "beta-local", "gamma-local", "prod-sim")
    }
    print("[verify_local_env_port_manifest] OK")
    print(json.dumps(preview, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
