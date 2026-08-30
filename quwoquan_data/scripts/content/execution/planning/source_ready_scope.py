"""Project absorbed source-ready coverage without mutating the freeze.

The immutable execution spec keeps the full oversampled candidate pool. After
``download_fetch`` persists ``source_unavailable_targets.json`` and absorbs the
ineligible object-level shortfall rows, every carrier's downstream stages may
author only the audited ready subset. ``approvedQuota`` remains a scale
milestone; it never widens the runtime scope back to source-unavailable objects.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from core.io import read_json
from core.paths import execution_root


def source_ready_runtime_spec(
    execution_id: str,
    spec: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Return a deepcopy of ``spec`` narrowed to absorbed ready targets when eligible."""
    runtime_spec = deepcopy(dict(spec or {}))
    quotas = (
        (runtime_spec.get("content") or {}).get("quotas")
        if isinstance(runtime_spec.get("content"), Mapping)
        else {}
    )
    absorbable_quota = (
        int((quotas or {}).get("entityArticlesPerTarget") or 0)
        + int((quotas or {}).get("entityArticles") or 0)
        + int((quotas or {}).get("imageWorksPerTarget") or 0)
        + int((quotas or {}).get("videoWorksPerTarget") or 0)
        + int((quotas or {}).get("entityHomepagesPerTarget") or 0)
    )
    if absorbable_quota <= 0:
        return runtime_spec

    availability_path = (
        execution_root(execution_id) / "_shared" / "source_unavailable_targets.json"
    )
    if not availability_path.is_file():
        return runtime_spec
    availability = read_json(availability_path)
    if not isinstance(availability, dict):
        raise ValueError("source availability must be an object")
    if str(availability.get("executionId") or "") != execution_id:
        raise ValueError("source availability executionId mismatch")

    scope = runtime_spec.get("scope")
    targets = scope.get("coverageTargets") if isinstance(scope, dict) else None
    if not isinstance(targets, list):
        raise ValueError("execution scope.coverageTargets must be an array")
    frozen_names = [str(target.get("name") or "").strip() for target in targets]
    if not frozen_names or any(not name for name in frozen_names):
        raise ValueError("frozen coverageTargets must have names")
    if len(frozen_names) != len(set(frozen_names)):
        raise ValueError("frozen coverageTargets must have unique names")

    ready_targets = [
        str(name or "").strip() for name in (availability.get("readyTargets") or [])
    ]
    ineligible_targets = [
        str(row.get("entityId") or "").strip()
        for row in (availability.get("ineligibleTargets") or [])
        if isinstance(row, dict)
    ]
    if (
        any(not name for name in ready_targets)
        or any(not name for name in ineligible_targets)
        or len(ready_targets) != len(set(ready_targets))
        or len(ineligible_targets) != len(set(ineligible_targets))
    ):
        raise ValueError("source availability contains invalid target names")
    ready_count = availability.get("readyTargetCount")
    ineligible_count = availability.get("ineligibleTargetCount")
    if (
        isinstance(ready_count, bool)
        or not isinstance(ready_count, int)
        or ready_count != len(ready_targets)
    ):
        raise ValueError("source availability readyTargetCount mismatch")
    if (
        isinstance(ineligible_count, bool)
        or not isinstance(ineligible_count, int)
        or ineligible_count != len(ineligible_targets)
    ):
        raise ValueError("source availability ineligibleTargetCount mismatch")
    ready_set = set(ready_targets)
    ineligible_set = set(ineligible_targets)
    frozen_set = set(frozen_names)
    if ready_set & ineligible_set or ready_set | ineligible_set != frozen_set:
        raise ValueError(
            "source availability must partition the frozen target set"
        )

    policy = runtime_spec.get("executionPolicy")
    quota = int((policy or {}).get("approvedQuota") or 0)
    if quota < 1:
        raise ValueError("executionPolicy.approvedQuota must be positive")
    scope["coverageTargets"] = [
        target
        for target in targets
        if str(target.get("name") or "").strip() in ready_set
    ]
    content = runtime_spec.get("content")
    if isinstance(content, dict) and "workUnits" in content:
        raw_work_units = content.get("workUnits")
        if not isinstance(raw_work_units, list):
            raise ValueError("execution content.workUnits must be an array")
        work_units_by_id: dict[str, dict[str, Any]] = {}
        for raw in raw_work_units:
            if not isinstance(raw, Mapping):
                raise ValueError("execution content.workUnits must contain objects")
            work_unit_id = str(raw.get("workUnitId") or "").strip()
            target = raw.get("coverageTarget")
            target_name = (
                str(target.get("name") or "").strip()
                if isinstance(target, Mapping)
                else ""
            )
            if not work_unit_id or not target_name:
                raise ValueError("execution media workUnit identity is incomplete")
            if work_unit_id in work_units_by_id:
                raise ValueError("execution content.workUnits contains duplicate ids")
            if target_name in ready_set:
                work_units_by_id[work_unit_id] = dict(raw)

        raw_ready_work_unit_ids = availability.get("readyWorkUnitIds")
        if raw_ready_work_unit_ids is None:
            ready_work_unit_ids = list(work_units_by_id)
        else:
            if not isinstance(raw_ready_work_unit_ids, list):
                raise ValueError("source availability readyWorkUnitIds must be an array")
            ready_work_unit_ids = [
                str(value or "").strip() for value in raw_ready_work_unit_ids
            ]
            if (
                any(not value for value in ready_work_unit_ids)
                or len(ready_work_unit_ids) != len(set(ready_work_unit_ids))
                or any(value not in work_units_by_id for value in ready_work_unit_ids)
            ):
                raise ValueError(
                    "source availability readyWorkUnitIds must be a unique frozen subset"
                )
            ready_work_unit_count = availability.get("readyWorkUnitCount")
            if (
                isinstance(ready_work_unit_count, bool)
                or not isinstance(ready_work_unit_count, int)
                or ready_work_unit_count != len(ready_work_unit_ids)
            ):
                raise ValueError(
                    "source availability readyWorkUnitCount mismatch"
                )
        ready_work_units = [
            work_units_by_id[work_unit_id]
            for work_unit_id in ready_work_unit_ids
        ]
        content["workUnits"] = ready_work_units
        unit_target_names = {
            str((row.get("coverageTarget") or {}).get("name") or "").strip()
            for row in ready_work_units
        }
        scope["coverageTargets"] = [
            target
            for target in scope["coverageTargets"]
            if str(target.get("name") or "").strip() in unit_target_names
        ]
        policy = runtime_spec.get("executionPolicy")
        if not isinstance(policy, dict):
            raise ValueError("execution executionPolicy must be an object")
        policy["targetObjectCount"] = len(ready_work_units)
        policy["targetEntityCount"] = len(scope["coverageTargets"])
        acceptance = runtime_spec.get("acceptance")
        if not isinstance(acceptance, dict):
            raise ValueError("execution acceptance must be an object")
        acceptance["minEntities"] = len(scope["coverageTargets"])
        acceptance["minPostsPerEntity"] = 0
    return runtime_spec


__all__ = ["source_ready_runtime_spec"]
