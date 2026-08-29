#!/usr/bin/env python3
"""Verify canonical publish has no dangling or orphaned consumer objects."""
from __future__ import annotations

import sys
from pathlib import Path


sys.dont_write_bytecode = True

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_ROOT))

from content.release.canonical.object_transaction_audit import validate_publish_invariants
from content.release.canonical.creator_avatar_quality import (
    creator_avatar_quality_issues,
)
from core.paths import PUBLISH_ROOT
from verify.verify_publish_purity import publish_structure_issues


def main() -> int:
    report = validate_publish_invariants(PUBLISH_ROOT)
    creator_issues = creator_avatar_quality_issues(PUBLISH_ROOT)
    structure_issues = publish_structure_issues(PUBLISH_ROOT)
    issues = [*report["issues"], *creator_issues]
    if structure_issues or issues:
        print("[verify_publish_closure] FAIL")
        for issue in structure_issues:
            print(f"  - publish_structure: {issue}")
        for issue in issues:
            print(f"  - {issue['code']}: {issue['ref']}")
        return 1
    print(f"[verify_publish_closure] OK mediaRefs={report['mediaRefCount']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
