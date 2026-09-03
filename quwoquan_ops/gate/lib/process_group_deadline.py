#!/usr/bin/env python3
"""Run one command in an isolated process group with a hard wall deadline."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Mapping, Sequence

TIMEOUT_EXIT_CODE = 124
DEFAULT_GRACE_SECONDS = 2.0


@dataclass(frozen=True)
class BoundedProcessResult:
    returncode: int
    stdout: bytes
    stderr: bytes
    timed_out: bool
    termination_signal: str | None
    process_returncode: int | None
    pid: int | None
    started: bool


def _signal_group(process: subprocess.Popen[bytes], sig: signal.Signals) -> None:
    try:
        os.killpg(process.pid, sig)
    except ProcessLookupError:
        pass


def run_command(
    argv: Sequence[str],
    *,
    cwd: Path | str | None = None,
    timeout_seconds: float,
    grace_seconds: float = DEFAULT_GRACE_SECONDS,
    capture_output: bool = False,
    stdout: BinaryIO | int | None = None,
    stderr: BinaryIO | int | None = None,
    env: Mapping[str, str] | None = None,
) -> BoundedProcessResult:
    """Run argv in its own POSIX process group and bound total wall time."""

    if not argv:
        raise ValueError("argv 不能为空")
    if timeout_seconds <= 0:
        return BoundedProcessResult(
            returncode=TIMEOUT_EXIT_CODE,
            stdout=b"",
            stderr=b"",
            timed_out=True,
            termination_signal=None,
            process_returncode=None,
            pid=None,
            started=False,
        )
    if grace_seconds < 0:
        raise ValueError("grace_seconds 不得为负数")
    if os.name != "posix":
        raise RuntimeError("process-group deadline runner 仅支持 POSIX")
    if capture_output and (stdout is not None or stderr is not None):
        raise ValueError("capture_output 与 stdout/stderr 不得同时设置")

    process = subprocess.Popen(
        list(argv),
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE if capture_output else stdout,
        stderr=subprocess.PIPE if capture_output else stderr,
        env=env,
        start_new_session=True,
    )
    try:
        out, err = process.communicate(timeout=timeout_seconds)
        return BoundedProcessResult(
            returncode=process.returncode,
            stdout=out or b"",
            stderr=err or b"",
            timed_out=False,
            termination_signal=None,
            process_returncode=process.returncode,
            pid=process.pid,
            started=True,
        )
    except subprocess.TimeoutExpired:
        _signal_group(process, signal.SIGTERM)
        termination_signal = "SIGTERM"
        try:
            out, err = process.communicate(timeout=grace_seconds)
        except subprocess.TimeoutExpired:
            _signal_group(process, signal.SIGKILL)
            termination_signal = "SIGKILL"
            out, err = process.communicate()
        return BoundedProcessResult(
            returncode=TIMEOUT_EXIT_CODE,
            stdout=out or b"",
            stderr=err or b"",
            timed_out=True,
            termination_signal=termination_signal,
            process_returncode=process.returncode,
            pid=process.pid,
            started=True,
        )


def _write_result(
    path: Path,
    *,
    result: BoundedProcessResult,
    deadline_epoch_seconds: float,
    grace_seconds: float,
) -> None:
    payload = {
        "schemaVersion": 1,
        "outcome": "timeout" if result.timed_out else "exited",
        "exitCode": result.returncode,
        "processReturnCode": result.process_returncode,
        "timedOut": result.timed_out,
        "terminationSignal": result.termination_signal,
        "pid": result.pid,
        "started": result.started,
        "deadlineEpochSeconds": deadline_epoch_seconds,
        "graceSeconds": grace_seconds,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".tmp.{os.getpid()}")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deadline-epoch-seconds", required=True, type=float)
    parser.add_argument(
        "--grace-seconds", type=float, default=DEFAULT_GRACE_SECONDS
    )
    parser.add_argument("--result-json", required=True, type=Path)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = list(args.command)
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        parser.error("-- 后必须提供命令")

    remaining = args.deadline_epoch_seconds - time.time()
    result = run_command(
        command,
        timeout_seconds=remaining,
        grace_seconds=args.grace_seconds,
    )
    _write_result(
        args.result_json,
        result=result,
        deadline_epoch_seconds=args.deadline_epoch_seconds,
        grace_seconds=args.grace_seconds,
    )
    if result.timed_out:
        print(
            "[deadline-runner] TIMEOUT: terminated isolated process group "
            f"pid={result.pid} signal={result.termination_signal}",
            file=sys.stderr,
        )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
