"""Deterministic target selection for one frozen content execution."""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.control_types import TargetSelector
from governance.coverage.entity_diversity_ledger import EntityDiversityGate

from content.execution.planning.selection_discovery import (
    leaf_selection_name,
    load_partitions,
    ordered_partition_leaves,
    partition_targets,
    resolve_target_names,
)
from content.execution.planning.source_pursuit import pursue_qualified_target_pool
from content.execution.planning.source_selection import (
    TargetSourceQualifier,
    qualify_source_ready_targets,
    restrict_to_qualification_candidates,
)


def _pursuit_drives_qualification(
    *,
    persist_qualified_source: bool,
    target_names: tuple[str, ...],
    qualification_candidate_names: tuple[str, ...] | None,
) -> bool:
    """Whether this lane may replenish its candidate pool across rounds.

    Replenishment needs freedom to draw further candidates, which exists only on
    the persisting lane where ``quota`` is the delivery promise and no caller has
    pinned an exact name set. An explicitly pinned set is the request's own truth
    and must be graded exactly once, and on a non-persisting lane the frozen
    external receipt already fixes the supply.
    """

    return (
        persist_qualified_source
        and not tuple(name for name in target_names if name.strip())
        and qualification_candidate_names is None
    )


def _candidate_pool_exhausted(
    *,
    selected_count: int,
    quota: int,
    limit: int,
    discovery_path: Path,
) -> ValueError:
    return ValueError(
        f"候选池耗尽，区域实体供给不足：selected={selected_count} quota={quota} "
        f"candidatePool={limit} discovery={discovery_path}"
    )


def _matches_category(
    row: Mapping[str, Any],
    category: str | None,
) -> bool:
    """Match a declared selection category against a structured entity type."""
    requested = str(category or "").strip()
    if not requested:
        return True
    entity_type = str(row.get("entityType") or "").strip()
    if not entity_type:
        return False
    if entity_type == requested:
        return True
    return requested in {
        segment.strip()
        for segment in entity_type.split("/")
        if segment.strip()
    }


