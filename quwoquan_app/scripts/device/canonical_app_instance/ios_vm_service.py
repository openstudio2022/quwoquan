"""Simulator VM discovery 只读取本次设备/PID日志并校验 listener 所有权。

同包名多模拟器的 mDNS 名称不唯一，不能作为启动实例 authority。
"""
from __future__ import annotations

import json
import math
import os
import re
import shlex
import subprocess
import time
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .activation import CanonicalExecutorError, compile_environment

APP_DIR = Path(__file__).resolve().parents[3]
IOS_SIMULATOR_VM_LOOKUP_TIMEOUT_SECONDS = 15.0
_VM_AUTH_CODE_INLINE_PATTERN = re.compile(r"(?i)(authCode=)[^\s\"'\\]+")
_VM_SERVICE_URI_PATTERN = re.compile(r"(?:ws|http)s?://(?:127\.0\.0\.1|localhost|\[::1\]):[0-9]+/[^\s\"'\\]+")
_LSOF_PID_PATTERN = re.compile(r"^p(?P<pid>[1-9][0-9]*)$", re.MULTILINE)
_IOS_STARTUP_MARKERS = ("ios_dart_startup_attempt ", "ios_startup_safe_terminal ", "ios_startup_safe_terminal_rejected ")
_VM_LOG_PREFIX = "The Dart VM service is listening on "


@dataclass(frozen=True)
class IOSSimulatorLaunch:
    device_id: str
    application_id: str
    process_id: int
    log_start: str


def redact_vm_service_tokens(line: str) -> str:
    redacted = _VM_SERVICE_URI_PATTERN.sub("<redacted-vm-service-uri>", line)
    return _VM_AUTH_CODE_INLINE_PATTERN.sub(r"\1<redacted-vm-service-auth-code>", redacted)


def launch_selected_simulator_application(device_id: str, application_id: str) -> IOSSimulatorLaunch:
    device, app = device_id.strip(), application_id.strip()
    if not device or not app:
        raise CanonicalExecutorError("iOS Simulator launch requires device and application identity")
    _terminate_selected_application(device, app)
    start = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S%z")
    command = ["xcrun", "simctl", "launch", "--terminate-running-process", device, app]
    try:
        result = subprocess.run(command, cwd=APP_DIR, env=compile_environment(os.environ), capture_output=True, text=True, check=False)
    except OSError as error:
        raise CanonicalExecutorError("unable to launch selected iOS Simulator application") from error
    if result.returncode != 0:
        raise CanonicalExecutorError(f"command failed with code {result.returncode}: {shlex.join(command)}")
    matches = re.findall(rf"(?m)^{re.escape(app)}:\s*([1-9][0-9]*)\s*$", f"{result.stdout or ''}\n{result.stderr or ''}")
    if len(matches) != 1:
        raise CanonicalExecutorError("iOS Simulator launch did not return one device-bound process id")
    return IOSSimulatorLaunch(device, app, int(matches[0]), start)


