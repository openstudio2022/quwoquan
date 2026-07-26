#!/usr/bin/env python3
"""Verify performance budgets are backed by specs and canonical tests."""

from __future__ import annotations

from nonfunctional_coverage_lib import Failures, FEATURE_TREE, ROOT


def main() -> int:
    failures = Failures()
    failures.require_path(ROOT / "quwoquan_service" / "contracts" / "metrics.md", "metrics contract")
    failures.require_path(ROOT / "quwoquan_ops" / "policies" / "gates" / "startup_ttid_ratchet_baseline.json", "startup performance baseline")
    failures.require_any_canonical_test(
        label="performance budget coverage",
        patterns=(r"performance", r"capacity", r"latency", r"p95", r"p99", r"budget"),
        minimum=2,
    )
    failures.require_any_text(
        label="performance acceptance points",
        roots=(FEATURE_TREE,),
        patterns=(r"performance_points", r"P95", r"P99", r"latency", r"jank"),
    )
    return failures.exit_code("[verify] OK: performance budget coverage checked")


if __name__ == "__main__":
    raise SystemExit(main())
