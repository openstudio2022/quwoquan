"""data explore — 发现任务候选实体并落 catalog。"""
from __future__ import annotations

import argparse
import sys

from core.command_packet import build_packet, write_packet
from core.io import write_ndjson
from content.execution.workspace import (
    ensure_execution_work_package_layout,
    execution_catalog_path,
    execution_explore_packet_path,
)
from content.source.discovery.gate import gate_explore
from content.execution import store


def _csv(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def _topic_rows(execution_id: str, regions: list[str], entity_types: list[str]) -> list[dict]:
    spec = store.load_spec(execution_id)
    scope = spec.get("scope") or {}
    task_region = str(scope.get("region") or "")
    task_entity_types = [str(v) for v in (scope.get("entityTypes") or []) if str(v)]
    allowed_regions = set(regions or [task_region]) if task_region else set(regions)
    allowed_entity_types = set(entity_types or task_entity_types) if task_entity_types else set(entity_types)
    rows: list[dict] = []
    seen: set[str] = set()
    for target in scope.get("coverageTargets") or []:
        if not isinstance(target, dict):
            continue
        name = str(target.get("name") or "").strip()
        entity_type = str(target.get("entityType") or "").strip()
        if not name or not entity_type:
            continue
        if allowed_entity_types and entity_type not in allowed_entity_types:
            continue
        topic_id = f"{entity_type}/{name}"
        if topic_id in seen:
            continue
        seen.add(topic_id)
        rows.append(
            {
                "topic_id": topic_id,
                "domain": entity_type.split("/", 1)[0] if "/" in entity_type else "",
                "entity_type": entity_type,
                "canonical_name": name,
                "region": task_region,
                "source_count": 1,
                # 收债 7：geo ref 只用行政区树路径制（coverageTargets 透传的 geoTagRef），无则留空。
                "geo_tag_ref": str(target.get("geoTagRef") or "").strip(),
                "source_kind": "coverageTarget",
                "status": "candidate",
                "executionId": execution_id,
            }
        )
    if allowed_regions and task_region and task_region not in allowed_regions:
        raise ValueError(f"execution region {task_region!r} not in requested regions {sorted(allowed_regions)!r}")
    return rows


def handle_explore(args: argparse.Namespace) -> None:
    """Freeze one execution's coverage targets as its candidate catalog."""
    execution_id = str(args.execution_id).strip()
    regions = _csv(getattr(args, "regions", None))
    entity_types = _csv(getattr(args, "entity_types", None))
    root = ensure_execution_work_package_layout(execution_id)
    spec = store.load_spec(execution_id)
    try:
        rows = _topic_rows(execution_id, regions, entity_types)
    except ValueError as exc:
        print(f"[explore] ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
    if not rows:
        print("[explore] ERROR: no candidate rows generated", file=sys.stderr)
        raise SystemExit(1)

    catalog_path = execution_catalog_path(execution_id)
    write_ndjson(catalog_path, rows)

    packet = build_packet(
        execution_id=execution_id,
        command="content execution explore",
        object_kind="execution",
        object_ref=execution_id,
        stage="explore",
        read_policy=[
            "content.yaml",
            "progress.json",
            "coverageTargets",
            "regions",
            "entityTypes",
        ],
        stop_if=[
            "execution spec missing",
            "coverageTargets empty",
            "regions/entityTypes mismatch",
            "catalog would be empty",
        ],
        output_policy=[
            "write only execution/_shared/catalog.ndjson",
            "write only execution/_shared/explore_packet.json",
        ],
        inputs={
            "executionSpecPath": str(root / "0.plan" / "execution_spec.yaml"),
            "progressPath": str(root / "_shared" / "execution_progress.json"),
            "regions": regions,
            "entityTypes": entity_types,
        },
        outputs={
            "catalogPath": str(catalog_path),
            "packetPath": str(execution_explore_packet_path(execution_id)),
        },
        handoff_to="content execution baseline",
        evidence={
            "required": ["catalog.ndjson"],
            "optional": ["explore_packet.json"],
        },
        summary={
            "catalogRowCount": len(rows),
            "coverageTargetCount": len((spec.get("scope") or {}).get("coverageTargets") or []),
            "executionRegion": str((spec.get("scope") or {}).get("region") or ""),
            "executionEntityTypes": [str(v) for v in (spec.get("scope") or {}).get("entityTypes") or [] if str(v)],
        },
    )
    write_packet(execution_explore_packet_path(execution_id), packet)
    issues = gate_explore(execution_id, expected_topic_ids=[row["topic_id"] for row in rows])
    print(f"[explore] executionId: {execution_id}")
    print(f"[explore] Regions: {regions or ['<execution scope>']}")
    print(f"[explore] Entity types: {entity_types or ['<execution scope>']}")
    print(f"[explore] Execution root: {root}")
    print(f"[explore] Wrote catalog: {catalog_path} ({len(rows)} rows)")
    print(f"[explore] Wrote packet: {execution_explore_packet_path(execution_id)}")
    if issues:
        print(f"[explore] FAILED ({len(issues)} issue(s))", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
        raise SystemExit(1)
    print("[explore] PASSED")
