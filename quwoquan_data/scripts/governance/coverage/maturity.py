"""规模化成熟度评估。"""
from __future__ import annotations

from typing import Any


LEVELS = [
    (1, "脚本可跑"),
    (2, "单批可恢复、有质量门"),
    (3, "千级/万级批量、coverage 可计数、preflight 阻断"),
    (4, "10 万级日产、worker 化、合法素材供应链、post-activation 扫描"),
    (5, "持续运营、自动扩容、质量漂移闭环、成本/版权/发布风险可观测"),
]


def evaluate_maturity(*, coverage_status: str, has_license_policy: bool, has_worker_queue: bool, has_post_activation: bool) -> dict[str, Any]:
    level = 2
    blockers: list[str] = []
    if coverage_status == "passed":
        level = max(level, 3)
    else:
        blockers.append("coverage registry has gaps")
    if not has_license_policy:
        blockers.append("image license policy not enforced")
    if not has_worker_queue:
        blockers.append("worker queue not implemented")
    if not has_post_activation:
        blockers.append("post-activation consistency scan not implemented")
    if has_license_policy and has_worker_queue and has_post_activation and coverage_status == "passed":
        level = 4
    return {
        "schema": "quwoquan.data_engineering_maturity",
        "level": level,
        "levelLabel": dict(LEVELS)[level],
        "blockers": blockers,
    }


def render_maturity(report: dict[str, Any]) -> str:
    lines = [f"[maturity] L{report['level']} {report['levelLabel']}"]
    for blocker in report.get("blockers") or []:
        lines.append(f"  BLOCKER {blocker}")
    return "\n".join(lines)
