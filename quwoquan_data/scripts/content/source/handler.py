"""Source-acquisition stage service split by plan, image, and fetch responsibilities."""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Mapping

from core.data_issue import (
    DataIssue, DataIssueCode, DataIssueError, DataIssueStage,
    DataIssueLane,
    DataRecoveryAction,
    data_issue,
    data_issues,
    issue_messages,
)
from content.source.gate import active_download_lanes
from content.source.handler_plan import (
    _curated_sources_for_lanes,
    _source_plan_gate_issues,
    _write_download_progress,
    selected_download_lanes,
)
from content.source.handler_images import _source_screen_report_ref
from content.source.handler_fetch import _fetch_download_entity
from content.source.prepare import prepare_source_plan, prepare_source_screen
from content.execution.runtime_state import write_execution_runtime_state, write_source_catalog
from content.execution.stage_reports import write_gate_report, write_stage_result
from content.source.gate import gate_download
from core.paths import ensure_execution_command_layout, execution_root
from core.source_catalog import (
    source_category_coverage,
    source_unit_category_issues,
    vertical_from_task_id,
)
from governance.coverage.entity_extract import require_domain_etype
from content.source.handler_fetch_failure import entity_fetch_issue
from content.source.source_inputs import content_type_for_lane


def _write_fetch_result_screen_outputs(
    *,
    execution_id: str,
    entity_id: str,
    entity_type: str,
    selected_lanes: set[str] | None,
    text_lane_selected: bool,
    fetched_sources: list[dict[str, Any]],
    quality_rows: list[dict[str, Any]],
) -> None:
    """Persist per-entity source_screen evidence as soon as fetch finishes."""
    if fetched_sources:
        prepare_source_screen(execution_id, fetched_sources)
    for source in fetched_sources:
        issues: list[str] = []
        if source["quality"] == "Reject":
            issues.append("sourceScreen: source scored Reject")
        report_ref = _source_screen_report_ref(source["entityId"], source["sourceId"])
        write_stage_result(
            execution_id,
            "source",
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
            execution_id=execution_id,
            command="source",
            step="source_screen",
            ref=report_ref,
            passed=not issues,
            issues=data_issues(
                DataIssueCode.QUALITY_FAILED,
                stage=DataIssueStage.SOURCE_SCREEN,
                ref=report_ref,
                messages=issues,
                recovery=DataRecoveryAction.REPLACE_SOURCE,
            ),
            evidence_summary={
                "entityId": source["entityId"],
                "sourceId": source["sourceId"],
                "quality": source["quality"],
                "score": source["score"],
            },
            next_step="quality_analysis",
        )
    retained = [row for row in quality_rows if row["quality"] != "Reject"]
    issues: list[str] = []
    if text_lane_selected and len(retained) < 1:
        issues.append("sourceScreen: no retained source for entity")
    for source in _curated_sources_for_lanes(
        execution_id,
        entity_id,
        entity_type,
        selected_lanes,
    ):
        issues.extend(source_unit_category_issues(source["source_id"], source.get("platform") or ""))
    write_gate_report(
        execution_id=execution_id,
        command="source",
        step="entity_source_bundle",
        ref=entity_id,
        passed=not issues,
        issues=data_issues(
            DataIssueCode.SOURCE_RETAINED_SHORTFALL,
            stage=DataIssueStage.ENTITY_SOURCE_BUNDLE,
            ref=entity_id,
            messages=issues,
            recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
        ),
        evidence_summary={
            "sourceCount": len(quality_rows),
            "retainedCount": len(retained),
            "qualities": [row["quality"] for row in quality_rows],
        },
        next_step="quality_analysis",
    )