def _terminate_selected_application(device_id: str, application_id: str, *, timeout_seconds: float = 2.0) -> None:
    result = subprocess.run(["xcrun", "simctl", "terminate", device_id, application_id], cwd=APP_DIR,
                            env=compile_environment(os.environ), capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise CanonicalExecutorError(f"unable to terminate iOS Simulator activation process (code {result.returncode})")
    deadline = time.monotonic() + timeout_seconds
    command = ["xcrun", "simctl", "spawn", device_id, "launchctl", "print", f"user/{os.getuid()}"]
    while True:
        probe = subprocess.run(command, cwd=APP_DIR, env=compile_environment(os.environ), capture_output=True, text=True, check=False)
        if probe.returncode != 0 or f"UIKitApplication:{application_id}[" not in str(probe.stdout):
            return
        if time.monotonic() >= deadline:
            raise CanonicalExecutorError("iOS Simulator activation process did not terminate before canonical launch")
        time.sleep(0.05)


def _device_log(launch: IOSSimulatorLaunch, predicate: str, *, timeout: float) -> list[dict]:
    command = ["xcrun", "simctl", "spawn", launch.device_id, "log", "show", "--start", launch.log_start,
               "--style", "ndjson", "--predicate", f"processIdentifier == {launch.process_id} AND ({predicate})"]
    try:
        result = subprocess.run(command, cwd=APP_DIR, env=compile_environment(os.environ),
                                capture_output=True, text=True, check=False, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise CanonicalExecutorError("selected iOS Simulator log readback failed or timed out") from error
    if result.returncode != 0:
        raise CanonicalExecutorError("selected iOS Simulator startup evidence readback failed")
    records = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise CanonicalExecutorError("selected iOS Simulator log is ambiguous") from error
        # log show 可能附加单独统计记录；只有没有eventMessage的统计对象不属于事件。
        if isinstance(record, dict) and "eventMessage" not in record and "finished" in record:
            continue
        if not isinstance(record, dict) or record.get("processID") != launch.process_id or not isinstance(record.get("eventMessage"), str):
            raise CanonicalExecutorError("selected iOS Simulator startup evidence identity is ambiguous")
        records.append(record)
    return records


def _vm_log_endpoint(records: list[dict]) -> tuple[int, str] | None:
    endpoints = set()
    for record in records:
        message = record["eventMessage"]
        if _VM_LOG_PREFIX not in message:
            continue
        raw = message.split(_VM_LOG_PREFIX, 1)[1].strip()
        try:
            uri = urllib.parse.urlparse(raw)
            port = uri.port
        except ValueError as error:
            raise CanonicalExecutorError("iOS Simulator VM log contains invalid endpoint") from error
        if (uri.scheme != "http" or uri.hostname not in {"127.0.0.1", "localhost", "::1"}
                or not port or uri.username or uri.password or uri.query or uri.fragment
                or not re.fullmatch(r"/[A-Za-z0-9_+%=\-]*/", uri.path)):
            raise CanonicalExecutorError("iOS Simulator VM log contains invalid loopback endpoint")
        token = urllib.parse.unquote(uri.path[1:-1])
        if not re.fullmatch(r"[A-Za-z0-9_+\-]*={0,2}", token):
            raise CanonicalExecutorError("iOS Simulator VM log contains invalid auth path")
        endpoints.add((port, token))
    if len(endpoints) > 1:
        raise CanonicalExecutorError("ambiguous iOS Simulator VM endpoints for selected process")
    return next(iter(endpoints)) if endpoints else None


def resolve_ios_simulator_debug_url(launch: IOSSimulatorLaunch, *, timeout_seconds: float) -> str:
    if not launch.application_id.strip() or not launch.device_id.strip() or launch.process_id <= 0:
        raise CanonicalExecutorError("iOS Simulator VM service requires device/application/process identity")
    try:
        datetime.strptime(launch.log_start, "%Y-%m-%d %H:%M:%S%z")
    except ValueError as error:
        raise CanonicalExecutorError("iOS Simulator pre-launch log anchor is invalid") from error
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise CanonicalExecutorError("iOS Simulator VM service lookup timeout must be positive and finite")
    budget = min(timeout_seconds, IOS_SIMULATOR_VM_LOOKUP_TIMEOUT_SECONDS)
    deadline = time.monotonic() + budget
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise CanonicalExecutorError(f"iOS Simulator VM service log was not resolved within {budget:g}s")
        records = _device_log(launch, f'eventMessage CONTAINS "{_VM_LOG_PREFIX}"', timeout=remaining)
        endpoint = _vm_log_endpoint(records)
        if endpoint is not None:
            port, token = endpoint
            _verify_selected_process_owns_vm_service(expected_process_id=launch.process_id, port=port, timeout=max(0.001, deadline-time.monotonic()))
            return f"http://127.0.0.1:{port}/{urllib.parse.quote(token, safe='')}/"
        time.sleep(min(0.1, max(0, deadline-time.monotonic())))


def read_ios_simulator_startup_evidence(launch: IOSSimulatorLaunch) -> tuple[str, ...]:
    records = _device_log(launch, 'eventMessage CONTAINS "ios_dart_startup_attempt" OR eventMessage CONTAINS "ios_startup_safe_terminal"', timeout=15)
    return tuple(dict.fromkeys(redact_vm_service_tokens(row["eventMessage"]).strip() for row in records
                               if any(marker in row["eventMessage"] for marker in _IOS_STARTUP_MARKERS)))


def _verify_selected_process_owns_vm_service(*, expected_process_id: int, port: int, timeout: float = 15) -> None:
    command = ["/usr/sbin/lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-Fp"]
    try:
        result = subprocess.run(command, cwd=APP_DIR, env=compile_environment(os.environ), capture_output=True,
                                text=True, check=False, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise CanonicalExecutorError("unable to verify iOS Simulator VM service ownership") from error
    pids = {int(match.group("pid")) for match in _LSOF_PID_PATTERN.finditer(str(result.stdout))}
    if result.returncode != 0 or pids != {expected_process_id}:
        raise CanonicalExecutorError("iOS Simulator VM service is not bound to the selected device process")
