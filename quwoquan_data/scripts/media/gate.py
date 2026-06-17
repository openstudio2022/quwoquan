"""Exit gate for media check-images command。

unsafe（水印/平台文字/版权）即阻断；needs_review（人脸/后端缺失）记为待人工复核。
produce review 阶段可选择放行为账本待人工项，真正发布前仍由 publish_filter / ship 准入裁决。
"""
from __future__ import annotations

from collections.abc import Iterable

from _common.stage_reports import iter_stage_envelopes


def gate_media_check(
    task_id: str,
    batch_id: str,
    *,
    allow_needs_review: bool = False,
    refs: Iterable[str] | None = None,
) -> list[str]:
    issues: list[str] = []
    allowed = {str(ref) for ref in refs or []}
    envelopes = iter_stage_envelopes(task_id, batch_id, "produce", "media_check")
    if not envelopes:
        return ["No media_check results produced"]
    for ref, envelope in envelopes:
        if allowed and ref not in allowed:
            continue
        payload = envelope.get("payload") or {}
        summary = payload.get("summary") or {}
        if summary.get("unsafe"):
            issues.append(f"{ref}: {summary['unsafe']} unsafe image(s) (watermark/platform/copyright)")
        if summary.get("duplicateGroups"):
            issues.append(f"{ref}: {summary['duplicateGroups']} duplicate image group(s)")
        if not allow_needs_review and summary.get("needsReview"):
            issues.append(f"{ref}: {summary['needsReview']} image(s) need human review (faces/backend)")
    return issues
