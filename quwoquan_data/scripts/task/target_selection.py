"""Reusable multimodal target selection and batch audit helpers."""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

from _common.entity_extract import require_domain_etype
from _common.io import read_json, write_json, write_ndjson
from _common.paths import batch_entity_page_input_path, batch_root, task_catalog
from task import store


DEFAULT_MANDATORY = ["四姑娘山", "毕棚沟", "稻城亚丁", "海螺沟", "墨石公园"]
DEFAULT_SOURCE_TASK_ID = "旅行/地域/四川省/景区/景区精选"
DEFAULT_ARTICLE_ANGLES = [
    "planning_consultation",
    "decision_experience",
    "route_transport",
    "seasonal_timing",
]


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
    if (
        "article source unit" in text
        or "article base draft" in text
        or "article research" in text
        or "text-qualified base source" in text
        or "article base source" in text
        or "article sources=" in text
        or "usable article base sources" in text
    ):
        return "article"
    if "image research" in text or "image gate" in text or "image fetch" in text:
        return "image"
    if "homepage" in text or "entity homepage" in text:
        return "homepage"
    return "workflow"


def _workflow_failure_items(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    status = str(state.get("status") or "").strip()
    failed_objects = [str(item) for item in state.get("failedObjects") or [] if str(item).strip()]
    if status in ("", "succeeded", "stopped_at_until"):
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
        for leaf in _ordered_partition_leaves(part):
            source_name = str(leaf.get("name") or "").strip()
            name = _leaf_selection_name(leaf)
            etype = str(leaf.get("entityType") or "地点/景区").strip()
            if name and name not in by_name:
                by_name[name] = {
                    "name": name,
                    "entityType": etype,
                    "region": region,
                    "sourceName": source_name,
                }
    return by_name


def _leaf_selection_name(leaf: Mapping[str, Any]) -> str:
    source_name = str(leaf.get("name") or "").strip()
    return str(leaf.get("canonicalName") or source_name).strip()


def _leaf_selection_priority(leaf: Mapping[str, Any]) -> float | None:
    if "selectionPriority" not in leaf:
        return None
    try:
        return float(leaf.get("selectionPriority"))
    except (TypeError, ValueError):
        return None


def _ordered_partition_leaves(part: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    leaves = [leaf for leaf in (part.get("leaves") or []) if isinstance(leaf, Mapping)]
    if not any(_leaf_selection_priority(leaf) is not None for leaf in leaves):
        return leaves
    return sorted(
        leaves,
        key=lambda leaf: (
            _leaf_selection_priority(leaf)
            if _leaf_selection_priority(leaf) is not None
            else float("inf"),
            _leaf_selection_name(leaf),
        ),
    )


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
    unavailable_path = shared / "source_unavailable_targets.json"
    if unavailable_path.is_file():
        try:
            availability = read_json(unavailable_path)
        except (OSError, ValueError, TypeError):
            availability = {}
        for item in availability.get("ineligibleTargets") or []:
            if isinstance(item, Mapping):
                name = str(item.get("entityId") or "").strip()
                if name:
                    out.add(name)
    auto_research_path = shared / "auto_research_plan.json"
    if auto_research_path.is_file():
        try:
            auto_research = read_json(auto_research_path)
        except (OSError, ValueError, TypeError):
            auto_research = {}
        availability = auto_research.get("sourceAvailability") if isinstance(auto_research.get("sourceAvailability"), Mapping) else {}
        for item in availability.get("ineligibleTargets") or []:
            if isinstance(item, Mapping):
                name = str(item.get("entityId") or "").strip()
                if name:
                    out.add(name)
    path = shared / "task_workflow_state.json"
    if not path.is_file():
        return out
    try:
        state = read_json(path)
    except (OSError, ValueError, TypeError):
        return out
    for item in state.get("abandonedObjects") or []:
        if isinstance(item, Mapping):
            name = str(item.get("entityId") or "").strip()
            if name:
                out.add(name)
    for item in state.get("abandonedContentObjects") or []:
        if not isinstance(item, Mapping):
            continue
        name = str(item.get("entityId") or "").strip()
        ref = str(item.get("ref") or "").strip()
        if not name and "_" in ref:
            name = ref.split("_", 1)[0].strip()
        if name:
            out.add(name)
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
    reserve_ratio: float = 0.0,
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
    reserve: list[dict[str, str]] = []
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
            leaves = _ordered_partition_leaves(part)
            if depth >= len(leaves):
                continue
            scanned_any = True
            name = _leaf_selection_name(leaves[depth])
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
    reserve_count = max(0, int(round(limit * max(0.0, float(reserve_ratio or 0.0)))))
    if reserve_count:
        for part in partitions:
            for leaf in _ordered_partition_leaves(part):
                name = _leaf_selection_name(leaf)
                if not name or name in seen or name in excluded:
                    continue
                row = by_name.get(name)
                if not row:
                    continue
                reserve.append(row)
                seen.add(name)
                if len(reserve) >= reserve_count:
                    break
            if len(reserve) >= reserve_count:
                break
    report = {
        "schemaVersion": "quwoquan_data.target_selection",
        "strategy": "mandatory targets plus deterministic round-robin regional coverage",
        "discoveryPath": str(discovery_path),
        "limit": limit,
        "reserveRatio": max(0.0, float(reserve_ratio or 0.0)),
        "mandatory": mandatory,
        "excluded": sorted(excluded),
        "targets": selected,
        "reserveTargets": reserve,
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
    intent_label: str | None = None,
    reserve_targets: list[dict[str, str]] | None = None,
    entity_articles_per_target: int = 4,
    image_works_per_target: int = 1,
) -> dict[str, Any]:
    entity_articles_per_target = max(0, int(entity_articles_per_target))
    image_works_per_target = max(0, int(image_works_per_target))
    required_article_angles = DEFAULT_ARTICLE_ANGLES[:entity_articles_per_target]
    spec = store.scaffold_spec(
        vertical="travel",
        organize_by="地域",
        key=region,
        category=category,
        name=name,
        title=title,
        intent_label=intent_label,
        scope={
            "region": region,
            "entityTypes": ["地点/景区"],
            "coverageTargets": [
                {"entityType": row["entityType"], "name": row["name"]}
                for row in targets
            ],
            "reserveCoverageTargets": [
                {"entityType": row["entityType"], "name": row["name"]}
                for row in (reserve_targets or [])
            ],
        },
        content={
            "modalityContract": "separated_research",
            "research": {
                "lanes": ["homepage", "article", "image"],
                "maxConcurrency": 10,
                "laneConcurrency": {"homepage": 3, "article": 3, "image": 4},
                "imageAssetStrategy": "open_license_publish",
                "imageCountPolicy": "score_bonus",
                "allowAiImages": False,
            },
            "carriers": ["article", "image"],
            "quotas": {
                "entityArticlesPerTarget": entity_articles_per_target,
                "imageWorksPerTarget": image_works_per_target,
                "entityHomepagesPerTarget": 1,
                "routeArticles": 0,
            },
        },
        acceptance={
            "minEntities": len(targets),
            "minPostsPerEntity": entity_articles_per_target + image_works_per_target,
            "requiredAngles": required_article_angles,
            "scoredAngles": (["image"] if image_works_per_target else []),
        },
        created_by=created_by,
    )
    spec["status"] = "active"
    reserve_count = len(reserve_targets or [])
    replacement_candidates_per_wave = max(8, min(50, int(math.ceil(max(len(targets), 1) * 0.25))))
    replacement_waves = max(3, int(math.ceil(max(reserve_count, 1) / replacement_candidates_per_wave)))
    spec["workflowPolicy"] = {
        "allowPartialContent": True,
        "deliveryMode": "partial_with_replacement_report",
        "maxReplacementWaves": replacement_waves,
        "maxReplacementCandidatesPerWave": replacement_candidates_per_wave,
        "maxReplacementScreenedPerRun": max(reserve_count, replacement_candidates_per_wave),
    }
    spec["queuePolicy"] = {
        "backend": "reliabletask",
        "reliableTask": {
            "taskType": "data.content_object.execute",
            "queue": "reliabletask.data.content_supply",
            "store": "MongoStore",
            "readyIndex": "RedisReadyIndex",
        },
        "leaseSeconds": 900,
        "heartbeatSeconds": 60,
        "deadLetterAfterAttempts": 3,
    }
    return spec


def write_selected_task(spec: dict[str, Any], report: dict[str, Any], *, force: bool) -> Path:
    if store.spec_exists(spec["taskId"]) and not force:
        raise FileExistsError(f"task already exists: {spec['taskId']} (use --force)")
    spec_path = store.save_spec(spec)
    targets = (spec.get("scope") or {}).get("coverageTargets") or []
    remaining = [f"{target['entityType']}/{target['name']}" for target in targets]
    store.save_progress(store.init_progress(spec["taskId"], remaining=remaining))
    rows = []
    region = str((spec.get("scope") or {}).get("region") or "")
    for target in targets:
        entity_type = str(target.get("entityType") or "").strip()
        name = str(target.get("name") or "").strip()
        if not entity_type or not name:
            continue
        rows.append(
            {
                "topic_id": f"{entity_type}/{name}",
                "domain": entity_type.split("/", 1)[0] if "/" in entity_type else "",
                "entity_type": entity_type,
                "canonical_name": name,
                "region": region,
                "source_count": 1,
                "geo_tag_ref": f"/tag/地域/{region}" if region else "",
                "source_kind": "coverageTarget",
                "status": "candidate",
                "taskId": spec["taskId"],
            }
        )
    write_ndjson(task_catalog(spec["taskId"]), rows)
    report_path = store.committed_task_root(spec["taskId"]) / "_shared" / "target_selection.json"
    write_json(report_path, report)
    return spec_path


def _batch_planned_entity_ids(task_id: str, batch_id: str) -> list[str]:
    shared = batch_root(task_id, batch_id) / "_shared"
    report = read_json(shared / "auto_research_plan.json") if (shared / "auto_research_plan.json").is_file() else {}
    availability = report.get("sourceAvailability") if isinstance(report.get("sourceAvailability"), dict) else {}
    ids: list[str] = []
    seen: set[str] = set()
    for entity_id in availability.get("readyTargets") or []:
        text = str(entity_id or "").strip()
        if text and text not in seen:
            ids.append(text)
            seen.add(text)
    for item in availability.get("ineligibleTargets") or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("entityId") or "").strip()
        if text and text not in seen:
            ids.append(text)
            seen.add(text)
    if ids:
        return ids
    for item in report.get("updated") or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("entityId") or "").strip()
        if text and text not in seen:
            ids.append(text)
            seen.add(text)
    return ids


