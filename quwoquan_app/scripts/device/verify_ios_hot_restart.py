#!/usr/bin/env python3
"""Run a real Flutter/iOS Simulator cold-start and hot-restart smoke.

The smoke can exercise either the canonical launcher or literal ``flutter run``.
Both surfaces must retain one canonical runtime handoff across the resident
compiler's cold start and hot restart.
"""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
import plistlib
import re
import select
import signal
import subprocess
import sys
import termios
import time
import tty
from pathlib import Path
from typing import Any

import pty

from verify_startup_first_frame import (
    classify_startup_terminal,
    extract_dart_startup_attempts,
    extract_startup_watchdog_evidence,
    parse_startup_sequence_log,
)
from verify_flutter_run_defines import validate_flutter_run_defines


APP_DIR = Path(__file__).resolve().parents[2]
ROOT = APP_DIR.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.app_identity import application_id_for  # noqa: E402

LAUNCHER = APP_DIR / "run.sh"
ENVIRONMENTS = ("alpha", "beta", "gamma")
LAUNCH_SURFACES = ("canonical_launcher", "direct_flutter_run")
SAFE_TERMINAL_HARD_LIMIT_MS = 6000


def _runtime_defines(environment: str, launch_surface: str) -> dict[str, str]:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/env/print_app_env_dart_defines.py",
            "--env",
            environment,
            "--format",
            "json",
            "--launch-mode",
            launch_surface,
            "--app-instance-id",
            f"{environment}-ios-hot-restart",
            "--app-instance-namespace",
            "ios-hot-restart-smoke",
        ],
        cwd=APP_DIR,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    decoded = json.loads(result.stdout)
    if not isinstance(decoded, dict):
        raise RuntimeError("runtime define source did not return an object")
    defines = {str(key): str(value) for key, value in decoded.items()}
    issues = validate_flutter_run_defines(defines, expected_env=environment, platform="ios")
    if issues:
        raise RuntimeError("Flutter CLI preflight failed: " + "; ".join(issues))
    return defines


def _redacted_command(command: list[str]) -> list[str]:
    redacted: list[str] = []
    for item in command:
        if item.startswith("--gateway-base-url") or item.startswith("--media-"):
            key = item.split(" ", 1)[0]
            redacted.append(f"{key}=<redacted>")
        else:
            redacted.append(item)
    return redacted


def _direct_consumer_lease_id(environment: str, device_id: str) -> str:
    value = (
        f"ios-simulator\0{environment}-local\0{device_id}\0direct-flutter-run"
    )
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _pump_pty(
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


def _read_simulator_startup_log(device_id: str) -> str:
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


def _attach_controlling_terminal(slave_fd: int) -> None:
    """Give Flutter's resident runner a real single-character terminal."""

    os.setsid()
    fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)


def _hot_restart_attempt_observed(
    raw_log: str,
    *,
    excluded_attempt_ids: set[str] | frozenset[str],
    require_safe_terminal: bool,
) -> bool:
    safe_terminal = re.compile(
        r"(?:ios|android)_startup_safe_terminal "
        r"(?:reportedElapsedMs|elapsedMs)="
    )
    for attempt, segment in _attempt_segments(
        raw_log,
        excluded_attempt_ids=excluded_attempt_ids,
    ):
        if attempt.get("hotRestart") != "true":
            continue
        if not require_safe_terminal or safe_terminal.search(segment):
            return True
    return False


