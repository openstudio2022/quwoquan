#!/usr/bin/env python3
"""Keep canonical publish limited to approved consumer objects."""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_ROOT))

from core.paths import PUBLISH_ROOT
from content.release.canonical.object_transaction_audit import validate_publish_invariants


ALLOWED_ROOTS = {"creators", "entities", "posts", "tags", "media"}
FORBIDDEN_PARTS = {"sources", "draft", "drafts", "prompt", "prompts", "reports", "logs", "evidence", "receipt", "receipts", "review"}
FORBIDDEN_SUFFIXES = (".log", ".jsonl")


def publish_structure_issues(publish_root: Path = PUBLISH_ROOT) -> list[str]:
    issues: list[str] = []
    if not publish_root.exists():
        return issues
    for entry in sorted(publish_root.iterdir()):
        if entry.name not in ALLOWED_ROOTS:
            issues.append(f"{entry}: publish root only permits {', '.join(sorted(ALLOWED_ROOTS))}")
    media_root = publish_root / "media"
    if media_root.is_dir():
        for entry in sorted(media_root.iterdir()):
            if entry.name != "objects":
                issues.append(f"{entry}: publish/media only permits content-addressed objects")
    for path in sorted(publish_root.rglob("*")):
        parts = {part.casefold() for part in path.relative_to(publish_root).parts}
        if parts & FORBIDDEN_PARTS:
            issues.append(f"{path}: intermediate source/draft/evidence must not enter publish")
            continue
        if path.is_file() and path.name.casefold().endswith(FORBIDDEN_SUFFIXES):
            issues.append(f"{path}: logs are runtime evidence, not publish objects")
    return issues


def publish_purity_issues(publish_root: Path = PUBLISH_ROOT) -> list[str]:
    issues = publish_structure_issues(publish_root)
    closure = validate_publish_invariants(publish_root)
    for issue in closure["issues"]:
        code = issue.get("code", "closure")
        ref = issue.get("ref", "")
        issues.append(f"{publish_root}: canonical closure {code}: {ref}")
    return issues


def main() -> int:
    issues = publish_purity_issues()
    if issues:
        print("[verify_publish_purity] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_publish_purity] OK")
    return 0
