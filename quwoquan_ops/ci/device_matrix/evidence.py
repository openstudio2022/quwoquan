#!/usr/bin/env python3
"""Helpers for auditable self-hosted device matrix evidence."""

from __future__ import annotations

import datetime as dt
import json
import subprocess
from pathlib import Path
from typing import Any

from quwoquan_ops.ci.device_matrix.android import resolve_android_debug_bridge


REPO_ROOT = Path(__file__).resolve().parents[3]


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")


def repo_relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def sanitize_device_id(device_id: str) -> str:
    return "".join(
        ch if ch.isalnum() or ch in {"-", "_", "."} else "_"
        for ch in (device_id or "unknown-device")
    )


def write_json(path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return repo_relative(path)


def write_device_manifest(
    path: Path,
    device: dict[str, Any],
    *,
    env_name: str,
    suite: str,
    extra: dict[str, Any] | None = None,
) -> str:
    payload: dict[str, Any] = {
        "capturedAt": utc_now(),
        "suite": suite,
        "environment": env_name,
        "device": device,
    }
    if extra:
        payload["extra"] = extra
    return write_json(path, payload)


def write_discovered_devices_snapshot(
    path: Path,
    devices: list[dict[str, Any]],
    *,
    suite: str,
    requested_environments: list[str],
    extra: dict[str, Any] | None = None,
) -> str:
    payload: dict[str, Any] = {
        "capturedAt": utc_now(),
        "suite": suite,
        "requestedEnvironments": requested_environments,
        "deviceCount": len(devices),
        "devices": devices,
    }
    if extra:
        payload["extra"] = extra
    return write_json(path, payload)


def capture_device_screenshot(device: dict[str, Any], output_path: Path) -> dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    device_id = str(device.get("id", ""))
    target_platform = str(device.get("targetPlatform", "")).lower()

    if target_platform.startswith("android"):
        adb = resolve_android_debug_bridge()
        if not adb:
            return {
                "status": "failed",
                "path": repo_relative(output_path),
                "command": [],
                "stderrSummary": (
                    "adb unavailable; set ANDROID_SDK_ROOT/ANDROID_HOME "
                    "or install Android platform-tools"
                ),
            }
        command = [adb, "-s", device_id, "exec-out", "screencap", "-p"]
        try:
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            return {
                "status": "failed",
                "path": repo_relative(output_path),
                "command": command,
                "failureKind": "screenshot_timeout",
                "stderrSummary": "Android screenshot capture timed out",
            }
        if result.returncode == 0 and result.stdout:
            output_path.write_bytes(result.stdout)
            return {
                "status": "captured",
                "path": repo_relative(output_path),
                "command": command,
                "stderrSummary": result.stderr.decode("utf-8", errors="replace")[-4000:],
            }
        return {
            "status": "failed",
            "path": repo_relative(output_path),
            "command": command,
            "stderrSummary": result.stderr.decode("utf-8", errors="replace")[-4000:],
        }

    if target_platform == "ios" and bool(device.get("emulator", False)):
        command = ["xcrun", "simctl", "io", device_id, "screenshot", str(output_path)]
        try:
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            return {
                "status": "failed",
                "path": repo_relative(output_path),
                "command": command,
                "failureKind": "screenshot_timeout",
                "outputSummary": "iOS screenshot capture timed out",
            }
        if result.returncode == 0 and output_path.exists():
            return {
                "status": "captured",
                "path": repo_relative(output_path),
                "command": command,
                "outputSummary": (result.stdout or "")[-4000:],
            }
        return {
            "status": "failed",
            "path": repo_relative(output_path),
            "command": command,
            "outputSummary": (result.stdout or "")[-4000:],
        }

    return {
        "status": "unsupported",
        "reason": "screenshot capture is only implemented for Android devices and iOS simulators",
        "targetPlatform": target_platform,
        "deviceId": device_id,
    }
