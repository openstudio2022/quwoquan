#!/usr/bin/env python3
"""Verify exception and recovery coverage is traceable."""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

from nonfunctional_coverage_lib import Failures, ROOT


def main() -> int:
    failures = Failures()
    failures.require_path(
        ROOT / "quwoquan_service" / "contracts" / "runtime_errors" / "errors" / "runtime_failure_codes.yaml",
        "runtime failure code contract",
    )
    failures.require_path(
        ROOT / "quwoquan_service" / "contracts" / "runtime_errors" / "errors" / "runtime_recovery_policy.schema.yaml",
        "runtime recovery policy contract",
    )
    failures.require_any_canonical_test(
        label="runtime error/recovery coverage",
        patterns=(
            r"runtime[_-]?failure",
            r"error[_-]?code",
            r"exception",
            r"recovery",
            r"permission",
            r"offline",
        ),
        minimum=3,
    )
    failures.require_any_canonical_test(
        label="api integration error boundary coverage",
        patterns=(r"/api_integration/.*error", r"RuntimeErrorResponse", r"requestId", r"traceId"),
        minimum=1,
    )
    return failures.exit_code("[verify] OK: runtime error coverage checked")


if __name__ == "__main__":
    raise SystemExit(main())
