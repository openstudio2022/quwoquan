"""Source-drift boundary predicates for failed campaign reconciliation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def source_drift_successor(
    plan: Mapping[str, Any],
    report: Mapping[str, Any],
    runtime: Mapping[str, Any],
) -> bool:
    distributed = plan.get("distributedRun")
    if not isinstance(distributed, Mapping):
        return False
    failure = (
        "ValueError: campaign sourceDigest drift: "
        f"frozen={plan.get('sourceDigest')} current="
    )
    return (
        report.get("status") == "blocked"
        and report.get("phase") == "freeze"
        and report.get("planDigest") is None
        and report.get("sourceDigest") is None
        and report.get("entityCatalogDigest") is None
        and str(report.get("failure") or "").startswith(failure)
        and runtime.get("status") == "blocked"
        and runtime.get("phase") == "freeze"
        and runtime.get("planDigest") is None
        and runtime.get("lanes") == {}
        and bool(runtime.get("finishedAt"))
        and runtime.get("failure") == report.get("failure")
        and runtime.get("runId") == report.get("campaignRunId")
        and runtime.get("generation") == report.get("campaignGeneration")
        and runtime.get("fencingToken") == report.get("campaignFencingToken")
        and int(runtime.get("generation") or 0)
        == int(distributed.get("campaignGeneration") or 0) + 1
        and runtime.get("runId") != distributed.get("campaignRunId")
    )


__all__ = ["source_drift_successor"]
