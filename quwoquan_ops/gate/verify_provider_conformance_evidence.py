#!/usr/bin/env python3
"""Validate every emitted Provider Conformance evidence artifact."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.provider_conformance import (
    READINESS_ENVIRONMENTS,
    load_validate_and_derive,
    readiness_issues,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Provider Conformance evidence and, when requested, release readiness."
    )
    parser.add_argument("--require-ready", choices=READINESS_ENVIRONMENTS)
    args = parser.parse_args()
    report, issues = load_validate_and_derive()
    if args.require_ready:
        issues.extend(readiness_issues(report, environment=args.require_ready))
    if issues:
        print("[verify_provider_conformance_evidence] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    if report["evidenceCount"] == 0:
        print(
            "[verify_provider_conformance_evidence] NO_EVIDENCE "
            "(validation only; release readiness was not requested)"
        )
    else:
        print(
            "[verify_provider_conformance_evidence] OK "
            f"({report['evidenceCount']} evidence artifacts)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
