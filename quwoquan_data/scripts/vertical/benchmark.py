"""规模化日产成熟度基准评估。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from _common.io import write_json
from _common.paths import RUNTIME_ROOT
from task.queue import QUEUE_ROOT
from vertical.coverage import evaluate_registry, list_verticals
from vertical.quality import verify_vertical_quality


TARGETS = [1000, 10000, 100000]


def evaluate_benchmark(targets: list[int] | None = None) -> dict[str, Any]:
    selected_targets = targets or TARGETS
    coverage_reports = [evaluate_registry(v) for v in list_verticals()]
    coverage_gap_units = sum(r["totals"]["gapUnits"] for r in coverage_reports)
    quality_issues = verify_vertical_quality()
    has_queue = QUEUE_ROOT.exists()
    results = []
    for target in selected_targets:
        blockers: list[str] = []
        if coverage_gap_units:
            blockers.append(f"coverage gap units={coverage_gap_units}")
        if quality_issues:
            blockers.append(f"vertical quality issues={len(quality_issues)}")
        if not has_queue:
            blockers.append("task queue has not been initialized")
        if target >= 10000:
            blockers.append("no measured worker throughput/cost budget report")
        if target >= 100000:
            blockers.append("no distributed queue/autoscaling evidence")
        results.append({
            "targetDailyPosts": target,
            "status": "passed" if not blockers else "blocked",
            "blockers": blockers,
        })
    return {
        "schemaVersion": "quwoquan.data_engineering_benchmark.v1",
        "coverageGapUnits": coverage_gap_units,
        "qualityIssueCount": len(quality_issues),
        "hasQueueRuntime": has_queue,
        "targets": results,
    }


def write_benchmark_report(report: dict[str, Any], *, name: str = "latest") -> Path:
    out = RUNTIME_ROOT / "benchmarks" / f"{name}.json"
    write_json(out, report)
    return out


def render_benchmark(report: dict[str, Any]) -> str:
    lines = [
        f"[benchmark] coverageGapUnits={report['coverageGapUnits']} qualityIssues={report['qualityIssueCount']} queue={report['hasQueueRuntime']}"
    ]
    for row in report["targets"]:
        lines.append(f"  {row['status'].upper()} {row['targetDailyPosts']}/day blockers={len(row['blockers'])}")
        for blocker in row["blockers"]:
            lines.append(f"    - {blocker}")
    return "\n".join(lines)
