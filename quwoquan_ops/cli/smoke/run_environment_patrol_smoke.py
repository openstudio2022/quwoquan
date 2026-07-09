#!/usr/bin/env python3
"""Run page-level Patrol smoke tests for one environment target."""

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
import urllib.parse
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from quwoquan_ops.ci.device_matrix.evidence import (
    capture_device_screenshot,
    repo_relative,
    sanitize_device_id,
    write_device_manifest,
    write_discovered_devices_snapshot,
    write_json,
)
from quwoquan_ops.cli.lib.dev_up import (
    ANDROID_LOCAL_DEBUG_CA_ENV,
    ANDROID_LOCAL_DEBUG_CA_PATHS,
    ANDROID_LOCAL_DEBUG_CA_REQUIRED_ENV,
)
from quwoquan_ops.cli.lib.patrol_cli import resolve_patrol_cli


APP_DIR = REPO_ROOT / "quwoquan_app"
DEFAULT_REPORT = REPO_ROOT / ".qwq_output" / "runs" / "device-matrix" / "environment-smoke" / "report.json"
DEFAULT_TARGET = "test/patrol/environment/basic_viability_test.dart"
IOS_SDK_VERSION_PATTERN = re.compile(r"iOS[- ](\d+)(?:[-._](\d+))?")
XCODE_GLOBAL_PRODUCTS_DIR = Path.home() / "Library" / "Developer" / "Xcode" / "XcodeDerivedData" / "Build" / "Products"
PATROL_IOS_PRODUCTS_DIR = APP_DIR / "build" / "ios_integ" / "Build" / "Products"
LOCAL_TARGETS = {"alpha-local", "beta-local", "gamma-local", "prod-sim"}
PUBLIC_TEST_SUFFIX = ".quwoquan-env.test"
LOCALHOST_SUFFIX = ".localhost"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _runtime_env_for_alias(alias: str) -> str:
    normalized = alias.strip().lower()
    if normalized in {"prod", "prod-sim", "prod-hosted"}:
        return "prod"
    if "gamma" in normalized:
        return "gamma"
    if "beta" in normalized:
        return "beta"
    return "alpha"


def _data_source_for_runtime(runtime_env: str) -> str:
    return "mock" if runtime_env == "alpha" else "remote"


def _is_local_target(env_name: str) -> bool:
    return env_name.strip() in LOCAL_TARGETS


def _device_uses_local_loopback(device: dict[str, Any]) -> bool:
    target = str(device.get("targetPlatform", "")).strip().lower()
    if target.startswith("android"):
        return True
    return target == "ios" and bool(device.get("emulator", False))


def _rewrite_local_loopback_base(url: str) -> str:
    parsed = urllib.parse.urlparse(url.strip())
    if not parsed.scheme or not parsed.hostname:
        return url
    host = parsed.hostname
    if host == "127.0.0.1":
        host = "localhost"
    elif host.endswith(PUBLIC_TEST_SUFFIX):
        host = host[: -len(PUBLIC_TEST_SUFFIX)] + LOCALHOST_SUFFIX
    elif host == "localhost" or host.endswith(LOCALHOST_SUFFIX):
        host = host
    else:
        return url
    if parsed.port:
        netloc = f"{host}:{parsed.port}"
    else:
        netloc = host
    return urllib.parse.urlunparse(parsed._replace(netloc=netloc))


def _effective_base_urls_for_device(
    args: argparse.Namespace,
    device: dict[str, Any],
) -> dict[str, str]:
    gateway_base_url = args.gateway_base_url.strip()
    product_ops_base_url = args.product_ops_base_url.strip()
    media_base_url = args.media_base_url.strip()
    if _is_local_target(args.env_name) and _device_uses_local_loopback(device):
        gateway_base_url = _rewrite_local_loopback_base(gateway_base_url)
        product_ops_base_url = _rewrite_local_loopback_base(product_ops_base_url)
        media_base_url = _rewrite_local_loopback_base(media_base_url)
    return {
        "gatewayBaseUrl": gateway_base_url,
        "productOpsBaseUrl": product_ops_base_url,
        "mediaBaseUrl": media_base_url,
    }


