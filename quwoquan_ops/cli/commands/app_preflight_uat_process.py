"""Read one already-running canonical App PID without launching the App."""

from __future__ import annotations

import os
import re
import json
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
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



def _ios_physical_process_id(
    *,
    device_id: str,
    application_id: str,
    runner: CommandRunner,
) -> int:
    xcrun = shutil.which("xcrun") or "xcrun"
    cache_root = Path(os.environ.get("QWQ_OUTPUT_ROOT", ".qwq_output")).expanduser()
    cache_root = cache_root / "env/repo/local/ios-physical-process/cache"
    cache_root.mkdir(parents=True, exist_ok=True)

    def read_result(arguments: Sequence[str]) -> dict[str, Any]:
        descriptor, raw_path = tempfile.mkstemp(
            prefix="devicectl-", suffix=".json", dir=cache_root
        )
        os.close(descriptor)
        output_path = Path(raw_path)
        output_path.unlink(missing_ok=True)
        try:
            result = _run_read_only(
                [xcrun, "devicectl", *arguments, "--json-output", str(output_path)],
                runner=runner,
            )
            if result.returncode != 0 or not output_path.is_file():
                raise ValueError("canonical iOS physical process state is unreadable")
            payload = json.loads(output_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("canonical iOS physical process state is unreadable") from exc
        finally:
            output_path.unlink(missing_ok=True)
        if not isinstance(payload, dict) or not isinstance(payload.get("result"), dict):
            raise ValueError("canonical iOS physical process state is malformed")
        return payload["result"]

    apps = read_result(
        ["device", "info", "apps", "--device", device_id, "--bundle-id", application_id]
    )
    installed = apps.get("apps")
    matches = [
        app
        for app in installed if isinstance(installed, list) and isinstance(app, dict)
        and str(app.get("bundleIdentifier") or "") == application_id
    ] if isinstance(installed, list) else []
    if len(matches) != 1 or not str(matches[0].get("url") or "").strip():
        raise ValueError("canonical iOS physical App is not installed")
    app_url = str(matches[0]["url"]).rstrip("/")
    processes = read_result(["device", "info", "processes", "--device", device_id])
    running = processes.get("runningProcesses")
    process_ids = [
        process.get("processIdentifier")
        for process in running if isinstance(running, list) and isinstance(process, dict)
        and str(process.get("executable") or "").startswith(app_url + "/")
        and isinstance(process.get("processIdentifier"), int)
        and not isinstance(process.get("processIdentifier"), bool)
        and int(process["processIdentifier"]) > 0
    ] if isinstance(running, list) else []
    if len(process_ids) != 1:
        raise ValueError("canonical iOS physical App did not expose one process")
    return int(process_ids[0])


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
    if normalized_platform in {"android", "android-physical"}:
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
    if normalized_platform == "ios-physical":
        return _ios_physical_process_id(
            device_id=normalized_device,
            application_id=normalized_application,
            runner=runner,
        )
    raise ValueError(
        f"canonical App process observation does not support {platform or '<missing>'}"
    )
