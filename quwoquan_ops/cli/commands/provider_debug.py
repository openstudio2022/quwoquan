"""stackctl `provider-debug` 子命令域。

从 stackctl.py 逐字迁出 argparse 表面与编排胶水；受保护的 Debug-local
OTP 读取逻辑保持在 `quwoquan_ops/cli/lib/local_sms_provider_debug.py`。
stackctl 命名空间符号一律经函数内延迟导入 `_stackctl` 属性访问，
保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import argparse
import getpass
import re
import sys
import urllib.error
from typing import Any


def register_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    provider_debug_parser = subparsers.add_parser(
        "provider-debug",
        help="受保护的 Debug-local Provider 控制面；不会写入 OTP 报告",
    )
    provider_debug_parser.add_argument("action", choices=("otp-read",))
    provider_debug_parser.add_argument(
        "--target",
        choices=("alpha-local", "beta-local", "gamma-local"),
        required=True,
    )


def command_provider_debug(args: argparse.Namespace) -> dict[str, Any]:
    """Read one random OTP through the protected local control plane."""
    import quwoquan_ops.cli.stackctl as _stackctl

    target_name = str(args.target)
    target = _stackctl.get_target(_stackctl.load_environment_topology(), target_name)
    environment = str(target["env"])
    if args.action != "otp-read":
        return {
            "exitCode": 2,
            "summary": "provider-debug is GATE_BLOCK",
            "details": ["unsupported provider-debug action"],
        }
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return {
            "exitCode": 2,
            "summary": "provider-debug otp-read is GATE_BLOCK",
            "details": ["otp-read requires an interactive TTY"],
        }
    try:
        phone = _stackctl._normalize_debug_phone(
            getpass.getpass("Phone (input is hidden): ")
        )
        protected_otp = _stackctl.read_latest_debug_otp(
            environment=environment,
            target_name=target_name,
            recipient=phone,
        )
        with open("/dev/tty", "w", encoding="utf-8") as tty:
            tty.write(f"OTP: {protected_otp.code}\n")
            tty.flush()
        protected_otp = None
    except (OSError, RuntimeError, ValueError, urllib.error.URLError) as exc:
        return {
            "exitCode": 2,
            "summary": "provider-debug otp-read is GATE_BLOCK",
            "details": [str(exc)],
        }
    return {
        "exitCode": 0,
        "summary": "protected OTP was displayed on the current TTY",
        "details": [
            f"target={target_name}",
            "OTP was not written to argv, reports, logs, or command output",
        ],
        "provider": {
            "adapterId": "ext.sms.local_capture",
            "environment": environment,
            "nonPromotable": True,
        },
    }


def _normalize_debug_phone(raw: str) -> str:
    normalized = re.sub(r"[\s\-()]", "", str(raw or "").strip())
    if re.fullmatch(r"1[0-9]{10}", normalized):
        normalized = "+86" + normalized
    if re.fullmatch(r"\+[1-9][0-9]{7,14}", normalized) is None:
        raise ValueError("phone must be an E.164 number or an 11-digit mainland number")
    return normalized
