#!/usr/bin/env python3
"""Run gamma Patrol on every mobile device visible to the self-hosted Mac runner."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "quwoquan_app"
DEFAULT_REPORT = REPO_ROOT / "artifacts" / "device-matrix" / "gamma-patrol" / "report.json"
DEFAULT_TARGET = "test/patrol/discovery/feed_load_test.dart"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--target", default=DEFAULT_TARGET)
    parser.add_argument("--timeout-seconds", type=int, default=1200)
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
    return {
        "command": command,
        "cwd": str(cwd),
        "exitCode": exit_code,
        "timedOut": timed_out,
        "durationMs": int((time.monotonic() - started) * 1000),
        "outputSummary": summarize_output(output),
    }


def discover_devices() -> list[dict[str, Any]]:
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
    return list(data.get("devices") or [])


def patrol_command(device: dict[str, Any], args: argparse.Namespace) -> list[str]:
    gamma_base_url = os.environ["GAMMA_BASE_URL"].strip()
    gamma_product_ops_base_url = os.environ["GAMMA_PRODUCT_OPS_BASE_URL"].strip()
    gamma_test_auth_token = os.environ["GAMMA_TEST_AUTH_TOKEN"].strip()
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


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = REPO_ROOT / report_path

    report: dict[str, Any] = {
        "status": "failed",
        "startedAt": utc_now(),
        "endedAt": "",
        "target": args.target,
        "devices": [],
        "runs": [],
        "failureReason": "",
    }

    missing = [
        name
        for name in ("GAMMA_BASE_URL", "GAMMA_PRODUCT_OPS_BASE_URL", "GAMMA_TEST_AUTH_TOKEN")
        if not os.environ.get(name, "").strip()
    ]
    if missing:
        report["status"] = "gate_block"
        report["failureReason"] = f"missing required env: {', '.join(missing)}"
        report["endedAt"] = utc_now()
        write_report(report_path, report)
        return 2

    try:
        devices = discover_devices()
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
    failed = False
    for device in devices:
        print(
            f"[gamma-patrol-matrix] run on {device['name']} ({device['id']}, {device['targetPlatform']})",
            flush=True,
        )
        result = run_command(
            patrol_command(device, args),
            cwd=APP_DIR,
            timeout_seconds=args.timeout_seconds,
        )
        result["device"] = device
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
