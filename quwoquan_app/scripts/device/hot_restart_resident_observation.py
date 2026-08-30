"""Resident Flutter 会话与模拟器启动日志的观测原语。

被 verify_ios_hot_restart.py 冒烟脚本消费：PTY 输出泵、模拟器启动日志读取、
attempt 分段、冷启动/热重启安全终态观测，以及 daemon 协议（``flutter attach
--machine``）的就绪与 appId 解析。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import select
import subprocess
import time
from typing import Any

from verify_startup_first_frame import extract_dart_startup_attempts


def redacted_command(command: list[str]) -> list[str]:
    redacted: list[str] = []
    for item in command:
        if item.startswith(("--gateway-base-url", "--media-")):
            key = item.split(" ", 1)[0]
            redacted.append(f"{key}=<redacted>")
        else:
            redacted.append(item)
    return redacted


def direct_consumer_lease_id(environment: str, device_id: str) -> str:
    value = (
        f"ios-simulator\0{environment}-local\0{device_id}\0direct-flutter-run"
    )
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def pump_pty(
    master_fd: int,
    process: subprocess.Popen[bytes],
    output: bytearray,
    *,
    timeout_seconds: float,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            wait_seconds = 0.25
        else:
            wait_seconds = min(0.25, max(0.0, deadline - time.monotonic()))
        ready, _, _ = select.select([master_fd], [], [], wait_seconds)
        if not ready:
            if process.poll() is not None:
                return
            continue
        try:
            output.extend(os.read(master_fd, 16 * 1024))
        except OSError:
            return


def read_simulator_startup_log(device_id: str) -> str:
    predicate = (
        'eventMessage CONTAINS "QWQStartup" '
        'OR eventMessage CONTAINS "startup_welcome_sequence" '
        'OR eventMessage CONTAINS "startup_probe"'
    )
    result = subprocess.run(
        [
            "xcrun",
            "simctl",
            "spawn",
            device_id,
            "log",
            "show",
            "--last",
            "10m",
            "--style",
            "compact",
            "--predicate",
            predicate,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout


def attempt_segments(
    raw_log: str,
    *,
    excluded_attempt_ids: set[str] | frozenset[str] = frozenset(),
) -> list[tuple[dict[str, Any], str]]:
    marker = re.compile(
        r"(?:android|ios)_dart_startup_attempt "
        r"attemptId=[A-Za-z0-9_-]+.*"
    )
    matches = list(marker.finditer(raw_log))
    segments: list[tuple[dict[str, Any], str]] = []
    attempts = extract_dart_startup_attempts(raw_log)
    for index, attempt in enumerate(attempts):
        if index >= len(matches):
            break
        if str(attempt.get("attemptId") or "") in excluded_attempt_ids:
            continue
        start = matches[index].start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(raw_log)
        segments.append((attempt, raw_log[start:end]))
    return segments


def hot_restart_attempt_observed(
    raw_log: str,
    *,
    excluded_attempt_ids: set[str] | frozenset[str],
    require_safe_terminal: bool,
) -> bool:
    safe_terminal = re.compile(
        r"(?:ios|android)_startup_safe_terminal "
        r"surface=router_shell "
        r"(?:reportedElapsedMs|elapsedMs)="
    )
    for attempt, segment in attempt_segments(
        raw_log,
        excluded_attempt_ids=excluded_attempt_ids,
    ):
        if attempt.get("hotRestart") != "true":
            continue
        if not require_safe_terminal or safe_terminal.search(segment):
            return True
    return False


def cold_startup_terminal_observed(
    raw_log: str,
    *,
    excluded_attempt_ids: set[str] | frozenset[str] = frozenset(),
) -> bool:
    """Return whether this run reached a cold Dart safe terminal."""

    safe_terminal = re.compile(
        r"(?:ios|android)_startup_safe_terminal "
        r"surface=router_shell "
        r"(?:reportedElapsedMs|elapsedMs)="
    )
    return any(
        attempt.get("hotRestart") == "false" and safe_terminal.search(segment)
        for attempt, segment in attempt_segments(
            raw_log,
            excluded_attempt_ids=excluded_attempt_ids,
        )
    )


def flutter_resident_ready_for_hot_restart(raw_output: bytes | bytearray) -> bool:
    """Return whether the resident Flutter session accepts hot-restart triggers.

    canonical launcher 经 ``flutter attach --machine`` 驻留（daemon JSON 协议，
    ``app.started`` 后可触发 hot restart）；交互式 key commands 面向历史直连
    会话保留识别。
    """

    return b'"event":"app.started"' in raw_output or (
        b"Flutter run key commands." in raw_output
        and b"R Hot restart." in raw_output
    )


def flutter_resident_uses_daemon_protocol(raw_output: bytes | bytearray) -> bool:
    """daemon 协议下没有键盘命令面，hot restart 走 app.restart JSON-RPC。"""

    return b'"event":"daemon.connected"' in raw_output


def daemon_resident_app_id(raw_output: bytes | bytearray) -> str | None:
    """从 daemon 事件流解析最近一次 app.start 的 appId。"""

    app_id: str | None = None
    for line in raw_output.decode("utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if '"event":"app.start"' not in stripped:
            continue
        try:
            events = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if not isinstance(events, list):
            continue
        for event in events:
            if not isinstance(event, dict) or event.get("event") != "app.start":
                continue
            candidate = str((event.get("params") or {}).get("appId") or "")
            if candidate:
                app_id = candidate
    return app_id


def wait_for_hot_restart(
    master_fd: int,
    process: subprocess.Popen[bytes],
    device_id: str,
    output: bytearray,
    *,
    excluded_attempt_ids: set[str] | frozenset[str],
    timeout_seconds: float,
    require_safe_terminal: bool,
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        pump_pty(
            master_fd,
            process,
            output,
            timeout_seconds=min(0.5, max(0.0, deadline - time.monotonic())),
        )
        simulator_log = read_simulator_startup_log(device_id)
        if hot_restart_attempt_observed(
            simulator_log,
            excluded_attempt_ids=excluded_attempt_ids,
            require_safe_terminal=require_safe_terminal,
        ):
            return True
        if process.poll() is not None:
            return False
        time.sleep(0.25)
    return False


def wait_for_cold_startup(
    master_fd: int,
    process: subprocess.Popen[bytes],
    device_id: str,
    output: bytearray,
    *,
    excluded_attempt_ids: set[str] | frozenset[str],
    timeout_seconds: float,
) -> bool:
    """Wait for the current app process before sending the hot-restart key."""

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        pump_pty(
            master_fd,
            process,
            output,
            timeout_seconds=min(0.5, max(0.0, deadline - time.monotonic())),
        )
        simulator_log = read_simulator_startup_log(device_id)
        if (
            cold_startup_terminal_observed(
                simulator_log,
                excluded_attempt_ids=excluded_attempt_ids,
            )
            and flutter_resident_ready_for_hot_restart(output)
        ):
            return True
        if process.poll() is not None:
            return False
        time.sleep(0.25)
    return False
