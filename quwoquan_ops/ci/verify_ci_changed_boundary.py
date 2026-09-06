#!/usr/bin/env python3
"""Verify changed candidate blobs for secret/PII and generated-boundary leaks."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.impact_planner_core import validate_delivery_impact_plan
from quwoquan_ops.cli.local_readiness import (
    LocalReadinessError,
    _PII_PATTERNS,
    _SECRET_PATTERNS,
    _staged_governance,
)


def _candidate_blob(source_sha: str, changed_path: str) -> bytes | None:
    proc = subprocess.run(
        ["git", "show", f"{source_sha}:{changed_path}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout


def verify(plan_path: Path, *, expected_source_sha: str, expected_tree_digest: str, expected_plan_digest: str) -> None:
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    plan = validate_delivery_impact_plan(
        payload,
        expected_source_sha=expected_source_sha,
        expected_tree_digest=expected_tree_digest,
    )
    if plan["plan_digest"] != expected_plan_digest:
        raise ValueError("impact plan digest differs from producer output")
    paths = list(plan["changed_paths"])
    _staged_governance(paths)
    for changed_path in paths:
        blob = _candidate_blob(expected_source_sha, changed_path)
        if blob is None:
            continue
        if any(pattern.search(blob) for pattern in _SECRET_PATTERNS):
            raise LocalReadinessError(
                f"changed candidate secret material detected: {changed_path}"
            )
        pii_matches = [
            match.group(0).decode("utf-8", errors="replace")
            for pattern in _PII_PATTERNS
            for match in pattern.finditer(blob)
        ]
        pii_matches = [
            value
            for value in pii_matches
            if not value.lower().endswith(
                ("@example.invalid", "@example.com", "@example.org")
            )
        ]
        if pii_matches:
            raise LocalReadinessError(
                f"changed candidate direct PII detected: {changed_path}"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--impact-plan", required=True, type=Path)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-tree-digest", required=True)
    parser.add_argument("--expected-plan-digest", required=True)
    args = parser.parse_args()
    try:
        verify(
            args.impact_plan,
            expected_source_sha=args.expected_source_sha,
            expected_tree_digest=args.expected_tree_digest,
            expected_plan_digest=args.expected_plan_digest,
        )
    except (OSError, ValueError, json.JSONDecodeError, LocalReadinessError) as error:
        print(f"verify_ci_changed_boundary: FAIL: {error}", file=sys.stderr)
        return 2
    print("verify_ci_changed_boundary: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
