"""Image-safety stage service used only by the execution orchestrator."""
from __future__ import annotations

from core.data_issue import DataIssueCode, DataIssueStage, DataRecoveryAction, data_issues
from core.image_safety import assess_asset_sources
from core.io import read_json
from content.execution.stage_reports import (
    iter_stage_envelopes,
    read_stage_envelope,
    write_gate_report,
    write_stage_result,
)


def _collect_assets_for_ref(execution_id: str, ref: str) -> list[dict]:
    """优先取 compose 结果里的 assets（含 sourcePath），回退到 materialized manifest。"""
    envelope = read_stage_envelope(execution_id, "post", "compose", ref)
    if envelope:
        payload = envelope.get("payload") or {}
        assets = payload.get("assets") or []
        if assets:
            return list(assets)
    # 回退：经路由定位内容对象成品 manifest（对象根 posts/{type}/{angle}/{title}/{seq}）。
    from content.post import object_index as content_object

    if content_object.content_coords(execution_id, ref):
        manifest = content_object.content_object_dir(execution_id, ref) / "manifest.json"
        if manifest.is_file():
            return list(read_json(manifest).get("assets") or [])
    return []


def _iter_refs(execution_id: str, refs: list[str]) -> list[str]:
    if refs:
        return refs
    return [ref for ref, _ in iter_stage_envelopes(execution_id, "post", "compose")]


def check_images(execution_id: str, refs: list[str], *, allow_needs_review: bool = False) -> list[dict]:
    statuses: list[dict] = []
    for ref in _iter_refs(execution_id, refs):
        assets = _collect_assets_for_ref(execution_id, ref)
        report = assess_asset_sources(assets)
        write_stage_result(execution_id, "post", "media_check", ref, report)
        summary = report["summary"]
        passed = summary["unsafe"] == 0 and summary["duplicateGroups"] == 0 and (
            allow_needs_review or summary["needsReview"] == 0
        )
        write_gate_report(
            execution_id=execution_id,
            command="post",
            step="media_check",
            ref=ref,
            passed=passed,
            issues=[] if passed else data_issues(
                DataIssueCode.QUALITY_FAILED,
                stage=DataIssueStage.MEDIA_CHECK,
                ref=ref,
                messages=_issues_from_summary(ref, summary, allow_needs_review),
                recovery=DataRecoveryAction.REWIND_COMPOSE,
            ),
            evidence_summary=summary,
            next_step="review" if passed else None,
        )
        statuses.append({"ref": ref, "passed": passed, "summary": summary})
    return statuses


def _issues_from_summary(ref: str, summary: dict, allow_needs_review: bool) -> list[str]:
    issues: list[str] = []
    if summary["unsafe"]:
        issues.append(f"{summary['unsafe']} unsafe image(s)")
    if summary["duplicateGroups"]:
        issues.append(f"{summary['duplicateGroups']} duplicate group(s)")
    if not allow_needs_review and summary["needsReview"]:
        issues.append(f"{summary['needsReview']} image(s) need human review")
    return issues


__all__ = ["check_images"]