def _replacement_target_rows(state: Mapping[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in state.get("replacementObjects") or []:
        if not isinstance(item, Mapping):
            continue
        if str(item.get("status") or "active") != "active":
            continue
        name = str(item.get("entityId") or "").strip()
        if not name or name in seen:
            continue
        etype = str(item.get("entityType") or "地点/景区").strip()
        rows.append({"name": name, "entityType": etype})
        seen.add(name)
    return rows


def audit_managed_batch(
    task_id: str,
    batch_id: str,
    *,
    workflow_state_override: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Summarize separated-current lane readiness and image-work capacity."""
    from download.source_inputs import curated_images_for_entity
    from task.run import (
        PipelineContext,
        _active_spec,
        _coverage_entity_ids,
        _coverage_entity_type,
        _download_research_lane_issues,
    )
    from build.homepage import validate_entity_page_inputs

    spec = store.load_spec(task_id)
    state_path = batch_root(task_id, batch_id) / "_shared" / "task_workflow_state.json"
    state = read_json(state_path) if state_path.is_file() else {}
    if workflow_state_override is not None:
        state = dict(workflow_state_override)
    abandoned_rows = [
        item for item in (state.get("abandonedObjects") or [])
        if isinstance(item, Mapping) and str(item.get("entityId") or "").strip()
    ]
    abandoned_content_rows = [
        item for item in (state.get("abandonedContentObjects") or [])
        if isinstance(item, Mapping) and str(item.get("ref") or "").strip()
    ]
    abandoned = {str(item.get("entityId") or "").strip() for item in abandoned_rows}
    coverage_entity_ids = _coverage_entity_ids(spec)
    planned_entity_ids = _batch_planned_entity_ids(task_id, batch_id)
    if len(planned_entity_ids) < len(coverage_entity_ids):
        planned_entity_ids = []
    entity_ids = [
        entity for entity in (planned_entity_ids or coverage_entity_ids)
        if entity not in abandoned
    ]
    for row in _replacement_target_rows(state):
        name = str(row.get("name") or "").strip()
        if name and name not in abandoned and name not in entity_ids:
            entity_ids.append(name)
    ctx = PipelineContext(
        task_id=task_id,
        batch_id=batch_id,
        entity_ids=entity_ids,
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
    active_spec = _active_spec(ctx)
    has_homepage_inputs = False
    for target in (active_spec.get("scope") or {}).get("coverageTargets") or []:
        name = str(target.get("name") or "").strip()
        if not name:
            continue
        domain, target_type = require_domain_etype(
            target.get("entityType"),
            context=f"coverageTargets[{name}]",
        )
        if batch_entity_page_input_path(task_id, batch_id, domain, target_type, name).is_file():
            has_homepage_inputs = True
            break
    if has_homepage_inputs:
        input_issues_by_entity: dict[str, list[str]] = {}
        for issue in validate_entity_page_inputs(task_id, batch_id, active_spec):
            label = str(issue).split(":", 1)[0]
            entity = label.split("/")[-1] if label else "__batch__"
            input_issues_by_entity.setdefault(entity, []).append(str(issue))
        for entity, issues in input_issues_by_entity.items():
            existing = next(
                (
                    item for item in failed
                    if str(item.get("entity") or "") == entity
                    and str(item.get("lane") or "") == "homepage"
                ),
                None,
            )
            if existing is None:
                failed.append({"entity": entity, "lane": "homepage", "issues": issues})
            else:
                current = existing.setdefault("issues", [])
                for issue in issues:
                    if issue not in current:
                        current.append(issue)
    failed_index = {
        (str(item.get("entity") or ""), str(item.get("lane") or "")): item
        for item in failed
    }
    for item in _workflow_failure_items(state):
        key = (str(item.get("entity") or ""), str(item.get("lane") or ""))
        lane = key[1]
        entity = key[0]
        if lane in passed_entities and entity in passed_entities[lane]:
            continue
        existing = failed_index.get(key)
        if existing is not None:
            issues = existing.setdefault("issues", [])
            for issue in item.get("issues") or []:
                if issue not in issues:
                    issues.append(issue)
            continue
        failed.append(item)
        failed_index[key] = item
    from _common.entity_artifacts import inactive_entity_artifact_rows

    inactive_artifacts = inactive_entity_artifact_rows(
        task_id,
        batch_id,
        active_entity_names=ctx.entity_ids,
    )
    for row in inactive_artifacts:
        entity = str(row.get("entity") or "")
        key = (entity, "homepage")
        issue = (
            "inactive entity has generated homepage artifact(s) outside active target set: "
            + ", ".join(str(item) for item in (row.get("artifacts") or [])[:8])
        )
        existing = failed_index.get(key)
        if existing is not None:
            issues = existing.setdefault("issues", [])
            if issue not in issues:
                issues.append(issue)
            continue
        item = {"entity": entity, "lane": "homepage", "issues": [issue]}
        failed.append(item)
        failed_index[key] = item
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
        "targetScope": "batch_planned" if planned_entity_ids else "task_coverage",
        "abandonedCount": len(abandoned_rows),
        "abandonedObjects": abandoned_rows,
        "replacementCount": len(_replacement_target_rows(state)),
        "replacementObjects": state.get("replacementObjects") or [],
        "abandonedContentCount": len(abandoned_content_rows),
        "abandonedContentObjects": abandoned_content_rows,
        "inactiveEntityArtifactCount": len(inactive_artifacts),
        "inactiveEntityArtifacts": inactive_artifacts,
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
    mandatory = _split_csv(args.mandatory) if args.mandatory is not None else list(DEFAULT_MANDATORY)
    targets, report = select_targets(
        discovery_path=discovery,
        limit=int(args.limit),
        mandatory=mandatory,
        excluded=excluded,
        reserve_ratio=float(getattr(args, "reserve_ratio", 0.2) or 0.0),
    )
    spec = build_multimodal_spec(
        name=args.name,
        title=args.title or args.name,
        region=args.region,
        category=args.category,
        targets=targets,
        intent_label=getattr(args, "intent_label", None),
        reserve_targets=report.get("reserveTargets") or [],
        created_by=args.owner or "task select-targets",
        entity_articles_per_target=int(getattr(args, "entity_articles_per_target", 4) or 0),
        image_works_per_target=int(getattr(args, "image_works_per_target", 1) or 0),
    )
    report["sourceTaskId"] = source_task
    report["taskId"] = spec["taskId"]
    report["quotas"] = (spec.get("content") or {}).get("quotas") or {}
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
    else:
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
    if getattr(args, "strict", False) and int(report.get("failedLaneCount") or 0) > 0:
        raise SystemExit(1)
