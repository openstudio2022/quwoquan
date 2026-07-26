#!/usr/bin/env python3
"""Aggregate local-gamma gate evidence into one commit gate report."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.output_paths import env_run_dir, target_process_dir  # noqa: E402
# Gamma verification evidence belongs to one run. Stack status is process
# state, so it remains in the only allowed local/process directory.
GAMMA_RUN_ROOT = Path(
    os.environ.get("QWQ_RUN_ROOT")
    or env_run_dir("gamma", "verify-local-gamma", target="gamma-local")
)
DEFAULT_REPORT = GAMMA_RUN_ROOT / "report.json"
DEFAULT_STACK_REPORT = target_process_dir("gamma-local") / "stack_status.json"
START_SCRIPT = ROOT / "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"
README = ROOT / "quwoquan_ops/environments/gamma/local/README.md"


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


def static_contract_issues() -> list[str]:
    """Guard local-gamma against falling back to retired taxonomy projections."""
    retired_tags_path = "/".join(("publish", "v1", "tags"))
    issues: list[str] = []
    for path in (START_SCRIPT, README):
        text = path.read_text(encoding="utf-8")
        if retired_tags_path in text:
            issues.append(f"{path.relative_to(ROOT)} still references {retired_tags_path}")
    script = START_SCRIPT.read_text(encoding="utf-8")
    expected = "$ROOT/quwoquan_data/control_plane/governance/taxonomy"
    if expected not in script:
        issues.append(
            "start_local_gamma_mirror.sh must default LOCAL_GAMMA_TAGS_DIR "
            "to quwoquan_data/control_plane/governance/taxonomy"
        )
    if "bootstrap_local_gamma_tag_taxonomy" in script:
        issues.append("local-gamma must not materialize a runtime taxonomy copy")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--stack-report", default=str(DEFAULT_STACK_REPORT))
    parser.add_argument("--t3-report", default=str(GAMMA_RUN_ROOT / "t3_report.json"))
    parser.add_argument("--t4-report", default=str(GAMMA_RUN_ROOT / "t4_report.json"))
    parser.add_argument("--config-version", default="local-gamma-v1")
    parser.add_argument("--image-version", default="0.0.1")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    static_issues = static_contract_issues()
    if static_issues:
        for issue in static_issues:
            print(f"[local-gamma] FAIL: {issue}")
        return 1

    if args.dry_run:
        report = {
            "status": "passed",
            "dryRun": True,
            "commitSha": git_sha(),
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "gammaValidationSuiteRegistry": "quwoquan_ops/environments/gamma/validation_suites.json",
            "serviceMode": "single-stack",
            "restartedFromPrevious": False,
            "tests": {
                "T1": {"status": "passed", "reason": "dry-run"},
                "T2": {"status": "passed", "reason": "dry-run"},
                "T3": {"status": "passed", "reason": "dry-run"},
                "T4": {"status": "passed", "reason": "dry-run"},
            },
        }
    else:
        stack = load_json(Path(args.stack_report))
        t3 = load_json(Path(args.t3_report))
        t4 = load_json(Path(args.t4_report))
        statuses = {
            "T1": "passed",
            "T2": "passed",
            "stack": status_of(stack),
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
            "gammaValidationSuiteRegistry": "quwoquan_ops/environments/gamma/validation_suites.json",
            "serviceMode": str(stack.get("serviceMode") or "single-stack"),
            "restartedFromPrevious": bool(stack.get("restartedFromPrevious")),
            "stack": stack,
            "tests": {
                "T1": {"status": "passed", "source": "make gate"},
                "T2": {"status": "passed", "source": "make gate"},
                "T3": t3,
                "T4": t4,
            },
            "prodGateReminder": (
                "Local gamma mirror does not replace prod-hosted validation, prod SLO, "
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
