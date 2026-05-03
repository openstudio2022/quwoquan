#!/usr/bin/env python3
"""Run chat group avatar E2E across available mobile simulators/devices."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import signal
import shutil
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "quwoquan_app"
DEFAULT_REPORT = REPO_ROOT / "artifacts/device-matrix/chat-avatar/report.json"
PATROL_TARGET = "test/patrol/chat/group_avatar_sync_e2e_test.dart"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", default="beta")
    parser.add_argument("--platform", choices=("android", "ios", "all"), default="all")
    parser.add_argument("--device-id", action="append", default=[])
    parser.add_argument("--gateway-base-url", default="")
    parser.add_argument("--media-base-url", default="")
    parser.add_argument("--test-auth-token", default=os.environ.get("GAMMA_TEST_AUTH_TOKEN", ""))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--test-timeout-seconds", type=int, default=600)
    parser.add_argument("--probe-timeout-seconds", type=int, default=180)
    parser.add_argument("--skip-media-check", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def run_command(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout_seconds: int | None = None,
    include_output: bool = False,
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
        "durationMs": int((time.monotonic() - started) * 1000),
        "timedOut": timed_out,
        "outputSummary": summarize_output(output),
    }
    if include_output:
        result["output"] = output
    return result


def summarize_output(output: str, *, max_lines: int = 80) -> str:
    lines = output.splitlines()
    if len(lines) <= max_lines:
        return output
    return "\n".join([f"... omitted {len(lines) - max_lines} earlier lines ...", *lines[-max_lines:]])


def discover_devices(platform: str) -> list[dict[str, Any]]:
    result = run_command(
        ["flutter", "devices", "--machine"],
        cwd=APP_DIR,
        timeout_seconds=60,
        include_output=True,
    )
    if result["exitCode"] != 0:
        raise RuntimeError("flutter devices --machine failed:\n" + result["outputSummary"])
    raw = result["output"]
    start = raw.find("[")
    end = raw.rfind("]")
    if start < 0 or end < start:
        raise RuntimeError("flutter devices output does not contain JSON array")
    devices = json.loads(raw[start : end + 1])
    selected: list[dict[str, Any]] = []
    for device in devices:
        target = str(device.get("targetPlatform", "")).lower()
        if platform == "android" and not target.startswith("android"):
            continue
        if platform == "ios" and target != "ios":
            continue
        if platform == "all" and target != "ios" and not target.startswith("android"):
            continue
        if not device.get("id"):
            continue
        selected.append(
            {
                "id": str(device.get("id", "")),
                "name": str(device.get("name", "")),
                "targetPlatform": str(device.get("targetPlatform", "")),
                "sdk": str(device.get("sdk", "")),
                "emulator": bool(device.get("emulator", False)),
                "screenClass": infer_screen_class(device),
            }
        )
    return selected


def infer_screen_class(device: dict[str, Any]) -> str:
    text = " ".join(
        [str(device.get("name", "")), str(device.get("id", "")), str(device.get("targetPlatform", ""))]
    ).lower()
    if any(token in text for token in ("ipad", "tablet", "pad ")):
        return "tablet"
    if any(token in text for token in ("iphone", "phone", "android")):
        return "phone"
    return "any"


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


def report_path(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else REPO_ROOT / path


def envs(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def default_base_url(env_name: str, override: str) -> str:
    if override:
        return override.rstrip("/")
    if env_name == "gamma":
        return os.environ.get("GAMMA_BASE_URL", "").rstrip("/")
    if env_name == "local-gamma":
        return os.environ.get("LOCAL_GAMMA_GATEWAY_BASE_URL", "http://127.0.0.1:18080").rstrip("/")
    return os.environ.get("CHAT_AVATAR_GATEWAY_BASE_URL", "http://127.0.0.1:18080").rstrip("/")


def default_media_url(env_name: str, override: str) -> str:
    if override:
        return override.rstrip("/")
    if env_name == "local-gamma":
        return os.environ.get("LOCAL_GAMMA_MEDIA_BASE_URL", "http://127.0.0.1:18080").rstrip("/")
    return os.environ.get("MEDIA_AVATAR_CDN_BASE_URL", "").rstrip("/")


def adb_reverse_if_needed(device: dict[str, Any], urls: list[str]) -> list[dict[str, Any]]:
    target = device["targetPlatform"].lower()
    if not target.startswith("android"):
        return []
    results = []
    for url in urls:
        parsed = urllib.parse.urlparse(url)
        if parsed.hostname not in {"127.0.0.1", "localhost"} or not parsed.port:
            continue
        command = ["adb", "-s", device["id"], "reverse", f"tcp:{parsed.port}", f"tcp:{parsed.port}"]
        results.append(run_command(command, cwd=REPO_ROOT, timeout_seconds=20))
    return results


def run_probe(
    env_name: str,
    base_url: str,
    media_url: str,
    args: argparse.Namespace,
    out_dir: Path,
) -> dict[str, Any]:
    path = out_dir / "probe.json"
    command = [
        sys.executable,
        str(REPO_ROOT / "scripts/run_chat_avatar_e2e_probe.py"),
        "--env",
        env_name,
        "--base-url",
        base_url,
        "--report",
        str(path),
        "--timeout-seconds",
        str(args.probe_timeout_seconds),
    ]
    if media_url:
        command.extend(["--media-base-url", media_url])
    if args.test_auth_token:
        command.extend(["--test-auth-token", args.test_auth_token])
    if args.skip_media_check:
        command.append("--skip-media-check")
    if env_name == "local-gamma":
        command.append("--compose-mongo")
    if args.dry_run:
        command.append("--dry-run")
    result = run_command(command, cwd=REPO_ROOT, timeout_seconds=args.probe_timeout_seconds + 60)
    report: dict[str, Any] = {}
    if path.exists():
        report = json.loads(path.read_text(encoding="utf-8"))
    return {"commandResult": result, "reportPath": str(path), "report": report}


def run_patrol(
    env_name: str,
    base_url: str,
    media_url: str,
    args: argparse.Namespace,
    device: dict[str, Any],
    probe_report: dict[str, Any],
    out_dir: Path,
) -> dict[str, Any]:
    ui_report = out_dir / "ui.json"
    conversation = probe_report.get("conversation") or {}
    conversation_id = str(conversation.get("conversationId") or "")
    final_avatar_url = str(conversation.get("finalAvatarUrl") or "")
    patrol_bin = shutil.which("patrol")
    if patrol_bin is None:
        candidate = Path.home() / ".pub-cache/bin/patrol"
        if candidate.exists():
            patrol_bin = str(candidate)
    if patrol_bin is None:
        return {
            "commandResult": {
                "command": ["patrol"],
                "exitCode": 127,
                "outputSummary": "patrol CLI not found",
            },
            "reportPath": str(ui_report),
            "report": {"status": "gate_block", "failureCategory": "env_not_ready"},
        }
    command = [
        patrol_bin,
        "test",
        "-t",
        PATROL_TARGET,
        "-d",
        device["id"],
        "--dart-define=RUN_T4_PATROL=true",
        f"--dart-define=APP_RUNTIME_ENV={'gamma' if env_name in {'gamma', 'local-gamma'} else env_name}",
        "--dart-define=APP_DATA_SOURCE=remote",
        f"--dart-define=API_CONTRACT_ENV={'gamma' if env_name == 'local-gamma' else env_name}",
        f"--dart-define=CLOUD_GATEWAY_BASE_URL={base_url}",
        f"--dart-define=API_CONTRACT_BASE_URL={base_url}",
        f"--dart-define=TEST_AUTH_TOKEN={args.test_auth_token}",
        f"--dart-define=CHAT_AVATAR_E2E_CONVERSATION_ID={conversation_id}",
        f"--dart-define=CHAT_AVATAR_E2E_FINAL_AVATAR_URL={final_avatar_url}",
        f"--dart-define=CHAT_AVATAR_UI_REPORT={ui_report}",
    ]
    if media_url:
        command.extend(
            [
                f"--dart-define=MEDIA_AVATAR_CDN_BASE_URL={media_url}",
                f"--dart-define=MEDIA_IMAGE_CDN_BASE_URL={media_url}",
                f"--dart-define=MEDIA_VIDEO_CDN_BASE_URL={media_url}",
                f"--dart-define=MEDIA_UPLOAD_BASE_URL={media_url}",
            ]
        )
    if args.dry_run:
        ui_report.write_text(
            json.dumps({"status": "passed", "dryRun": True}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return {"command": command, "exitCode": 0, "reportPath": str(ui_report), "report": json.loads(ui_report.read_text())}
    result = run_command(command, cwd=APP_DIR, timeout_seconds=args.test_timeout_seconds)
    report: dict[str, Any] = {}
    if ui_report.exists():
        report = json.loads(ui_report.read_text(encoding="utf-8"))
    return {"commandResult": result, "reportPath": str(ui_report), "report": report}


def main() -> int:
    args = parse_args()
    out = report_path(args.report)
    requested_envs = envs(args.env)
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "scenario": "chat.group_avatar.sync_display_e2e.matrix",
        "status": "running",
        "failureCategory": "",
        "blockingReason": "",
        "retryable": False,
        "startedAt": utc_now(),
        "endedAt": "",
        "requestedEnvironments": requested_envs,
        "platform": args.platform,
        "devices": [],
        "runs": [],
    }
    try:
        devices = dry_run_devices(args) if args.dry_run else discover_devices(args.platform)
        if args.device_id:
            allowed = set(args.device_id)
            devices = [device for device in devices if device["id"] in allowed]
        if not devices:
            report["status"] = "gate_block"
            report["failureCategory"] = "device_not_found"
            report["blockingReason"] = "no matching simulator or device found"
            report["retryable"] = True
            return write_report(report, out, 2)
        report["devices"] = devices
        if any(env_name == "gamma" and not default_base_url(env_name, args.gateway_base_url) for env_name in requested_envs):
            report["status"] = "gate_block"
            report["failureCategory"] = "gateway_unreachable"
            report["blockingReason"] = "gamma gateway base URL is not configured"
            report["retryable"] = True
            return write_report(report, out, 2)
        failed = False
        for env_name in requested_envs:
            base_url = default_base_url(env_name, args.gateway_base_url)
            media_url = default_media_url(env_name, args.media_base_url)
            for device in devices:
                run_dir = out.parent / env_name / device["id"].replace("/", "_")
                run_dir.mkdir(parents=True, exist_ok=True)
                reverse = adb_reverse_if_needed(device, [base_url, media_url])
                probe = run_probe(env_name, base_url, media_url, args, run_dir)
                patrol = {"status": "skipped", "reason": "probe failed"}
                if (probe.get("report") or {}).get("status") == "passed":
                    patrol = run_patrol(env_name, base_url, media_url, args, device, probe["report"], run_dir)
                run = {
                    "env": env_name,
                    "device": device,
                    "gatewayBaseUrl": base_url,
                    "mediaBaseUrl": media_url,
                    "adbReverse": reverse,
                    "probe": probe,
                    "patrol": patrol,
                }
                probe_failed = (probe.get("report") or {}).get("status") != "passed"
                patrol_failed = (patrol.get("report") or {}).get("status") != "passed"
                run["status"] = "failed" if probe_failed or patrol_failed else "passed"
                failed = failed or run["status"] != "passed"
                report["runs"].append(run)
        report["status"] = "failed" if failed else "passed"
        if failed:
            report["failureCategory"] = first_failure_category(report) or "ui_avatar_not_visible"
            report["blockingReason"] = first_blocking_reason(report)
            report["retryable"] = True
        return write_report(report, out, 1 if failed else 0)
    except Exception as exc:  # noqa: BLE001
        report["status"] = "failed"
        report["failureCategory"] = "unknown"
        report["blockingReason"] = str(exc)
        report["retryable"] = True
        report["error"] = str(exc)
        return write_report(report, out, 1)


def write_report(report: dict[str, Any], path: Path, code: int) -> int:
    report["endedAt"] = utc_now()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[chat-avatar-device-matrix] report: {path}", flush=True)
    print(f"[chat-avatar-device-matrix] status: {report['status']}", flush=True)
    return code


def first_failure_category(report: dict[str, Any]) -> str:
    for run in report.get("runs") or []:
        for key in ("probe", "patrol"):
            nested = ((run.get(key) or {}).get("report") or {})
            category = str(nested.get("failureCategory") or "").strip()
            if category:
                return category
    return ""


def first_blocking_reason(report: dict[str, Any]) -> str:
    for run in report.get("runs") or []:
        for key in ("probe", "patrol"):
            nested = ((run.get(key) or {}).get("report") or {})
            reason = str(nested.get("blockingReason") or nested.get("error") or "").strip()
            if reason:
                return reason
    return ""


if __name__ == "__main__":
    raise SystemExit(main())
