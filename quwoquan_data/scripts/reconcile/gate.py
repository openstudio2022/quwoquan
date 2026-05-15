"""Exit gate for reconcile command."""
from __future__ import annotations

from _common.paths import batch_results_dir
from .diff import compute_diff


def gate_reconcile(task_id: str, batch_id: str) -> list[str]:
    """Re-run diff after patches; gate passes when drifts == 0 and pending items are addressed."""
    diff_report = compute_diff(task_id, batch_id)
    issues = []

    if diff_report.get("totalDrifts", 0) > 0:
        issues.append(f"Still {diff_report['totalDrifts']} drifts remaining")

    patch_plan_dir = batch_results_dir(task_id, batch_id, "reconcile", "patch_plan")
    has_patch_plan = patch_plan_dir.exists() and any(patch_plan_dir.glob("*.json"))

    if not has_patch_plan:
        pending_e = diff_report.get("pendingEntities", [])
        pending_t = diff_report.get("pendingTags", [])
        if pending_e:
            issues.append(f"{len(pending_e)} pending entities not yet processed")
        if pending_t:
            issues.append(f"{len(pending_t)} pending tags not yet processed")

    return issues
