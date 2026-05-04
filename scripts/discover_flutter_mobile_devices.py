#!/usr/bin/env python3
"""Discover mobile Flutter devices visible to the current runner."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_APP_DIR = REPO_ROOT / "quwoquan_app"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--app-dir",
        default=str(DEFAULT_APP_DIR),
        help="Flutter app directory used to run `flutter devices --machine`.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional JSON output path.",
    )
    parser.add_argument(
        "--require-mobile",
        action="store_true",
        help="Exit with code 2 when no iOS/Android device is visible.",
    )
    return parser.parse_args()


def summarize_output(output: str, *, max_lines: int = 80) -> str:
    lines = output.splitlines()
    if len(lines) <= max_lines:
        return output
    return "\n".join(
        [
            f"... omitted {len(lines) - max_lines} earlier lines ...",
            *lines[-max_lines:],
        ]
    )


def extract_json_array(output: str) -> str:
    start = output.find("[")
    end = output.rfind("]")
    if start < 0 or end < start:
        raise ValueError("flutter devices output missing JSON array")
    return output[start : end + 1]


def discover_devices(app_dir: Path) -> list[dict[str, Any]]:
    result = subprocess.run(
        ["flutter", "devices", "--machine"],
        cwd=str(app_dir),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "flutter devices --machine failed:\n"
            + summarize_output((result.stdout or "") + (result.stderr or ""))
        )
    raw_devices = json.loads(extract_json_array(result.stdout or ""))
    devices: list[dict[str, Any]] = []
    for device in raw_devices:
        target = str(device.get("targetPlatform", "")).lower()
        if target != "ios" and not target.startswith("android"):
            continue
        device_id = str(device.get("id", "")).strip()
        if not device_id:
            continue
        devices.append(
            {
                "id": device_id,
                "name": str(device.get("name", "")),
                "targetPlatform": str(device.get("targetPlatform", "")),
                "sdk": str(device.get("sdk", "")),
                "emulator": bool(device.get("emulator", False)),
                "ephemeral": bool(device.get("ephemeral", False)),
            }
        )
    return devices


def build_report(devices: list[dict[str, Any]]) -> dict[str, Any]:
    android = [
        device
        for device in devices
        if str(device.get("targetPlatform", "")).lower().startswith("android")
    ]
    ios = [
        device for device in devices if str(device.get("targetPlatform", "")).lower() == "ios"
    ]
    return {
        "deviceCount": len(devices),
        "platforms": [
            platform
            for platform, items in (("android", android), ("ios", ios))
            if items
        ],
        "android": android,
        "ios": ios,
        "devices": devices,
    }


def main() -> int:
    args = parse_args()
    app_dir = Path(args.app_dir)
    report = build_report(discover_devices(app_dir))
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = REPO_ROOT / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload, encoding="utf-8")
    sys.stdout.write(payload)
    if args.require_mobile and report["deviceCount"] == 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
