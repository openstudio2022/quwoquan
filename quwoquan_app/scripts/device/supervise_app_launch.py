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

from quwoquan_app.scripts.device.startup_first_frame import (
    extract_dart_startup_attempts,
)
from quwoquan_ops.cli.lib.app_launch_attempt import (
    CONFIGURATION_STATES,
    create_app_launch_attempt,
    read_app_launch_attempt,
    record_app_launch_attempt_observation,
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


_PHASE_MARKER = re.compile(
    r"^QWQ_APP_LAUNCH_PHASE status="
    r"(compiled|installing|installed|configuring|configured|launching|launched)$"
)


def _advance(receipt: Path, target: str) -> None:
    current = str(read_app_launch_attempt(receipt)["status"])
    if current == target:
        return
    transition_app_launch_attempt(receipt, target)


def _observed_phase_from(line: str) -> str:
    match = _PHASE_MARKER.fullmatch(line.strip())
    return match.group(1) if match is not None else ""


def _failure_for(status: str) -> str:
    if status in {"prepared", "compiling"}:
        return "APP.LAUNCH.compile_failed"
    if status in {"compiled", "installing"}:
        return "APP.LAUNCH.install_failed"
    if status == "installed":
        return "APP.LAUNCH.runtime_config_missing"
    if status == "configuring":
        return "APP.LAUNCH.runtime_config_activation_failed"
    return "APP.LAUNCH.launch_failed"


def _configuration_state_from(line: str) -> str:
    """Read configurationState off the canonical dart startup attempt line.

    文法只有一处定义：`(android|ios)_dart_startup_attempt`。这里复用
    startup_log 的解析器，不为同一事实另立第二条 marker。
    """

    for attempt in extract_dart_startup_attempts(line):
        state = str(attempt.get("configurationState") or "")
        if state in CONFIGURATION_STATES:
            return state
    return ""


def _settle_runtime_health(receipt: Path) -> None:
    """Settle runtime health once, from what this attempt actually observed.

    运行时健康只有真的到达 launched 才可观测；未启动的 attempt 保持 unobserved，
    不得用编译或安装阶段的结论冒充运行时结论。
    """

    payload = read_app_launch_attempt(receipt)
    launched = any(
        str(item.get("status") or "") == "launched"
        for item in payload["transitions"]
        if isinstance(item, dict)
    )
    if not launched or payload["runtimeHealthStatus"] != "unobserved":
        return
    degraded = any(
        warning.startswith("warning/runtime_degraded")
        for warning in payload["warnings"]
    ) or payload["status"] == "runtime_degraded"
    record_app_launch_attempt_observation(
        receipt,
        runtime_health_status="degraded" if degraded else "healthy",
    )


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
            observed_phase = _observed_phase_from(line)
            if observed_phase:
                _advance(args.receipt, observed_phase)
            if "error launching application" in lowered:
                observed_launch_error = True
            if "[bootstrap] source=bootstrap_failure" in lowered:
                record_app_launch_attempt_warning(
                    args.receipt,
                    "warning/runtime_degraded: bootstrap_failure",
                )
            configuration_state = _configuration_state_from(line)
            if configuration_state:
                record_app_launch_attempt_observation(
                    args.receipt,
                    configuration_state=configuration_state,
                )
            # Flutter/Xcode 的人类可读文案会随工具版本变化，不能作为状态事实。
            # compile/install/configure/launch 只能由 executor 发出的规范 marker 推进。
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
        _settle_runtime_health(args.receipt)
        return 1
    finally:
        for handle in log_handles:
            handle.close()

    current = read_app_launch_attempt(args.receipt)["status"]
    if interrupted:
        transition_app_launch_attempt(args.receipt, "stopped")
        _settle_runtime_health(args.receipt)
        return 130
    if timed_out:
        current = read_app_launch_attempt(args.receipt)["status"]
        transition_app_launch_attempt(
            args.receipt,
            "failed",
            first_blocker=_failure_for(current),
            warning=f"launch did not reach launched within {args.timeout_seconds:g}s",
        )
        _settle_runtime_health(args.receipt)
        return 124
    if exit_code != 0:
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
        _settle_runtime_health(args.receipt)
        return exit_code
    if current == "launched":
        transition_app_launch_attempt(args.receipt, "stopped")
        _settle_runtime_health(args.receipt)
        return 0
    transition_app_launch_attempt(
        args.receipt,
        "failed",
        first_blocker=_failure_for(current),
        warning="launch command exited before a launched milestone",
    )
    _settle_runtime_health(args.receipt)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
