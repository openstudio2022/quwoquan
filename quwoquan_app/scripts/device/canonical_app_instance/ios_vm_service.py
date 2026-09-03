"""Resolve an iOS Simulator VM service without leaking its auth token.

The Simulator advertises the just-launched Dart VM service over mDNS.  This
leaf module owns that bounded lookup and the matching log redaction; the
canonical executor only consumes the resulting debug URL.
"""

from __future__ import annotations

import json
import math
import os
import queue
import re
import shlex
import signal
import subprocess
import threading
import time
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .activation import CanonicalExecutorError, compile_environment

APP_DIR = Path(__file__).resolve().parents[3]
IOS_SIMULATOR_MDNS_LOOKUP_TIMEOUT_SECONDS = 15.0
IOS_SIMULATOR_MDNS_AMBIGUITY_SETTLE_SECONDS = 0.25
_PROCESS_TERMINATION_GRACE_SECONDS = 1.0
_VM_ENDPOINT_PATTERN = re.compile(
    r"can be reached at .+\.:(?P<port>[0-9]+) "
    r"\(interface [0-9]+\)"
)
_VM_AUTH_CODE_PATTERN = re.compile(
    r"^\s*authCode=(?P<auth_code>[A-Za-z0-9_+\-/]*={0,2})\s*$"
)
_VM_AUTH_CODE_INLINE_PATTERN = re.compile(r"(?i)(authCode=)[^\s\"'\\]+")
_VM_SERVICE_URI_PATTERN = re.compile(
    r"(?:ws|http)s?://(?:127\.0\.0\.1|localhost|\[::1\]):[0-9]+/"
    r"[^\s\"'\\]+"
)
_LSOF_PID_PATTERN = re.compile(r"^p(?P<pid>[1-9][0-9]*)$", re.MULTILINE)
_IOS_STARTUP_MARKERS = (
    "ios_dart_startup_attempt ",
    "ios_startup_safe_terminal ",
    "ios_startup_safe_terminal_rejected ",
)


@dataclass(frozen=True)
class IOSSimulatorLaunch:
    device_id: str
    application_id: str
    process_id: int
    log_start: str


def redact_vm_service_tokens(line: str) -> str:
    """Remove VM-service URIs and TXT auth codes before output reaches logs."""

    redacted = _VM_SERVICE_URI_PATTERN.sub("<redacted-vm-service-uri>", line)
    return _VM_AUTH_CODE_INLINE_PATTERN.sub(
        r"\1<redacted-vm-service-auth-code>",
        redacted,
    )


