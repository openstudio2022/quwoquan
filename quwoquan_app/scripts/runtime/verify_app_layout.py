#!/usr/bin/env python3
from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = ROOT / "quwoquan_app"

FORBIDDEN_EXISTING_PATHS = {
    ".cursor",
    "assistant",
    "personal_assistant",
    "node_modules",
    "package.json",
    "package-lock.json",
    "figma.config.json",
    "openspec-README.md",
    "scripts/find_team_files.js",
    "scripts/extract_figma_file_id.js",
    "scripts/quick_sync.sh",
    "scripts/run_figma_sync.sh",
    "scripts/setup_figma_config.sh",
    "scripts/sync_figma.js",
    "scripts/sync_figma.py",
    "scripts/sync_figma_enhanced.js",
}

FORBIDDEN_TRACKED_EXACT = {
    "quwoquan_app/android/local.properties",
}

FORBIDDEN_TRACKED_SEGMENTS = (
    "/.dart_tool/",
    "/.gradle/",
    "/.kotlin/",
    "/build/",
    "/node_modules/",
    "/ios/Pods/",
)


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "quwoquan_app"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def app_layout_issues() -> list[str]:
    issues: list[str] = []
    for rel in sorted(FORBIDDEN_EXISTING_PATHS):
        path = APP_ROOT / rel
        if path.exists():
            issues.append(f"{_rel(path)}: retired App-local tool/config path")

    for tracked in _tracked_files():
        if tracked in FORBIDDEN_TRACKED_EXACT:
            issues.append(f"{tracked}: local machine file must not be tracked")
        if any(segment in f"/{tracked}/" for segment in FORBIDDEN_TRACKED_SEGMENTS):
            issues.append(f"{tracked}: generated/cache dependency output must not be tracked")
    return issues


def main() -> int:
    issues = app_layout_issues()
    if issues:
        print("[verify_app_layout] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_app_layout] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
