#!/usr/bin/env python3
"""Reject one-off rollout facts in reusable Data engineering inputs."""
from __future__ import annotations

import re
import sys
from pathlib import Path

from core.paths import REPO_ROOT


_STATIC_ROOTS = (
    "quwoquan_data/control_plane",
    "quwoquan_data/verticals",
    "quwoquan_data/prompts",
    "quwoquan_data/templates",
    "quwoquan_data/schema",
    "quwoquan_data/AGENTS.md",
    "quwoquan_data/README.md",
    ".cursor/commands/crawl.md",
    ".cursor/commands/crawl-topic.md",
    ".cursor/skills/quwoquan-data-content/SKILL.md",
    "specs/feature-tree/discovery-content/object-homepage-coverage-scaling",
    "specs/feature-tree/runtime/runtime-data-engineering",
)
_REFERENCE_ROOT = "quwoquan_data/reference"
_FIXTURE_ROOT = "quwoquan_data/tests/support"
_FORBIDDEN = (
    re.compile(r"\b(?:two[_ -]?province|canary|m[1-3]|h10k)\b", re.IGNORECASE),
    re.compile(r"(?:浙江|四川|普陀山|东钱湖|海螺沟)"),
    re.compile(r"\b(?:922|1977|2899)\b"),
)
_SCALE_CATALOG_PATH = Path("quwoquan_data/control_plane/campaigns/scale_catalog.yaml")
_SCALE_CATALOG_FORBIDDEN = (
    re.compile(r"\b(?:two[_ -]?province|canary|h10k)\b", re.IGNORECASE),
    *_FORBIDDEN[1:],
)
_KNOWN_PROVIDER_KEY = re.compile(r"\bknown[A-Z][A-Za-z]*\s*:")
_PROVIDER_TASK_KEY = re.compile(
    r"^\s*(?:expectedCount|minimumLaneCounts|maturity)\s*:",
    re.MULTILINE,
)
_RUNTIME_REFERENCE = re.compile(
    r"(?:executionId|taskId|batchId|retryOf|targetSetDigest|reviewedAt|releaseId)\s*:",
    re.IGNORECASE,
)
_URL = re.compile(r"https?://", re.IGNORECASE)
_VERTICAL_POLICY_FILES = frozenset({"providers.yaml", "content_policy.yaml"})
_VERTICAL_RIGHTS_FILES = frozenset({"license_policy.yaml"})
def _readable_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    if not root.is_dir():
        return []
    return sorted(path for path in root.rglob("*") if path.is_file())


def _is_static_contract_file(path: Path) -> bool:
    relative = path.relative_to(REPO_ROOT)
    parts = relative.parts
    if "governance" in parts and "taxonomy" in parts:
        return False
    if len(parts) >= 3 and parts[0:2] == ("quwoquan_data", "verticals"):
        return path.name in {"providers.yaml", "content_policy.yaml", "license_policy.yaml"}
    return True


def _vertical_layout_issues() -> list[str]:
    issues: list[str] = []
    vertical_root = REPO_ROOT / "quwoquan_data/verticals"
    if not vertical_root.is_dir():
        return ["quwoquan_data/verticals: directory is missing"]
    for vertical_dir in sorted(path for path in vertical_root.iterdir() if path.is_dir()):
        for path in sorted(item for item in vertical_dir.rglob("*") if item.is_file()):
            relative = path.relative_to(vertical_dir)
            if len(relative.parts) == 1 and relative.name in _VERTICAL_POLICY_FILES:
                continue
            if (
                len(relative.parts) == 2
                and relative.parts[0] == "rights"
                and relative.name in _VERTICAL_RIGHTS_FILES
            ):
                continue
            issues.append(
                f"{path.relative_to(REPO_ROOT)}: verticals only own provider, content, and license policy files"
            )
    return issues


def reusable_data_contract_issues() -> list[str]:
    issues: list[str] = _vertical_layout_issues()
    for relative in _STATIC_ROOTS:
        for path in _readable_files(REPO_ROOT / relative):
            if not _is_static_contract_file(path):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            relative_path = path.relative_to(REPO_ROOT)
            forbidden_patterns = (
                _SCALE_CATALOG_FORBIDDEN
                if relative_path == _SCALE_CATALOG_PATH
                else _FORBIDDEN
            )
            for pattern in forbidden_patterns:
                if pattern.search(text):
                    issues.append(
                        f"{path.relative_to(REPO_ROOT)}: reusable contract contains task-specific value {pattern.pattern}"
                    )
                    break
            if path.name == "providers.yaml" and _KNOWN_PROVIDER_KEY.search(text):
                issues.append(
                    f"{path.relative_to(REPO_ROOT)}: provider policy must not contain known* task exceptions"
                )
            if path.name == "providers.yaml" and _PROVIDER_TASK_KEY.search(text):
                issues.append(
                    f"{path.relative_to(REPO_ROOT)}: provider policy must not contain rollout counts or maturity"
                )
    reference_root = REPO_ROOT / _REFERENCE_ROOT
    for path in _readable_files(reference_root):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if _RUNTIME_REFERENCE.search(text):
            issues.append(
                f"{path.relative_to(REPO_ROOT)}: reference contains runtime state or release conclusion"
            )
        if _URL.search(text):
            issues.append(
                f"{path.relative_to(REPO_ROOT)}: reference must not contain task source URLs"
            )
    for path in _readable_files(REPO_ROOT / _FIXTURE_ROOT):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in _FORBIDDEN:
            if pattern.search(text):
                issues.append(
                    f"{path.relative_to(REPO_ROOT)}: shared fixture contains production rollout value {pattern.pattern}"
                )
                break
    return issues


def main() -> int:
    issues = reusable_data_contract_issues()
    if issues:
        print("[verify_reusable_data_contract] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_reusable_data_contract] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
