"""冻结 source-pool 目标的选择校验与治理地理元数据回联（拆分自 scale_source_pool_runtime）。"""
from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.source.research.scale_source_pool_runtime_blockers import _fail


def select_frozen_source_pool_targets(
    *,
    targets: tuple[dict[str, Any], ...],
    requested_limit: int,
    approved_quota: int,
    target_names: tuple[str, ...],
    discovery_path: Path,
    pool_binding: Mapping[str, Any],
    lane_selection: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Validate request cardinality and emit the immutable selection receipt."""

    rows = _enrich_frozen_targets_from_discovery(
        targets,
        discovery_path=discovery_path,
    )
    selected_names = tuple(sorted(str(row.get("name") or "") for row in rows))
    requested_names = tuple(sorted(target_names))
    expected_count = int(lane_selection.get("candidateCount") or 0)
    if (
        len(rows) != requested_limit
        or len(rows) != expected_count
        or approved_quota > len(rows)
        or (requested_names and requested_names != selected_names)
    ):
        raise _fail(
            "frozen source-pool targets do not match count/quota/requested target names"
        )
    return rows, {
        "discoveryPath": str(discovery_path),
        "selectionAuthority": "frozen_scale_source_pool",
        "sourcePoolPlanDigest": pool_binding["planDigest"],
        "sourcePoolSelectionDigest": lane_selection["selectionDigest"],
        "selectedCount": len(rows),
        "quota": approved_quota,
    }


def _enrich_frozen_targets_from_discovery(
    targets: tuple[dict[str, Any], ...],
    *,
    discovery_path: Path,
) -> list[dict[str, Any]]:
    """Join exact source-pool identities back to governed geography metadata.

    Source-pool candidates deliberately carry the canonical entity identity and
    source evidence, while the execution spec owns ``geoTagRef`` and taxonomy
    fields needed by qualification/materialization.  The join is exact on
    canonical name + entity type and fails closed on missing or ambiguous rows;
    it never performs network discovery or changes the frozen candidate order.
    """

    from governance.coverage.admin_entity_catalog import admin_entity_partitions

    from content.execution.planning.selection_discovery import (
        apply_master_list_fields,
        leaf_selection_name,
        load_partitions,
    )

    def exact_text(value: object) -> str:
        return unicodedata.normalize("NFKC", str(value or "")).strip()

    by_identity: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    if any(str(row.get("entityType") or "").strip() != "地点/城市" for row in targets):
        for partition in load_partitions(discovery_path):
            for leaf in partition.get("leaves") or []:
                if not isinstance(leaf, Mapping):
                    continue
                name = exact_text(leaf_selection_name(leaf))
                entity_type = exact_text(leaf.get("entityType"))
                if name and entity_type:
                    by_identity.setdefault((entity_type, name), []).append(leaf)

    admin_by_identity: dict[tuple[str, str, str], list[Mapping[str, Any]]] = {}
    if any(str(row.get("entityType") or "").strip() == "地点/城市" for row in targets):
        for partition in admin_entity_partitions():
            for leaf in partition.get("leaves") or []:
                if not isinstance(leaf, Mapping):
                    continue
                identity = (
                    exact_text(leaf.get("entityType")),
                    exact_text(leaf_selection_name(leaf)),
                    exact_text(leaf.get("canonicalEntityRef")),
                )
                if all(identity):
                    admin_by_identity.setdefault(identity, []).append(leaf)

    enriched: list[dict[str, Any]] = []
    for target in targets:
        row = dict(target)
        identity = (
            exact_text(row.get("entityType")),
            exact_text(row.get("name")),
        )
        if identity[0] == "地点/城市":
            canonical_ref = exact_text(row.get("canonicalEntityRef"))
            matches = admin_by_identity.get((*identity, canonical_ref), [])
            authority = "admin"
        else:
            matches = by_identity.get(identity, [])
            authority = "discovery"
        if len(matches) != 1:
            reason = "missing" if not matches else "ambiguous"
            raise _fail(
                f"{reason} governed {authority} target for "
                f"{identity[0]}/{identity[1]}"
            )
        enriched.append(apply_master_list_fields(row, matches[0]))
    return enriched
