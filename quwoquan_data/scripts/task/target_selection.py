"""Reusable multimodal target selection and batch audit helpers."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

from _common.io import read_json, write_json
from _common.paths import batch_root
from task import store


DEFAULT_MANDATORY = ["四姑娘山", "毕棚沟", "稻城亚丁", "海螺沟", "墨石公园"]
DEFAULT_SOURCE_TASK_ID = "旅行/地域/四川省/景区/景区精选"


def _split_csv(value: str | None) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _default_discovery_path(source_task_id: str) -> Path:
    return store.committed_task_root(source_task_id) / "discovery_sichuan_100e.json"


def _failed_object_entity(raw: Any) -> str:
    text = str(raw or "")
    match = re.match(r"^\s*([^:：]+)\s*[:：]", text)
    return match.group(1).strip() if match else ""


def _workflow_failure_lane(raw: Any) -> str:
    text = str(raw or "").casefold()
    if "article source unit" in text or "article base draft" in text:
        return "article"
    if "image research" in text or "image gate" in text or "image fetch" in text:
        return "image"
    if "homepage" in text or "entity homepage" in text:
        return "homepage"
    return "workflow"


def _workflow_failure_items(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    status = str(state.get("status") or "").strip()
    failed_objects = [str(item) for item in state.get("failedObjects") or [] if str(item).strip()]
    if status in ("", "succeeded"):
        return []
    items: list[dict[str, Any]] = []
    for raw in failed_objects:
        entity = _failed_object_entity(raw)
        items.append(
            {
                "entity": entity or "__batch__",
                "lane": _workflow_failure_lane(raw),
                "issues": [raw],
            }
        )
    if not items:
        items.append(
            {
                "entity": "__batch__",
                "lane": "workflow",
                "issues": [f"workflow status={status}"],
            }
        )
    return items


def _load_partitions(path: Path) -> list[dict[str, Any]]:
    data = read_json(path)
    rows = data.get("partitions") if isinstance(data, dict) else []
    if not isinstance(rows, list):
        raise ValueError(f"{path}: partitions must be an array")
    return [row for row in rows if isinstance(row, dict)]


def _partition_targets(partitions: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, str]]:
    by_name: dict[str, dict[str, str]] = {}
    for part in partitions:
        region = str(part.get("key") or "").strip()
        for leaf in part.get("leaves") or []:
            if not isinstance(leaf, Mapping):
                continue
            name = str(leaf.get("name") or "").strip()
            etype = str(leaf.get("entityType") or "地点/景区").strip()
            if name and name not in by_name:
                by_name[name] = {"name": name, "entityType": etype, "region": region}
    return by_name


def ineligible_targets_from_batch(task_id: str, batch_id: str) -> set[str]:
    """Extract unresolved target names from a managed batch state."""
    shared = batch_root(task_id, batch_id) / "_shared"
    out: set[str] = set()
    audit_path = shared / "managed_batch_audit.json"
    if audit_path.is_file():
        try:
            audit = read_json(audit_path)
        except (OSError, ValueError, TypeError):
            audit = {}
        for item in audit.get("failedLanes") or []:
            if isinstance(item, Mapping):
                name = str(item.get("entity") or "").strip()
                if name:
                    out.add(name)
    path = shared / "task_workflow_state.json"
    if not path.is_file():
        return out
    try:
        state = read_json(path)
    except (OSError, ValueError, TypeError):
        return out
    for raw in state.get("failedObjects") or []:
        name = _failed_object_entity(raw)
        if name:
            out.add(name)
    return {item for item in out if item}


def _parse_run_ref(value: str) -> tuple[str, str]:
    raw = str(value or "").strip()
    if "::" not in raw:
        raise ValueError("--exclude-from-run must use TASK_ID::BATCH_ID")
    task_id, batch_id = raw.rsplit("::", 1)
    task_id = task_id.strip()
    batch_id = batch_id.strip()
    if not task_id or not batch_id:
        raise ValueError("--exclude-from-run must use non-empty TASK_ID::BATCH_ID")
    return task_id, batch_id


def select_targets(
    *,
    discovery_path: Path,
    limit: int,
    mandatory: list[str],
    excluded: set[str],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    partitions = _load_partitions(discovery_path)
    by_name = _partition_targets(partitions)
    missing_mandatory = [name for name in mandatory if name not in by_name]
    if missing_mandatory:
        raise ValueError(f"mandatory targets missing from discovery: {missing_mandatory}")
    blocked_mandatory = [name for name in mandatory if name in excluded]
    if blocked_mandatory:
        raise ValueError(
            "mandatory targets are marked ineligible and cannot be auto-replaced: "
            + ", ".join(blocked_mandatory)
        )

    selected: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(name: str) -> None:
        if name in seen or name in excluded or len(selected) >= limit:
            return
        row = by_name.get(name)
        if not row:
            return
        selected.append(row)
        seen.add(name)

    for name in mandatory:
        add(name)

    depth = 0
    while len(selected) < limit:
        scanned_any = False
        for part in partitions:
            leaves = [leaf for leaf in (part.get("leaves") or []) if isinstance(leaf, Mapping)]
            if depth >= len(leaves):
                continue
            scanned_any = True
            name = str(leaves[depth].get("name") or "").strip()
            add(name)
            if len(selected) >= limit:
                break
        if not scanned_any:
            break
        depth += 1

    if len(selected) != limit:
        raise ValueError(
            f"selected {len(selected)} targets, expected {limit}; "
            f"excluded={len(excluded)} may leave too few candidates"
        )
    report = {
        "schemaVersion": "quwoquan_data.target_selection",
        "strategy": "mandatory targets plus deterministic round-robin regional coverage",
        "discoveryPath": str(discovery_path),
        "limit": limit,
        "mandatory": mandatory,
        "excluded": sorted(excluded),
        "targets": selected,
    }
    return selected, report


def build_multimodal_spec(
    *,
    name: str,
    title: str,
    region: str,
    category: str,
    targets: list[dict[str, str]],
    created_by: str,
) -> dict[str, Any]:
    spec = store.scaffold_spec(
        vertical="travel",
        organize_by="地域",
        key=region,
        category=category,
        name=name,
        title=title,
        scope={
            "region": region,
            "entityTypes": ["地点/景区"],
            "coverageTargets": [
                {"entityType": row["entityType"], "name": row["name"]}
                for row in targets
            ],
        },
        content={
            "modalityContract": "separated_research",
            "research": {
                "lanes": ["homepage", "article", "image"],
                "maxConcurrency": 10,
                "laneConcurrency": {"homepage": 3, "article": 3, "image": 4},
                "allowAiImages": False,
            },
            "carriers": ["article", "image"],
            "quotas": {
                "entityArticlesPerTarget": 4,
                "imageWorksPerTarget": 1,
                "entityHomepagesPerTarget": 1,
                "routeArticles": 0,
            },
        },
        acceptance={
            "minEntities": len(targets),
            "minPostsPerEntity": 5,
            "requiredAngles": ["planning_consultation", "decision_experience", "route_transport", "seasonal_timing", "image"],
        },
        created_by=created_by,
    )
    spec["status"] = "active"
    return spec


def write_selected_task(spec: dict[str, Any], report: dict[str, Any], *, force: bool) -> Path:
    if store.spec_exists(spec["taskId"]) and not force:
        raise FileExistsError(f"task already exists: {spec['taskId']} (use --force)")
    spec_path = store.save_spec(spec)
    remaining = [
        f"{target['entityType']}/{target['name']}"
        for target in (spec.get("scope") or {}).get("coverageTargets") or []
    ]
    store.save_progress(store.init_progress(spec["taskId"], remaining=remaining))
    report_path = store.committed_task_root(spec["taskId"]) / "_shared" / "target_selection.json"
    write_json(report_path, report)
    return spec_path


def audit_managed_batch(task_id: str, batch_id: str) -> dict[str, Any]:
    """Summarize separated-current lane readiness and image-work capacity."""
    from download.source_inputs import curated_images_for_entity
    from task.run import (
        PipelineContext,
        _coverage_entity_ids,
        _coverage_entity_type,
        _download_research_lane_issues,
    )

    spec = store.load_spec(task_id)
    ctx = PipelineContext(
        task_id=task_id,
        batch_id=batch_id,
        entity_ids=_coverage_entity_ids(spec),
        spec=spec,
    )
    etype = _coverage_entity_type(spec)
    lanes = ("homepage", "article", "image")
    passed_entities = {lane: set() for lane in lanes}
    failed: list[dict[str, Any]] = []
    image_capacity: dict[str, dict[str, Any]] = {}
    for entity in ctx.entity_ids:
        for lane in lanes:
            issues = _download_research_lane_issues(ctx, entity, etype, lane)
            if issues:
                failed.append({"entity": entity, "lane": lane, "issues": issues})
            else:
                passed_entities[lane].add(entity)
        images = [
            image for image in curated_images_for_entity(task_id, batch_id, entity, etype)
            if str(image.get("researchLane") or "image") == "image"
        ]
        collections: dict[str, int] = {}
        for image in images:
            collection = str(image.get("sourceCollectionId") or "").strip()
            if collection:
                collections[collection] = collections.get(collection, 0) + 1
        image_capacity[entity] = {
            "images": len(images),
            "collections": collections,
            "workCapacity": sum(min(count, 2) for count in collections.values()),
        }
    state_path = batch_root(task_id, batch_id) / "_shared" / "task_workflow_state.json"
    state = read_json(state_path) if state_path.is_file() else {}
    failed.extend(_workflow_failure_items(state))
    for item in failed:
        lane = str(item.get("lane") or "")
        entity = str(item.get("entity") or "")
        if lane in passed_entities and entity in passed_entities[lane]:
            passed_entities[lane].remove(entity)
    passed = {lane: len(passed_entities[lane]) for lane in lanes}
    return {
        "schemaVersion": "quwoquan_data.managed_batch_audit",
        "taskId": task_id,
        "batchId": batch_id,
        "targetCount": len(ctx.entity_ids),
        "lanePassed": passed,
        "failedLaneCount": len(failed),
        "failedLanes": failed,
        "imageCapacity": {
            row["entity"]: image_capacity[row["entity"]]
            for row in failed
            if row["lane"] == "image"
        },
        "workflowState": {
            key: state.get(key)
            for key in (
                "status",
                "waitingCheckpoint",
                "nextAction",
                "retryCounts",
                "infrastructureRetryCounts",
                "failedObjects",
            )
        },
        "lastAgentRun": {
            key: (state.get("lastAgentRun") or {}).get(key)
            for key in (
                "stage",
                "jobCount",
                "startedCount",
                "finishedCount",
                "infrastructureFailures",
                "finishedAt",
            )
        },
    }


def handle_select_targets(args: argparse.Namespace) -> None:
    source_task = args.source_task or DEFAULT_SOURCE_TASK_ID
    discovery = Path(args.discovery) if args.discovery else _default_discovery_path(source_task)
    excluded = set(_split_csv(args.exclude))
    if args.exclude_from_task and args.exclude_from_batch:
        excluded |= ineligible_targets_from_batch(args.exclude_from_task, args.exclude_from_batch)
    for run_ref in getattr(args, "exclude_from_run", None) or []:
        task_id, batch_id = _parse_run_ref(run_ref)
        excluded |= ineligible_targets_from_batch(task_id, batch_id)
    mandatory = _split_csv(args.mandatory) or list(DEFAULT_MANDATORY)
    targets, report = select_targets(
        discovery_path=discovery,
        limit=int(args.limit),
        mandatory=mandatory,
        excluded=excluded,
    )
    spec = build_multimodal_spec(
        name=args.name,
        title=args.title or args.name,
        region=args.region,
        category=args.category,
        targets=targets,
        created_by=args.owner or "task select-targets",
    )
    report["sourceTaskId"] = source_task
    report["taskId"] = spec["taskId"]
    if args.write:
        path = write_selected_task(spec, report, force=bool(args.force))
        print(f"[task select-targets] wrote {spec['taskId']}")
        print(f"  spec: {path}")
        print(f"  targets: {len(targets)} excluded: {len(excluded)}")
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))


def handle_audit_batch(args: argparse.Namespace) -> None:
    report = audit_managed_batch(args.task, args.batch)
    if args.write:
        out = batch_root(args.task, args.batch) / "_shared" / "managed_batch_audit.json"
        write_json(out, report)
        print(f"[task audit-batch] wrote {out}")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    print(
        f"[task audit-batch] {args.task} / {args.batch}: "
        f"targets={report['targetCount']} failedLanes={report['failedLaneCount']}"
    )
    print(f"  lanePassed={report['lanePassed']}")
    state = report.get("workflowState") or {}
    print(f"  status={state.get('status')} checkpoint={state.get('waitingCheckpoint')}")
    for item in (report.get("failedLanes") or [])[:50]:
        print(
            f"  - {item['entity']} {item['lane']}: "
            + "; ".join(str(issue) for issue in item.get("issues") or [])[:240]
        )
