#!/usr/bin/env python3
"""Credential contract: external 0600 key file, no repo secret or old alias."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_ROOT))

from core.cursor_credentials import cursor_key_file_issues
from core.paths import REPO_ROOT


RETIRED_ALIAS = "QWQ_CURSOR_API_KEY" + "FILE"


def cursor_credential_contract_issues(
    *,
    require_configured_file: bool = False,
    repo_root: Path = REPO_ROOT,
) -> list[str]:
    issues: list[str] = []
    if require_configured_file:
        issues.extend(cursor_key_file_issues())
    tracked = subprocess.run(
        ["git", "grep", "-n", "-I", "-e", RETIRED_ALIAS, "--", "."],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if tracked.stdout.strip():
        issues.extend(f"retired credential alias: {line}" for line in tracked.stdout.splitlines()[:20])
    return issues


def main() -> int:
    issues = cursor_credential_contract_issues(require_configured_file=False)
    if issues:
        print("[verify_cursor_credential_contract] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_cursor_credential_contract] OK")
    return 0
