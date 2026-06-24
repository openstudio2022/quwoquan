"""data download — multi-platform source acquisition.

This module is the stable CLI/test facade; implementation is split by plan, image and fetch responsibilities.
"""
from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from download.handler_plan import *  # noqa: F403
from download.handler_images import *  # noqa: F403
from download.handler_fetch import *  # noqa: F403

def handle_download(args: argparse.Namespace) -> None:
    """Orchestrate download: source_plan → fetch → source_screen.

    Steps:
    1. source_plan: Agent plans multi-platform download strategy per entity
    2. fetch: Script executes HTTP fetches + text extraction
    3. source_screen: Agent screens quality/relevance/copyright

    Output: batches/{batch_id}/entities/{domain}/{type}/{entity}/1.download/sources/{NN}.{source_id}/source.md
    """
    task_id = args.task
    batch_id = args.batch
    entity_ids = args.entity_ids.split(",") if args.entity_ids else []
    selected_lanes = _selected_download_lanes(args)

    ensure_batch_layout(task_id, batch_id, "download")
    dl_root = batch_root(task_id, batch_id) / "entities"
    # 批次级公共信息上提（规格 §4/§14）：定义快照 + 受控来源类目，不在对象目录重复。
    write_batch_manifest(task_id, batch_id, command="download")
    write_source_catalog(task_id, batch_id)

    print(f"[download] Task: {task_id}, Batch: {batch_id}", flush=True)
    print(f"[download] Target entities: {entity_ids}", flush=True)
    print(f"[download] Work dir: {dl_root}", flush=True)
    print(
        "[download] Steps: source_plan → fetch → source_screen"
        + (f" (lane={','.join(sorted(selected_lanes))})" if selected_lanes else ""),
        flush=True,
    )

    entity_type = getattr(args, "entity_type", "") or ""
    vertical = vertical_from_task_id(task_id)
    entities = [{"entityId": entity_id, "canonicalName": entity_id, "entityType": entity_type} for entity_id in entity_ids]
    prepare_source_plan(task_id, batch_id, entities)
    for entity in entities:
        planned_sources = [
            {
                "source_id": source.get("source_id") or "",
                "platform": source["platform"],
                "url": source["url"],
                "category": source.get("category") or "",
                "sourceRole": source.get("sourceRole") or "",
                "researchLane": source.get("researchLane") or "",
                "expectedContentType": "article",
                "priority": index + 1,
            }
            for index, source in enumerate(
                _curated_sources_for_lanes(
                    task_id,
                    batch_id,
                    entity["entityId"],
                    entity_type,
                    selected_lanes,
                )
            )
        ]
        write_stage_result(
            task_id,
            batch_id,
            "download",
            "source_plan",
            entity["entityId"],
            {
                "entityId": entity["entityId"],
                "sources": planned_sources,
            },
        )
        # 源类别覆盖门（「全」硬约束）：≥2 源 + 覆盖 ≥N 类（含核心类），杜绝同质单一来源。
        coverage = source_category_coverage(planned_sources, vertical=vertical)
        plan_issues = _source_plan_gate_issues(
            task_id=task_id,
            batch_id=batch_id,
            entity_id=entity["entityId"],
            entity_type=entity_type,
            planned_sources=planned_sources,
            selected_lanes=selected_lanes,
            vertical=vertical,
        )
        write_gate_report(
            task_id=task_id,
            batch_id=batch_id,
            command="download",
            step="source_plan",
            ref=entity["entityId"],
            passed=not plan_issues,
            issues=plan_issues,
            evidence_summary={
                "plannedSourceCount": len(planned_sources),
                "coveredCategories": coverage["coveredCategories"],
                "coveredCount": coverage["coveredCount"],
                "minCategories": coverage["minCategories"],
                "missingCore": coverage["missingCore"],
                "unknownPlatforms": coverage["unknownPlatforms"],
            },
            next_step="fetch",
            fallback_stage="source_plan" if plan_issues else None,
        )

    domain, etype = require_domain_etype(
        entity_type,
        context=f"download entity_type for task={task_id} batch={batch_id}",
    )
    fetched_sources: list[dict] = []
    quality_by_entity: dict[str, list[dict]] = defaultdict(list)
    failed_image_entities: list[str] = []
    _write_download_progress(
        task_id,
        batch_id,
        status="running",
        entity_count=len(entity_ids),
        message="download_fetch started",
    )
    max_workers = max(1, min(int(getattr(args, "max_workers", 1) or 1), len(entity_ids) or 1))
    entity_order = {entity_id: index for index, entity_id in enumerate(entity_ids, start=1)}

    def _merge_fetch_result(result: Mapping[str, Any]) -> None:
        entity_id = str(result.get("entityId") or "")
        fetched_sources.extend(result.get("fetchedSources") or [])
        quality_by_entity[entity_id].extend(result.get("qualityRows") or [])
        if result.get("failedImage"):
            failed_image_entities.append(entity_id)

    if max_workers == 1 or len(entity_ids) <= 1:
        for entity_index, entity_id in enumerate(entity_ids, start=1):
            result = _fetch_download_entity(
                task_id=task_id,
                batch_id=batch_id,
                entity_type=entity_type,
                vertical=vertical,
                domain=domain,
                etype=etype,
                entity_id=entity_id,
                entity_index=entity_index,
                entity_count=len(entity_ids),
                selected_lanes=selected_lanes,
            )
            _merge_fetch_result(result)
    else:
        print(
            f"[download] Fetch concurrency: {max_workers} workers for {len(entity_ids)} entities",
            flush=True,
        )
        executor = ThreadPoolExecutor(max_workers=max_workers)
        futures = {}
        interrupted = False
        try:
            futures = {
                executor.submit(
                    _fetch_download_entity,
                    task_id=task_id,
                    batch_id=batch_id,
                    entity_type=entity_type,
                    vertical=vertical,
                    domain=domain,
                    etype=etype,
                    entity_id=entity_id,
                    entity_index=entity_index,
                    entity_count=len(entity_ids),
                    selected_lanes=selected_lanes,
                ): (entity_index, entity_id)
                for entity_index, entity_id in enumerate(entity_ids, start=1)
            }
            for future in as_completed(futures):
                entity_index, entity_id = futures[future]
                try:
                    result = future.result()
                except Exception as exc:  # noqa: BLE001
                    issue = f"downloadFetch: {entity_id} raised {type(exc).__name__}: {exc}"
                    print(f"[download] Entity failed {entity_index}/{len(entity_ids)}: {issue}", file=sys.stderr, flush=True)
                    quality_by_entity[entity_id].extend([])
                    failed_image_entities.append(entity_id)
                    write_gate_report(
                        task_id=task_id,
                        batch_id=batch_id,
                        command="download",
                        step="image_fetch",
                        ref=entity_id,
                        passed=False,
                        issues=[issue],
                        evidence_summary={"entityIndex": entity_index, "workerException": type(exc).__name__},
                        next_step="quality_analysis",
                        fallback_stage="source_plan",
                    )
                    _write_download_progress(
                        task_id,
                        batch_id,
                        status="running",
                        entity_id=entity_id,
                        entity_index=entity_index,
                        entity_count=len(entity_ids),
                        message=issue,
                    )
                    continue
                _merge_fetch_result(result)
        except KeyboardInterrupt:
            interrupted = True
            for future in futures:
                future.cancel()
            message = (
                "download_fetch interrupted; cancelled queued entity fetch jobs "
                f"({len(futures)} submitted)"
            )
            _write_download_progress(
                task_id,
                batch_id,
                status="interrupted",
                entity_count=len(entity_ids),
                message=message,
            )
            print(f"[download] {message}", file=sys.stderr, flush=True)
            raise
        finally:
            executor.shutdown(wait=not interrupted, cancel_futures=True)
    fetched_sources.sort(
        key=lambda row: (
            entity_order.get(str(row.get("entityId") or ""), 1_000_000),
            str(row.get("sourceId") or ""),
        )
    )

    prepare_source_screen(task_id, batch_id, fetched_sources)
    for source in fetched_sources:
        issues: list[str] = []
        if source["quality"] == "Reject":
            issues.append("sourceScreen: source scored Reject")
        report_ref = _source_screen_report_ref(source["entityId"], source["sourceId"])
        write_stage_result(
            task_id,
            batch_id,
            "download",
            "source_screen",
            report_ref,
            {
                "sourceId": source["sourceId"],
                "decision": "retain" if source["quality"] != "Reject" else "reject",
                "qualityScore": source["score"],
                "relevanceScore": source["score"],
                "copyrightStatus": "internal_reference",
                "reason": "quality gate auto-screen",
                "entityId": source["entityId"],
            },
        )
        write_gate_report(
            task_id=task_id,
            batch_id=batch_id,
            command="download",
            step="source_screen",
            ref=report_ref,
            passed=not issues,
            issues=issues,
            evidence_summary={
                "entityId": source["entityId"],
                "sourceId": source["sourceId"],
                "quality": source["quality"],
                "score": source["score"],
            },
            next_step="quality_analysis",
            fallback_stage="fetch" if issues else None,
        )
    for entity_id, rows in quality_by_entity.items():
        retained = [row for row in rows if row["quality"] != "Reject"]
        issues: list[str] = []
        if len(retained) < 1:
            issues.append("sourceScreen: no retained source for entity")
        # 受控类目门：阻断无类别的 weather_* 散来源（天气应作为百科/官方/攻略来源内事实）。
        for source in _curated_sources_for_lanes(
            task_id,
            batch_id,
            entity_id,
            entity_type,
            selected_lanes,
        ):
            issues.extend(source_unit_category_issues(source["source_id"], source.get("platform") or ""))
        write_gate_report(
            task_id=task_id,
            batch_id=batch_id,
            command="download",
            step="entity_source_bundle",
            ref=entity_id,
            passed=not issues,
            issues=issues,
            evidence_summary={
                "sourceCount": len(rows),
                "retainedCount": len(retained),
                "qualities": [row["quality"] for row in rows],
            },
            next_step="quality_analysis",
            fallback_stage="source_plan" if issues else None,
        )
    print(
        f"[download] Planned {len(entities)} entity/entities and fetched {len(fetched_sources)} source bundle(s)",
        flush=True,
    )
    gate_issues = gate_download(task_id, batch_id, target_entities=set(entity_ids))
    gate_issues.extend(
        f"{entity_id}: image gates failed (rights/fetch/safety/min-count); unsafe or unauthorized images must not enter assets"
        for entity_id in failed_image_entities
    )
    if gate_issues:
        print(f"[download] Gate FAILED ({len(gate_issues)} issue(s)):", file=sys.stderr, flush=True)
        for issue in gate_issues:
            print(f"  - {issue}", file=sys.stderr, flush=True)
        _write_download_progress(
            task_id,
            batch_id,
            status="failed",
            entity_count=len(entity_ids),
            sources=len(fetched_sources),
            message="; ".join(gate_issues[:5]),
        )
        raise SystemExit(1)
    _write_download_progress(
        task_id,
        batch_id,
        status="done",
        entity_count=len(entity_ids),
        sources=len(fetched_sources),
        message="download gate passed",
    )
    print("[download] Gate PASSED", flush=True)

def register_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("download", help="Multi-platform source acquisition")
    p.add_argument("--task", required=True, help="Task ID")
    p.add_argument("--batch", required=True, help="Batch ID")
    p.add_argument("--entity-ids", required=True, help="Comma-separated entity IDs")
    p.add_argument("--entity-type", default="", help="实体类型(可选，仅记录到 source_plan)")
    p.add_argument("--lane", choices=("all", "homepage", "article", "image"), default="all", help="只抓取/修复指定 research lane")
    p.add_argument("--max-workers", type=int, default=1, help="download_fetch entity-level concurrency")
    p.set_defaults(handler=handle_download)
