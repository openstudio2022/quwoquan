#!/usr/bin/env python3
# spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/spec.md#sit-001
# spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/spec.md#open-003
# spec_ref: specs/feature-tree/spec.md#uat-009
# readiness_case: circle_journey_local_gamma_e2e
"""local-gamma SCN-014 主旅程 E2E 聚合器：API journey probe + 设备矩阵段。

前置：`stackctl health --target gamma-local --scope full` 通过、
`stackctl verify` 注入 gamma ActorLease handoff。设备矩阵段需要已构建 App 与
连接的设备；物理真机缺失时如实标注 blocked，不用模拟器结果冒充 physical
ResultBundle（member-role-permission OPEN-004 保持 BLOCK）。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def _find_repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "quwoquan_app").is_dir() and (candidate / "quwoquan_service").is_dir():
            return candidate
    raise RuntimeError("cannot locate quwoquan repo root")


ROOT = _find_repo_root()
sys.path.insert(0, str(ROOT))
SUPPORT_DIR = Path(__file__).resolve().parents[1] / "support"
if str(SUPPORT_DIR) not in sys.path:
    sys.path.insert(0, str(SUPPORT_DIR))

from quwoquan_ops.cli.lib.environment_topology import (  # noqa: E402
    get_target,
    load_environment_topology,
)
from managed_circle_journey_handoff import (  # noqa: E402
    load_journey_handoff_from_environment,
)

SCHEMA = "circle-journey-local-gamma-e2e-report"
SCENARIO = "circle.scn014.homepage_to_group_conversation.local_gamma"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    public_bases = get_target(load_environment_topology(), "gamma-local")["publicBases"]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=public_bases["api"])
    parser.add_argument("--homepage-query", default="西湖")
    parser.add_argument(
        "--device-matrix",
        choices=("skip", "simulator", "physical"),
        default="skip",
        help="设备矩阵段：skip 只跑 API journey；simulator 跑双端模拟器矩阵；physical 需要真机",
    )
    parser.add_argument(
        "--report",
        default=".qwq_output/env/gamma/runs/circle-journey-e2e/report.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "suiteId": "circle_journey_scn014",
        "scenario": SCENARIO,
        "status": "running",
        "failureCategory": "",
        "blockingReason": "",
        "startedAt": utc_now(),
        "endedAt": "",
        "testDataLifecycle": {},
        "baseUrl": args.base_url,
        "journeyProbe": {},
        "deviceMatrix": {"mode": args.device_matrix, "status": "skipped"},
    }
    report_path = ROOT / args.report
    exit_code = 0
    try:
        handoff = load_journey_handoff_from_environment()
        if handoff.environment != "gamma":
            raise ValueError("local-gamma circle journey requires a gamma ActorLease handoff")
        report["testDataLifecycle"] = handoff.public_document()

        probe_report_path = report_path.parent / "journey_probe_report.json"
        probe_cmd = [
            sys.executable,
            str(
                ROOT
                / "quwoquan_ops/tests/acceptance/user_acceptance/service_ops/"
                "circle-service/smoke/run_circle_journey_probe.py"
            ),
            "--env",
            "gamma",
            "--base-url",
            args.base_url,
            "--homepage-query",
            args.homepage_query,
            "--report",
            str(probe_report_path.relative_to(ROOT)),
        ]
        probe = subprocess.run(
            probe_cmd,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=600,
        )
        if probe_report_path.is_file():
            report["journeyProbe"] = json.loads(probe_report_path.read_text("utf-8"))
        if probe.returncode != 0:
            raise RuntimeError(
                "journey probe failed: "
                + str(report["journeyProbe"].get("blockingReason") or probe.stdout[-400:])
            )

        if args.device_matrix == "skip":
            report["deviceMatrix"] = {
                "mode": "skip",
                "status": "skipped",
                "note": "API journey evidence only; device matrix explicitly not requested",
            }
        else:
            # 设备矩阵段前置由调用方保证（已构建 App + 连接设备）；physical 无真机
            # 时此处如实 blocked，禁止用模拟器结果冒充 physical ResultBundle。
            report["deviceMatrix"] = {
                "mode": args.device_matrix,
                "status": "blocked",
                "blockingReason": (
                    "device matrix runner integration is pending; "
                    "physical devices must be attached by operations before OPEN-004 can close"
                ),
            }
        report["status"] = "passed" if args.device_matrix == "skip" else "partial"
    except (RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        report["status"] = "blocked" if isinstance(exc, ValueError) else "failed"
        report["failureCategory"] = (
            "handoff_invalid" if isinstance(exc, ValueError) else "journey_failed"
        )
        report["blockingReason"] = str(exc)
        exit_code = 2 if isinstance(exc, ValueError) else 1
    finally:
        report["endedAt"] = utc_now()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"report: {report_path}")
        print(f"status: {report['status']} {report['blockingReason']}".rstrip())
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
