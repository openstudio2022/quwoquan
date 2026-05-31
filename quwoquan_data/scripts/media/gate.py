"""Exit gate for media check-images command。

unsafe（水印/平台文字/版权）即阻断；needs_review（人脸/后端缺失）记为待人工复核，
默认也阻断图文自动发布（strict）。
"""
from __future__ import annotations

from _common.io import read_json
from _common.paths import batch_results_dir


def gate_media_check(task_id: str, batch_id: str, *, allow_needs_review: bool = False) -> list[str]:
    issues: list[str] = []
    results_dir = batch_results_dir(task_id, batch_id, "produce", "media_check")
    if not results_dir.exists() or not any(results_dir.glob("*.json")):
        return ["No media_check results produced"]
    for result_file in sorted(results_dir.glob("*.json")):
        payload = read_json(result_file).get("payload") or {}
        ref = result_file.stem
        summary = payload.get("summary") or {}
        if summary.get("unsafe"):
            issues.append(f"{ref}: {summary['unsafe']} unsafe image(s) (watermark/platform/copyright)")
        if summary.get("duplicateGroups"):
            issues.append(f"{ref}: {summary['duplicateGroups']} duplicate image group(s)")
        if not allow_needs_review and summary.get("needsReview"):
            issues.append(f"{ref}: {summary['needsReview']} image(s) need human review (faces/backend)")
    return issues
