"""规模化日产成熟度基准评估。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from core.io import write_json
from core.paths import RUNTIME_ROOT
from governance.coverage.coverage import evaluate_registry, list_verticals
from governance.coverage.quality import verify_vertical_quality


TARGETS = [1000, 10000, 100000]


def evaluate_benchmark(targets: list[int] | None = None) -> dict[str, Any]:
    selected_targets = targets or TARGETS
    coverage_reports = [evaluate_registry(v) for v in list_verticals()]
    coverage_gap_units = sum(r["totals"]["gapUnits"] for r in coverage_reports)
    quality_issues = verify_vertical_quality()
    results = []
    for target in selected_targets:
        blockers: list[str] = []
        if coverage_gap_units:
            blockers.append(f"coverage gap units={coverage_gap_units}")
        if quality_issues:
            blockers.append(f"vertical quality issues={len(quality_issues)}")
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
        "schema": "quwoquan.data_engineering_benchmark",
        "coverageGapUnits": coverage_gap_units,
        "qualityIssueCount": len(quality_issues),
        "targets": results,
    }


def write_benchmark_report(report: dict[str, Any], *, name: str = "latest") -> Path:
    out = RUNTIME_ROOT / "benchmarks" / f"{name}.json"
    write_json(out, report)
    return out


def render_benchmark(report: dict[str, Any]) -> str:
    lines = [
        f"[benchmark] coverageGapUnits={report['coverageGapUnits']} qualityIssues={report['qualityIssueCount']}"
    ]
    for row in report["targets"]:
        lines.append(f"  {row['status'].upper()} {row['targetDailyPosts']}/day blockers={len(row['blockers'])}")
        for blocker in row["blockers"]:
            lines.append(f"    - {blocker}")
    return "\n".join(lines)
