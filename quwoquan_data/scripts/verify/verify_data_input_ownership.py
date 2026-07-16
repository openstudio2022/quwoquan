#!/usr/bin/env python3
"""Ensure reusable data inputs do not become province/date/run-specific recipes."""
from __future__ import annotations

import re
import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_ROOT))

from core.paths import REPO_ROOT


INPUT_ROOTS = (
    "quwoquan_data/control_plane/families",
    "quwoquan_data/prompts",
    "quwoquan_data/templates",
    "quwoquan_data/schema",
)
FORBIDDEN = (
    re.compile(r"20\d{6}--[a-z0-9-]+--"),
    re.compile(r"(?:executionId|executionId|executionId)\s*[:=]", re.IGNORECASE),
    re.compile(r"\.qwq_output/(?:data/tasks|data/releases)"),
)


def data_input_ownership_issues() -> list[str]:
    issues: list[str] = []
    for rel_root in INPUT_ROOTS:
        root = REPO_ROOT / rel_root
        if not root.is_dir():
            continue
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for pattern in FORBIDDEN:
                if pattern.search(text):
                    issues.append(f"{path.relative_to(REPO_ROOT)}: reusable input contains run-specific value '{pattern.pattern}'")
                    break
    return issues


def main() -> int:
    issues = data_input_ownership_issues()
    if issues:
        print("[verify_data_input_ownership] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_data_input_ownership] OK")
    return 0
