#!/usr/bin/env python3
"""Collect dual-platform usability matrix evidence for Alpha/Beta/Gamma/Prod.

Success is only recorded when both platforms reach router shell and four-core
userneys pass. Missing Android physical, iPhone physical, signing, or public
recovery stays an honest GATE_BLOCK.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "quwoquan_app"
DEFAULT_REPORT = (
    ROOT
    / ".qwq_output"
    / "env"
    / "repo"
    / "runs"
    / "dual-platform-usability"
    / "matrix_report.json"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def run_command(command: list[str], *, cwd: Path | None = None) -> dict[str, Any]:
    started = utc_now()
    result = subprocess.run(
        command,
        cwd=str(cwd or ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "command": command,
        "startedAt": started,
        "endedAt": utc_now(),
        "exitCode": result.returncode,
        "stdoutTail": (result.stdout or "")[-4000:],
        "stderrTail": (result.stderr or "")[-4000:],
        "status": "passed" if result.returncode == 0 else "failed",
    }


def discover_devices() -> dict[str, Any]:
    flutter = shutil.which("flutter")
    adb = shutil.which("adb")
    devices: dict[str, Any] = {
        "iosSimulators": [],
        "androidPhysical": [],
        "iphonePhysical": [],
    }
    if flutter:
        listed = subprocess.run(
            [flutter, "devices", "--machine"],
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            check=False,
        )
        if listed.returncode == 0 and listed.stdout.strip():
            try:
                payload = json.loads(listed.stdout)
            except json.JSONDecodeError:
                payload = []
            for item in payload:
                if not isinstance(item, dict):
                    continue
                target = str(item.get("targetPlatform") or "")
                device_id = str(item.get("id") or "").strip()
                name = str(item.get("name") or "").strip()
                emulator = bool(item.get("emulator", False))
                if target.startswith("ios") and emulator:
                    devices["iosSimulators"].append(
                        {"id": device_id, "name": name}
                    )
                elif target.startswith("ios") and not emulator:
                    devices["iphonePhysical"].append(
                        {"id": device_id, "name": name}
                    )
                elif target.startswith("android") and not emulator:
                    devices["androidPhysical"].append(
                        {"id": device_id, "name": name}
                    )
    if adb and not devices["androidPhysical"]:
        listed = subprocess.run(
            [adb, "devices"],
            text=True,
            capture_output=True,
            check=False,
        )
        for line in (listed.stdout or "").splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                devices["androidPhysical"].append(
                    {"id": parts[0], "name": parts[0]}
                )
    return devices


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--skip-alpha-launch", action="store_true")
    parser.add_argument("--skip-gamma-t3", action="store_true")
    parser.add_argument("--ios-simulator-id", default="")
    parser.add_argument("--release-id", default="")
    parser.add_argument("--gamma-import-run-id", default="")
    args = parser.parse_args()

    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = ROOT / report_path
    report_path.parent.mkdir(parents=True, exist_ok=True)

    devices = discover_devices()
    ios_id = args.ios_simulator_id.strip()
    if not ios_id and devices["iosSimulators"]:
        ios_id = str(devices["iosSimulators"][0]["id"])

    report: dict[str, Any] = {
        "suiteId": "dual_platform_usability_matrix",
        "status": "running",
        "startedAt": utc_now(),
        "devices": devices,
        "checks": {},
        "stableBaseline": False,
        "gateBlocks": [],
    }

    report["checks"]["staticBaseline"] = run_command(
        [
            "python3",
            "quwoquan_app/scripts/runtime/verify_dual_platform_usability_baseline.py",
        ]
    )

    if args.skip_gamma_t3:
        report["checks"]["gammaCoreReadbackT3"] = {
            "status": "skipped",
            "reason": "skip-gamma-t3",
        }
    elif not args.release_id or not args.gamma_import_run_id:
        report["checks"]["gammaCoreReadbackT3"] = {
            "status": "gate_block",
            "reason": "release-id-and-gamma-import-run-id-required",
        }
    else:
        report["checks"]["gammaCoreReadbackT3"] = run_command(
            [
                "python3",
                "quwoquan_app/scripts/gamma/run_local_gamma_t3.py",
                "--release-id",
                args.release_id,
                "--import-run-id",
                args.gamma_import_run_id,
                "--report",
                str(
                    report_path.parent
                    / f"t3_app_core_readback_{utc_now()}.json"
                ),
            ]
        )

    if args.skip_alpha_launch:
        report["checks"]["alphaIosLauncher"] = {
            "status": "skipped",
            "reason": "skip-alpha-launch",
        }
    elif not ios_id:
        report["checks"]["alphaIosLauncher"] = {
            "status": "gate_block",
            "reason": "no iOS Simulator available for Alpha natural entry",
        }
        report["gateBlocks"].append("alpha_ios_simulator_missing")
    else:
        # Dry-run the launcher contract by validating run.sh device selection path
        # without leaving a long-lived flutter run attached to the agent.
        report["checks"]["alphaIosLauncher"] = run_command(
            [
                "bash",
                "-lc",
                (
                    f'test -x "{APP / "run.sh"}" && '
                    f'flutter devices | grep -F "{ios_id}" >/dev/null && '
                    'python3 quwoquan_app/scripts/runtime/verify_dual_platform_usability_baseline.py'
                ),
            ]
        )
        report["checks"]["alphaIosLauncher"]["deviceId"] = ios_id

    if not devices["androidPhysical"]:
        report["checks"]["alphaAndroidLauncher"] = {
            "status": "gate_block",
            "reason": (
                "Android physical device not attached; adb reverse + GetFeed "
                "path cannot be proven"
            ),
        }
        report["gateBlocks"].append("android_physical_missing")
    else:
        android_id = str(devices["androidPhysical"][0]["id"])
        report["checks"]["alphaAndroidLauncher"] = {
            "status": "gate_block",
            "deviceId": android_id,
            "reason": (
                "Android device visible but natural entry via "
                "quwoquan_app/run.sh -d <device> + four-core UI journey "
                "has not been proven in this evidence pack"
            ),
        }
        report["gateBlocks"].append("android_natural_entry_unproven")

    if not devices["iphonePhysical"]:
        report["checks"]["prodIphoneCanary"] = {
            "status": "gate_block",
            "reason": "iPhone physical / TestFlight evidence unavailable",
        }
        report["gateBlocks"].append("iphone_physical_missing")
    else:
        report["checks"]["prodIphoneCanary"] = {
            "status": "gate_block",
            "deviceId": devices["iphonePhysical"][0]["id"],
            "reason": "physical iPhone present but signed Prod canary not executed",
        }
        report["gateBlocks"].append("prod_iphone_canary_unproven")

    report["checks"]["betaRemote"] = {
        "status": "gate_block",
        "reason": (
            "Beta dual-end Remote package install + login + four-core readback "
            "requires self-hosted device matrix job app-core-readback"
        ),
    }
    report["gateBlocks"].append("beta_device_matrix_pending")

    t3_passed = report["checks"]["gammaCoreReadbackT3"].get("status") == "passed"
    static_passed = report["checks"]["staticBaseline"].get("status") == "passed"
    ios_ok = report["checks"]["alphaIosLauncher"].get("status") == "passed"
    # Stable baseline requires zero gate blocks and dual-end four-core proof.
    report["stableBaseline"] = bool(
        static_passed
        and t3_passed
        and ios_ok
        and not report["gateBlocks"]
    )
    if report["stableBaseline"]:
        report["status"] = "passed"
    elif any(
        check.get("status") == "failed"
        for check in report["checks"].values()
        if isinstance(check, dict)
    ):
        report["status"] = "failed"
    else:
        report["status"] = "gate_block"

    report["endedAt"] = utc_now()
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": report["status"], "report": str(report_path)}, ensure_ascii=False))
    if report["status"] == "passed":
        return 0
    if report["status"] == "gate_block":
        return 2
    return 1


if __name__ == "__main__":
    sys.exit(main())
