"""Exit gate for media check-images command。

unsafe（水印/平台文字/版权）即阻断；needs_review（人脸/后端缺失）记为待人工复核，
默认也阻断图文自动发布（strict）。
"""
from __future__ import annotations

from _common.stage_reports import iter_stage_envelopes


def gate_media_check(task_id: str, batch_id: str, *, allow_needs_review: bool = False) -> list[str]:
    issues: list[str] = []
    envelopes = iter_stage_envelopes(task_id, batch_id, "produce", "media_check")
    if not envelopes:
        return ["No media_check results produced"]
    for ref, envelope in envelopes:
        payload = envelope.get("payload") or {}
        summary = payload.get("summary") or {}
        if summary.get("unsafe"):
            issues.append(f"{ref}: {summary['unsafe']} unsafe image(s) (watermark/platform/copyright)")
        if summary.get("duplicateGroups"):
            issues.append(f"{ref}: {summary['duplicateGroups']} duplicate image group(s)")
        if not allow_needs_review and summary.get("needsReview"):
            issues.append(f"{ref}: {summary['needsReview']} image(s) need human review (faces/backend)")
    return issues
