#!/usr/bin/env python3
"""Verify canonical publish has no dangling or orphaned consumer objects."""
from __future__ import annotations

import sys
from pathlib import Path


SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_ROOT))

from content.release.canonical.object_transaction_audit import validate_canonical_publish
from content.release.canonical.creator_commercial_closure import (
    creator_commercial_closure_issues,
)
from core.paths import PUBLISH_ROOT


def main() -> int:
    report = validate_canonical_publish(PUBLISH_ROOT)
    creator_issues = creator_commercial_closure_issues(PUBLISH_ROOT)
    issues = [*report["issues"], *creator_issues]
    if issues:
        print("[verify_publish_closure] FAIL")
        for issue in issues:
            print(f"  - {issue['code']}: {issue['ref']}")
        return 1
    print(f"[verify_publish_closure] OK casObjects={report['casObjectCount']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
