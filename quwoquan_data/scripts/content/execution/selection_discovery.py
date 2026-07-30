"""Region reference parsing shared by target selection.

主清单目录 / 单文件 / decompose discovery JSON 三种输入统一投影成同构 partition，
再由 selection 决定候选池顺序。这里只做解析与字段透传，不做配额或过采判定。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

from core.control_types import TargetSelector
from core.io import read_json
from content.source.contracts import QualifiedHomepageSource
from governance.coverage.admin_entity_catalog import (
    ADMIN_REGION_REFERENCE_PATH,
    admin_entity_partitions,
)
from governance.coverage.master_list import leaf_coordinates

# 主清单 leaf → coverageTarget 契约字段透传集（task_spec.schema.json coverageTargets 同口径）。
_MASTER_LIST_LIST_FIELDS = ("geoTagRefs", "typeTagRefs", "aliases")


def _master_list_file_partitions(path: Path) -> list[dict[str, Any]]:
    """单个主清单市州文件（discovery_seed/2）→ 区县分区列表。"""
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, Mapping):
        raise ValueError(f"{path}: 主清单文件顶层必须是 mapping")
    partitions: list[dict[str, Any]] = []
    for group in data.get("districts") or []:
        if not isinstance(group, Mapping):
            continue
        district = str(group.get("district") or "").strip()
        leaves = [leaf for leaf in (group.get("leaves") or []) if isinstance(leaf, Mapping)]
        if district and leaves:
            partitions.append({"key": district, "leaves": leaves})
    return partitions


def _master_list_partitions(root: Path) -> list[dict[str, Any]]:
    """walk 主清单目录：区县分组映射为 partition，与 decompose discovery JSON partitions 同构。"""
    partitions: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.yaml")):
        partitions.extend(_master_list_file_partitions(path))
    if not partitions:
        raise ValueError(f"{root}: 主清单目录未发现任何区县分组（districts/leaves）")
    return partitions


def load_partitions(path: Path) -> list[dict[str, Any]]:
    if path.is_dir():
        return _master_list_partitions(path)
    if path.suffix in {".yaml", ".yml"}:
        # 市州级主清单单文件允许执行请求精确圈定一个市州。
        partitions = _master_list_file_partitions(path)
        if not partitions:
            raise ValueError(f"{path}: 主清单文件未发现任何区县分组（districts/leaves）")
        return partitions
    if path.resolve() == ADMIN_REGION_REFERENCE_PATH.resolve():
        # 全国行政实体无需物化 3000+ YAML；直接消费 pca + taxonomy 的只读投影。
        return admin_entity_partitions(pca_path=path)
    data = read_json(path)
    rows = data.get("partitions") if isinstance(data, dict) else []
    if not isinstance(rows, list):
        raise ValueError(f"{path}: partitions must be an array")
    return [row for row in rows if isinstance(row, dict)]


def apply_master_list_fields(row: dict[str, Any], leaf: Mapping[str, Any]) -> dict[str, Any]:
    geo_tag_ref = str(leaf.get("geoTagRef") or "").strip()
    if geo_tag_ref:
        row["geoTagRef"] = geo_tag_ref
    # coordinates 是 Homepage.location（2dsphere / filters.near）的唯一上游；
    # 解析口径由 master_list.leaf_coordinates 独占，这里只做透传。
    coordinates = leaf_coordinates(dict(leaf))
    if coordinates is not None:
        row["coordinates"] = coordinates
    for list_field in _MASTER_LIST_LIST_FIELDS:
        values = [str(v).strip() for v in (leaf.get(list_field) or []) if str(v).strip()]
        if list_field == "aliases":
            source_name = str(leaf.get("name") or "").strip()
            canonical_name = str(leaf.get("canonicalName") or source_name).strip()
            if source_name and source_name != canonical_name and source_name not in values:
                values.insert(0, source_name)
        if values:
            row[list_field] = values
    return row


def coverage_target_from_selection(row: Mapping[str, Any]) -> dict[str, Any]:
    """Project the one runtime qualification binding into the frozen spec."""

    target = apply_master_list_fields(
        {"entityType": row["entityType"], "name": row["name"]},
        row,
    )
    raw_source = row.get("qualifiedHomepageSource")
    if raw_source is not None:
        if not isinstance(raw_source, Mapping):
            raise TypeError("qualifiedHomepageSource must be an object")
        target["qualifiedHomepageSource"] = QualifiedHomepageSource.from_mapping(
            raw_source
        ).to_dict()
    return target


def leaf_selection_name(leaf: Mapping[str, Any]) -> str:
    source_name = str(leaf.get("name") or "").strip()
    return str(leaf.get("canonicalName") or source_name).strip()


def _leaf_selection_priority(leaf: Mapping[str, Any]) -> float | None:
    if "selectionPriority" not in leaf:
        return None
    try:
        return float(leaf.get("selectionPriority"))
    except (TypeError, ValueError):
        return None


def ordered_partition_leaves(
    part: Mapping[str, Any],
    *,
    target_selector: TargetSelector,
) -> list[Mapping[str, Any]]:
    leaves = [leaf for leaf in (part.get("leaves") or []) if isinstance(leaf, Mapping)]
    if target_selector is TargetSelector.ALL:
        return leaves
    if target_selector not in {
        TargetSelector.PRIORITY,
        TargetSelector.SOURCE_READY_PRIORITY,
    }:
        raise ValueError(f"unsupported target selector: {target_selector}")
    if not any(_leaf_selection_priority(leaf) is not None for leaf in leaves):
        return leaves
    return sorted(
        leaves,
        key=lambda leaf: (
            _leaf_selection_priority(leaf)
            if _leaf_selection_priority(leaf) is not None
            else float("inf"),
            leaf_selection_name(leaf),
        ),
    )


def partition_targets(
    partitions: Iterable[Mapping[str, Any]],
    *,
    target_selector: TargetSelector,
) -> dict[str, dict[str, Any]]:
    by_name: dict[str, dict[str, Any]] = {}
    for part in partitions:
        region = str(part.get("key") or "").strip()
        for leaf in ordered_partition_leaves(part, target_selector=target_selector):
            source_name = str(leaf.get("name") or "").strip()
            name = leaf_selection_name(leaf)
            etype = str(leaf.get("entityType") or "地点/景区").strip()
            if name and name not in by_name:
                by_name[name] = apply_master_list_fields(
                    {
                        "name": name,
                        "entityType": etype,
                        "region": region,
                        "sourceName": source_name,
                    },
                    leaf,
                )
    return by_name


__all__ = [
    "apply_master_list_fields",
    "coverage_target_from_selection",
    "leaf_selection_name",
    "load_partitions",
    "ordered_partition_leaves",
    "partition_targets",
]
