"""Execution service extracted from the retired monolithic runner."""
from __future__ import annotations
from content.execution.coverage import coverage_entity_type, coverage_entity_type_for_entity
from content.execution.support import Any, DataIssue, DataIssueCode, DataIssueStage, DataIssueLane, DataRecoveryAction, ExecutionContext, Mapping, Path, Sequence, _download_diagnostic_image_repair_hints, _download_issue_repair_hints, _research_image_repair_hints, data_issue, execution_command_root, execution_root, issue_messages, read_json, store, write_json

def _record_download_repair(ctx: ExecutionContext, issues: Sequence[DataIssue]) -> Path:
    """把真实抓取门失败转成下一轮 Agent 可消费的对象级 repair packet。"""
    from content.execution.recovery.download_gate import _download_repair_fetch_only_retryable, _download_repair_path, _download_research_lane_issues, _source_plan_revision
    from content.execution.recovery.download_unresolved import _issue_mentions_entity_id
    from core.download_diagnostics import entity_download_diagnostics
    from content.source.source_unit import resolve_entity_object_dir
    batch_etype = coverage_entity_type(ctx.spec)
    entities: list[dict[str, Any]] = []
    root = execution_root(ctx.execution_id)
    result_root = execution_command_root(ctx.execution_id, "source") / "results"
    path = _download_repair_path(ctx)
    previous_by_entity: dict[str, dict[str, Any]] = {}
    if path.is_file():
        try:
            previous_packet = read_json(path)
        except (OSError, ValueError, TypeError):
            previous_packet = {}
        previous_by_entity = {
            str(item.get("entityId") or ""): item
            for item in (previous_packet.get("entities") or [])
            if isinstance(item, dict)
        }
    issue_records = list(issues)
    if not all(isinstance(issue, DataIssue) for issue in issue_records):
        raise TypeError("download repair requires typed DataIssue records")
    issue_entity_hits: dict[str, list[DataIssue]] = {
        entity_id: [
            issue for issue in issue_records if _issue_mentions_entity_id(entity_id, issue)
        ]
        for entity_id in ctx.entity_ids
    }
    general_issues = [
        issue
        for issue in issue_records
        if not any(issue in rows for rows in issue_entity_hits.values())
    ]
    for entity_id in ctx.entity_ids:
        entity_etype = (
            coverage_entity_type_for_entity(ctx.spec, entity_id) or batch_etype
        )
        entity_issue_records = list(issue_entity_hits.get(entity_id) or [])
        if not entity_issue_records and len(ctx.entity_ids) == 1:
            entity_issue_records.extend(general_issues)
        if not entity_issue_records:
            continue
        research_lane_issue_records = {
            lane: _download_research_lane_issues(
                ctx,
                entity_id,
                entity_etype,
                lane,
            )
            for lane in ("homepage", "article", "image")
        }
        combined_issue_records = list(entity_issue_records)
        for lane_records in research_lane_issue_records.values():
            for issue in lane_records:
                if issue not in combined_issue_records:
                    combined_issue_records.append(issue)
        entity_issues = issue_messages(combined_issue_records)
        plan_dir = (
            resolve_entity_object_dir(
                ctx.execution_id,
                entity_id,
                etype_hint=entity_etype,
            )
            / "1.download"
        )
        lane_paths = [
            plan_dir / name
            for name in (
                "homepage_source_plan.json",
                "article_source_plan.json",
                "image_source_plan.json",
            )
        ]
        existing_lane_paths = [path for path in lane_paths if path.is_file()]
        plan_paths = existing_lane_paths or lane_paths
        source_plan_revision = _source_plan_revision(plan_paths)
        diagnostics = entity_download_diagnostics(root, entity_id)
        image_repair_hints = _download_issue_repair_hints(
            combined_issue_records,
            entity_id=entity_id,
        )
        image_repair_hints.extend(
            _research_image_repair_hints(ctx, entity_id, entity_etype)
        )
        image_repair_hints.extend(
            _download_diagnostic_image_repair_hints(diagnostics, entity_id=entity_id)
        )
        previous = previous_by_entity.get(entity_id) or {}
        same_plan = str(previous.get("sourcePlanRevision") or "") == source_plan_revision
        probe_repair = {
            "entityId": entity_id,
            "issues": entity_issues,
            "issueRecords": [issue.as_dict() for issue in combined_issue_records],
            "sourcePlanRevision": source_plan_revision,
            "downloadDiagnostics": diagnostics,
            "imageRepairHints": image_repair_hints,
            "fetchRetryCount": (
                int(previous.get("fetchRetryCount") or 0)
                if same_plan
                else 0
            ),
        }
        fetch_retry_count = 0
        if _download_repair_fetch_only_retryable(probe_repair):
            fetch_retry_count = int(probe_repair.get("fetchRetryCount") or 0) + 1
        entities.append(
            {
                "entityId": entity_id,
                "issues": entity_issues,
                "issueRecords": [issue.as_dict() for issue in combined_issue_records],
                "sourcePlanPath": str(plan_paths[0]),
                "sourcePlanPaths": [str(path) for path in plan_paths],
                "sourcePlanRevision": source_plan_revision,
                "fetchRetryCount": fetch_retry_count,
                "reportPaths": [
                    str(result_root / "entity_source_bundle_gate" / f"{entity_id}.json"),
                    str(result_root / "image_fetch_gate" / f"{entity_id}.json"),
                    str(result_root / "image_rights_gate" / f"{entity_id}.json"),
                ],
                "downloadDiagnostics": diagnostics,
                "imageRepairHints": image_repair_hints,
            }
        )
    write_json(
        path,
        {
            "schema": "quwoquan.download_repair",
            "executionId": ctx.execution_id,
            "createdAt": store.now_iso(),
            "entities": entities,
        },
    )
    return path
