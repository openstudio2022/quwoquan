#!/usr/bin/env python3
"""Run gamma Patrol on every mobile device visible to the self-hosted Mac runner."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from device_matrix_evidence import (
    capture_device_screenshot,
    repo_relative,
    sanitize_device_id,
    write_device_manifest,
    write_discovered_devices_snapshot,
    write_json,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "quwoquan_app"
DEFAULT_REPORT = REPO_ROOT / "artifacts" / "device-matrix" / "gamma-patrol" / "report.json"
DEFAULT_TARGET = "test/patrol/discovery/feed_load_test.dart"
IOS_SDK_VERSION_PATTERN = re.compile(r"iOS[- ](\d+)(?:[-._](\d+))?")
XCODE_GLOBAL_PRODUCTS_DIR = Path.home() / "Library" / "Developer" / "Xcode" / "XcodeDerivedData" / "Build" / "Products"
PATROL_IOS_PRODUCTS_DIR = APP_DIR / "build" / "ios_integ" / "Build" / "Products"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--target", default=DEFAULT_TARGET)
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    parser.add_argument("--env-name", default="gamma")
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
    parser.add_argument("--device-id", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def summarize_output(output: str, *, max_lines: int = 120) -> str:
    lines = output.splitlines()
    if len(lines) <= max_lines:
        return output
    return "\n".join(
        [
            f"... omitted {len(lines) - max_lines} earlier lines ...",
            *lines[-max_lines:],
        ]
    )


def run_command(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout_seconds: int | None = None,
    log_path: Path | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    process: subprocess.Popen[str] | None = None
    try:
        process = subprocess.Popen(
            command,
            cwd=str(cwd),
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        output, _ = process.communicate(timeout=timeout_seconds)
        output = output or ""
        exit_code = process.returncode
        timed_out = False
    except subprocess.TimeoutExpired:
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                output, _ = process.communicate(timeout=10)
            except Exception:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except Exception:
                    pass
                output = ""
        else:
            output = ""
        exit_code = 124
        timed_out = True
    result = {
        "command": command,
        "cwd": str(cwd),
        "exitCode": exit_code,
        "timedOut": timed_out,
        "durationMs": int((time.monotonic() - started) * 1000),
        "outputSummary": summarize_output(output),
    }
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(output, encoding="utf-8")
        result["logPath"] = repo_relative(log_path)
    return result


def ios_sdk_version(device: dict[str, Any]) -> tuple[int, int] | None:
    sdk = str(device.get("sdk", "")).strip()
    match = IOS_SDK_VERSION_PATTERN.search(sdk)
    if match is None:
        return None
    major = int(match.group(1))
    minor = int(match.group(2) or 0)
    return (major, minor)


def discover_devices(platform: str, device_ids: list[str]) -> list[dict[str, Any]]:
    payload = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "discover_flutter_mobile_devices.py"),
        ],
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    if payload.returncode != 0:
        raise RuntimeError(
            "discover_flutter_mobile_devices.py failed:\n"
            + summarize_output((payload.stdout or "") + (payload.stderr or ""))
        )
    data = json.loads(payload.stdout)
    devices = list(data.get("devices") or [])
    allowed_ids = {item for item in device_ids if item}
    selected: list[dict[str, Any]] = []
    for device in devices:
        target = str(device.get("targetPlatform", "")).lower()
        device_id = str(device.get("id", "")).strip()
        if not device_id:
            continue
        if allowed_ids and device_id not in allowed_ids:
            continue
        if platform == "android" and not target.startswith("android"):
            continue
        if platform == "ios" and target != "ios":
            continue
        if platform == "all" and target != "ios" and not target.startswith("android"):
            continue
        selected.append(device)
    if not allowed_ids and platform in ("ios", "all"):
        latest_ios_sdk = max(
            (
                version
                for device in selected
                if str(device.get("targetPlatform", "")).lower() == "ios"
                for version in [ios_sdk_version(device)]
                if version is not None
            ),
            default=None,
        )
        if latest_ios_sdk is not None:
            selected = [
                device
                for device in selected
                if str(device.get("targetPlatform", "")).lower() != "ios"
                or ios_sdk_version(device) == latest_ios_sdk
            ]
    return selected


def patrol_command(device: dict[str, Any], args: argparse.Namespace) -> list[str]:
    gamma_base_url = args.gateway_base_url.strip()
    gamma_product_ops_base_url = args.product_ops_base_url.strip()
    gamma_test_auth_token = args.test_auth_token.strip()
    media_base_url = os.environ.get("MEDIA_AVATAR_CDN_BASE_URL", "").strip()
    command = [
        "patrol",
        "test",
        "-t",
        args.target,
        "-d",
        str(device["id"]),
        "--dart-define=RUN_T4_PATROL=true",
        "--dart-define=APP_RUNTIME_ENV=gamma",
        "--dart-define=APP_DATA_SOURCE=remote",
        "--dart-define=API_CONTRACT_ENV=gamma",
        f"--dart-define=CLOUD_GATEWAY_BASE_URL={gamma_base_url}",
        f"--dart-define=API_CONTRACT_BASE_URL={gamma_base_url}",
        f"--dart-define=API_CONTRACT_PRODUCT_OPS_BASE_URL={gamma_product_ops_base_url}",
        f"--dart-define=TEST_AUTH_TOKEN={gamma_test_auth_token}",
    ]
    if media_base_url:
        command.extend(
            [
                f"--dart-define=MEDIA_AVATAR_CDN_BASE_URL={media_base_url}",
                f"--dart-define=MEDIA_IMAGE_CDN_BASE_URL={media_base_url}",
                f"--dart-define=MEDIA_VIDEO_CDN_BASE_URL={media_base_url}",
                f"--dart-define=MEDIA_UPLOAD_BASE_URL={media_base_url}",
            ]
        )
    return command


def ensure_patrol_ios_products_bridge() -> None:
    """Bridge Patrol's expected ios_integ products path to Xcode 26 global products."""
    patrol_products = PATROL_IOS_PRODUCTS_DIR
    patrol_products.parent.mkdir(parents=True, exist_ok=True)
    if patrol_products.is_symlink():
        try:
            if patrol_products.resolve() == XCODE_GLOBAL_PRODUCTS_DIR.resolve():
                return
        except FileNotFoundError:
            patrol_products.unlink()
    elif patrol_products.exists():
        return
    patrol_products.symlink_to(XCODE_GLOBAL_PRODUCTS_DIR)


