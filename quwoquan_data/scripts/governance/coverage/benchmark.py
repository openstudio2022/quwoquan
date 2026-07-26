"""规模化日产成熟度基准评估。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from core.io import write_json
from core.paths import RUNTIME_ROOT
from governance.coverage.vertical_inventory import evaluate_vertical_inventory, list_verticals
from governance.coverage.quality import verify_vertical_quality


def evaluate_benchmark(targets: list[int]) -> dict[str, Any]:
    if not targets or any(isinstance(target, bool) or target < 1 for target in targets):
        raise ValueError("benchmark targets must be explicit positive integers")
    coverage_reports = [evaluate_vertical_inventory(v) for v in list_verticals()]
    inventory_invalid = sum(r["status"] != "passed" for r in coverage_reports)
    quality_issues = verify_vertical_quality()
    results = []
    for target in targets:
        blockers: list[str] = []
        if inventory_invalid:
            blockers.append(f"invalid vertical inventories={inventory_invalid}")
        if quality_issues:
            blockers.append(f"vertical quality issues={len(quality_issues)}")
        blockers.append("runtime throughput and cost measurement receipt is required")
        results.append({
            "targetDailyPosts": target,
            "status": "passed" if not blockers else "blocked",
            "blockers": blockers,
        })
    return {
        "schema": "quwoquan.data_engineering_benchmark",
        "invalidInventoryCount": inventory_invalid,
        "qualityIssueCount": len(quality_issues),
        "targets": results,
    }


def write_benchmark_report(report: dict[str, Any], *, name: str = "latest") -> Path:
    out = RUNTIME_ROOT / "benchmarks" / f"{name}.json"
    write_json(out, report)
    return out


def render_benchmark(report: dict[str, Any]) -> str:
    lines = [
        f"[benchmark] invalidInventories={report['invalidInventoryCount']} qualityIssues={report['qualityIssueCount']}"
    ]
    for row in report["targets"]:
        lines.append(f"  {row['status'].upper()} {row['targetDailyPosts']}/day blockers={len(row['blockers'])}")
        for blocker in row["blockers"]:
            lines.append(f"    - {blocker}")
    return "\n".join(lines)
