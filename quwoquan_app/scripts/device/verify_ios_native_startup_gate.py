#!/usr/bin/env python3
"""Verify that confirmed iOS startup fatal recovery never creates Flutter."""

from __future__ import annotations

import argparse
import json
import plistlib
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def run(*command: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=check,
        capture_output=True,
        text=True,
    )


def read_plist(path: Path) -> dict[str, Any]:
    with path.open("rb") as source:
        payload = plistlib.load(source)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a plist dictionary")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", required=True, help="Built Runner.app path")
    parser.add_argument("--simulator", default="booted")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    app = Path(args.app).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    issues: list[str] = []
    log_text = ""
    normal_log_text = ""
    bundle_id = ""
    process_id = ""
    normal_process_id = ""

    try:
        info = read_plist(app / "Info.plist")
        native_runtime = read_plist(app / "QWQNativeRuntime.plist")
        bundle_id = str(info.get("CFBundleIdentifier") or "").strip()
        build_number = str(info.get("CFBundleVersion") or "").strip()
        environment = str(
            native_runtime.get("runtimeEnvironment") or ""
        ).strip()
        runtime_digest = str(
            native_runtime.get("runtimeConfigDigest") or ""
        ).strip()
        defines_digest = str(
            native_runtime.get("dartDefinesDigest") or ""
        ).strip()
        launch_target = str(native_runtime.get("launchTarget") or "").strip()
        effective_digest = str(
            native_runtime.get("effectiveLaunchManifestDigest") or ""
        ).strip()
        if not bundle_id or not build_number or not environment:
            raise ValueError("iOS app runtime identity is incomplete")
        for label, digest in (
            ("runtime config", runtime_digest),
            ("Dart defines", defines_digest),
            ("effective launch manifest", effective_digest),
        ):
            if not digest.startswith("sha256:") or len(digest) != 71:
                raise ValueError(f"iOS {label} digest is invalid")
        if not launch_target:
            raise ValueError("iOS launch target is missing")

        run(
            "xcrun",
            "simctl",
            "uninstall",
            args.simulator,
            bundle_id,
            check=False,
        )
        run("xcrun", "simctl", "install", args.simulator, str(app))
        launched = run(
            "xcrun",
            "simctl",
            "launch",
            "--terminate-running-process",
            args.simulator,
            bundle_id,
            "--qwq-test-confirmed-startup-fatal",
        )
        process_id = launched.stdout.strip().rsplit(":", 1)[-1].strip()
        if not process_id.isdigit():
            raise ValueError(f"simctl launch did not return a PID: {launched.stdout}")
        time.sleep(4.0)
        log_result = run(
            "xcrun",
            "simctl",
            "spawn",
            args.simulator,
            "log",
            "show",
            "--last",
            "2m",
            "--style",
            "compact",
            "--predicate",
            f'processIdentifier == {process_id} AND eventMessage CONTAINS "QWQStartup"',
        )
        log_text = log_result.stdout
        (output_dir / "ios-native-startup-gate.log").write_text(
            log_text,
            encoding="utf-8",
        )
        run(
            "xcrun",
            "simctl",
            "io",
            args.simulator,
            "screenshot",
            str(output_dir / "ios-native-startup-recovery.png"),
        )

        if "ios_native_startup_gate_recovery" not in log_text:
            issues.append("confirmed native startup recovery gate was not observed")
        if "ios_native_startup_recovery_scene_connected" not in log_text:
            issues.append("native recovery scene did not connect")
        if "ios_implicit_flutter_engine_initialized" in log_text:
            issues.append("fatal recovery created the implicit Flutter engine")
        if "ios_did_finish_launching" in log_text:
            issues.append("fatal recovery entered the normal Flutter launch path")

        run(
            "xcrun",
            "simctl",
            "terminate",
            args.simulator,
            bundle_id,
            check=False,
        )
        run(
            "xcrun",
            "simctl",
            "uninstall",
            args.simulator,
            bundle_id,
        )
        run("xcrun", "simctl", "install", args.simulator, str(app))
        time.sleep(0.5)
        normal_launch = run(
            "xcrun",
            "simctl",
            "launch",
            args.simulator,
            bundle_id,
        )
        normal_process_id = normal_launch.stdout.strip().rsplit(":", 1)[-1].strip()
        if not normal_process_id.isdigit():
            raise ValueError(
                "normal simctl launch did not return a PID: "
                f"{normal_launch.stdout}"
            )
        time.sleep(4.0)
        normal_log = run(
            "xcrun",
            "simctl",
            "spawn",
            args.simulator,
            "log",
            "show",
            "--last",
            "2m",
            "--style",
            "compact",
            "--predicate",
            (
                f"processIdentifier == {normal_process_id} "
                'AND eventMessage CONTAINS "QWQStartup"'
            ),
        )
        normal_log_text = normal_log.stdout
        (output_dir / "ios-normal-startup.log").write_text(
            normal_log_text,
            encoding="utf-8",
        )
        if "ios_did_finish_launching" not in normal_log_text:
            issues.append("normal iOS startup did not enter Flutter launch path")
        if "ios_implicit_flutter_engine_initialized" not in normal_log_text:
            issues.append("normal iOS startup did not initialize implicit Flutter engine")
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        issues.append(str(error))
    finally:
        if bundle_id:
            run(
                "xcrun",
                "simctl",
                "terminate",
                args.simulator,
                bundle_id,
                check=False,
            )

    report = {
        "schema": "qwq.ios-native-startup-gate.v1",
        "status": "passed" if not issues else "GATE_BLOCK",
        "bundleId": bundle_id,
        "processId": process_id,
        "normalProcessId": normal_process_id,
        "fatalFlutterEngineCreated": (
            "ios_implicit_flutter_engine_initialized" in log_text
        ),
        "fatalLaunchEnteredFlutterPath": "ios_did_finish_launching" in log_text,
        "normalFlutterEngineCreated": (
            "ios_implicit_flutter_engine_initialized" in normal_log_text
        ),
        "normalLaunchEntered": "ios_did_finish_launching" in normal_log_text,
        "normalLaunchVerified": (
            "ios_did_finish_launching" in normal_log_text
            and "ios_implicit_flutter_engine_initialized" in normal_log_text
        ),
        "issues": issues,
    }
    (output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not issues else 2


if __name__ == "__main__":
    sys.exit(main())
