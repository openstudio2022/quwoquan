#!/usr/bin/env python3
"""Run gamma Patrol journeys for a named validation profile."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List


REPO_ROOT = Path(__file__).resolve().parents[3]
REGISTRY_PATH = REPO_ROOT / "deploy" / "shared" / "gamma_validation_suites.json"
RUNNER = REPO_ROOT / "scripts" / "run_gamma_patrol_matrix_ci.py"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="nightly_full")
    parser.add_argument(
        "--report",
        default="artifacts/gamma-validation/ui/nightly_full/report.json",
    )
    parser.add_argument(
        "--gateway-base-url",
        default=os.environ.get("GAMMA_BASE_URL", "").strip(),
    )
    parser.add_argument(
        "--product-ops-base-url",
        default=os.environ.get("GAMMA_PRODUCT_OPS_BASE_URL", "").strip(),
    )
    parser.add_argument(
        "--test-auth-token",
        default=os.environ.get("GAMMA_TEST_AUTH_TOKEN", "").strip(),
    )
    parser.add_argument("--platform", choices=("android", "ios", "all"), default="all")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def load_registry() -> Dict[str, Any]:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def load_report(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_report(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_suite(
    *,
    suite_id: str,
    suite: Dict[str, Any],
    args: argparse.Namespace,
    suite_report_path: Path,
) -> Dict[str, Any]:
    command = [
        sys.executable,
        str(RUNNER),
        "--report",
        str(suite_report_path),
        "--target",
        str(suite.get("target", "")).strip(),
        "--env-name",
        "gamma",
        "--platform",
        args.platform,
        "--gateway-base-url",
        args.gateway_base_url,
        "--product-ops-base-url",
        args.product_ops_base_url,
        "--test-auth-token",
        args.test_auth_token,
    ]
    if args.dry_run:
        command.append("--dry-run")
    started = time.monotonic()
    result = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    suite_report = load_report(suite_report_path)
    return {
        "suiteId": suite_id,
        "target": suite.get("target", ""),
        "tier": suite.get("tier", ""),
        "budgetSeconds": suite.get("budgetSeconds", 0),
        "longTailType": suite.get("longTailType", ""),
        "optimizationPlan": suite.get("optimizationPlan", ""),
        "status": suite_report.get("status", "failed"),
        "exitCode": result.returncode,
        "durationMs": int((time.monotonic() - started) * 1000),
        "reportPath": str(suite_report_path.relative_to(REPO_ROOT)),
        "outputSummary": (result.stdout or "")[-1200:],
    }


def main() -> int:
    args = parse_args()
    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = REPO_ROOT / report_path
    registry = load_registry()
    profiles = registry.get("profiles") or {}
    profile = profiles.get(args.profile)
    if not isinstance(profile, dict):
        raise SystemExit("unknown gamma validation profile: {0}".format(args.profile))
    journey_ids = list(profile.get("uiJourneys") or [])
    journeys = registry.get("uiJourneys") or {}
    if not journey_ids:
        raise SystemExit("profile {0} has no uiJourneys".format(args.profile))

    report: Dict[str, Any] = {
        "profile": args.profile,
        "status": "running",
        "startedAt": utc_now(),
        "endedAt": "",
        "platform": args.platform,
        "gatewayBaseUrl": args.gateway_base_url,
        "productOpsBaseUrl": args.product_ops_base_url,
        "runs": [],
    }
    if not args.dry_run:
        missing = [
            name
            for name, value in (
                ("gateway_base_url", args.gateway_base_url),
                ("product_ops_base_url", args.product_ops_base_url),
                ("test_auth_token", args.test_auth_token),
            )
            if not str(value).strip()
        ]
        if missing:
            report["status"] = "gate_block"
            report["blockingReason"] = "missing required env: {0}".format(", ".join(missing))
            report["endedAt"] = utc_now()
            write_report(report_path, report)
            return 2

    overall_exit_code = 0
    for journey_id in journey_ids:
        suite = journeys.get(journey_id)
        if not isinstance(suite, dict):
            report["runs"].append(
                {
                    "suiteId": journey_id,
                    "status": "gate_block",
                    "exitCode": 2,
                    "outputSummary": "missing uiJourneys definition",
                }
            )
            overall_exit_code = max(overall_exit_code, 2)
            continue
        suite_report_path = report_path.parent / journey_id / "report.json"
        run = run_suite(
            suite_id=journey_id,
            suite=suite,
            args=args,
            suite_report_path=suite_report_path,
        )
        report["runs"].append(run)
        overall_exit_code = max(overall_exit_code, run["exitCode"])

    if overall_exit_code == 0:
        report["status"] = "passed"
    elif overall_exit_code == 2:
        report["status"] = "gate_block"
    else:
        report["status"] = "failed"
    report["endedAt"] = utc_now()
    write_report(report_path, report)
    print("[gamma-patrol-profile] profile={0} status={1}".format(args.profile, report["status"]))
    print("[gamma-patrol-profile] report: {0}".format(report_path))
    return overall_exit_code


if __name__ == "__main__":
    raise SystemExit(main())