def _wait_for_hot_restart(
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
        _pump_pty(
            master_fd,
            process,
            output,
            timeout_seconds=min(0.5, max(0.0, deadline - time.monotonic())),
        )
        simulator_log = _read_simulator_startup_log(device_id)
        if _hot_restart_attempt_observed(
            simulator_log,
            excluded_attempt_ids=excluded_attempt_ids,
            require_safe_terminal=require_safe_terminal,
        ):
            return True
        if process.poll() is not None:
            return False
        time.sleep(0.25)
    return False


def _read_flutter_pid(state_root: Path, environment: str, device_id: str) -> int | None:
    safe_device_id = re.sub(r"[^A-Za-z0-9._-]+", "_", device_id).strip("_")
    state_file = state_root / environment / f"{safe_device_id or 'device'}.json"
    try:
        payload = json.loads(state_file.read_text(encoding="utf-8"))
        pid = int(payload.get("pid") or 0)
        os.kill(pid, 0)
        return pid
    except (FileNotFoundError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _find_descendant_flutter_pid(root_pid: int) -> int | None:
    pending = [root_pid]
    visited: set[int] = set()
    while pending:
        parent_pid = pending.pop()
        if parent_pid in visited:
            continue
        visited.add(parent_pid)
        try:
            children = subprocess.run(
                ["pgrep", "-P", str(parent_pid)],
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError:
            return None
        for raw_pid in children.stdout.split():
            try:
                child_pid = int(raw_pid)
            except ValueError:
                continue
            try:
                command = subprocess.run(
                    ["ps", "-o", "command=", "-p", str(child_pid)],
                    check=False,
                    capture_output=True,
                    text=True,
                ).stdout
            except OSError:
                return None
            if "flutter_tools.snapshot run" in command:
                return child_pid
            pending.append(child_pid)
    return None


def _terminate_stale_device_runtime(device_id: str, bundle_id: str) -> dict[str, Any]:
    """Terminate only the target app; never sweep unrelated host processes.

    The outer app-content UAT operation lock serializes this runner.  Host-wide
    process discovery cannot prove ownership and previously allowed one iOS
    run to terminate Android or another Simulator's frontend server.  The
    resident process created below is instead owned through its Popen handle
    and is always reaped in ``finally``.
    """
    native = subprocess.run(
        ["xcrun", "simctl", "terminate", device_id, bundle_id],
        check=False,
        capture_output=True,
        text=True,
    )
    return {
        "cleanupScope": "simulator_bundle_only",
        "terminatedFlutterResidentPids": [],
        "terminatedFrontendServerPids": [],
        "terminatedNativeApp": native.returncode == 0,
    }


def _read_installed_runtime_identity(
    device_id: str,
    bundle_id: str,
) -> dict[str, str]:
    container = subprocess.run(
        ["xcrun", "simctl", "get_app_container", device_id, bundle_id, "app"],
        check=False,
        capture_output=True,
        text=True,
    )
    if container.returncode != 0:
        raise RuntimeError(
            container.stderr.strip()
            or container.stdout.strip()
            or "installed iOS app container is unavailable"
        )
    manifest_path = Path(container.stdout.strip()) / "QWQNativeRuntime.plist"
    try:
        with manifest_path.open("rb") as source:
            manifest = plistlib.load(source)
    except (OSError, plistlib.InvalidFileException) as error:
        raise RuntimeError(
            f"installed iOS runtime manifest is unreadable: {error}"
        ) from error
    if not isinstance(manifest, dict):
        raise RuntimeError("installed iOS runtime manifest must be an object")
    identity = {
        "environment": str(manifest.get("runtimeEnvironment") or "").strip(),
        "target": str(manifest.get("launchTarget") or "").strip(),
        "runtimeConfigDigest": str(
            manifest.get("runtimeConfigDigest") or ""
        ).strip(),
        "effectiveLaunchManifestDigest": str(
            manifest.get("effectiveLaunchManifestDigest") or ""
        ).strip(),
    }
    if not identity["environment"] or not identity["target"]:
        raise RuntimeError("installed iOS runtime identity is incomplete")
    for key in ("runtimeConfigDigest", "effectiveLaunchManifestDigest"):
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", identity[key]):
            raise RuntimeError(f"installed iOS {key} is invalid")
    return identity


def _runtime_identity_issues(
    snapshots: list[dict[str, str]],
    *,
    expected_environment: str,
) -> list[str]:
    if not snapshots:
        return ["no installed iOS runtime identity snapshots were captured"]
    issues: list[str] = []
    expected_target = f"{expected_environment}-local"
    baseline = snapshots[0]
    for index, snapshot in enumerate(snapshots):
        label = "cold" if index == 0 else f"hot_restart_{index}"
        if snapshot.get("environment") != expected_environment:
            issues.append(
                f"{label}: environment is {snapshot.get('environment')!r}, "
                f"expected {expected_environment!r}"
            )
        if snapshot.get("target") != expected_target:
            issues.append(
                f"{label}: target is {snapshot.get('target')!r}, "
                f"expected {expected_target!r}"
            )
        for key in (
            "environment",
            "target",
            "runtimeConfigDigest",
            "effectiveLaunchManifestDigest",
        ):
            if snapshot.get(key) != baseline.get(key):
                issues.append(
                    f"{label}: {key} drifted from the cold runtime identity"
                )
    return issues


def _stop_original_process_group(
    process: subprocess.Popen[bytes],
    process_group_id: int,
    *,
    attempts: int = 3,
    wait_seconds: float = 5.0,
) -> bool:
    """Stop only the process group created for this Flutter session."""

    if process.poll() is not None:
        return True
    for _ in range(attempts):
        try:
            os.killpg(process_group_id, signal.SIGINT)
        except ProcessLookupError:
            return True
        try:
            process.wait(timeout=wait_seconds)
            return True
        except subprocess.TimeoutExpired:
            continue
    return process.poll() is not None


def _count_native_launches_since(raw_log: str, since: dt.datetime) -> int:
    count = 0
    for line in raw_log.splitlines():
        if "ios_did_finish_launching" not in line:
            continue
        try:
            timestamp = dt.datetime.strptime(
                line[:23],
                "%Y-%m-%d %H:%M:%S.%f",
            )
        except ValueError:
            continue
        if timestamp >= since:
            count += 1
    return count


def _attempt_segments(
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


def cold_startup_terminal_observed(
    raw_log: str,
    *,
    excluded_attempt_ids: set[str] | frozenset[str] = frozenset(),
) -> bool:
    """Return whether this run reached a cold Dart safe terminal."""

    safe_terminal = re.compile(
        r"(?:ios|android)_startup_safe_terminal "
        r"(?:reportedElapsedMs|elapsedMs)="
    )
    return any(
        attempt.get("hotRestart") == "false" and safe_terminal.search(segment)
        for attempt, segment in _attempt_segments(
            raw_log,
            excluded_attempt_ids=excluded_attempt_ids,
        )
    )


def flutter_resident_ready_for_hot_restart(raw_output: bytes | bytearray) -> bool:
    """Return whether Flutter has installed its resident command reader."""

    return (
        b"Flutter run key commands." in raw_output
        and b"R Hot restart." in raw_output
    )


def _wait_for_cold_startup(
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
        _pump_pty(
            master_fd,
            process,
            output,
            timeout_seconds=min(0.5, max(0.0, deadline - time.monotonic())),
        )
        simulator_log = _read_simulator_startup_log(device_id)
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


def _validate_attempt(attempt: dict[str, Any], raw_segment: str) -> dict[str, Any]:
    sequence = parse_startup_sequence_log(raw_segment)
    terminal = classify_startup_terminal(raw_segment, sequence)
    watchdog = extract_startup_watchdog_evidence(raw_segment)
    failures = any(
        marker in raw_segment
        for marker in (
            "startup_bootstrap_failure",
            "ios_startup_bootstrap_failure",
            "android_startup_bootstrap_failure",
        )
    )
    return {
        "attemptId": attempt.get("attemptId"),
        "launchMode": attempt.get("launchMode"),
        "hotRestart": attempt.get("hotRestart") == "true",
        "configurationState": attempt.get("configurationState"),
        "missingDefineKeys": attempt.get("missingDefineKeys"),
        "failureCode": watchdog.get("failureCode", ""),
        "canonicalTerminal": terminal,
        "bootstrapFailure": failures,
        "terminalEventCount": len(
            re.findall(
                r"(?:ios|android)_startup_safe_terminal "
                r"(?:reportedElapsedMs|elapsedMs)=",
                raw_segment,
            )
        ),
        "reportedSafeTerminalMs": watchdog.get("reportedSafeTerminalMs"),
        "nativeReceivedSafeTerminalMs": watchdog.get(
            "nativeReceivedSafeTerminalMs"
        ),
    }


def _attempt_evidence_issues(
    label: str,
    item: dict[str, Any],
    *,
    expected_launch_surface: str,
    is_cold: bool,
    max_cold_native_safe_terminal_ms: int = SAFE_TERMINAL_HARD_LIMIT_MS,
) -> list[str]:
    issues: list[str] = []
    if item["launchMode"] != expected_launch_surface:
        issues.append(
            f"{label}: launchMode is {item['launchMode']!r}, "
            f"expected {expected_launch_surface!r}"
        )
    if item["bootstrapFailure"]:
        issues.append(f"{label}: startup_bootstrap_failure observed")
    if item["canonicalTerminal"] != "routerShell":
        issues.append(
            f"{label}: canonical terminal is {item['canonicalTerminal']!r}, "
            "expected routerShell"
        )
    if item["configurationState"] != "complete":
        issues.append(f"{label}: runtime configuration was not complete")
    if item["missingDefineKeys"]:
        issues.append(f"{label}: missing define keys reported")
    if item["terminalEventCount"] != 1:
        issues.append(
            f"{label}: expected exactly one safe terminal event, "
            f"got {item['terminalEventCount']}"
        )

    reported_value = item.get("reportedSafeTerminalMs")
    if (
        not isinstance(reported_value, int)
        or reported_value > SAFE_TERMINAL_HARD_LIMIT_MS
    ):
        issues.append(
            f"{label}: reportedSafeTerminalMs is missing or exceeds "
            f"{SAFE_TERMINAL_HARD_LIMIT_MS}ms"
        )

    native_limit_ms = (
        max_cold_native_safe_terminal_ms
        if is_cold
        else SAFE_TERMINAL_HARD_LIMIT_MS
    )
    native_value = item.get("nativeReceivedSafeTerminalMs")
    if not isinstance(native_value, int) or native_value > native_limit_ms:
        issues.append(
            f"{label}: nativeReceivedSafeTerminalMs is missing or exceeds "
            f"{native_limit_ms}ms"
        )
    return issues


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", choices=ENVIRONMENTS, required=True)
    parser.add_argument("--device-id", required=True)
    # 默认按 环境 × Debug 派生 bundle id（本 smoke 为 flutter run/Debug 面）。
    parser.add_argument("--bundle", default="")
    parser.add_argument(
        "--launch-surface",
        choices=LAUNCH_SURFACES,
        default="canonical_launcher",
    )
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--ready-timeout-seconds", type=float, default=180)
    parser.add_argument(
        "--max-cold-native-safe-terminal-ms",
        type=int,
        default=SAFE_TERMINAL_HARD_LIMIT_MS,
        help=(
            "Maximum native receipt latency for the cold attempt only; "
            "reported and hot-restart terminals remain capped at 6000ms."
        ),
    )
    parser.add_argument("--restart-wait-seconds", type=float, default=20)
    parser.add_argument("--hot-restart-count", type=int, default=3)
    parser.add_argument("--preflight-only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.hot_restart_count < 1:
        print("--hot-restart-count must be at least 1", file=sys.stderr)
        return 2
    if args.max_cold_native_safe_terminal_ms < SAFE_TERMINAL_HARD_LIMIT_MS:
        print(
            "--max-cold-native-safe-terminal-ms must be at least 6000",
            file=sys.stderr,
        )
        return 2
    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else ROOT / ".qwq_output/env/repo/runs/ios_hot_restart"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    run_dir = output_dir / f"{args.env}-{stamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    if not str(args.bundle or "").strip():
        args.bundle = application_id_for("ios", args.env, "debug")

    try:
        defines = _runtime_defines(args.env, args.launch_surface)
    except (RuntimeError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 2

    if args.preflight_only:
        report_path = run_dir / "report.json"
        report = {
            "status": "passed",
            "environment": args.env,
            "deviceId": args.device_id,
            "verifiedDefineKeys": sorted(defines),
            "launchMode": defines.get("QWQ_APP_LAUNCH_MODE"),
            "consumerLeaseId": _direct_consumer_lease_id(
                args.env,
                args.device_id,
            ),
            "reportPath": str(report_path),
        }
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    stale_runtime_cleanup = _terminate_stale_device_runtime(
        args.device_id,
        args.bundle,
    )
    command = (
        ["bash", str(LAUNCHER), "-d", args.device_id]
        if args.launch_surface == "canonical_launcher"
        else ["flutter", "run", "--flavor", args.env, "-d", args.device_id]
    )
    baseline_captured_at = dt.datetime.now()
    baseline_simulator_log = _read_simulator_startup_log(args.device_id)
    baseline_attempt_ids = frozenset(
        str(attempt.get("attemptId") or "")
        for attempt in extract_dart_startup_attempts(baseline_simulator_log)
    )
    instance_state_root = run_dir / "app-instance-state"
    environment = dict(os.environ)
    environment["QWQ_IOS_SIMULATOR_UDID"] = args.device_id
    if args.launch_surface == "canonical_launcher":
        environment["QWQ_APP_RUNTIME_ENV"] = args.env
    else:
        # Direct Debug is selected only by QWQ_ENVIRONMENT. A partial
        # QWQ_APP_* identity must continue to fail closed.
        for key in (
            "QWQ_APP_RUNTIME_ENV",
            "QWQ_APP_LAUNCH_MODE",
            "QWQ_LAUNCH_TARGET",
            "QWQ_DART_DEFINES_DIGEST",
            "QWQ_EXPECTED_RUNTIME_CONFIG_DIGEST",
            "QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST",
        ):
            environment.pop(key, None)
        environment["QWQ_ENVIRONMENT"] = args.env
    environment["QWQ_APP_INSTANCE_PRESERVE_TTY"] = "1"
    environment["APP_INSTANCE_STATE_ROOT"] = str(instance_state_root)
    master_fd, slave_fd = pty.openpty()
    process = subprocess.Popen(
        command,
        cwd=APP_DIR,
        env=environment,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        preexec_fn=lambda: _attach_controlling_terminal(slave_fd),
    )
    process_group_id = os.getpgid(process.pid)
    if process_group_id != process.pid:
        raise RuntimeError(
            "Flutter session did not retain its dedicated process group"
        )
    os.close(slave_fd)
    output = bytearray()
    hot_restart_triggers: list[str] = []
    runtime_identity_snapshots: list[dict[str, str]] = []
    runtime_identity_capture_issues: list[str] = []
    process_group_stopped = False
    try:
        cold_ready = _wait_for_cold_startup(
            master_fd,
            process,
            args.device_id,
            output,
            excluded_attempt_ids=baseline_attempt_ids,
            timeout_seconds=args.ready_timeout_seconds,
        )
        observed_attempt_ids = set(baseline_attempt_ids)
        if cold_ready and process.poll() is None:
            try:
                runtime_identity_snapshots.append(
                    _read_installed_runtime_identity(
                        args.device_id,
                        args.bundle,
                    )
                )
            except RuntimeError as error:
                runtime_identity_capture_issues.append(f"cold: {error}")
            observed_attempt_ids.update(
                str(item.get("attemptId") or "")
                for item in extract_dart_startup_attempts(
                    _read_simulator_startup_log(args.device_id)
                )
            )
            for _ in range(args.hot_restart_count):
                terminal_state = termios.tcgetattr(master_fd)
                trigger = "R"
                try:
                    # Flutter may not switch to single-character mode when the
                    # launcher is nested under a noninteractive shell. Set the
                    # PTY raw for the one command so R cannot remain line-buffered.
                    tty.setraw(master_fd)
                    hot_restart_output_offset = len(output)
                    os.write(master_fd, b"R")
                    hot_grace_seconds = min(8.0, args.restart_wait_seconds)
                    hot_attempt_ready = _wait_for_hot_restart(
                        master_fd,
                        process,
                        args.device_id,
                        output,
                        excluded_attempt_ids=observed_attempt_ids,
                        timeout_seconds=hot_grace_seconds,
                        require_safe_terminal=False,
                    )
                    hot_restart_cli_started = b"Performing hot restart" in output[
                        hot_restart_output_offset:
                    ]
                    if (
                        not hot_attempt_ready
                        and not hot_restart_cli_started
                        and process.poll() is None
                    ):
                        flutter_pid = _read_flutter_pid(
                            instance_state_root,
                            args.env,
                            args.device_id,
                        )
                        if flutter_pid is None:
                            flutter_pid = _find_descendant_flutter_pid(process.pid)
                        if flutter_pid is not None:
                            try:
                                os.kill(flutter_pid, signal.SIGUSR2)
                                trigger = "SIGUSR2_fallback"
                            except OSError:
                                trigger = "SIGUSR2_fallback_failed"
                    hot_safe_ready = _wait_for_hot_restart(
                        master_fd,
                        process,
                        args.device_id,
                        output,
                        excluded_attempt_ids=observed_attempt_ids,
                        timeout_seconds=max(
                            0.0,
                            args.restart_wait_seconds - hot_grace_seconds,
                        ),
                        require_safe_terminal=True,
                    )
                    hot_restart_triggers.append(trigger)
                    if hot_safe_ready:
                        try:
                            runtime_identity_snapshots.append(
                                _read_installed_runtime_identity(
                                    args.device_id,
                                    args.bundle,
                                )
                            )
                        except RuntimeError as error:
                            runtime_identity_capture_issues.append(
                                f"hot_restart_{len(hot_restart_triggers)}: {error}"
                            )
                    observed_attempt_ids.update(
                        str(item.get("attemptId") or "")
                        for item in extract_dart_startup_attempts(
                            _read_simulator_startup_log(args.device_id)
                        )
                    )
                finally:
                    termios.tcsetattr(master_fd, termios.TCSANOW, terminal_state)
    finally:
        process_group_stopped = _stop_original_process_group(
            process,
            process_group_id,
        )
        _pump_pty(master_fd, process, output, timeout_seconds=1)
        os.close(master_fd)

    flutter_output = output.decode("utf-8", errors="replace")
    (run_dir / "flutter-run.log").write_text(flutter_output, encoding="utf-8")
    simulator_log = _read_simulator_startup_log(args.device_id)
    (run_dir / "ios-startup.log").write_text(simulator_log, encoding="utf-8")

    segments = _attempt_segments(
        simulator_log,
        excluded_attempt_ids=baseline_attempt_ids,
    )
    attempt_reports = [_validate_attempt(attempt, segment) for attempt, segment in segments]
    cold = next(
        (item for item in attempt_reports if not item["hotRestart"]),
        None,
    )
    hot_restarts = [item for item in attempt_reports if item["hotRestart"]]
    native_did_finish_count = _count_native_launches_since(
        simulator_log,
        baseline_captured_at,
    )
    issues: list[str] = []
    issues.extend(runtime_identity_capture_issues)
    issues.extend(
        _runtime_identity_issues(
            runtime_identity_snapshots,
            expected_environment=args.env,
        )
    )
    if len(runtime_identity_snapshots) != args.hot_restart_count + 1:
        issues.append(
            "expected runtime identity readback for cold plus "
            f"{args.hot_restart_count} hot restarts, got "
            f"{len(runtime_identity_snapshots)}"
        )
    if not process_group_stopped:
        issues.append(
            "Flutter process group did not exit after scoped SIGINT requests"
        )
    if cold is None:
        issues.append("cold Dart startup attempt was not observed")
    if len(hot_restarts) != args.hot_restart_count:
        issues.append(
            "expected "
            f"{args.hot_restart_count} hot-restart Dart startup attempts, "
            f"got {len(hot_restarts)}"
        )
    labeled_attempts = [("cold", cold)] + [
        (f"hot_restart_{index}", item)
        for index, item in enumerate(hot_restarts, start=1)
    ]
    for label, item in labeled_attempts:
        if item is None:
            continue
        issues.extend(
            _attempt_evidence_issues(
                label,
                item,
                expected_launch_surface=args.launch_surface,
                is_cold=label == "cold",
                max_cold_native_safe_terminal_ms=(
                    args.max_cold_native_safe_terminal_ms
                ),
            )
        )
    if native_did_finish_count != 1:
        issues.append(
            "expected exactly one ios_did_finish_launching for the cold "
            f"process launch, got {native_did_finish_count}; "
            "native relaunch must not be mistaken for hot restart"
        )

    report_path = run_dir / "report.json"
    report = {
        "status": "passed" if not issues else "failed",
        "environment": args.env,
        "deviceId": args.device_id,
        "launchMode": defines.get("QWQ_APP_LAUNCH_MODE"),
        "consumerLeaseId": _direct_consumer_lease_id(args.env, args.device_id),
        "hotRestartCount": args.hot_restart_count,
        "hotRestartTriggers": hot_restart_triggers,
        "staleRuntimeCleanup": stale_runtime_cleanup,
        "flutterProcessGroupId": process_group_id,
        "flutterProcessGroupStoppedBySigint": process_group_stopped,
        "flutterRunExitCode": process.returncode,
        "nativeDidFinishLaunchingCount": native_did_finish_count,
        "runtimeIdentitySnapshots": runtime_identity_snapshots,
        "safeTerminalBudgetsMs": {
            "reported": SAFE_TERMINAL_HARD_LIMIT_MS,
            "hotNativeReceived": SAFE_TERMINAL_HARD_LIMIT_MS,
            "coldNativeReceived": args.max_cold_native_safe_terminal_ms,
        },
        "attempts": attempt_reports,
        "issues": issues,
        "flutterRunLog": str(run_dir / "flutter-run.log"),
        "iosStartupLog": str(run_dir / "ios-startup.log"),
        "command": _redacted_command(command),
        "reportPath": str(report_path),
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