def launch_selected_simulator_application(
    device_id: str,
    application_id: str,
) -> IOSSimulatorLaunch:
    """Launch one exact Simulator App and return its bound log/PID identity."""

    normalized_device_id = device_id.strip()
    normalized_application_id = application_id.strip()
    if not normalized_device_id or not normalized_application_id:
        raise CanonicalExecutorError(
            "iOS Simulator launch requires device and application identity"
        )

    command = [
        "xcrun",
        "simctl",
        "launch",
        "--terminate-running-process",
        normalized_device_id,
        normalized_application_id,
    ]
    try:
        # Activation-only 进程在回执提交后仍可能存活；先显式终止并确认其
        # launchd service 消失，再记录 canonical launch 的日志边界。
        _terminate_selected_application(
            normalized_device_id,
            normalized_application_id,
        )
        log_start = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S%z")
        result = subprocess.run(
            command,
            cwd=APP_DIR,
            env=compile_environment(os.environ),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        raise CanonicalExecutorError(
            f"unable to launch selected iOS Simulator application: {error}"
        ) from error
    if result.returncode != 0:
        raise CanonicalExecutorError(
            f"command failed with code {result.returncode}: {shlex.join(command)}"
        )
    launch_output = f"{result.stdout or ''}\n{result.stderr or ''}"
    process_matches = re.findall(
        rf"(?m)^{re.escape(normalized_application_id)}:\s*([1-9][0-9]*)\s*$",
        launch_output,
    )
    if len(process_matches) != 1:
        raise CanonicalExecutorError(
            "iOS Simulator launch did not return one device-bound process id"
        )
    return IOSSimulatorLaunch(
        device_id=normalized_device_id,
        application_id=normalized_application_id,
        process_id=int(process_matches[0]),
        log_start=log_start,
    )


def _terminate_selected_application(
    device_id: str,
    application_id: str,
    *,
    timeout_seconds: float = 2.0,
) -> None:
    terminate_command = [
        "xcrun",
        "simctl",
        "terminate",
        device_id,
        application_id,
    ]
    terminate = subprocess.run(
        terminate_command,
        cwd=APP_DIR,
        env=compile_environment(os.environ),
        capture_output=True,
        text=True,
        check=False,
    )
    if terminate.returncode != 0:
        raise CanonicalExecutorError(
            "unable to terminate iOS Simulator activation process "
            f"(code {terminate.returncode})"
        )

    deadline = time.monotonic() + timeout_seconds
    service_fragment = f"UIKitApplication:{application_id}["
    probe_command = [
        "xcrun",
        "simctl",
        "spawn",
        device_id,
        "launchctl",
        "print",
        f"user/{os.getuid()}",
    ]
    while True:
        probe = subprocess.run(
            probe_command,
            cwd=APP_DIR,
            env=compile_environment(os.environ),
            capture_output=True,
            text=True,
            check=False,
        )
        if probe.returncode != 0 or service_fragment not in str(probe.stdout):
            return
        if time.monotonic() >= deadline:
            raise CanonicalExecutorError(
                "iOS Simulator activation process did not terminate before "
                "canonical launch"
            )
        time.sleep(0.05)


def resolve_ios_simulator_debug_url(
    launch: IOSSimulatorLaunch,
    *,
    timeout_seconds: float,
) -> str:
    """Return the device/PID-bound loopback URL for one exact launch.

    The auth code is returned only to the caller for ``flutter attach``.  Raw
    mDNS output and the resulting URL are never printed or included in errors.
    """

    normalized_application_id = launch.application_id.strip()
    if not normalized_application_id:
        raise CanonicalExecutorError("application id is required")
    if not launch.device_id.strip():
        raise CanonicalExecutorError("iOS Simulator device id is required")
    if launch.process_id <= 0:
        raise CanonicalExecutorError(
            "iOS Simulator launch process identity is required"
        )
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise CanonicalExecutorError(
            "iOS Simulator VM service lookup timeout must be positive and finite"
        )
    bounded_timeout = min(
        timeout_seconds,
        IOS_SIMULATOR_MDNS_LOOKUP_TIMEOUT_SECONDS,
    )
    command = [
        "dns-sd",
        "-L",
        normalized_application_id,
        "_dartVmService._tcp",
        "local.",
    ]
    try:
        process = subprocess.Popen(
            command,
            cwd=APP_DIR,
            env=compile_environment(os.environ),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
    except OSError as error:
        raise CanonicalExecutorError(
            f"unable to start iOS Simulator VM service lookup: {error}"
        ) from error
    assert process.stdout is not None
    output: queue.Queue[str | None] = queue.Queue()

    def read_output() -> None:
        try:
            for line in process.stdout:
                output.put(line)
        finally:
            output.put(None)

    threading.Thread(target=read_output, daemon=True).start()
    deadline = time.monotonic() + bounded_timeout
    try:
        port, auth_code = _read_unique_vm_service_record(
            output,
            lookup_deadline=deadline,
            bounded_timeout=bounded_timeout,
        )
    finally:
        _terminate_lookup_process(process)
    _verify_selected_process_owns_vm_service(
        expected_process_id=launch.process_id,
        port=port,
    )
    encoded_auth_code = urllib.parse.quote(auth_code, safe="")
    auth_path = f"{encoded_auth_code}/" if encoded_auth_code else ""
    return f"http://127.0.0.1:{port}/{auth_path}"


def read_ios_simulator_startup_evidence(
    launch: IOSSimulatorLaunch,
) -> tuple[str, ...]:
    """Read markers since pre-launch anchor from the selected device and PID."""

    predicate = (
        f"processIdentifier == {launch.process_id} AND ("
        'eventMessage CONTAINS "ios_dart_startup_attempt" OR '
        'eventMessage CONTAINS "ios_startup_safe_terminal")'
    )
    command = [
        "xcrun",
        "simctl",
        "spawn",
        launch.device_id,
        "log",
        "show",
        "--start",
        launch.log_start,
        "--style",
        "ndjson",
        "--predicate",
        predicate,
    ]
    try:
        result = subprocess.run(
            command,
            cwd=APP_DIR,
            env=compile_environment(os.environ),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        raise CanonicalExecutorError(
            f"unable to read selected iOS Simulator startup evidence: {error}"
        ) from error
    if result.returncode != 0:
        raise CanonicalExecutorError(
            "selected iOS Simulator startup evidence readback failed"
        )
    evidence: list[str] = []
    for raw_line in str(result.stdout).splitlines():
        if not any(marker in raw_line for marker in _IOS_STARTUP_MARKERS):
            continue
        try:
            document = json.loads(raw_line)
        except json.JSONDecodeError as error:
            raise CanonicalExecutorError(
                "selected iOS Simulator startup evidence is ambiguous"
            ) from error
        if (
            not isinstance(document, dict)
            or document.get("processID") != launch.process_id
            or not isinstance(document.get("eventMessage"), str)
        ):
            raise CanonicalExecutorError(
                "selected iOS Simulator startup evidence identity is ambiguous"
            )
        event = str(document["eventMessage"])
        if any(marker in event for marker in _IOS_STARTUP_MARKERS):
            redacted = redact_vm_service_tokens(event).strip()
            if redacted and redacted not in evidence:
                evidence.append(redacted)
    return tuple(evidence)


def _read_unique_vm_service_record(
    output: queue.Queue[str | None],
    *,
    lookup_deadline: float,
    bounded_timeout: float,
) -> tuple[int, str]:
    """Read one coherent mDNS record and reject any conflicting candidate."""

    selected: tuple[int, str] | None = None
    candidate_port: int | None = None
    candidate_auth_code: str | None = None
    candidate_auth_seen = False
    settle_deadline: float | None = None
    while True:
        active_deadline = settle_deadline or lookup_deadline
        remaining = active_deadline - time.monotonic()
        if remaining <= 0:
            if selected is not None:
                return selected
            raise CanonicalExecutorError(
                "iOS Simulator VM service mDNS record was not resolved "
                f"within {bounded_timeout:g}s"
            )
        try:
            line = output.get(timeout=min(remaining, 0.1))
        except queue.Empty:
            continue
        if line is None:
            if selected is not None:
                return selected
            raise CanonicalExecutorError(
                "iOS Simulator VM service lookup exited before a complete record"
            )

        endpoint_match = _VM_ENDPOINT_PATTERN.search(line)
        if endpoint_match is not None:
            # dns-sd 的 interface 是 mDNS 广播到达的宿主网卡，不是 VM
            # service 的监听地址；Simulator 可合法地经 en0 广播。真正的
            # loopback/device authority 由下方 127.0.0.1 URL 与全局 lsof
            # 唯一 PID 校验共同给出。
            observed_port = int(endpoint_match.group("port"))
            if not 1 <= observed_port <= 65535:
                raise CanonicalExecutorError(
                    "iOS Simulator VM service record contains an invalid port"
                )
            if candidate_port is not None and candidate_port != observed_port:
                raise CanonicalExecutorError(
                    "ambiguous iOS Simulator VM service records were advertised"
                )
            if selected is not None and selected[0] != observed_port:
                raise CanonicalExecutorError(
                    "ambiguous iOS Simulator VM service records were advertised"
                )
            candidate_port = observed_port

        auth_match = _VM_AUTH_CODE_PATTERN.match(line)
        if auth_match is not None:
            observed_auth_code = auth_match.group("auth_code")
            if selected is None and candidate_port is None:
                raise CanonicalExecutorError(
                    "iOS Simulator VM service record is not coherently ordered"
                )
            if candidate_auth_seen and candidate_auth_code != observed_auth_code:
                raise CanonicalExecutorError(
                    "ambiguous iOS Simulator VM service records were advertised"
                )
            if selected is not None and candidate_port is None:
                if selected[1] != observed_auth_code:
                    raise CanonicalExecutorError(
                        "ambiguous iOS Simulator VM service records were advertised"
                    )
                continue
            candidate_auth_code = observed_auth_code
            candidate_auth_seen = True

        if candidate_port is None or not candidate_auth_seen:
            continue
        candidate = (candidate_port, candidate_auth_code or "")
        if selected is not None:
            raise CanonicalExecutorError(
                "ambiguous iOS Simulator VM service records were advertised"
            )
        selected = candidate
        candidate_port = None
        candidate_auth_code = None
        candidate_auth_seen = False
        if settle_deadline is None:
            settle_deadline = min(
                lookup_deadline,
                time.monotonic()
                + IOS_SIMULATOR_MDNS_AMBIGUITY_SETTLE_SECONDS,
            )


def _verify_selected_process_owns_vm_service(
    *,
    expected_process_id: int,
    port: int,
) -> None:
    """Bind the mDNS endpoint to the PID returned by device-scoped simctl."""

    command = [
        "/usr/sbin/lsof",
        "-nP",
        f"-iTCP:{port}",
        "-sTCP:LISTEN",
        "-Fp",
    ]
    try:
        result = subprocess.run(
            command,
            cwd=APP_DIR,
            env=compile_environment(os.environ),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        raise CanonicalExecutorError(
            f"unable to verify iOS Simulator VM service ownership: {error}"
        ) from error
    observed_process_ids = {
        int(match.group("pid"))
        for match in _LSOF_PID_PATTERN.finditer(str(result.stdout))
    }
    if result.returncode != 0 or observed_process_ids != {expected_process_id}:
        raise CanonicalExecutorError(
            "iOS Simulator VM service is not bound to the selected device process"
        )


def _terminate_lookup_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        process.wait()
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        process.wait()
        return
    try:
        process.wait(timeout=_PROCESS_TERMINATION_GRACE_SECONDS)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()
