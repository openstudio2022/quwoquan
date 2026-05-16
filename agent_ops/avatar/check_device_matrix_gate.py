#!/usr/bin/env python3
"""校验设备矩阵汇总 gate 的通过条件。"""

from __future__ import annotations

import argparse
import sys


DISCOVER_HINT = "检查 self-hosted runner、flutter devices --machine 与可见移动设备数量"
ANDROID_HINT = "检查 Android 设备矩阵执行与 beta/gamma 网关链路"
IOS_HINT = "检查 iOS 设备矩阵执行与 beta/gamma 网关链路"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discover-result", required=True)
    parser.add_argument("--android-result", required=True)
    parser.add_argument("--ios-result", required=True)
    parser.add_argument("--has-android", required=True)
    parser.add_argument("--has-ios", required=True)
    parser.add_argument("--allow-missing-platforms", action="store_true")
    return parser.parse_args()


def as_bool(value: str) -> bool:
    return value.strip().lower() == "true"


def expect_success(errors: list[str], name: str, value: str, hint: str) -> None:
    if value != "success":
        errors.append(f"{name} expected success, got {value}. {hint}")


def main() -> int:
    args = parse_args()
    errors: list[str] = []
    notices: list[str] = []

    has_android = as_bool(args.has_android)
    has_ios = as_bool(args.has_ios)

    expect_success(errors, "discover_devices", args.discover_result, DISCOVER_HINT)

    if not has_android and not has_ios:
        errors.append("至少需要一个可见移动设备，但当前未发现 Android 或 iOS 设备")

    if has_android:
        expect_success(errors, "android", args.android_result, ANDROID_HINT)
    elif args.allow_missing_platforms:
        notices.append("未发现 Android 设备；allow_missing_platforms=true，跳过 Android gate。")
    else:
        errors.append("android device environment is required, but no Android device was discovered")

    if has_ios:
        expect_success(errors, "ios", args.ios_result, IOS_HINT)
    elif args.allow_missing_platforms:
        notices.append("未发现 iOS 设备；allow_missing_platforms=true，跳过 iOS gate。")
    else:
        errors.append("ios device environment is required, but no iOS device was discovered")

    for notice in notices:
        print(f"::notice::{notice}")

    if errors:
        for error in errors:
            print(f"::error::{error}", file=sys.stderr)
        print(
            "::error::App Env Device Matrix 未全部成功；请按上列分项修复后重跑。",
            file=sys.stderr,
        )
        return 1

    print("device matrix gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
