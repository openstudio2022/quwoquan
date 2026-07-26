#!/usr/bin/env python3
"""Reject retired task/batch identities from active data-engineering code."""
from __future__ import annotations

import re
import sys
from pathlib import Path


SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SCRIPTS_ROOT.parent.parent
ACTIVE_TEXT_ROOTS = (
    REPO_ROOT / ".cursor" / "rules",
    REPO_ROOT / ".cursor" / "commands",
    REPO_ROOT / "specs" / "feature-tree" / "runtime" / "runtime-data-engineering",
)
FORBIDDEN = (
    re.compile(r"\btaskId\b"),
    re.compile(r"\bbatchId\b"),
    re.compile(r"\btask_root\b"),
    re.compile(r"\bbatch_root\b"),
    re.compile(r"\btask\s*:\s*(?:str|Path)\b"),
    re.compile(r"\bbatch\s*:\s*(?:str|Path)\b"),
    re.compile(r"\bTASKS_ROOT\b"),
    re.compile(r"\bQWQ_BATCH_"),
    re.compile(r"--task\b"),
    re.compile(r"--batch\b"),
    re.compile(r"\bargs\.task\b"),
    re.compile(r"\bargs\.batch\b"),
    re.compile(r"\bbatch_size\b"),
    re.compile(r"\bminBatchCompletionMode\b"),
    re.compile(r"\bmin_batch_completion_mode\b"),
)


def execution_identity_purity_issues() -> list[str]:
    issues: list[str] = []
    paths = [
        path
        for path in SCRIPTS_ROOT.rglob("*.py")
        if "verify" not in path.relative_to(SCRIPTS_ROOT).parts
    ]
    for root in ACTIVE_TEXT_ROOTS:
        if root.is_dir():
            paths.extend(
                path
                for path in root.rglob("*")
                if path.is_file() and path.suffix in {".md", ".mdc", ".yaml", ".yml"}
            )
    for path in sorted(set(paths)):
        if "__pycache__" in path.parts or path == Path(__file__).resolve():
            continue
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for pattern in FORBIDDEN:
                if pattern.search(line):
                    issues.append(
                        f"{path.relative_to(REPO_ROOT)}:{line_number}: retired execution identity '{pattern.pattern}'"
                    )
                    break
    return issues


def main() -> int:
    issues = execution_identity_purity_issues()
    if issues:
        print("[verify_execution_identity_purity] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_execution_identity_purity] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