def handle_download(
    *,
    execution_id: str,
    entity_ids: list[str],
    entity_type: str = "",
    lane: str = "all",
    max_workers: int | None = None,
    defer_gate: bool = False,
) -> None:
    """Orchestrate download: source_plan → fetch → source_screen.

    Steps:
    1. source_plan: Agent plans multi-platform download strategy per entity
    2. fetch: Script executes HTTP fetches + text extraction
    3. source_screen: Agent screens quality/relevance/copyright

    Output: entities/*/1.download/source_refs.json plus source-unit evidence.
    """
    entity_ids = [str(entity_id).strip() for entity_id in entity_ids if str(entity_id).strip()]
    selected_lanes = selected_download_lanes(lane)
    from content.execution.campaign.external_input_runtime import (
        bound_runtime_external_input_context,
    )
    from content.execution.identity import parse_execution_id

    carrier = parse_execution_id(execution_id).content_type.value
    external_input_context = bound_runtime_external_input_context(
        execution_id,
        carrier,
    )

    ensure_execution_command_layout(execution_id, "source")
    dl_root = execution_root(execution_id) / "entities"
    # 批次级公共信息上提（规格 §4/§14）：定义快照 + 受控来源类目，不在对象目录重复。
    write_execution_runtime_state(execution_id, command="source")
    write_source_catalog(execution_id)

    print(f"[source] Execution: {execution_id}", flush=True)
    print(f"[download] Target entities: {entity_ids}", flush=True)
    print(f"[download] Work dir: {dl_root}", flush=True)
    print(
        "[download] Steps: source_plan → fetch → source_screen"
        + (f" (lane={','.join(sorted(selected_lanes))})" if selected_lanes else ""),
        flush=True,
    )

    vertical = vertical_from_task_id(execution_id)
    effective_lanes = selected_lanes
    if effective_lanes is None:
        effective_lanes = active_download_lanes(execution_id)
    text_lane_selected = bool(effective_lanes & {"homepage", "article"})
    # 类型以 coverageTargets canonical 为真相源校正（WP5 漂移修复）；
    # 全体同类型时同步收敛单值 entity_type，避免 CLI 传错类型造成目录/后续步骤分叉。
    from content.source.prepare import resolve_research_entity_types

    resolved_types = resolve_research_entity_types(execution_id, entity_ids, fallback_type=entity_type)
    unique_types = sorted(set(resolved_types.values()))
    if len(unique_types) == 1:
        entity_type = unique_types[0]
    entities = [
        {"entityId": entity_id, "canonicalName": entity_id, "entityType": resolved_types[entity_id]}
        for entity_id in entity_ids
    ]
    prepare_source_plan(execution_id, entities)
    for entity in entities:
        planned_sources = [
            {
                "source_id": source.get("source_id") or "",
                "platform": source["platform"],
                "url": source["url"],
                "sourceKind": source.get("sourceKind") or "",
                "sourceTitle": source.get("sourceTitle") or "",
                "canonicalUrl": source.get("canonicalUrl") or "",
                "extractor": source.get("extractor") or "",
                "policyRevision": source.get("policyRevision") or "",
                "category": source.get("category") or "",
                "sourceRole": source.get("sourceRole") or "",
                "researchLane": source.get("researchLane") or "",
                "candidateGate": source.get("candidateGate") or {},
                "imageEvidenceMode": source.get("imageEvidenceMode") or "",
                "sourceUseMode": source.get("sourceUseMode") or "",
                "publishMediaMode": source.get("publishMediaMode") or "",
                "articleCommercialAdmission": source.get("articleCommercialAdmission") or "",
                "articleSiteId": source.get("articleSiteId") or "",
                "sourceDiscoveryProfileDigest": source.get("sourceDiscoveryProfileDigest") or "",
                # P3 三类解耦：内容类型按 lane 路由（homepage=entity/article=article/image=image），
                # 不再「全部当 article」实体键控；下游分类型下发调度据此区分来源处理。
                "expectedContentType": content_type_for_lane(source.get("researchLane") or ""),
                "priority": index + 1,
            }
            for index, source in enumerate(
                _curated_sources_for_lanes(
                    execution_id,
                    entity["entityId"],
                    entity_type,
                    selected_lanes,
                )
            )
        ]
        # P3 分类型下发调度：按内容类型对来源分桶，dispatch 记录显式区分三类，便于审计与续跑。
        dispatch_by_content_type: dict[str, int] = {}
        for planned in planned_sources:
            ctype = str(planned.get("expectedContentType") or "article")
            dispatch_by_content_type[ctype] = dispatch_by_content_type.get(ctype, 0) + 1
        write_stage_result(
            execution_id,
            "source",
            "source_plan",
            entity["entityId"],
            {
                "entityId": entity["entityId"],
                "entityName": entity["canonicalName"],
                "policyRevision": "encyclopedia-primary",
                "sources": planned_sources,
                "dispatchByContentType": dispatch_by_content_type,
            },
        )
        # 源类别覆盖门（「全」硬约束）：≥2 源 + 覆盖 ≥N 类（含核心类），杜绝同质单一来源。
        coverage = source_category_coverage(planned_sources, vertical=vertical)
        plan_issues = _source_plan_gate_issues(
            execution_id=execution_id,
            entity_id=entity["entityId"],
            entity_type=entity_type,
            planned_sources=planned_sources,
            selected_lanes=selected_lanes,
            vertical=vertical,
        )
        write_gate_report(
            execution_id=execution_id,
            command="source",
            step="source_plan",
            ref=entity["entityId"],
            passed=not plan_issues,
            issues=data_issues(
                DataIssueCode.SOURCE_PLAN_INVALID,
                stage=DataIssueStage.SOURCE_PLAN,
                ref=entity["entityId"],
                messages=plan_issues,
                recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
            ),
            evidence_summary={
                "plannedSourceCount": len(planned_sources),
                "coveredCategories": coverage["coveredCategories"],
                "coveredCount": coverage["coveredCount"],
                "minCategories": coverage["minCategories"],
                "missingCore": coverage["missingCore"],
                "unknownPlatforms": coverage["unknownPlatforms"],
            },
            next_step="fetch",
        )

    domain, etype = require_domain_etype(
        entity_type,
        context=f"source entity_type for execution={execution_id}",
    )
    fetched_sources: list[dict] = []
    successful_entity_ids: set[str] = set()
    quality_by_entity: dict[str, list[dict]] = defaultdict(list)
    failed_image_entities: list[str] = []
    typed_fetch_issues: list[DataIssue] = []
    _write_download_progress(
        execution_id,
        status="running",
        entity_count=len(entity_ids),
        message="download_fetch started",
    )
    requested_workers = len(entity_ids) if max_workers is None else int(max_workers)
    if requested_workers < 1 and entity_ids:
        raise ValueError("download max_workers must be positive when work is present")
    max_workers = min(requested_workers, len(entity_ids)) if entity_ids else 0
    entity_order = {entity_id: index for index, entity_id in enumerate(entity_ids, start=1)}

    def _merge_fetch_result(result: Mapping[str, Any]) -> None:
        entity_id = str(result.get("entityId") or "")
        entity_sources = list(result.get("fetchedSources") or [])
        entity_quality_rows = list(result.get("qualityRows") or [])
        fetched_sources.extend(entity_sources)
        quality_by_entity[entity_id].extend(entity_quality_rows)
        if entity_sources:
            successful_entity_ids.add(entity_id)
        _write_fetch_result_screen_outputs(
            execution_id=execution_id,
            entity_id=entity_id,
            entity_type=entity_type,
            selected_lanes=selected_lanes,
            text_lane_selected=text_lane_selected,
            fetched_sources=entity_sources,
            quality_rows=entity_quality_rows,
        )
        if result.get("failedImage"):
            failed_image_entities.append(entity_id)

    def _record_typed_fetch_failure(
        entity_id: str,
        entity_index: int,
        error: DataIssueError,
    ) -> None:
        typed_fetch_issues.extend(error.issues)
        write_gate_report(
            execution_id=execution_id,
            command="source",
            step="download_fetch",
            ref=entity_id,
            passed=False,
            issues=list(error.issues),
            evidence_summary={
                "entityIndex": entity_index,
                "issueCodes": [issue.code.value for issue in error.issues],
            },
            next_step="typed_repair_queue",
        )
        _write_download_progress(
            execution_id,
            status="running",
            entity_id=entity_id,
            entity_index=entity_index,
            entity_count=len(entity_ids),
            message="typed source fetch failure recorded",
        )

    def _record_entity_fetch_exception(
        entity_id: str,
        entity_index: int,
        exc: Exception,
    ) -> None:
        issue = entity_fetch_issue(
            entity_id,
            exc,
            selected_lanes=selected_lanes,
        )
        print(
            f"[download] Entity excluded {entity_index}/{len(entity_ids)}: {issue}",
            file=sys.stderr,
            flush=True,
        )
        _record_typed_fetch_failure(
            entity_id,
            entity_index,
            DataIssueError([issue]),
        )

    if max_workers == 1 or len(entity_ids) <= 1:
        for entity_index, entity_id in enumerate(entity_ids, start=1):
            try:
                result = _fetch_download_entity(
                    execution_id=execution_id,
                    entity_type=entity_type,
                    vertical=vertical,
                    domain=domain,
                    etype=etype,
                    entity_id=entity_id,
                    entity_index=entity_index,
                    entity_count=len(entity_ids),
                    selected_lanes=selected_lanes,
                    external_input_context=external_input_context,
                )
            except DataIssueError as exc:
                _record_typed_fetch_failure(entity_id, entity_index, exc)
                continue
            except Exception as exc:  # noqa: BLE001
                _record_entity_fetch_exception(entity_id, entity_index, exc)
                continue
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
                    execution_id=execution_id,
                    entity_type=entity_type,
                    vertical=vertical,
                    domain=domain,
                    etype=etype,
                    entity_id=entity_id,
                    entity_index=entity_index,
                    entity_count=len(entity_ids),
                    selected_lanes=selected_lanes,
                    external_input_context=external_input_context,
                ): (entity_index, entity_id)
                for entity_index, entity_id in enumerate(entity_ids, start=1)
            }
            for future in as_completed(futures):
                entity_index, entity_id = futures[future]
                try:
                    result = future.result()
                except DataIssueError as exc:
                    _record_typed_fetch_failure(entity_id, entity_index, exc)
                    continue
                except Exception as exc:  # noqa: BLE001
                    _record_entity_fetch_exception(entity_id, entity_index, exc)
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
                execution_id,
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

    prepare_source_screen(execution_id, fetched_sources)
    for source in fetched_sources:
        issues: list[str] = []
        if source["quality"] == "Reject":
            issues.append("sourceScreen: source scored Reject")
        report_ref = _source_screen_report_ref(source["entityId"], source["sourceId"])
        write_stage_result(
            execution_id,
            "source",
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
            execution_id=execution_id,
            command="source",
            step="source_screen",
            ref=report_ref,
            passed=not issues,
            issues=data_issues(
                DataIssueCode.QUALITY_FAILED,
                stage=DataIssueStage.SOURCE_SCREEN,
                ref=report_ref,
                messages=issues,
                recovery=DataRecoveryAction.REPLACE_SOURCE,
            ),
            evidence_summary={
                "entityId": source["entityId"],
                "sourceId": source["sourceId"],
                "quality": source["quality"],
                "score": source["score"],
            },
            next_step="quality_analysis",
        )
    for entity_id, rows in quality_by_entity.items():
        retained = [row for row in rows if row["quality"] != "Reject"]
        issues: list[str] = []
        if text_lane_selected and len(retained) < 1:
            issues.append("sourceScreen: no retained source for entity")
        # 受控类目门：阻断无类别的 weather_* 散来源（天气应作为百科/官方/攻略来源内事实）。
        for source in _curated_sources_for_lanes(
            execution_id,
            entity_id,
            entity_type,
            selected_lanes,
        ):
            issues.extend(source_unit_category_issues(source["source_id"], source.get("platform") or ""))
        write_gate_report(
            execution_id=execution_id,
            command="source",
            step="entity_source_bundle",
            ref=entity_id,
            passed=not issues,
            issues=data_issues(
                DataIssueCode.SOURCE_RETAINED_SHORTFALL,
                stage=DataIssueStage.ENTITY_SOURCE_BUNDLE,
                ref=entity_id,
                messages=issues,
                recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
            ),
            evidence_summary={
                "sourceCount": len(rows),
                "retainedCount": len(retained),
                "qualities": [row["quality"] for row in rows],
            },
            next_step="quality_analysis",
        )
    print(
        f"[download] Planned {len(entities)} entity/entities and fetched {len(fetched_sources)} source bundle(s)",
        flush=True,
    )
    if defer_gate:
        _write_download_progress(
            execution_id,
            status="running",
            entity_count=len(entity_ids),
            sources=len(fetched_sources),
            message="source group completed; execution gate deferred",
        )
        print("[source] Execution gate deferred until all entity-type groups finish", flush=True)
        return
    gate_targets = successful_entity_ids or set(entity_ids)
    gate_issues = gate_download(execution_id, target_entities=gate_targets)
    if not successful_entity_ids:
        seen_gate_issues = set(gate_issues)
        gate_issues.extend(
            issue for issue in typed_fetch_issues if issue not in seen_gate_issues
        )
    gate_issues.extend(
        data_issue(
            DataIssueCode.MEDIA_FETCH_FAILED,
            stage=DataIssueStage.DOWNLOAD_FETCH,
            ref=entity_id,
            lane=DataIssueLane.IMAGE,
            recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
            message="image gates failed; unsafe or unauthorized images must not enter assets",
        )
        for entity_id in failed_image_entities
    )
    if gate_issues:
        print(f"[download] Gate FAILED ({len(gate_issues)} issue(s)):", file=sys.stderr, flush=True)
        for issue in gate_issues:
            print(f"  - {issue}", file=sys.stderr, flush=True)
        _write_download_progress(
            execution_id,
            status="failed",
            entity_count=len(entity_ids),
            sources=len(fetched_sources),
            message="; ".join(issue_messages(gate_issues[:5])),
        )
        raise SystemExit(1)
    _write_download_progress(
        execution_id,
        status="done",
        entity_count=len(entity_ids),
        sources=len(fetched_sources),
        message="download gate passed",
    )
    print("[source] Gate PASSED", flush=True)
