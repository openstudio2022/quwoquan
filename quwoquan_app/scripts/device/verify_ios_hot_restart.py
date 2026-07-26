#!/usr/bin/env python3
"""Run the real canonical Flutter/iOS Simulator hot-restart smoke.

The smoke deliberately launches through ``start_app_instance.sh``. That keeps
the Flutter CLI define set identical to a developer launch and makes a missing
define fail before Flutter builds or installs the kernel.
"""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import os
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
LAUNCHER = APP_DIR / "scripts/device/start_app_instance.sh"
ENVIRONMENTS = ("alpha", "beta", "gamma", "prod")
IOS_BUNDLE = "com.example.quwoquanApp"


def _runtime_defines(environment: str) -> dict[str, str]:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/env/print_app_env_dart_defines.py",
            "--env",
            environment,
            "--format",
            "json",
            "--launch-mode",
            "canonical_launcher",
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
        children = subprocess.run(
            ["pgrep", "-P", str(parent_pid)],
            check=False,
            capture_output=True,
            text=True,
        )
        for raw_pid in children.stdout.split():
            try:
                child_pid = int(raw_pid)
            except ValueError:
                continue
            command = subprocess.run(
                ["ps", "-o", "command=", "-p", str(child_pid)],
                check=False,
                capture_output=True,
                text=True,
            ).stdout
            if "flutter_tools.snapshot run" in command:
                return child_pid
            pending.append(child_pid)
    return None


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
        if cold_startup_terminal_observed(
            simulator_log,
            excluded_attempt_ids=excluded_attempt_ids,
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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", choices=ENVIRONMENTS, required=True)
    parser.add_argument("--device-id", required=True)
    parser.add_argument("--bundle", default=IOS_BUNDLE)
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--ready-timeout-seconds", type=float, default=180)
    parser.add_argument("--restart-wait-seconds", type=float, default=20)
    parser.add_argument("--preflight-only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else ROOT / ".qwq_output/env/repo/runs/ios_hot_restart"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    run_dir = output_dir / f"{args.env}-{stamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    try:
        defines = _runtime_defines(args.env)
    except (RuntimeError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 2

    if args.preflight_only:
        report = {
            "status": "passed",
            "environment": args.env,
            "deviceId": args.device_id,
            "verifiedDefineKeys": sorted(defines),
            "launchMode": defines.get("QWQ_APP_LAUNCH_MODE"),
        }
        (run_dir / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    command = [
        "bash",
        str(LAUNCHER),
        "--env",
        args.env,
        "--device-id",
        args.device_id,
        "--instance-namespace",
        "ios-hot-restart-smoke",
        "--service-mode",
        "ios-hot-restart-smoke",
    ]
    baseline_captured_at = dt.datetime.now()
    baseline_simulator_log = _read_simulator_startup_log(args.device_id)
    baseline_attempt_ids = frozenset(
        str(attempt.get("attemptId") or "")
        for attempt in extract_dart_startup_attempts(baseline_simulator_log)
    )
    instance_state_root = run_dir / "app-instance-state"
    environment = dict(os.environ)
    environment["QWQ_IOS_SIMULATOR_UDID"] = args.device_id
    environment["QWQ_APP_RUNTIME_ENV"] = args.env
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
    os.close(slave_fd)
    output = bytearray()
    hot_restart_trigger = ""
    try:
        cold_ready = _wait_for_cold_startup(
            master_fd,
            process,
            args.device_id,
            output,
            excluded_attempt_ids=baseline_attempt_ids,
            timeout_seconds=args.ready_timeout_seconds,
        )
        if cold_ready and process.poll() is None:
            terminal_state = termios.tcgetattr(master_fd)
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
                    excluded_attempt_ids=baseline_attempt_ids,
                    timeout_seconds=hot_grace_seconds,
                    require_safe_terminal=False,
                )
                hot_restart_trigger = "R"
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
                            hot_restart_trigger = "SIGUSR2_fallback"
                        except OSError:
                            hot_restart_trigger = "SIGUSR2_fallback_failed"
                _wait_for_hot_restart(
                    master_fd,
                    process,
                    args.device_id,
                    output,
                    excluded_attempt_ids=baseline_attempt_ids,
                    timeout_seconds=max(
                        0.0,
                        args.restart_wait_seconds - hot_grace_seconds,
                    ),
                    require_safe_terminal=True,
                )
            finally:
                termios.tcsetattr(master_fd, termios.TCSANOW, terminal_state)
    finally:
        if process.poll() is None:
            try:
                os.write(master_fd, b"\x03")
            except OSError:
                pass
            _pump_pty(master_fd, process, output, timeout_seconds=5)
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
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
    hot = next(
        (item for item in reversed(attempt_reports) if item["hotRestart"]),
        None,
    )
    native_did_finish_count = _count_native_launches_since(
        simulator_log,
        baseline_captured_at,
    )
    issues: list[str] = []
    if cold is None:
        issues.append("cold Dart startup attempt was not observed")
    if hot is None:
        issues.append("hot-restart Dart startup attempt was not observed")
    for label, item in (("cold", cold), ("hot_restart", hot)):
        if item is None:
            continue
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
        for key in ("reportedSafeTerminalMs", "nativeReceivedSafeTerminalMs"):
            value = item.get(key)
            if not isinstance(value, int) or value > 6000:
                issues.append(f"{label}: {key} is missing or exceeds 6000ms")
    if native_did_finish_count != 1:
        issues.append(
            "expected exactly one ios_did_finish_launching for the cold "
            f"process launch, got {native_did_finish_count}; "
            "native relaunch must not be mistaken for hot restart"
        )

    report = {
        "status": "passed" if not issues else "failed",
        "environment": args.env,
        "deviceId": args.device_id,
        "launchMode": defines.get("QWQ_APP_LAUNCH_MODE"),
        "hotRestartTrigger": hot_restart_trigger,
        "flutterRunExitCode": process.returncode,
        "nativeDidFinishLaunchingCount": native_did_finish_count,
        "attempts": attempt_reports,
        "issues": issues,
        "flutterRunLog": str(run_dir / "flutter-run.log"),
        "iosStartupLog": str(run_dir / "ios-startup.log"),
        "command": _redacted_command(command),
    }
    (run_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
