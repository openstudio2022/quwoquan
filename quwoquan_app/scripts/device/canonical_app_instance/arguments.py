"""Canonical executor 的 CLI 参数契约。

叶子模块：launcher 在首个工具调用前的 fail-closed 参数预检直接导入本模块，
因此这里只允许标准库依赖，不得引入 metadata/契约等仓库依赖链。
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path


CANONICAL_EXECUTOR_DESCRIPTION = (
    "构建、安装、原生激活并附着一个 canonical Debug App 实例。"
)
DEVICE_KINDS = (
    "android_physical",
    "android_emulator",
    "ios-simulator",
    "ios-physical",
)


class CanonicalExecutorError(RuntimeError):
    """Canonical launch executor 的 typed 失败。"""


def sanitize_attach_arguments(arguments: tuple[str, ...]) -> list[str]:
    """只放行不改变设备、身份、VM URI/端口或编译输入的诊断参数。"""
    sanitized: list[str] = []
    for argument in arguments:
        if argument != "--verbose":
            raise CanonicalExecutorError(
                f"canonical executor owns Flutter attach argument {argument}"
            )
        sanitized.append(argument)
    return sanitized


def positive_finite_seconds(raw_value: str) -> float:
    try:
        value = float(raw_value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "timeout must be a positive finite number"
        ) from error
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError(
            "timeout must be a positive finite number"
        )
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=CANONICAL_EXECUTOR_DESCRIPTION)
    parser.add_argument(
        "--device-kind",
        choices=DEVICE_KINDS,
        required=True,
    )
    parser.add_argument("--device", required=True)
    parser.add_argument("--application-id", required=True)
    parser.add_argument("--entrypoint", required=True)
    parser.add_argument("--handoff-file", type=Path)
    parser.add_argument("--vm-service-info-file", type=Path)
    parser.add_argument("--vm-service-info-allowed-root", type=Path)
    parser.add_argument(
        "--activation-timeout-seconds",
        type=positive_finite_seconds,
        default=30.0,
    )
    parser.add_argument(
        "--attach-timeout-seconds",
        type=positive_finite_seconds,
        default=900.0,
    )
    parser.add_argument("attach_arguments", nargs=argparse.REMAINDER)
    return parser
