"""stackctl `provider-debug` 子命令域。

从 stackctl.py 逐字迁出 argparse 表面与编排胶水；受保护的 Debug-local
OTP 读取逻辑保持在 `quwoquan_ops/cli/lib/local_sms_provider_debug.py`。
stackctl 命名空间符号一律经函数内延迟导入 `_stackctl` 属性访问，
保持 monkeypatch 语义并避免顶层循环 import。

`otp-read` 是规格允许的唯一人工 OTP 读取面（provider-adapter-conformance-suite
L3）：手机号与 OTP 只写当前 `/dev/tty`，不进入 argv、命令 JSON、日志或 receipt。
`--research-identity` 复用同一读取面，只是把手机号来源从交互隐藏输入换成
当前 target 的 Research 白名单身份绑定，开发者可先起命令再在 App 发码。
"""

from __future__ import annotations

import argparse
import getpass
import re
import sys
import time
import urllib.error
from typing import Any

DEFAULT_WAIT_SECONDS = 3.0
RESEARCH_IDENTITY_DEFAULT_WAIT_SECONDS = 60.0
MAX_WAIT_SECONDS = 300.0
_TRANSIENT_POLL_INTERVAL_SECONDS = 0.5


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
    provider_debug_parser.add_argument(
        "--research-identity",
        action="store_true",
        help=(
            "使用当前 target 的 Research 白名单身份手机号，不再交互输入；"
            "手机号与 OTP 只在当前 TTY 展示"
        ),
    )
    provider_debug_parser.add_argument(
        "--wait-seconds",
        type=float,
        default=None,
        help=(
            f"等待 OTP 出现的最长秒数（默认 {DEFAULT_WAIT_SECONDS:g}；"
            f"--research-identity 默认 {RESEARCH_IDENTITY_DEFAULT_WAIT_SECONDS:g}，"
            "便于先起命令再在 App 发码）"
        ),
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
    research_identity = bool(getattr(args, "research_identity", False))
    try:
        wait_seconds = resolve_wait_seconds(
            getattr(args, "wait_seconds", None),
            research_identity=research_identity,
        )
    except ValueError as exc:
        return {
            "exitCode": 2,
            "summary": "provider-debug otp-read is GATE_BLOCK",
            "details": [str(exc)],
        }
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return {
            "exitCode": 2,
            "summary": "provider-debug otp-read is GATE_BLOCK",
            "details": ["otp-read requires an interactive TTY"],
        }
    try:
        with open("/dev/tty", "w", encoding="utf-8") as tty:
            if research_identity:
                phone = _research_identity_phone(environment, target_name)
                tty.write(f"Research phone ({target_name}): {phone}\n")
                tty.write(
                    f"Waiting up to {wait_seconds:g}s for the OTP; "
                    "request the code in the App now.\n"
                )
            else:
                phone = _stackctl._normalize_debug_phone(
                    getpass.getpass("Phone (input is hidden): ")
                )
            tty.flush()
            protected_otp = _read_protected_otp(
                _stackctl,
                environment=environment,
                target_name=target_name,
                recipient=phone,
                wait_seconds=wait_seconds,
            )
            tty.write(f"OTP: {protected_otp.code}\n")
            tty.flush()
            protected_otp = None
    except (OSError, RuntimeError, ValueError, urllib.error.URLError) as exc:
        return {
            "exitCode": 2,
            "summary": "provider-debug otp-read is GATE_BLOCK",
            "details": [str(exc)],
        }
    details = [
        f"target={target_name}",
        "OTP was not written to argv, reports, logs, or command output",
    ]
    if research_identity:
        details.append(
            "recipient=research_identity_binding "
            "(phone was displayed only on the current TTY)"
        )
    return {
        "exitCode": 0,
        "summary": "protected OTP was displayed on the current TTY",
        "details": details,
        "provider": {
            "adapterId": "ext.sms.local_capture",
            "environment": environment,
            "nonPromotable": True,
        },
    }


def resolve_wait_seconds(
    raw: object,
    *,
    research_identity: bool,
) -> float:
    """Bound the OTP wait budget; unset falls back to the mode default."""
    if raw is None:
        return (
            RESEARCH_IDENTITY_DEFAULT_WAIT_SECONDS
            if research_identity
            else DEFAULT_WAIT_SECONDS
        )
    if isinstance(raw, bool):
        raise ValueError("--wait-seconds must be a positive number of seconds")
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("--wait-seconds must be a positive number of seconds") from exc
    if not (value > 0) or value != value or value > MAX_WAIT_SECONDS:
        raise ValueError(
            f"--wait-seconds must be within (0, {MAX_WAIT_SECONDS:g}] seconds"
        )
    return value


def _research_identity_phone(environment: str, target_name: str) -> str:
    # 经包属性访问，保持 research_identity 模块声明的测试 patch 锚点语义。
    import quwoquan_ops.cli.lib.local_environment_auth as _auth

    binding = _auth.load_local_research_identity_binding(
        environment=environment,
        target_name=target_name,
    )
    return _normalize_debug_phone(str(binding["phone"]))


def _read_protected_otp(
    stackctl_module: Any,
    *,
    environment: str,
    target_name: str,
    recipient: str,
    wait_seconds: float,
) -> Any:
    """Poll the protected readback until the OTP appears or the budget expires.

    The substitute stores one capture per recipient and deletes it on read, so
    a 404 only means the App has not sent (or the code was already read).  A
    loaded host can also drop a TLS handshake; that is retried inside the same
    budget instead of surfacing as a false "no OTP".
    """
    deadline = time.monotonic() + wait_seconds
    last_error: Exception | None = None
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            return stackctl_module.read_latest_debug_otp(
                environment=environment,
                target_name=target_name,
                recipient=recipient,
                timeout_seconds=min(3.0, max(1.0, remaining)),
            )
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
            last_error = exc
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last_error = exc
        except RuntimeError as exc:
            if "timed out" not in str(exc):
                raise
            last_error = exc
        time.sleep(min(_TRANSIENT_POLL_INTERVAL_SECONDS, max(0.0, deadline - time.monotonic())))
    raise RuntimeError(
        f"no OTP was captured for this recipient within {wait_seconds:g}s "
        "(tap 获取验证码 in the App first; the readback is one-time and "
        "clears the code once displayed)"
    ) from last_error


def _normalize_debug_phone(raw: str) -> str:
    normalized = re.sub(r"[\s\-()]", "", str(raw or "").strip())
    if re.fullmatch(r"1[0-9]{10}", normalized):
        normalized = "+86" + normalized
    if re.fullmatch(r"\+[1-9][0-9]{7,14}", normalized) is None:
        raise ValueError("phone must be an E.164 number or an 11-digit mainland number")
    return normalized
