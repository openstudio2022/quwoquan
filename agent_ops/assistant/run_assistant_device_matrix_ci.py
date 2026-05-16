#!/usr/bin/env python3
"""CI wrapper for assistant device matrix jobs.

Keep workflow shell snippets minimal because Android emulator runner executes
scripts through /bin/sh on hosted Linux runners.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build assistant device matrix CLI args from CI env."
    )
    parser.add_argument("--platform", choices=("android", "ios"), required=True)
    return parser.parse_args()


def discover_device_ids(platform: str) -> list[str]:
    """按平台发现当前 runner 可访问设备，支持“全设备逐一验证”模式。"""
    result = subprocess.run(
        ["flutter", "devices", "--machine"],
        cwd=str(REPO_ROOT / "quwoquan_app"),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        print(
            "::error::flutter devices --machine 执行失败，无法进入全设备验证模式",
            file=sys.stderr,
        )
        if result.stdout.strip():
            print(result.stdout, file=sys.stderr)
        if result.stderr.strip():
            print(result.stderr, file=sys.stderr)
        return []
    raw = result.stdout or ""
    start = raw.find("[")
    end = raw.rfind("]")
    if start < 0 or end < start:
        print("::error::flutter devices 输出无法解析为 JSON 数组", file=sys.stderr)
        return []
    try:
        devices = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        print("::error::flutter devices JSON 解析失败", file=sys.stderr)
        return []

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


def diagnose_gamma_failure() -> None:
    """将 gamma 失败粗分为：配置/连通/鉴权/可达四类，便于流水线分流。"""
    base = os.environ.get("GAMMA_BASE_URL", "").strip()
    token = os.environ.get("GAMMA_TEST_AUTH_TOKEN", "").strip()
    if not base:
        print(
            "::error::[gamma/connectivity_config] 缺少 GAMMA_BASE_URL（连通性配置）",
            file=sys.stderr,
        )
        return
    if not token:
        print(
            "::warning::[gamma/auth_config] GAMMA_TEST_AUTH_TOKEN 为空，可能导致鉴权相关用例失败",
            file=sys.stderr,
        )
    health = base.rstrip("/") + "/healthz"
    try:
        with urllib.request.urlopen(health, timeout=12) as resp:
            status = getattr(resp, "status", 200)
            if 200 <= int(status) < 300:
                print(
                    "::error::[gamma/service_reachable] 网关 /healthz 可达但设备矩阵失败，"
                    "请查看 flutter 输出与 assistant_device_matrix_report",
                    file=sys.stderr,
                )
            else:
                print(
                    f"::error::[gamma/connectivity_http] /healthz 返回非常态 HTTP {status}",
                    file=sys.stderr,
                )
    except urllib.error.HTTPError as exc:
        print(
            f"::error::[gamma/connectivity_http] /healthz HTTP 错误: {exc.code} {exc.reason}",
            file=sys.stderr,
        )
    except Exception as exc:  # noqa: BLE001
        print(
            "::error::[gamma/connectivity_reachability] 无法在超时内访问 "
            f"{health}: {exc}",
            file=sys.stderr,
        )


def main() -> int:
    args = parse_args()
    env_name = os.environ.get("API_CONTRACT_ENV", "").strip()
    if env_name not in {"alpha", "beta", "gamma"}:
        print(
            f"::error::API_CONTRACT_ENV={env_name!r} 不属于 alpha/beta/gamma",
            file=sys.stderr,
        )
        return 2

    all_devices_mode = (
        os.environ.get("ASSISTANT_MATRIX_ALL_DEVICES", "").strip().lower()
        in {"1", "true", "yes", "on"}
    )
    android_device = os.environ.get("ANDROID_DEVICE_ID", "").strip()
    ios_device = os.environ.get("IOS_DEVICE_ID", "").strip()
    device_ids: list[str]
    if all_devices_mode:
        device_ids = discover_device_ids(args.platform)
        if not device_ids:
            print(
                f"::error::全设备模式下未发现可用 {args.platform} 设备，请检查 runner 设备连接状态",
                file=sys.stderr,
            )
            return 2
        print(
            f"::notice::全设备模式：{args.platform} 将逐一验证设备 {device_ids}",
            file=sys.stderr,
        )
    elif args.platform == "android":
        device_ids = [android_device or "emulator-5554"]
    else:
        if not ios_device:
            print("::error::缺少 IOS_DEVICE_ID，无法执行 iOS 端侧矩阵", file=sys.stderr)
            return 2
        device_ids = [ios_device]

    command = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "run_assistant_device_matrix.py"),
        "--env",
        env_name,
        "--report",
        f"artifacts/device-matrix/{env_name}-{args.platform}.json",
    ]
    for device_id in device_ids:
        command.extend(["--device-id", device_id])

    if env_name == "gamma":
        gamma_base_url = os.environ.get("GAMMA_BASE_URL", "").strip()
        if not gamma_base_url:
            print(
                f"::error::缺少 GAMMA_BASE_URL，无法执行 gamma {args.platform} 端侧矩阵",
                file=sys.stderr,
            )
            diagnose_gamma_failure()
            return 1
        command.extend(["--skip-beta-services", "--gateway-base-url", gamma_base_url])

    if env_name == "beta":
        command.extend(["--service-start-timeout-seconds", "180"])

    # iOS 26+ 等新模拟器在全场景 smoke 下容易超过默认 420s（见 beta-ios 矩阵报告：
    # iPhone 17 Pro 上多次 SIGTERM/timeout），为 beta/gamma 的 iOS 矩阵单独放宽。
    if env_name in {"beta", "gamma"} and args.platform == "ios":
        ios_test_timeout = os.environ.get(
            "ASSISTANT_DEVICE_MATRIX_TEST_TIMEOUT_SECONDS", "900"
        ).strip()
        if ios_test_timeout.isdigit():
            command.extend(["--test-timeout-seconds", ios_test_timeout])

    code = subprocess.call(command, cwd=str(REPO_ROOT))
    if env_name == "gamma" and code != 0:
        diagnose_gamma_failure()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
