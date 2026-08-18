"""Frozen active-workload identity for campaign reconciliation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.execution.campaign.lane import (
    CAMPAIGN_CARRIERS,
    normalize_active_carriers,
    normalize_workloads,
)
from content.execution.identity import parse_execution_id


class CampaignSubmissionReconciliationError(ValueError):
    """Submission evidence is missing, mutable, or not terminal."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"GATE_BLOCK {code}: {detail}")
        self.code = code


def typed(code: str, detail: str) -> CampaignSubmissionReconciliationError:
    return CampaignSubmissionReconciliationError(
        f"DATA.CAMPAIGN.SUBMISSION_RECONCILIATION_{code}", detail
    )


def campaigns_root(output_root: Path) -> Path:
    return output_root / "data/local/workspace/content-campaign-submissions"


def campaign_root_for_submission(
    execution_id: str,
    *,
    output_root: Path,
) -> str | None:
    """Locate the immutable campaign owner without assuming a homepage root."""

    normalized = parse_execution_id(execution_id).execution_id
    matches = sorted(
        campaigns_root(output_root).glob(f"*/submissions/{normalized}.json")
    )
    if not matches:
        return None
    if len(matches) != 1:
        raise typed(
            "REFERENCE_DRIFT",
            f"execution {normalized} belongs to multiple campaign roots",
        )
    return matches[0].parent.parent.name


def frozen_submission_workload(
    submissions: Mapping[str, Mapping[str, Any]],
    *,
    root_execution_id: str | None = None,
) -> tuple[tuple[str, ...], dict[str, int], str]:
    """Resolve active carriers, quotas, and root from immutable submissions."""

    if not submissions or not set(submissions) <= set(CAMPAIGN_CARRIERS):
        raise typed("SUBMISSIONS_INCOMPLETE", "submission carriers are invalid")
    active_documents = {
        json.dumps(row.get("activeCarriers"), ensure_ascii=False)
        for row in submissions.values()
        if row.get("activeCarriers") is not None
    }
    workload_documents = {
        json.dumps(row.get("workloads"), ensure_ascii=False, sort_keys=True)
        for row in submissions.values()
        if row.get("workloads") is not None
    }
    has_current_shape = any(
        row.get("activeCarriers") is not None or row.get("workloads") is not None
        for row in submissions.values()
    )
    if has_current_shape:
        if len(active_documents) != 1 or len(workload_documents) != 1:
            raise typed("IDENTITY_DRIFT", "submission active workload drifted")
        active_raw = json.loads(next(iter(active_documents)))
        workloads_raw = json.loads(next(iter(workload_documents)))
        if not isinstance(active_raw, list) or not isinstance(workloads_raw, dict):
            raise typed("IDENTITY_DRIFT", "submission active workload is invalid")
        try:
            active = normalize_active_carriers(active_raw)
            workloads = normalize_workloads(
                workloads_raw,
                active_carriers=active,
            )
        except ValueError as exc:
            raise typed("IDENTITY_DRIFT", str(exc)) from exc
    else:
        # Terminal evidence created before the active-workload envelope was
        # frozen can only identify the former complete canonical preset.
        active = CAMPAIGN_CARRIERS
        legacy_quotas = {int(row.get("quota") or 0) for row in submissions.values()}
        if len(legacy_quotas) != 1 or next(iter(legacy_quotas)) < 1:
            raise typed("IDENTITY_DRIFT", "legacy submission quotas are invalid")
        legacy_quota = next(iter(legacy_quotas))
        workloads = {carrier: legacy_quota for carrier in active}

    roots = {str(row.get("rootExecutionId") or "") for row in submissions.values()}
    if len(roots) != 1 or not next(iter(roots)):
        raise typed("IDENTITY_DRIFT", "submission rootExecutionId drifted")
    frozen_root = next(iter(roots))
    if root_execution_id is not None and frozen_root != root_execution_id:
        raise typed("IDENTITY_DRIFT", "submission campaign root drift")
    if parse_execution_id(frozen_root).content_type.value != active[0]:
        raise typed(
            "IDENTITY_DRIFT",
            "campaign root must be the first active carrier submission",
        )
    if set(submissions) - set(active):
        raise typed("IDENTITY_DRIFT", "submission contains an inactive carrier")
    for carrier, row in submissions.items():
        if str(row.get("rootExecutionId") or "") != frozen_root:
            raise typed("IDENTITY_DRIFT", f"{carrier} submission root drift")
    return active, workloads, frozen_root


def frozen_plan_workload(
    plan: Mapping[str, Any],
    *,
    root_execution_id: str | None = None,
) -> tuple[tuple[str, ...], dict[str, int], dict[str, str], str]:
    """Resolve active carriers, quotas, ids, and root from one frozen plan."""

    execution_ids_raw = plan.get("executionIds")
    if not isinstance(execution_ids_raw, Mapping) or not execution_ids_raw:
        raise typed("IDENTITY_DRIFT", "campaign plan executionIds are missing")
    active_raw = plan.get("activeCarriers")
    try:
        active = normalize_active_carriers(
            active_raw if isinstance(active_raw, list) else execution_ids_raw.keys()
        )
    except ValueError as exc:
        raise typed("IDENTITY_DRIFT", str(exc)) from exc
    if set(execution_ids_raw) != set(active):
        raise typed("IDENTITY_DRIFT", "campaign plan executionIds drifted")
    execution_ids = {
        carrier: str(execution_ids_raw[carrier] or "") for carrier in active
    }
    if any(not value for value in execution_ids.values()):
        raise typed("IDENTITY_DRIFT", "campaign plan executionId is invalid")
    workloads_raw = plan.get("workloads")
    if isinstance(workloads_raw, Mapping):
        try:
            workloads = normalize_workloads(
                workloads_raw,
                active_carriers=active,
            )
        except ValueError as exc:
            raise typed("IDENTITY_DRIFT", str(exc)) from exc
    else:
        workloads = {}
    frozen_root = str(plan.get("rootExecutionId") or "")
    if root_execution_id is not None and frozen_root != root_execution_id:
        raise typed("IDENTITY_DRIFT", "campaign plan rootExecutionId drifted")
    if execution_ids[active[0]] != frozen_root:
        raise typed("IDENTITY_DRIFT", "campaign plan active root identity drifted")
    return active, workloads, execution_ids, frozen_root


__all__ = [
    "CampaignSubmissionReconciliationError",
    "campaign_root_for_submission",
    "campaigns_root",
    "frozen_plan_workload",
    "frozen_submission_workload",
    "typed",
]
