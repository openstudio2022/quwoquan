"""Exact immutable active-workload scope for campaign release selection."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from content.execution.planning.carrier_demand import (
    CAMPAIGN_CARRIERS,
    normalize_active_carriers,
    normalize_workloads,
)
from content.execution.planning.scale import campaign_workload_targets
from content.execution.identity import parse_execution_id
from core.source_digest import ExecutionBundleIdentity


def active_campaign_scope(
    plan: Mapping[str, Any],
    *,
    root_execution_id: str | None = None,
) -> tuple[tuple[str, ...], dict[str, int], dict[str, str]]:
    """Validate and return the carriers, quotas, and executions frozen by plan."""

    raw_active = plan.get("activeCarriers")
    raw_workloads = plan.get("workloads")
    raw_execution_ids = plan.get("executionIds")
    if not isinstance(raw_active, list) or not isinstance(raw_workloads, Mapping):
        raise ValueError("campaign plan active workload is missing")
    if not isinstance(raw_execution_ids, Mapping):
        raise ValueError("campaign plan executionIds are missing")
    active = normalize_active_carriers(raw_active)
    workloads = normalize_workloads(raw_workloads, active_carriers=active)
    if set(raw_execution_ids) != set(active):
        raise ValueError("campaign plan executionIds differ from active carriers")
    execution_ids = {
        carrier: str(raw_execution_ids[carrier] or "").strip()
        for carrier in active
    }
    if not all(execution_ids.values()) or len(set(execution_ids.values())) != len(active):
        raise ValueError("campaign plan active executionIds must be non-empty and unique")
    frozen_root = str(plan.get("rootExecutionId") or "").strip()
    if root_execution_id is not None and frozen_root != root_execution_id:
        raise ValueError("campaign plan rootExecutionId drifted")
    if execution_ids[active[0]] != frozen_root:
        raise ValueError("campaign root must be the first active carrier execution")

    root_identity = parse_execution_id(frozen_root)
    for carrier, execution_id in execution_ids.items():
        identity = parse_execution_id(execution_id)
        if (
            identity.execution_id != execution_id
            or identity.content_type.value != carrier
            or identity.vertical != root_identity.vertical
        ):
            raise ValueError(f"campaign {carrier} execution identity drifted")

    for field in ("laneExternalInputs", "submissionDigests"):
        value = plan.get(field)
        if not isinstance(value, Mapping) or set(value) != set(active):
            raise ValueError(f"campaign plan {field} differ from active carriers")
    ExecutionBundleIdentity.from_document(plan.get("executionBundle"))

    workload_mode = str(plan.get("workloadMode") or "")
    scale = str(plan.get("scale") or "")
    if workload_mode == "milestone_preset":
        expected = campaign_workload_targets(scale)
        if active != CAMPAIGN_CARRIERS or workloads != expected:
            raise ValueError("campaign milestone preset workload drifted")
    elif workload_mode != "explicit":
        raise ValueError("campaign workloadMode is invalid")
    return active, workloads, execution_ids


__all__ = ["active_campaign_scope"]