def select_targets(
    *,
    discovery_path: Path,
    limit: int,
    quota: int,
    target_selector: TargetSelector,
    source_qualifier: TargetSourceQualifier | None = None,
    qualification_source_key: str = "qualifiedHomepageSource",
    persist_qualified_source: bool = True,
    qualification_candidate_names: tuple[str, ...] | None = None,
    qualification_supply_count: int | None = None,
    target_names: tuple[str, ...] = (),
    category: str | None = None,
    inherit_frozen_targets: bool = False,
    inherited_targets: tuple[dict[str, Any], ...] = (),
    diversity_carriers: tuple[str, ...] = (),
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """Select up to ``limit`` candidates and require at least ``quota`` of them.

    ``limit`` is the oversampled candidate pool, not a delivery promise: objects
    that later fail a quality gate are discarded rather than retried, so the pool
    is intentionally larger than the approved quota.  Only falling below the
    quota is a selection failure.
    """
    if not isinstance(target_selector, TargetSelector):
        raise TypeError("target_selector must be TargetSelector")
    if isinstance(quota, bool) or not isinstance(quota, int) or quota < 1:
        raise ValueError("quota must be a positive integer")
    object_supply_mode = qualification_supply_count is not None
    if quota > limit and not object_supply_mode:
        raise ValueError(
            f"approved quota {quota} exceeds the candidate pool {limit}"
        )
    partitions = load_partitions(discovery_path)
    all_by_name = partition_targets(partitions, target_selector=target_selector)
    by_name = {
        name: row
        for name, row in all_by_name.items()
        if _matches_category(row, category)
    }
    selected: list[dict[str, str]] = []
    seen: set[str] = set()

    if target_selector is TargetSelector.SOURCE_READY_PRIORITY and source_qualifier is None:
        raise ValueError("source-ready-priority requires source_qualifier")
    if target_names:
        target_catalog = all_by_name if inherit_frozen_targets else by_name
        resolved_target_names = resolve_target_names(target_catalog, target_names)
        if (
            target_selector is not TargetSelector.SOURCE_READY_PRIORITY
            or inherit_frozen_targets
        ):
            if inherit_frozen_targets and target_selector is TargetSelector.SOURCE_READY_PRIORITY:
                # retryOf must keep the predecessor's exact candidate pool.
                # Re-probing Commons/Wikipedia here is unbounded and can reshape
                # the immutable retry set; download admission re-verifies rights.
                if source_qualifier is None:
                    raise ValueError("source-ready-priority requires source_qualifier")
            if inherited_targets:
                inherited_names = tuple(
                    str(row.get("name") or "").strip()
                    for row in inherited_targets
                )
                if inherited_names != resolved_target_names:
                    raise ValueError(
                        "inherited target rows must match the resolved canonical "
                        "target order exactly"
                    )
                selected = [dict(row) for row in inherited_targets]
            else:
                selected = [target_catalog[name] for name in resolved_target_names]
            report = {
                "schema": "quwoquan_data.target_selection",
                "strategy": (
                    "inherited frozen target order"
                    if inherit_frozen_targets
                    else "explicit frozen target order"
                ),
                "targetSelector": target_selector.value,
                "discoveryPath": str(discovery_path),
                "limit": limit,
                "approvedQuota": quota,
                "selectedCount": len(selected),
                "selectionShortfall": max(
                    0,
                    quota - (
                        qualification_supply_count
                        if qualification_supply_count is not None
                        else len(selected)
                    ),
                ),
                "targets": selected,
                "requestedTargetNames": list(target_names),
                "inheritedFrozenTargets": bool(inherit_frozen_targets),
            }
            if category:
                report["category"] = str(category).strip()
            if len(selected) < quota and (
                not object_supply_mode or not selected
            ):
                raise _candidate_pool_exhausted(
                    selected_count=len(selected),
                    quota=quota,
                    limit=limit,
                    discovery_path=discovery_path,
                )
            return selected, report

    def add(name: str) -> None:
        if name in seen or len(selected) >= limit:
            return
        row = by_name.get(name)
        if not row:
            return
        selected.append(row)
        seen.add(name)

    candidate_rows: list[dict[str, Any]] = []
    candidate_names: set[str] = set()
    depth = 0
    while True:
        scanned_any = False
        for part in partitions:
            leaves = ordered_partition_leaves(part, target_selector=target_selector)
            if depth >= len(leaves):
                continue
            scanned_any = True
            name = leaf_selection_name(leaves[depth])
            row = by_name.get(name)
            if row is not None and name not in candidate_names:
                candidate_rows.append(row)
                candidate_names.add(name)
        if not scanned_any:
            break
        depth += 1

    if target_selector is TargetSelector.SOURCE_READY_PRIORITY:
        assert source_qualifier is not None
        if _pursuit_drives_qualification(
            persist_qualified_source=persist_qualified_source,
            target_names=target_names,
            qualification_candidate_names=qualification_candidate_names,
        ):
            # Quota is a delivery promise on this lane and no explicit name set
            # pins the pool, so the open deficit may be replenished from later
            # slices of the ordered reference set instead of being reported as a
            # shortfall the moment one oversampled draw under-delivers.
            pool = pursue_qualified_target_pool(
                candidate_rows,
                quota=quota,
                discovery_ref=str(discovery_path),
                source_qualifier=source_qualifier,
                qualification_source_key=qualification_source_key,
                persist_qualified_source=persist_qualified_source,
                diversity_gate=(
                    EntityDiversityGate.for_carriers(diversity_carriers)
                    if diversity_carriers
                    else None
                ),
            )
            selected = list(pool.targets)
            source_qualification = pool.report()
            requested_target_names = ()
        else:
            selected, source_qualification, requested_target_names = (
                qualify_source_ready_targets(
                    candidate_rows,
                    discovery_ref=str(discovery_path),
                    limit=limit,
                    quota=quota,
                    source_qualifier=source_qualifier,
                    target_names=target_names,
                    qualification_source_key=qualification_source_key,
                    persist_qualified_source=persist_qualified_source,
                    qualification_candidate_names=qualification_candidate_names,
                    qualification_supply_count=qualification_supply_count,
                )
            )
    else:
        unmatched_qualification_names: tuple[str, ...] = ()
        scoped_candidate_rows = candidate_rows
        if qualification_candidate_names is not None:
            scoped_candidate_rows, unmatched_qualification_names = (
                restrict_to_qualification_candidates(
                    candidate_rows,
                    qualification_candidate_names,
                )
            )
        for row in scoped_candidate_rows:
            add(str(row["name"]))
            if len(selected) >= limit:
                break
    # 与 qualify_source_ready_targets 的非 persist 语义保持同一真相源：
    # persist lane（homepage）把 quota 当交付承诺的准入门；非 persist lane
    # （video 等）的真实供给由冻结外部输入 receipt 决定，qualification 只是
    # precheck，approvedQuota 是 scale milestone 而非 lane 级 veto。内层已对
    # persist 或零供给 fail-closed，这里不得对非 persist 的部分供给二次 veto。
    non_persist_source_ready = (
        target_selector is TargetSelector.SOURCE_READY_PRIORITY
        and not persist_qualified_source
    )
    if len(selected) < quota and (
        (not non_persist_source_ready and not object_supply_mode) or not selected
    ):
        raise _candidate_pool_exhausted(
            selected_count=len(selected),
            quota=quota,
            limit=limit,
            discovery_path=discovery_path,
        )
    report = {
        "schema": "quwoquan_data.target_selection",
        "strategy": "deterministic round-robin regional coverage",
        "targetSelector": target_selector.value,
        "discoveryPath": str(discovery_path),
        "limit": limit,
        "approvedQuota": quota,
        "selectedCount": len(selected),
        "selectionShortfall": max(
            0,
            quota - (
                qualification_supply_count
                if qualification_supply_count is not None
                else len(selected)
            ),
        ),
        "targets": selected,
    }
    if category:
        report["category"] = str(category).strip()
    if target_selector is TargetSelector.SOURCE_READY_PRIORITY:
        report["sourceQualification"] = source_qualification
        if requested_target_names:
            report["requestedTargetNames"] = list(requested_target_names)
    elif qualification_candidate_names is not None:
        report["sourceQualification"] = {
            "qualificationCandidateCount": len(qualification_candidate_names),
            "availableSupplyCount": qualification_supply_count,
            "supplyShortfallCount": max(
                0, quota - int(qualification_supply_count or 0)
            ),
            "unmatchedQualificationNames": list(unmatched_qualification_names),
        }
    return selected, report