def _resolved_current_user_id(args: argparse.Namespace) -> str:
    explicit = str(getattr(args, "current_user_id", "") or "").strip()
    if explicit:
        return explicit
    if _is_local_target(args.env_name):
        return "fixture_user_current"
    return ""


def _local_debug_ca_path(env_name: str) -> Path | None:
    path = ANDROID_LOCAL_DEBUG_CA_PATHS.get(env_name.strip())
    if path is None:
        return None
    return path if path.is_file() else None


def _install_booted_simulator_root_ca(cert_path: Path) -> dict[str, Any]:
    try:
        result = subprocess.run(
            ["xcrun", "simctl", "keychain", "booted", "add-root-cert", str(cert_path)],
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        return {
            "status": "skipped",
            "reason": "xcrun unavailable",
            "certPath": str(cert_path),
        }
    output = summarize_output((result.stdout or "") + (result.stderr or ""))
    return {
        "status": "attempted" if result.returncode == 0 else "best_effort_failed",
        "exitCode": result.returncode,
        "certPath": str(cert_path),
        "outputSummary": output,
    }


def _device_command_env(args: argparse.Namespace, device: dict[str, Any]) -> dict[str, str]:
    env = dict(os.environ)
    cert_path = _local_debug_ca_path(args.env_name)
    target = str(device.get("targetPlatform", "")).strip().lower()
    if target.startswith("android") and cert_path is not None:
        env[ANDROID_LOCAL_DEBUG_CA_ENV] = str(cert_path)
        env[ANDROID_LOCAL_DEBUG_CA_REQUIRED_ENV] = "1"
    return env


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--target", default=DEFAULT_TARGET)
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    parser.add_argument("--env-name", "--environment-alias", dest="env_name", default="gamma-local")
    parser.add_argument("--runtime-env", default="")
    parser.add_argument("--api-contract-env", default="")
    parser.add_argument("--data-source", choices=("mock", "remote"), default="")
    parser.add_argument("--gateway-base-url", default="")
    parser.add_argument("--product-ops-base-url", default="")
    parser.add_argument("--media-base-url", default="")
    parser.add_argument("--test-auth-token", default=os.environ.get("TEST_AUTH_TOKEN", "").strip())
    parser.add_argument("--current-user-id", default=os.environ.get("APP_CURRENT_USER_ID", "").strip())
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
            str(REPO_ROOT / "quwoquan_app" / "scripts" / "device" / "discover_flutter_mobile_devices.py"),
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


def patrol_command(device: dict[str, Any], args: argparse.Namespace, patrol_executable: str = "patrol") -> list[str]:
    runtime_env = args.runtime_env.strip() or _runtime_env_for_alias(args.env_name)
    api_contract_env = args.api_contract_env.strip() or runtime_env
    data_source = args.data_source.strip() or _data_source_for_runtime(runtime_env)
    base_urls = _effective_base_urls_for_device(args, device)
    gateway_base_url = base_urls["gatewayBaseUrl"]
    product_ops_base_url = base_urls["productOpsBaseUrl"]
    media_base_url = base_urls["mediaBaseUrl"]
    current_user_id = _resolved_current_user_id(args)
    command = [
        patrol_executable,
        "test",
        "-t",
        args.target,
        "-d",
        str(device["id"]),
        "--dart-define=RUN_T4_PATROL=true",
        f"--dart-define=APP_RUNTIME_ENV={runtime_env}",
        f"--dart-define=APP_DATA_SOURCE={data_source}",
        f"--dart-define=API_CONTRACT_ENV={api_contract_env}",
        f"--dart-define=CLOUD_GATEWAY_BASE_URL={gateway_base_url}",
        f"--dart-define=API_CONTRACT_BASE_URL={gateway_base_url}",
        f"--dart-define=API_CONTRACT_PRODUCT_OPS_BASE_URL={product_ops_base_url}",
        f"--dart-define=TEST_AUTH_TOKEN={args.test_auth_token.strip()}",
    ]
    if current_user_id:
        command.append(f"--dart-define=APP_CURRENT_USER_ID={current_user_id}")
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


def _missing_required_args(args: argparse.Namespace) -> list[str]:
    required = [
        ("gateway_base_url", args.gateway_base_url),
        ("product_ops_base_url", args.product_ops_base_url),
        ("test_auth_token", args.test_auth_token),
    ]
    return [name for name, value in required if not str(value).strip()]


def main() -> int:
    args = parse_args()
    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = REPO_ROOT / report_path

    runtime_env = args.runtime_env.strip() or _runtime_env_for_alias(args.env_name)
    api_contract_env = args.api_contract_env.strip() or runtime_env
    data_source = args.data_source.strip() or _data_source_for_runtime(runtime_env)
    report: dict[str, Any] = {
        "suiteId": "environment_page_smoke",
        "status": "failed",
        "startedAt": utc_now(),
        "endedAt": "",
        "environmentAlias": args.env_name,
        "runtimeEnv": runtime_env,
        "apiContractEnv": api_contract_env,
        "dataSource": data_source,
        "target": args.target,
        "platform": args.platform,
        "gatewayBaseUrl": args.gateway_base_url,
        "productOpsBaseUrl": args.product_ops_base_url,
        "mediaBaseUrl": args.media_base_url,
        "currentUserId": _resolved_current_user_id(args),
        "devices": [],
        "runs": [],
        "failureReason": "",
        "deviceInventoryPath": "",
        "evidenceRoot": "",
    }
    patrol_resolution = resolve_patrol_cli()
    patrol_executable = patrol_resolution.executable or "patrol"
    report["patrolCli"] = patrol_resolution.as_report(required=not args.dry_run)

    if not args.dry_run:
        if patrol_resolution.executable is None:
            report["status"] = "gate_block"
            report["failureReason"] = patrol_resolution.error
            report["endedAt"] = utc_now()
            write_report(report_path, report)
            return 2
        missing = _missing_required_args(args)
        if missing:
            report["status"] = "gate_block"
            report["failureReason"] = f"missing required args: {', '.join(missing)}"
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
        suite="environment-page-smoke",
        requested_environments=[args.env_name],
        extra={
            "target": args.target,
            "runtimeEnv": runtime_env,
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
            env_name=args.env_name,
            suite="environment-page-smoke",
            extra={"target": args.target, "runtimeEnv": runtime_env},
        )
        if str(device.get("targetPlatform", "")).lower() == "ios":
            ensure_patrol_ios_products_bridge()
        tls_trust = {"status": "skipped", "reason": "not-required"}
        if (
            _is_local_target(args.env_name)
            and str(device.get("targetPlatform", "")).lower() == "ios"
            and bool(device.get("emulator", False))
        ):
            cert_path = _local_debug_ca_path(args.env_name)
            if cert_path is None:
                tls_trust = {
                    "status": "missing",
                    "reason": f"local debug root CA missing for {args.env_name}",
                }
            else:
                tls_trust = _install_booted_simulator_root_ca(cert_path)
        command = patrol_command(device, args, patrol_executable)
        command_env = _device_command_env(args, device)
        command_path = write_json(
            run_dir / "command.json",
            {
                "capturedAt": utc_now(),
                "target": args.target,
                "deviceId": device["id"],
                "command": command,
                "environment": {
                    "QWQ_ANDROID_LOCAL_ENV_CA_PATH": command_env.get(ANDROID_LOCAL_DEBUG_CA_ENV, ""),
                    "QWQ_ANDROID_LOCAL_ENV_CA_REQUIRED": command_env.get(ANDROID_LOCAL_DEBUG_CA_REQUIRED_ENV, ""),
                },
            },
        )
        before_screenshot = capture_device_screenshot(device, run_dir / "before.png")
        print(
            f"[environment-page-smoke] run {args.env_name} on "
            f"{device['name']} ({device['id']}, {device['targetPlatform']})",
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
                env=command_env,
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
            "localTlsTrust": tls_trust,
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
