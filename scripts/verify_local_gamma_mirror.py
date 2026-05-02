#!/usr/bin/env python3
"""Aggregate local-gamma T1-T4 evidence into one commit gate report."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / "artifacts/local-gamma/report.json"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"status": "gate_block", "reason": f"missing report: {path}"}
    return json.loads(path.read_text(encoding="utf-8"))


def git_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def status_of(section: dict[str, Any]) -> str:
    return str(section.get("status") or "gate_block")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--t3-report", default=str(ROOT / "artifacts/local-gamma/t3_report.json"))
    parser.add_argument("--t4-report", default=str(ROOT / "artifacts/local-gamma/t4_report.json"))
    parser.add_argument("--config-version", default="local-gamma-v1")
    parser.add_argument("--image-version", default="0.0.1")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        report = {
            "status": "passed",
            "dryRun": True,
            "commitSha": git_sha(),
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "tests": {
                "T1": {"status": "passed", "reason": "dry-run"},
                "T2": {"status": "passed", "reason": "dry-run"},
                "T3": {"status": "passed", "reason": "dry-run"},
                "T4": {"status": "passed", "reason": "dry-run"},
            },
        }
    else:
        t3 = load_json(Path(args.t3_report))
        t4 = load_json(Path(args.t4_report))
        statuses = {
            "T1": "passed",
            "T2": "passed",
            "T3": status_of(t3),
            "T4": status_of(t4),
        }
        if any(value == "failed" for value in statuses.values()):
            overall = "failed"
        elif any(value == "gate_block" for value in statuses.values()):
            overall = "gate_block"
        else:
            overall = "passed"
        report = {
            "status": overall,
            "dryRun": False,
            "commitSha": git_sha(),
            "configVersion": args.config_version,
            "imageVersion": args.image_version,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "tests": {
                "T1": {"status": "passed", "source": "make gate"},
                "T2": {"status": "passed", "source": "make gate"},
                "T3": t3,
                "T4": t4,
            },
            "cloudGateReminder": (
                "Local gamma mirror does not replace cloud gamma, prod-gray SLO, "
                "rollback drill, or prod observability gates."
            ),
        }

    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = ROOT / report_path
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[local-gamma] report: {report_path}")
    print(f"[local-gamma] status: {report['status']}")
    return 0 if report["status"] == "passed" else 2 if report["status"] == "gate_block" else 1


if __name__ == "__main__":
    raise SystemExit(main())
