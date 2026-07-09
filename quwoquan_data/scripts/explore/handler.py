"""data explore — 发现任务候选实体并落 catalog。"""
from __future__ import annotations

import argparse
import sys

from _common.command_packet import build_packet, write_packet
from _common.io import write_ndjson
from _common.paths import (
    ensure_task_layout,
    task_catalog,
    task_explore_packet_path,
)
from explore.gate import gate_explore
from task import store


def _csv(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def _topic_rows(task_id: str, regions: list[str], entity_types: list[str]) -> list[dict]:
    spec = store.load_spec(task_id)
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
                "taskId": task_id,
            }
        )
    if allowed_regions and task_region and task_region not in allowed_regions:
        raise ValueError(f"task region {task_region!r} not in requested regions {sorted(allowed_regions)!r}")
    return rows


def handle_explore(args: argparse.Namespace) -> None:
    """把任务 coverageTargets 冻成候选 catalog，并生成 explore packet。"""
    task_id = str(args.task).strip()
    regions = _csv(getattr(args, "regions", None))
    entity_types = _csv(getattr(args, "entity_types", None))
    root = ensure_task_layout(task_id)
    spec = store.load_spec(task_id)
    try:
        rows = _topic_rows(task_id, regions, entity_types)
    except ValueError as exc:
        print(f"[explore] ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
    if not rows:
        print("[explore] ERROR: no candidate rows generated", file=sys.stderr)
        raise SystemExit(1)

    catalog_path = task_catalog(task_id)
    write_ndjson(catalog_path, rows)

    packet = build_packet(
        task_id=task_id,
        command="data explore",
        object_kind="task",
        object_ref=task_id,
        stage="explore",
        read_policy=[
            "task.yaml",
            "progress.json",
            "coverageTargets",
            "regions",
            "entityTypes",
        ],
        stop_if=[
            "task spec missing",
            "coverageTargets empty",
            "regions/entityTypes mismatch",
            "catalog would be empty",
        ],
        output_policy=[
            "write only task/catalog.ndjson",
            "write only task/_shared/explore_packet.json",
        ],
        inputs={
            "taskSpecPath": str(root / "task.yaml"),
            "progressPath": str(root / "progress.json"),
            "regions": regions,
            "entityTypes": entity_types,
        },
        outputs={
            "catalogPath": str(catalog_path),
            "packetPath": str(task_explore_packet_path(task_id)),
        },
        handoff_to="data baseline",
        evidence={
            "required": ["catalog.ndjson"],
            "optional": ["explore_packet.json"],
        },
        summary={
            "catalogRowCount": len(rows),
            "coverageTargetCount": len((spec.get("scope") or {}).get("coverageTargets") or []),
            "taskRegion": str((spec.get("scope") or {}).get("region") or ""),
            "taskEntityTypes": [str(v) for v in (spec.get("scope") or {}).get("entityTypes") or [] if str(v)],
        },
    )
    write_packet(task_explore_packet_path(task_id), packet)
    issues = gate_explore(task_id, expected_topic_ids=[row["topic_id"] for row in rows])
    print(f"[explore] Task: {task_id}")
    print(f"[explore] Regions: {regions or ['<task scope>']}")
    print(f"[explore] Entity types: {entity_types or ['<task scope>']}")
    print(f"[explore] Task root: {root}")
    print(f"[explore] Wrote catalog: {catalog_path} ({len(rows)} rows)")
    print(f"[explore] Wrote packet: {task_explore_packet_path(task_id)}")
    if issues:
        print(f"[explore] FAILED ({len(issues)} issue(s))", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
        raise SystemExit(1)
    print("[explore] PASSED")


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("explore", help="Discover POI candidates for a region")
    p.add_argument("--task", required=True, help="Task ID")
    p.add_argument("--regions", required=True, help="Comma-separated target regions")
    p.add_argument("--entity-types", required=True, help="Comma-separated entity types")
    p.set_defaults(handler=handle_explore)
