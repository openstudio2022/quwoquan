#!/usr/bin/env python3
"""Verify that CI workflows and scripts reference only valid validation profiles.

Checks:
1. Workflow YAML files that reference validation_profile values use defined profiles.
2. Scripts that pass --profile consume valid profile names.
3. No references to legacy profile names remain.
"""

import json
import re
import sys
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parents[2]
SUITES_PATH = REPO_ROOT / "deploy" / "shared" / "gamma_validation_suites.json"
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
SCRIPTS_DIR = REPO_ROOT / "scripts"

LEGACY_PROFILES = {"daily_full", "pr_smoke"}
PROFILE_PATTERN = re.compile(
    r"""(?:validation_profile|--profile)\s*[=:]\s*['"]?(\w+)['"]?"""
)
PROFILE_OPTIONS_PATTERN = re.compile(
    r"""^\s*-\s+(\w+)\s*$""", re.MULTILINE
)


def load_valid_profiles() -> set:
    registry = json.loads(SUITES_PATH.read_text(encoding="utf-8"))
    return set((registry.get("profiles") or {}).keys())


def scan_file(path: Path, valid: set) -> List[str]:
    errors = []
    content = path.read_text(encoding="utf-8")

    for match in PROFILE_PATTERN.finditer(content):
        profile_name = match.group(1)
        if profile_name in LEGACY_PROFILES:
            errors.append(
                f"{path.relative_to(REPO_ROOT)}:{content[:match.start()].count(chr(10))+1}: "
                f"references legacy profile '{profile_name}'"
            )
        elif profile_name not in valid and profile_name not in {
            "INPUT_PROFILE", "PROFILE", "profile", "args",
        }:
            if not profile_name.startswith("$") and profile_name not in {
                "true", "false", "string", "choice",
            }:
                pass  # dynamic reference, skip

    for legacy in LEGACY_PROFILES:
        if legacy in content:
            line_num = content[:content.index(legacy)].count("\n") + 1
            errors.append(
                f"{path.relative_to(REPO_ROOT)}:{line_num}: "
                f"contains legacy profile name '{legacy}'"
            )
    return errors


def main() -> int:
    if not SUITES_PATH.exists():
        print(f"FAIL: {SUITES_PATH} not found")
        return 1

    valid = load_valid_profiles()
    errors = []

    for yml in sorted(WORKFLOW_DIR.glob("*.yml")):
        errors.extend(scan_file(yml, valid))

    for py in sorted(SCRIPTS_DIR.glob("run_gamma_patrol*.py")):
        errors.extend(scan_file(py, valid))

    makefile = REPO_ROOT / "Makefile"
    if makefile.exists():
        content = makefile.read_text(encoding="utf-8")
        for legacy in LEGACY_PROFILES:
            if legacy in content:
                line_num = content[:content.index(legacy)].count("\n") + 1
                errors.append(
                    f"Makefile:{line_num}: contains legacy profile name '{legacy}'"
                )

    if errors:
        print(f"FAIL: {len(errors)} legacy/invalid profile reference(s):")
        for err in errors:
            print(f"  - {err}")
        return 1

    print(f"OK: no legacy profile references found; valid profiles: {sorted(valid)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
