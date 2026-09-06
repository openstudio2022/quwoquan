#!/usr/bin/env python3
"""Compact owner-scoped hotspot view for Agent PRE and plan-next.

读取顺序：本地最新 weekly report → 最新 OCI weekly fact（需要 oras）→ typed `unavailable`。
只投影已存在的报告字段，不重算、不建 backlog、不开 OPEN。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.code_health_evidence import pull_weekly_history  # noqa: E402
from quwoquan_ops.gate.code_health_delta.weekly import WEEKLY_SCHEMA  # noqa: E402

WEEKLY_ROOT = ROOT / ".qwq_output/env/repo/runs/code-health/weekly"
ACTIONABLE_WEEKS = 2


def _load_reports(paths: list[Path]) -> list[dict[str, Any]]:
    reports = []
    for path in paths:
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if isinstance(report, dict) and report.get("schema") == WEEKLY_SCHEMA:
            reports.append(report)
    return reports


def latest_local_report(weekly_root: Path = WEEKLY_ROOT) -> dict[str, Any] | None:
    reports = _load_reports(sorted(weekly_root.glob("*/report.json")))
    if not reports:
        return None
    return max(reports, key=lambda item: (str(item["window"]["end"]), str(item.get("observedAt", ""))))


def latest_oci_report(repository: str | None) -> dict[str, Any] | None:
    if not repository:
        return None
    with tempfile.TemporaryDirectory(prefix="qwq-code-health-hotspots-") as directory:
        result = pull_weekly_history(repository, limit=1, output_dir=Path(directory))
        if result["status"] != "available" or not result["reports"]:
            return None
        reports = _load_reports([Path(result["reports"][0]["path"])])
    return reports[0] if reports else None


def project(report: dict[str, Any], owner: str) -> dict[str, Any]:
    """Only this owner's hotspots and weak points, with the actionable streak flag."""
    prefix = owner.rstrip("/")
    persistence = {
        item["path"]: item["consecutiveWeeksInTopN"]
        for item in (report.get("hotspotPersistence") or {}).get("items", [])
    }
    hotspots = [
        {
            "path": item["path"], "score": item["score"], "lines": item["lines"],
            "maxCyclomatic": item["maxCyclomatic"], "maxCognitive": item["maxCognitive"],
            "cloneLines": item["cloneLines"], "changeFrequency": item["changeFrequency"],
            "consecutiveWeeksInTopN": persistence.get(item["path"], 1),
            "actionable": persistence.get(item["path"], 1) >= ACTIONABLE_WEEKS,
        }
        for item in report.get("topHotspots", [])
        if item["path"].startswith(prefix + "/") or item["ownerScope"] == prefix
    ]
    weak_points = [
        item for item in report.get("ownerScopeWeakPoints", [])
        if item["ownerScope"] == prefix or item["ownerScope"].startswith(prefix + "/")
    ]
    thresholds = {
        "fileLinesAdvisory": None, "fileLinesBlock": None,
    }
    tiers = (report.get("sizeDistribution") or {}).get("tiers") or []
    if len(tiers) >= 2:
        thresholds = {"fileLinesAdvisory": tiers[-2], "fileLinesBlock": tiers[-1]}
    return {
        "status": "available", "owner": prefix, "headSha": report["headSha"],
        "windowEnd": report["window"]["end"], "historyReports": (report.get("hotspotPersistence") or {}).get("historyReports", 0),
        "thresholds": thresholds,
        "hotspots": hotspots, "ownerScopeWeakPoints": weak_points,
        "actionableCount": sum(item["actionable"] for item in hotspots),
    }


def unavailable(owner: str, reason: str) -> dict[str, Any]:
    return {"status": "unavailable", "owner": owner.rstrip("/"), "reason": reason, "hotspots": [], "actionableCount": 0}


def render(projection: dict[str, Any]) -> str:
    if projection["status"] != "available":
        return f"code-health-hotspots: unavailable owner={projection['owner']} reason={projection['reason']}\n"
    lines = [
        f"code-health-hotspots: owner={projection['owner']} head={projection['headSha'][:12]} "
        f"window_end={projection['windowEnd'][:10]} history={projection['historyReports']} "
        f"actionable={projection['actionableCount']}",
    ]
    for item in projection["hotspots"]:
        flag = "ACTIONABLE" if item["actionable"] else "observe"
        lines.append(
            f"  - [{flag}] {item['path']} weeks={item['consecutiveWeeksInTopN']} lines={item['lines']} "
            f"cyc={item['maxCyclomatic']} cog={item['maxCognitive']} clone={item['cloneLines']} changes={item['changeFrequency']}"
        )
    for item in projection["ownerScopeWeakPoints"]:
        lines.append(
            f"  - weak-point {item['ownerScope']}: >advisory={item['overAdvisory']} >block={item['overBlock']} "
            f"complex={item['overComplexity']} clone={item['cloneLines']} dead={item['deadCandidates']}"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", required=True, help="Owner scope prefix, e.g. quwoquan_ops/gate")
    parser.add_argument("--weekly-root", type=Path, default=WEEKLY_ROOT)
    parser.add_argument("--oci-repository", default=os.environ.get("QWQ_CODE_HEALTH_WEEKLY_OCI", ""))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = latest_local_report(args.weekly_root) or latest_oci_report(args.oci_repository or None)
    projection = (
        project(report, args.owner) if report is not None
        else unavailable(args.owner, "no local weekly report and no reachable OCI weekly fact")
    )
    print(json.dumps(projection, ensure_ascii=False, sort_keys=True) if args.json else render(projection), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
