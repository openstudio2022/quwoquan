#!/usr/bin/env python3
"""Run Flutter once and project compile/install/launch milestones into a receipt."""

from __future__ import annotations

import argparse
import os
import queue
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import TextIO

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.app_launch_attempt import (
    create_app_launch_attempt,
    read_app_launch_attempt,
    record_app_launch_attempt_warning,
    transition_app_launch_attempt,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--platform", choices=("android", "ios"), required=True)
    parser.add_argument("--build-mode", choices=("debug", "profile", "release"), required=True)
    parser.add_argument(
        "--run-mode",
        choices=("content-live", "ui-only", "release-artifact"),
        required=True,
    )
    parser.add_argument("--device", required=True)
    parser.add_argument("--application-id", default="")
    parser.add_argument("--artifact-digest", default="")
    parser.add_argument("--launch-digest", default="")
    parser.add_argument("--log-ref", action="append", default=[])
    parser.add_argument("--warning", action="append", default=[])
    parser.add_argument("--timeout-seconds", type=float, default=900.0)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser


def _advance(receipt: Path, target: str) -> None:
    current = read_app_launch_attempt(receipt)["status"]
    order = ("prepared", "compiling", "compiled", "installing", "installed", "launching", "launched")
    if current not in order or order.index(current) >= order.index(target):
        return
    while current != target:
        next_state = order[order.index(current) + 1]
        transition_app_launch_attempt(receipt, next_state)
        current = next_state


def _failure_for(status: str) -> str:
    if status in {"prepared", "compiling"}:
        return "APP.LAUNCH.compile_failed"
    if status in {"compiled", "installing"}:
        return "APP.LAUNCH.install_failed"
    return "APP.LAUNCH.launch_failed"


def _installation_snapshot(
    platform: str,
    device: str,
    application_id: str,
) -> str:
    """Return a reinstall-sensitive package identity without changing device state."""

    if not application_id:
        return ""
    if platform == "ios":
        command = [
            "xcrun",
            "simctl",
            "get_app_container",
            device,
            application_id,
            "app",
        ]
    else:
        command = [
            "adb",
            "-s",
            device,
            "shell",
            "dumpsys",
            "package",
            application_id,
        ]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    output = result.stdout.strip()
    if platform == "ios":
        path = Path(output)
        try:
            return f"{path.resolve()}\0{path.stat().st_mtime_ns}"
        except OSError:
            return ""
    values = []
    for pattern in (
        r"^\s*codePath=(.+)$",
        r"^\s*versionCode=(\S+)",
        r"^\s*lastUpdateTime=(.+)$",
    ):
        match = re.search(pattern, output, re.MULTILINE)
        values.append(match.group(1).strip() if match else "")
    return "\0".join(values) if any(values) else ""


def _advance_fresh_install(
    receipt: Path,
    *,
    before: str,
    platform: str,
    device: str,
    application_id: str,
) -> bool:
    after = _installation_snapshot(platform, device, application_id)
    if not after or after == before:
        return False
    _advance(receipt, "launching")
    return True


def main() -> int:
    args = _parser().parse_args()
    command = list(args.command)
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        raise SystemExit("APP.LAUNCH.compile_failed: missing launch command")
    create_app_launch_attempt(
        args.receipt,
        environment=args.environment,
        target=args.target,
        platform=args.platform,
        build_mode=args.build_mode,
        run_mode=args.run_mode,
        device_id=args.device,
        artifact_digest=args.artifact_digest,
        launch_digest=args.launch_digest,
        warnings=args.warning,
        log_refs=args.log_ref,
    )
    if args.environment == "prod" and args.build_mode != "release":
        transition_app_launch_attempt(
            args.receipt,
            "failed",
            first_blocker="APP.LAUNCH.prod_debug_forbidden",
        )
        return 2

    child: subprocess.Popen[str] | None = None
    log_handles: list[TextIO] = []
    interrupted = False
    timed_out = False
    observed_launch_error = False
    installation_before = _installation_snapshot(
        args.platform,
        args.device,
        args.application_id,
    )

    def forward(signum: int, _frame: object) -> None:
        nonlocal interrupted
        interrupted = True
        if child is not None and child.poll() is None:
            try:
                os.killpg(child.pid, signum)
            except ProcessLookupError:
                pass

    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, forward)
    transition_app_launch_attempt(args.receipt, "compiling")
    try:
        for raw_path in args.log_ref:
            log_path = Path(raw_path)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_handles.append(log_path.open("w", encoding="utf-8"))
        child = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        assert child.stdout is not None
        output: queue.Queue[str | None] = queue.Queue()

        def read_output() -> None:
            assert child is not None and child.stdout is not None
            for emitted_line in child.stdout:
                output.put(emitted_line)
            output.put(None)

        threading.Thread(target=read_output, daemon=True).start()
        deadline = time.monotonic() + args.timeout_seconds
        while True:
            current = read_app_launch_attempt(args.receipt)["status"]
            if current != "launched" and time.monotonic() >= deadline:
                timed_out = True
                if child.poll() is None:
                    os.killpg(child.pid, signal.SIGTERM)
                break
            try:
                line = output.get(timeout=0.25)
            except queue.Empty:
                if child.poll() is not None:
                    continue
                continue
            if line is None:
                break
            print(line, end="", flush=True)
            for handle in log_handles:
                handle.write(line)
                handle.flush()
            lowered = line.lower()
            if (
                "built " in lowered
                or "build succeeded" in lowered
                or "xcode build done." in lowered
            ):
                _advance(args.receipt, "compiled")
            if "installing" in lowered:
                _advance(args.receipt, "installing")
            if "installing and launching" in lowered:
                _advance(args.receipt, "launching")
            if "error launching application" in lowered:
                observed_launch_error = True
            if "[bootstrap] source=bootstrap_failure" in lowered:
                record_app_launch_attempt_warning(
                    args.receipt,
                    "warning/runtime_degraded: bootstrap_failure",
                )
            if "syncing files" in lowered or "install complete" in lowered:
                _advance(args.receipt, "launching")
            if (
                "flutter run key commands" in lowered
                or "a dart vm service" in lowered
                or "the flutter devtools debugger" in lowered
            ):
                _advance(args.receipt, "launched")
        try:
            exit_code = child.wait(timeout=5 if timed_out else None)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            exit_code = child.wait()
    except OSError as error:
        current = read_app_launch_attempt(args.receipt)["status"]
        transition_app_launch_attempt(
            args.receipt,
            "failed",
            first_blocker=_failure_for(current),
            warning=str(error),
        )
        return 1
    finally:
        for handle in log_handles:
            handle.close()

    current = read_app_launch_attempt(args.receipt)["status"]
    if interrupted:
        transition_app_launch_attempt(args.receipt, "stopped")
        return 130
    if timed_out:
        _advance_fresh_install(
            args.receipt,
            before=installation_before,
            platform=args.platform,
            device=args.device,
            application_id=args.application_id,
        )
        current = read_app_launch_attempt(args.receipt)["status"]
        transition_app_launch_attempt(
            args.receipt,
            "failed",
            first_blocker=_failure_for(current),
            warning=f"launch did not reach launched within {args.timeout_seconds:g}s",
        )
        return 124
    if exit_code != 0:
        _advance_fresh_install(
            args.receipt,
            before=installation_before,
            platform=args.platform,
            device=args.device,
            application_id=args.application_id,
        )
        current = read_app_launch_attempt(args.receipt)["status"]
        if current == "launched":
            transition_app_launch_attempt(
                args.receipt,
                "runtime_degraded",
                warning=f"Flutter process exited after launch with code {exit_code}",
            )
        else:
            transition_app_launch_attempt(
                args.receipt,
                "failed",
                first_blocker=(
                    "APP.LAUNCH.launch_failed"
                    if observed_launch_error
                    else _failure_for(current)
                ),
            )
        return exit_code
    if current == "launched":
        transition_app_launch_attempt(args.receipt, "stopped")
        return 0
    transition_app_launch_attempt(
        args.receipt,
        "failed",
        first_blocker=_failure_for(current),
        warning="launch command exited before a launched milestone",
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
