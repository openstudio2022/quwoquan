#!/usr/bin/env python3
"""CI wrapper for chat avatar device matrix jobs."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.parse
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
FAIL_FAST_EXIT_CODE = 86
FAIL_FAST_CATEGORIES = {
    "device_not_found",
    "gateway_unreachable",
    "gateway_response_not_json",
    "gateway_response_empty",
    "gateway_response_html",
    "stream_decode_error",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=("android", "ios"), required=True)
    return parser.parse_args()


def discover_device_ids(platform: str) -> list[str]:
    result = subprocess.run(
        ["flutter", "devices", "--machine"],
        cwd=str(REPO_ROOT / "quwoquan_app"),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        print("::error::flutter devices --machine 执行失败", file=sys.stderr)
        return []
    raw = result.stdout or ""
    start = raw.find("[")
    end = raw.rfind("]")
    if start < 0 or end < start:
        print("::error::flutter devices 输出无法解析为 JSON 数组", file=sys.stderr)
        return []
    devices = json.loads(raw[start : end + 1])
    ids: list[str] = []
    for device in devices:
        target = str(device.get("targetPlatform", "")).lower()
        device_id = str(device.get("id", "")).strip()
        if not device_id:
            continue
        if platform == "android" and target.startswith("android"):
            ids.append(device_id)
        if platform == "ios" and target == "ios":
            ids.append(device_id)
    return ids


def parse_gateway_port(raw_url: str) -> int:
    parsed = urllib.parse.urlparse(raw_url)
    if parsed.port is not None:
        return int(parsed.port)
    if parsed.scheme == "https":
        return 443
    return 80


def main() -> int:
    args = parse_args()
    env_name = os.environ.get("API_CONTRACT_ENV", "").strip()
    if env_name not in {"alpha", "beta", "gamma", "local-gamma"}:
        print(f"::error::API_CONTRACT_ENV={env_name!r} 不支持 chat avatar 矩阵", file=sys.stderr)
        return 2
    all_devices = os.environ.get("CHAT_AVATAR_MATRIX_ALL_DEVICES", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    configured = os.environ.get(
        "ANDROID_DEVICE_ID" if args.platform == "android" else "IOS_DEVICE_ID",
        "",
    ).strip()
    device_ids = discover_device_ids(args.platform) if all_devices else [configured]
    device_ids = [item for item in device_ids if item]
    if not device_ids:
        print(f"::error::未发现可用 {args.platform} 设备", file=sys.stderr)
        return 2
    command = [
        sys.executable,
        str(REPO_ROOT / "agent_ops/avatar/run_chat_avatar_device_matrix.py"),
        "--env",
        env_name,
        "--platform",
        args.platform,
        "--report",
        f"artifacts/device-matrix/chat-avatar/{env_name}-{args.platform}.json",
    ]
    report_path = (
        REPO_ROOT / "artifacts" / "device-matrix" / "chat-avatar" / f"{env_name}-{args.platform}.json"
    )
    for device_id in device_ids:
        command.extend(["--device-id", device_id])
    base_url = (
        os.environ.get("GAMMA_BASE_URL", "").strip()
        if env_name == "gamma"
        else os.environ.get("CHAT_AVATAR_GATEWAY_BASE_URL", "").strip()
    )
    if base_url:
        command.extend(["--gateway-base-url", base_url])
    media_url = os.environ.get("MEDIA_AVATAR_CDN_BASE_URL", "").strip()
    if media_url:
        command.extend(["--media-base-url", media_url])
    if env_name == "beta" and not base_url:
        default_beta_gateway = os.environ.get(
            "BETA_LOCAL_GATEWAY_BASE_URL", "http://127.0.0.1:18000"
        ).strip()
        command.extend(["--gateway-base-url", default_beta_gateway])
        if not media_url:
            command.extend(
                [
                    "--media-base-url",
                    os.environ.get(
                        "BETA_LOCAL_MEDIA_BASE_URL", "http://127.0.0.1:18100"
                    ).strip(),
                ]
            )
    token = os.environ.get("GAMMA_TEST_AUTH_TOKEN", "").strip()
    if token:
        command.extend(["--test-auth-token", token])
    code = subprocess.call(command, cwd=str(REPO_ROOT))
    if report_path.exists():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            report = {}
        failure_category = str(report.get("failureCategory") or "").strip()
        blocking_reason = str(report.get("blockingReason") or "").strip()
        if failure_category in FAIL_FAST_CATEGORIES:
            print(
                f"::error::[chat-avatar-matrix-fail-fast/{failure_category}] {blocking_reason or 'matrix failed with fail-fast category'}",
                file=sys.stderr,
            )
            return FAIL_FAST_EXIT_CODE
    return code


if __name__ == "__main__":
    raise SystemExit(main())
