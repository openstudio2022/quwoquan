"""Read one already-running canonical App PID without launching the App."""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable, Sequence
from typing import Any

from quwoquan_ops.ci.device_matrix.android import resolve_android_debug_bridge

CommandRunner = Callable[..., subprocess.CompletedProcess[Any]]
AdbResolver = Callable[[], str | None]


def _run_read_only(
    command: Sequence[str],
    *,
    runner: CommandRunner,
) -> subprocess.CompletedProcess[Any]:
    try:
        return runner(
            list(command),
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError(
            "canonical App process observation could not execute"
        ) from exc


def _positive_single_pid(raw: object, *, label: str) -> int:
    tokens = str(raw or "").strip().split()
    if len(tokens) != 1 or not tokens[0].isdigit():
        raise ValueError(f"{label} did not expose one canonical process")
    process_id = int(tokens[0])
    if process_id <= 0:
        raise ValueError(f"{label} processId is invalid")
    return process_id


def _android_process_id(
    *,
    device_id: str,
    application_id: str,
    runner: CommandRunner,
    adb_resolver: AdbResolver,
) -> int:
    adb = str(adb_resolver() or "").strip()
    if not adb:
        raise ValueError("canonical Android App process observation requires adb")
    result = _run_read_only(
        [adb, "-s", device_id, "shell", "pidof", application_id],
        runner=runner,
    )
    if result.returncode != 0:
        raise ValueError("canonical Android App process is not running")
    return _positive_single_pid(
        result.stdout,
        label="canonical Android App",
    )


def _ios_simulator_process_id(
    *,
    device_id: str,
    application_id: str,
    runner: CommandRunner,
) -> int:
    # The simulator user launchd domain is read-only.  Unlike `simctl launch`,
    # this command cannot create or replace the App process it is proving.
    result = _run_read_only(
        [
            "xcrun",
            "simctl",
            "spawn",
            device_id,
            "launchctl",
            "print",
            f"user/{os.getuid()}",
        ],
        runner=runner,
    )
    if result.returncode != 0:
        raise ValueError("canonical iOS Simulator process state is unreadable")
    service = re.compile(
        r"^\s*(?P<pid>[0-9]+)\s+\S+\s+"
        + re.escape(f"UIKitApplication:{application_id}")
        + r"\[[^\]\r\n]+\](?:\[[^\]\r\n]+\])*\s*$"
    )
    matches = [
        match
        for line in str(result.stdout or "").splitlines()
        if (match := service.fullmatch(line)) is not None
    ]
    if len(matches) != 1:
        raise ValueError(
            "canonical iOS Simulator App did not expose one launchd process"
        )
    return _positive_single_pid(
        matches[0].group("pid"),
        label="canonical iOS Simulator App",
    )


def observe_canonical_app_process_id(
    *,
    platform: str,
    device_id: str,
    application_id: str,
    runner: CommandRunner = subprocess.run,
    adb_resolver: AdbResolver = resolve_android_debug_bridge,
) -> int:
    """Observe one exact process and reject any launch-capable fallback."""

    normalized_platform = str(platform or "").strip().lower()
    normalized_device = str(device_id or "").strip()
    normalized_application = str(application_id or "").strip()
    if not normalized_device or not normalized_application:
        raise ValueError("canonical App process identity is incomplete")
    if normalized_platform == "android":
        return _android_process_id(
            device_id=normalized_device,
            application_id=normalized_application,
            runner=runner,
            adb_resolver=adb_resolver,
        )
    if normalized_platform == "ios-simulator":
        return _ios_simulator_process_id(
            device_id=normalized_device,
            application_id=normalized_application,
            runner=runner,
        )
    raise ValueError(
        f"canonical App process observation does not support {platform or '<missing>'}"
    )