def dry_run_devices(args: argparse.Namespace) -> list[dict[str, Any]]:
    raw_ids = args.device_id or ["dry-run-device"]
    devices = []
    for device_id in raw_ids:
        target_platform = "ios" if args.platform == "ios" else "android-arm64"
        if args.platform == "all":
            target_platform = "ios"
        devices.append(
            {
                "id": device_id,
                "name": "Dry Run Device",
                "targetPlatform": target_platform,
                "sdk": "dry-run",
                "emulator": True,
                "screenClass": "phone",
            }
        )
    return devices


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = REPO_ROOT / report_path

    report: dict[str, Any] = {
        "suiteId": "content_feed_patrol",
        "status": "failed",
        "startedAt": utc_now(),
        "endedAt": "",
        "environmentAlias": args.env_name,
        "target": args.target,
        "platform": args.platform,
        "gatewayBaseUrl": args.gateway_base_url,
        "productOpsBaseUrl": args.product_ops_base_url,
        "devices": [],
        "runs": [],
        "failureReason": "",
        "deviceInventoryPath": "",
        "evidenceRoot": "",
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
            report["failureReason"] = f"missing required env: {', '.join(missing)}"
            report["endedAt"] = utc_now()
            write_report(report_path, report)
            return 2

    try:
        devices = dry_run_devices(args) if args.dry_run else discover_devices(args.platform, args.device_id)
    except Exception as exc:  # noqa: BLE001
        report["status"] = "failed"
        report["failureReason"] = str(exc)
        report["endedAt"] = utc_now()
        write_report(report_path, report)
        return 1

    if not devices:
        report["status"] = "gate_block"
        report["failureReason"] = "no mobile Flutter devices available on self-hosted Mac runner"
        report["endedAt"] = utc_now()
        write_report(report_path, report)
        return 2

    report["devices"] = devices
    evidence_root = report_path.parent / "runs"
    report["evidenceRoot"] = repo_relative(evidence_root)
    report["deviceInventoryPath"] = write_discovered_devices_snapshot(
        report_path.parent / "discovered_devices.json",
        devices,
        suite="gamma-patrol-matrix",
        requested_environments=[args.env_name],
        extra={
            "target": args.target,
            "platform": args.platform,
            "reportPath": repo_relative(report_path),
        },
    )
    failed = False
    for device in devices:
        run_dir = evidence_root / sanitize_device_id(str(device.get("id", "")))
        run_dir.mkdir(parents=True, exist_ok=True)
        device_manifest_path = write_device_manifest(
            run_dir / "device.json",
            device,
            env_name="gamma",
            suite="gamma-patrol-matrix",
            extra={"target": args.target},
        )
        if str(device.get("targetPlatform", "")).lower() == "ios":
            ensure_patrol_ios_products_bridge()
        command = patrol_command(device, args)
        command_path = write_json(
            run_dir / "command.json",
            {
                "capturedAt": utc_now(),
                "target": args.target,
                "deviceId": device["id"],
                "command": command,
            },
        )
        before_screenshot = capture_device_screenshot(device, run_dir / "before.png")
        print(
            f"[gamma-patrol-matrix] run on {device['name']} ({device['id']}, {device['targetPlatform']})",
            flush=True,
        )
        if args.dry_run:
            log_path = run_dir / "patrol.log"
            log_path.write_text("dry-run\n", encoding="utf-8")
            result = {
                "command": command,
                "cwd": str(APP_DIR),
                "exitCode": 0,
                "timedOut": False,
                "durationMs": 0,
                "outputSummary": "dry-run",
                "logPath": repo_relative(log_path),
            }
        else:
            result = run_command(
                command,
                cwd=APP_DIR,
                timeout_seconds=args.timeout_seconds,
                log_path=run_dir / "patrol.log",
            )
        after_screenshot = (
            capture_device_screenshot(device, run_dir / "after.png")
            if result["exitCode"] == 0 and not args.dry_run
            else {"status": "skipped", "reason": "command failed"}
        )
        failure_screenshot = (
            capture_device_screenshot(device, run_dir / "failure.png")
            if result["exitCode"] != 0 and not args.dry_run
            else {"status": "skipped", "reason": "command passed"}
        )
        result["device"] = device
        result["evidence"] = {
            "runDirectory": repo_relative(run_dir),
            "deviceManifestPath": device_manifest_path,
            "commandPath": command_path,
            "rawLogPath": result.get("logPath", ""),
            "beforeScreenshot": before_screenshot,
            "afterScreenshot": after_screenshot,
            "failureScreenshot": failure_screenshot,
        }
        report["runs"].append(result)
        failed = failed or result["exitCode"] != 0

    report["status"] = "failed" if failed else "passed"
    if failed:
        report["failureReason"] = "one or more Patrol runs failed"
    report["endedAt"] = utc_now()
    write_report(report_path, report)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
