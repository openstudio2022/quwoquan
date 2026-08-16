#!/usr/bin/env python3
"""Verify observability coverage is backed by contracts and canonical tests."""

from __future__ import annotations

import sys

from nonfunctional_coverage_lib import Failures, ROOT

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate.verify_observability_envelope import envelope_issues
from quwoquan_ops.gate.verify_observability_layout import (
    layout_issues,
    materialize_repo_gate_observability_run,
)


def main() -> int:
    materialize_repo_gate_observability_run()
    failures = Failures()
    failures.require_path(
        ROOT
        / "quwoquan_service"
        / "services"
        / "product-ops-service"
        / "contracts"
        / "product_ops"
        / "event_record"
        / "event_catalog.yaml",
        "telemetry event catalog",
    )
    failures.require_path(
        ROOT / "quwoquan_service" / "contracts" / "metadata" / "log_kv_policy.yaml",
        "log field policy",
    )
    failures.require_path(
        ROOT / "quwoquan_ops" / "observability" / "monitoring" / "alerts" / "quwoquan_alerts.yaml",
        "alert contract",
    )
    failures.require_any_canonical_test(
        label="observability coverage",
        patterns=(r"observability", r"telemetry", r"metric", r"log", r"trace", r"audit", r"event"),
        minimum=3,
    )
    for issue in layout_issues():
        failures.add(f"observability layout: {issue}")
    for issue in envelope_issues():
        failures.add(f"observability envelope: {issue}")
    return failures.exit_code("[verify] OK: observability coverage checked")


if __name__ == "__main__":
    raise SystemExit(main())
