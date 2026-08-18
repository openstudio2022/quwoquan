#!/usr/bin/env python3
"""Prevent profile fallback and retired tier/gate entrypoints from returning."""
from __future__ import annotations

import sys
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ACTIVE_PATHS = (
    ROOT / "Makefile",
    ROOT / "AGENTS.md",
    ROOT / "README.md",
    ROOT / "quwoquan_data" / "AGENTS.md",
    ROOT / "quwoquan_ops" / "AGENTS.md",
    ROOT / ".cursor" / "rules" / "07-ios-native-ux.mdc",
    ROOT / ".agents" / "skills" / "environment-ops" / "SKILL.md",
    ROOT / ".agents" / "skills" / "content-production" / "SKILL.md",
    ROOT / ".github" / "workflows" / "deploy-prod-auto.yml",
    ROOT / "specs" / "feature-tree" / "README.md",
    ROOT / "specs" / "feature-tree" / "runtime" / "runtime-test-pyramid" / "spec.md",
    ROOT / "specs" / "feature-tree" / "runtime" / "runtime-client-foundation" / "ios-native-page-enforcement" / "spec.md",
    ROOT / "quwoquan_ops" / "cli" / "stackctl.py",
)
RETIRED_TOKENS = ("gate" + "-full", "--" + "tier")
RETIRED_PROD_ENVIRONMENT_PATTERNS = (
    re.compile(r"--env-name\s+prod-gray"),
    re.compile(r"environment-smoke-prod-gray"),
)
def main() -> int:
    issues: list[str] = []
    for path in ACTIVE_PATHS:
        text = path.read_text(encoding="utf-8")
        for token in RETIRED_TOKENS:
            if token in text:
                issues.append(f"retired entrypoint {token!r} remains in {path.relative_to(ROOT)}")
        if path.name == "Makefile":
            for pattern in RETIRED_PROD_ENVIRONMENT_PATTERNS:
                if pattern.search(text):
                    issues.append(
                        "production UAT must use env=prod plus rolloutStage, "
                        "not a prod-gray environment alias"
                    )
    if issues:
        print("[verify_execution_profiles] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_execution_profiles] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
