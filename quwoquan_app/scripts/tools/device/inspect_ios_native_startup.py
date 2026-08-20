#!/usr/bin/env python3
"""Verify that confirmed iOS startup fatal recovery never creates Flutter."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

_SCRIPTS_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file()
)
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from _common.paths import APP_ROOT

_OPS_ROOT = APP_ROOT.parent
if str(_OPS_ROOT) not in sys.path:
    sys.path.insert(0, str(_OPS_ROOT))

from quwoquan_ops.cli.lib.app_identity import application_id_for

# 生产 iOS 工程不持有 test target；恢复面 XCUITest runner 归物理隔离的 test host。
PATROL_HOST_IOS_DIR = APP_ROOT / "test_host/patrol/ios"


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


def public_web_identity(native_runtime: dict[str, Any]) -> dict[str, str]:
    raw_url = str(native_runtime.get("publicWebURL") or "").strip()
    parsed = urlsplit(raw_url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ValueError("iOS publicWebURL must be an exact trusted HTTPS URL")
    return {
        "publicWebURL": raw_url,
        "publicWebURLDigest": "sha256:"
        + hashlib.sha256(raw_url.encode("utf-8")).hexdigest(),
    }


def resolve_simulator_udid(simulator: str) -> str:
    if simulator != "booted":
        return simulator
    result = run(
        "xcrun",
        "simctl",
        "getenv",
        "booted",
        "SIMULATOR_UDID",
    )
    device_id = result.stdout.strip()
    if not device_id:
        raise ValueError("booted iOS Simulator UDID is unavailable")
    return device_id


def verify_web_cta_with_xcuitest(
    *,
    simulator_udid: str,
    environment: str,
    expected_url_digest: str,
    output_dir: Path,
) -> dict[str, Any]:
    test_environment = dict(os.environ)
    for key in (
        "QWQ_APP_RUNTIME_ENV",
        "QWQ_APP_LAUNCH_MODE",
        "QWQ_LAUNCH_TARGET",
        "QWQ_LAUNCH_HANDOFF_JSON",
        "QWQ_DART_DEFINES_DIGEST",
        "QWQ_EXPECTED_RUNTIME_CONFIG_DIGEST",
        "QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST",
    ):
        test_environment.pop(key, None)
    test_environment["QWQ_ENVIRONMENT"] = environment
    test_environment["QWQ_IOS_SIMULATOR_UDID"] = simulator_udid
    test_environment["QWQ_IOS_TARGET_BUNDLE_ID"] = application_id_for(
        "ios", environment, "debug"
    )
    command = [
        "xcodebuild",
        "-workspace",
        "Runner.xcworkspace",
        "-scheme",
        "Runner",
        "-configuration",
        "Debug",
        "-destination",
        f"platform=iOS Simulator,id={simulator_udid}",
        "-destination-timeout",
        "60",
        (
            "-only-testing:RunnerUITests/"
            "QWQNativeStartupRecoveryWebUITests/"
            "testRecoveryWebCTAOpensSafariAndReturnsToSameProcess"
        ),
        "test",
    ]
    log_started_at = time.strftime("%Y-%m-%d %H:%M:%S")
    test = subprocess.run(
        command,
        cwd=PATROL_HOST_IOS_DIR,
        env=test_environment,
        check=False,
        capture_output=True,
        text=True,
    )
    test_output = test.stdout + test.stderr
    (output_dir / "ios-native-startup-web-cta-xcuitest.log").write_text(
        test_output,
        encoding="utf-8",
    )
    time.sleep(1.0)
    app_log = run(
        "xcrun",
        "simctl",
        "spawn",
        simulator_udid,
        "log",
        "show",
        "--start",
        log_started_at,
        "--style",
        "compact",
        "--predicate",
        (
            'eventMessage CONTAINS "ios_native_recovery_external_open" '
            'OR eventMessage CONTAINS "ios_native_recovery_external_returned"'
        ),
    ).stdout
    (output_dir / "ios-native-startup-web-cta-app.log").write_text(
        app_log,
        encoding="utf-8",
    )
    requested = (
        "ios_native_recovery_external_open_requested "
        f"urlDigest={expected_url_digest}"
    ) in app_log
    opened = (
        "ios_native_recovery_external_open_completed "
        f"urlDigest={expected_url_digest} opened=true"
    ) in app_log
    safari_foreground = (
        "QWQNativeStartupUITest recovery_web_cta_safari_foreground"
        in test_output
    )
    returned_foreground = (
        "QWQNativeStartupUITest recovery_web_cta_returned_app_foreground"
        in test_output
    )
    requested_process_id = ""
    same_process = False
    request_pattern = re.compile(
        r"ios_native_recovery_external_open_requested "
        rf"urlDigest={re.escape(expected_url_digest)} processId=(\d+)"
    )
    return_pattern = re.compile(
        r"ios_native_recovery_external_returned processId=(\d+)"
    )
    for line in app_log.splitlines():
        request_match = request_pattern.search(line)
        if request_match:
            requested_process_id = request_match.group(1)
            continue
        return_match = return_pattern.search(line)
        if return_match and requested_process_id:
            same_process = return_match.group(1) == requested_process_id
            requested_process_id = ""
    return {
        "xcodeTestPassed": test.returncode == 0,
        "trustedExactPublicWebURLRequested": requested,
        "safariForegroundObserved": safari_foreground,
        "trustedExactPublicWebURLOpened": opened,
        "sameAppProcessAfterReturn": same_process and returned_foreground,
        "xcodeTestExitCode": test.returncode,
        "xcodeTestLog": str(
            output_dir / "ios-native-startup-web-cta-xcuitest.log"
        ),
        "appOpenLog": str(
            output_dir / "ios-native-startup-web-cta-app.log"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", required=True, help="Built Runner.app path")
    parser.add_argument("--simulator", default="booted")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    app = Path(args.app).expanduser()
    if not app.is_absolute():
        app = APP_ROOT / app
    app = app.resolve()
    output_dir = Path(args.output_dir).expanduser()
    if not output_dir.is_absolute():
        output_dir = APP_ROOT / output_dir
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    issues: list[str] = []
    log_text = ""
    normal_log_text = ""
    bundle_id = ""
    process_id = ""
    normal_process_id = ""
    web_identity: dict[str, str] = {}
    web_cta_result: dict[str, Any] = {}

    try:
        info = read_plist(app / "Info.plist")
        native_runtime = read_plist(app / "QWQNativeRuntime.plist")
        bundle_id = str(info.get("CFBundleIdentifier") or "").strip()
        build_number = str(info.get("CFBundleVersion") or "").strip()
        environment = str(
            native_runtime.get("runtimeEnvironment") or ""
        ).strip()
        web_identity = public_web_identity(native_runtime)
        simulator_udid = resolve_simulator_udid(args.simulator)
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
            "terminate",
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

        web_cta_result = verify_web_cta_with_xcuitest(
            simulator_udid=simulator_udid,
            environment=environment,
            expected_url_digest=web_identity["publicWebURLDigest"],
            output_dir=output_dir,
        )
        for key, message in (
            ("xcodeTestPassed", "native recovery Web CTA XCUITest failed"),
            (
                "trustedExactPublicWebURLRequested",
                "Web CTA did not request the exact trusted publicWebURL",
            ),
            (
                "safariForegroundObserved",
                "Web CTA did not put Safari in the foreground",
            ),
            (
                "trustedExactPublicWebURLOpened",
                "Safari did not open the exact trusted publicWebURL",
            ),
            (
                "sameAppProcessAfterReturn",
                "App did not return in the same native recovery process",
            ),
        ):
            if not web_cta_result.get(key):
                issues.append(message)

        run(
            "xcrun",
            "simctl",
            "terminate",
            args.simulator,
            bundle_id,
            check=False,
        )
        run("xcrun", "simctl", "install", args.simulator, str(app))
        time.sleep(0.5)
        normal_launch = run(
            "xcrun",
            "simctl",
            "launch",
            args.simulator,
            bundle_id,
            "--qwq-test-clear-startup-fatal",
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
        "schema": "qwq.ios-native-startup-gate",
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
        **web_identity,
        "webCta": web_cta_result,
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
