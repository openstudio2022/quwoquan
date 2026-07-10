#!/usr/bin/env python3
from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = ROOT / "quwoquan_data"

FORBIDDEN_EXISTING_DIRS = {
    "data",
    "scripts/_scratch",
    "scripts/ops",
}

FORBIDDEN_EXISTING_FILES = {
    "scripts/ops/ship_all_environments.sh",
}

FORBIDDEN_TRACKED_SEGMENTS = (
    "/.venv/",
    "/__pycache__/",
    "/.pytest_cache/",
)


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "quwoquan_data"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def data_layout_issues() -> list[str]:
    issues: list[str] = []
    for rel in sorted(FORBIDDEN_EXISTING_DIRS):
        path = DATA_ROOT / rel
        if path.exists():
            issues.append(f"{_rel(path)}: retired or ambiguous data-engineering directory")
    for rel in sorted(FORBIDDEN_EXISTING_FILES):
        path = DATA_ROOT / rel
        if path.exists():
            issues.append(f"{_rel(path)}: retired direct-run ops script; use qwq-data CLI")
    for tracked in _tracked_files():
        if any(segment in f"/{tracked}/" for segment in FORBIDDEN_TRACKED_SEGMENTS):
            issues.append(f"{tracked}: generated/cache Python output must not be tracked")
    return issues


def main() -> int:
    issues = data_layout_issues()
    if issues:
        print("[verify_data_layout] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_data_layout] OK")
    return 0
