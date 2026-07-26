#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = ROOT / "quwoquan_data"
ALLOWED_SCHEMA_DIRECTORIES = {
    "_common",
    "content",
    "execution",
    "governance",
    "publish",
    "release",
    "source",
}

FORBIDDEN_EXISTING_DIRS = {
    ".venv",
    "data",
    "scripts/migration",
    "scripts/_scratch",
    "scripts/ops",
    "scripts/verify/audit",
    "publish/user_media",
}

FORBIDDEN_EXISTING_FILES = {
    "scripts/ops/ship_all_environments.sh",
}

FORBIDDEN_TRACKED_SEGMENTS = (
    "/.venv/",
    "/__pycache__/",
    "/.pytest_cache/",
)
FORBIDDEN_GENERATED_DIRECTORY_NAMES = {
    ".qwq_output",
    "__pycache__",
    ".pytest_cache",
    ".venv",
}


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
    for path in sorted(DATA_ROOT.rglob("*")):
        if path.is_dir() and path.name in FORBIDDEN_GENERATED_DIRECTORY_NAMES:
            issues.append(f"{_rel(path)}: generated/cache directory must not exist in source tree")
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
    schema_root = DATA_ROOT / "schema"
    schema_directories = {
        path.name for path in schema_root.iterdir() if path.is_dir()
    }
    if schema_directories != ALLOWED_SCHEMA_DIRECTORIES:
        issues.append(
            f"{_rel(schema_root)}: schema directories must equal "
            f"{sorted(ALLOWED_SCHEMA_DIRECTORIES)}, got {sorted(schema_directories)}"
        )
    cli_path = DATA_ROOT / "scripts/cli.py"
    cli_source = cli_path.read_text(encoding="utf-8")
    if re.search(
        r"(?:from\s+migration\b|reg_migration\b|add_parser\(\s*['\"]migration['\"])",
        cli_source,
    ):
        issues.append(
            f"{_rel(cli_path)}: retired top-level migration command must not be registered"
        )
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


if __name__ == "__main__":
    raise SystemExit(main())
