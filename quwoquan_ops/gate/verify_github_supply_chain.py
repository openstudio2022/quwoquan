#!/usr/bin/env python3
"""阻断浮动 GitHub Action 引用和缺失的关键 CODEOWNERS 规则。"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
CODEOWNERS = ROOT / ".github" / "CODEOWNERS"
USES_PATTERN = re.compile(r"^\s*(?:-\s*)?uses:\s*([^\s#]+)", re.MULTILINE)
PINNED_ACTION_PATTERN = re.compile(r"^[^/@\s]+/[^@\s]+(?:/[^@\s]+)*@[0-9a-f]{40}$")
REQUIRED_CODEOWNER_PATHS = {
    "*",
    "/.github/workflows/",
    "/quwoquan_ops/",
    "/quwoquan_service/contracts/metadata/",
    "/specs/feature-tree/platform-ops-governance/",
}


def verify_action_pins() -> list[str]:
    failures: list[str] = []
    for path in sorted([*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")]):
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        try:
            permissions_index = lines.index("permissions:")
        except ValueError:
            failures.append(
                f"{path.relative_to(ROOT)}: top-level permissions must default to contents: read"
            )
        else:
            permission_block: list[str] = []
            for line in lines[permissions_index + 1 :]:
                if line and not line.startswith((" ", "\t")):
                    break
                permission_block.append(line.strip())
            if "contents: read" not in permission_block:
                failures.append(
                    f"{path.relative_to(ROOT)}: top-level permissions must include contents: read"
                )
            if any(item == "write-all" or item.endswith(": write") for item in permission_block):
                failures.append(
                    f"{path.relative_to(ROOT)}: write permissions belong on the minimum required job, not workflow scope"
                )
        for match in USES_PATTERN.finditer(text):
            reference = match.group(1)
            if reference.startswith("./") or reference.startswith("docker://"):
                continue
            if not PINNED_ACTION_PATTERN.fullmatch(reference):
                line = text.count("\n", 0, match.start()) + 1
                failures.append(
                    f"{path.relative_to(ROOT)}:{line}: third-party action must use a full 40-character commit SHA: {reference}"
                )
    return failures


def verify_production_execution_isolation() -> list[str]:
    failures: list[str] = []
    deploy_paths = {
        WORKFLOWS / "deploy-prod-auto.yml",
        WORKFLOWS / "deploy-prod-gray.yml",
    }
    for path in sorted([*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")]):
        text = path.read_text(encoding="utf-8")
        if path in deploy_paths:
            for token in (
                "runs-on: [self-hosted, macOS, prod-release]",
                "environment: production",
                "verify_release_governance.py",
                "governance-receipt.json",
                "pull-requests: read",
            ):
                if token not in text:
                    failures.append(
                        f"{path.relative_to(ROOT)} missing production isolation control: {token}"
                    )
        elif "prod-release" in text:
            failures.append(
                f"{path.relative_to(ROOT)} must not target the dedicated prod-release runner"
            )
    return failures


def verify_codeowners() -> list[str]:
    if not CODEOWNERS.is_file():
        return [".github/CODEOWNERS is required"]
    declared: set[str] = set()
    for raw_line in CODEOWNERS.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2 or not all(owner.startswith("@") for owner in parts[1:]):
            return [f".github/CODEOWNERS has an invalid rule: {raw_line}"]
        declared.add(parts[0])
    missing = sorted(REQUIRED_CODEOWNER_PATHS - declared)
    return [f".github/CODEOWNERS missing critical path rule: {path}" for path in missing]


def main() -> int:
    failures = [
        *verify_action_pins(),
        *verify_codeowners(),
        *verify_production_execution_isolation(),
    ]
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("OK: GitHub Actions are immutable and critical paths have CODEOWNERS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
