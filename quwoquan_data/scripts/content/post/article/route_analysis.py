"""Quality analysis stage for route production."""
from __future__ import annotations

from typing import Any, Mapping

from core.data_issue import DataIssueCode, DataIssueStage, DataRecoveryAction, data_issues
from content.post.article.evidence_bundle import (
    build_related_search_plan,
    build_route_evidence_bundle,
    gate_route_evidence_bundle,
    load_source_records,
)
from content.post.article.evidence_text import entity_names_from_refs
from content.post.object_index import content_type_from_brief, register_from_brief, require_title_hint
from core.evidence_contract import quality_payload_contract_issues
from content.execution.stage_reports import write_gate_report, write_repair_report, write_stage_result
from content.post.article.route_core import _unique_strings

def analyze_route_ref(execution_id: str, ref: str, brief: Mapping[str, Any]) -> dict[str, Any]:
    from content.post.object_index import content_type_from_brief, register_from_brief, require_title_hint

    register_from_brief(execution_id, ref, brief, content_type=content_type_from_brief(brief))
    title = require_title_hint(brief, ref=ref)
    entity_refs = [str(item) for item in brief.get("entityRefs") or [] if item]
    entity_names = entity_names_from_refs(entity_refs)
    base_source_ref = str(brief.get("baseSourceRef") or "").strip()
    source_records = load_source_records(
        execution_id,
        entity_names,
        entity_refs=entity_refs,
        base_source_ref=base_source_ref,
    )
    evidence_bundle = build_route_evidence_bundle(
        ref,
        brief,
        source_records,
        entity_refs=entity_refs,
        title=title,
    )
    source_quality = evidence_bundle.get("storySpine", {}).get("sourceQuality", [])
    issues = gate_route_evidence_bundle(brief, evidence_bundle)
    related_search_plan = (
        build_related_search_plan({"ref": ref, "entityRefs": entity_refs}, evidence_bundle["storySpine"])
        if issues
        else None
    )
    retained_scores = [int(row.get("score") or 0) for row in source_quality if row.get("quality") != "Reject"]
    retained_avg = sum(retained_scores) / max(len(retained_scores), 1) if retained_scores else 0
    coverage = evidence_bundle.get("coverage") or {}
    coverage_ratio = 0.0
    expected = int(coverage.get("expectedEntityCount") or 0)
    if expected:
        coverage_ratio = float(coverage.get("coveredEntityCount") or 0) / expected
    quality_score = round(min(100.0, retained_avg * 12 + coverage_ratio * 28))
    recommendation = "proceed" if not issues else ("skip" if coverage_ratio == 0 else "needs_improvement")
    payload = {
        "topicId": ref,
        "qualityScore": quality_score,
        "breakdown": {
            "depth": round(min(25.0, retained_avg * 4), 1),
            "originality": 22.0,
            "practicality": round(min(30.0, coverage_ratio * 30), 1),
            "readability": 20.0,
        },
        "recommendation": recommendation,
        "templateId": brief.get("templateId"),
        "title": title,
        "evidenceBundle": evidence_bundle,
        "sourceUrls": _unique_strings(str(row.get("url") or "") for row in source_records),
        "sourcePaths": _unique_strings(str(row.get("sourcePath") or "") for row in source_records),
    }
    contract_issues = quality_payload_contract_issues(payload)
    if contract_issues:
        issues = [*issues, *contract_issues]
        recommendation = "skip" if coverage_ratio == 0 else "needs_improvement"
        payload["recommendation"] = recommendation
    write_stage_result(execution_id, "post", "quality_analysis", ref, payload)
    write_gate_report(
        execution_id=execution_id,
        command="post",
        step="quality_analysis",
        ref=ref,
        passed=not issues,
        issues=data_issues(
            DataIssueCode.SOURCE_PLAN_INVALID,
            stage=DataIssueStage.QUALITY_ANALYSIS,
            ref=ref,
            messages=issues,
            recovery=DataRecoveryAction.REWIND_DOWNLOAD,
        ),
        evidence_summary={
            "coveredEntityCount": coverage.get("coveredEntityCount"),
            "expectedEntityCount": coverage.get("expectedEntityCount"),
            "retainedSourceCount": len(retained_scores),
            "relatedSearchPlan": related_search_plan,
        },
        next_step="compose-brief",
    )
    if issues:
        write_repair_report(
            execution_id=execution_id,
            command="post",
            ref=ref,
            failed_stage=DataIssueStage.QUALITY_ANALYSIS,
            failed_gate="routeEvidence",
            issues=data_issues(
                DataIssueCode.SOURCE_PLAN_INVALID,
                stage=DataIssueStage.QUALITY_ANALYSIS,
                ref=ref,
                messages=issues,
                recovery=DataRecoveryAction.REWIND_DOWNLOAD,
            ),
            evidence_summary={"relatedSearchPlan": related_search_plan},
            fallback_stage="download",
            rerun_chain=["download", "quality_analysis", "compose-brief", "review", "materialize"],
        )
    return payload

__all__ = [name for name in globals() if not name.startswith("__")]
