#!/usr/bin/env python3
"""Legacy entrypoint that now enforces zero App runtime seed manifests."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "quwoquan_app"
FORBIDDEN = (
    "CONTRACT_FIXTURE_PROFILE",
    "app_alpha_seed_manifest",
    "app_beta_seed_manifest",
    "app_gamma_seed_manifest",
    "seedRefs",
    "requiresSeedReset",
)


def main() -> int:
    issues: list[str] = []
    candidates = [
        *(APP / "configs").glob("*/app_runtime.yaml"),
        APP / "run.sh",
        APP / "scripts/device/build_launcher_handoff.py",
        APP / "scripts/device/start_app_instance.sh",
        APP / "scripts/env/print_app_env_dart_defines.py",
    ]
    for path in candidates:
        text = path.read_text(encoding="utf-8", errors="replace")
        if path.name == "app_runtime.yaml" and "\nseed:" in text:
            issues.append(f"{path.relative_to(ROOT)}: runtime seed section is forbidden")
        for token in FORBIDDEN:
            if token in text:
                issues.append(f"{path.relative_to(ROOT)}: forbidden token `{token}`")
    if issues:
        print("app_runtime_seed_isolation: FAIL", file=sys.stderr)
        for issue in issues:
            print(f"- {issue}", file=sys.stderr)
        return 1
    print("app_runtime_seed_isolation: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
