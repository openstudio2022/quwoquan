"""Patrol 测试执行：命令运行、进程组终止与执行摘要/失败原因归因。

正文自 run_environment_patrol_smoke.py 逐字搬入。
"""
from __future__ import annotations

import os
import queue
import re
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable

from quwoquan_ops.ci.device_matrix.evidence import repo_relative

from .cli_args import (
    _redact_command,
    _redact_text,
    summarize_output,
)
from .constants import (
    PATROL_EXECUTION_SUMMARY_PATTERN,
    XCTEST_EXECUTION_SUMMARY_PATTERN,
)


def patrol_test_execution_summary(output: str) -> dict[str, Any]:
    """Prefer XCTest's executed-test record over Patrol's known zero summary."""

    xctest = XCTEST_EXECUTION_SUMMARY_PATTERN.search(output)
    if xctest is not None:
        return {
            "framework": "xctest",
            "executed": int(xctest.group("executed")),
            "failed": int(xctest.group("failed")),
            "skipped": int(xctest.group("skipped") or 0),
        }
    patrol = PATROL_EXECUTION_SUMMARY_PATTERN.search(output)
    if patrol is not None:
        return {
            "framework": "patrol",
            "executed": int(patrol.group("executed")),
            "failed": int(patrol.group("failed")),
            "skipped": int(patrol.group("skipped")),
        }
    return {
        "framework": "unknown",
        "executed": None,
        "failed": None,
        "skipped": None,
    }


def patrol_test_execution_failure_reason(summary: dict[str, Any]) -> str:
    """Return why a real Patrol/XCTest summary cannot prove a passed run."""

    framework = summary.get("framework")
    executed = summary.get("executed")
    failed = summary.get("failed")
    skipped = summary.get("skipped")
    if framework not in {"xctest", "patrol"} or any(
        not isinstance(value, int) or isinstance(value, bool)
        for value in (executed, failed, skipped)
    ):
        return "Patrol/XCTest execution summary is missing or incomplete"
    if executed <= 0:
        return "Patrol/XCTest execution summary reports zero executed tests"
    if failed != 0:
        return f"Patrol/XCTest execution summary reports {failed} failed tests"
    if skipped != 0:
        return f"Patrol/XCTest execution summary reports {skipped} skipped tests"
    return ""


def apply_patrol_test_execution_summary(
    result: dict[str, Any],
    output: str,
    *,
    dry_run: bool,
) -> None:
    """Attach the summary and fail a real run that lacks passing test counts."""

    result["testExecution"] = patrol_test_execution_summary(output)
    if dry_run:
        return
    execution_failure = patrol_test_execution_failure_reason(
        result["testExecution"]
    )
    if not execution_failure:
        return
    result["exitCode"] = 1
    result["outputSummary"] = (
        str(result.get("outputSummary") or "") + "\n" + execution_failure
    ).strip()


def _first_typed_patrol_blocker(output: str) -> dict[str, Any]:
    """Extract the first canonical Cloud failure without copying its payload."""

    normalized = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", output)
    match = re.search(
        r"CloudException\(.*?statusCode:\s*(?P<status>null|[0-9]{3}),"
        r".*?code:\s*(?P<code>[A-Z][A-Za-z0-9_.]+),"
        r".*?sourceOperationId:\s*(?P<operation>[A-Za-z][A-Za-z0-9_.]+)\)",
        normalized,
        flags=re.DOTALL,
    )
    if match is None:
        return {}
    raw_status = match.group("status")
    return {
        "errorCode": match.group("code"),
        "sourceOperationId": match.group("operation"),
        "httpStatus": None if raw_status == "null" else int(raw_status),
    }


def run_command(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout_seconds: int | None = None,
    log_path: Path | None = None,
    secret_values: tuple[str, ...] = (),
    output_line_handler: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    process: subprocess.Popen[str] | None = None
    try:
        process = subprocess.Popen(
            command,
            cwd=str(cwd),
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        if output_line_handler is None:
            output, _ = process.communicate(timeout=timeout_seconds)
            output = output or ""
            exit_code = process.returncode
            timed_out = False
        else:
            output_queue: queue.Queue[str | None] = queue.Queue()

            def read_output() -> None:
                assert process is not None and process.stdout is not None
                try:
                    for line in process.stdout:
                        output_queue.put(line)
                finally:
                    output_queue.put(None)

            reader = threading.Thread(target=read_output, daemon=True)
            reader.start()
            deadline = (
                time.monotonic() + timeout_seconds
                if timeout_seconds is not None
                else None
            )
            chunks: list[str] = []
            handler_error: Exception | None = None
            timed_out = False
            stream_ended = False
            while not stream_ended:
                if deadline is not None and time.monotonic() >= deadline:
                    timed_out = True
                    break
                wait_seconds = (
                    min(0.25, max(0.01, deadline - time.monotonic()))
                    if deadline is not None
                    else 0.25
                )
                try:
                    line = output_queue.get(timeout=wait_seconds)
                except queue.Empty:
                    if process.poll() is not None and not reader.is_alive():
                        break
                    continue
                if line is None:
                    stream_ended = True
                    continue
                chunks.append(line)
                try:
                    output_line_handler(line)
                except Exception as error:  # noqa: BLE001
                    handler_error = error
                    break
            if timed_out or handler_error is not None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait()
            else:
                process.wait()
            reader.join(timeout=10)
            while True:
                try:
                    line = output_queue.get_nowait()
                except queue.Empty:
                    break
                if line is not None:
                    chunks.append(line)
            output = "".join(chunks)
            if handler_error is not None:
                output += f"\ncontrolled output handler failed: {handler_error}\n"
                exit_code = 2
            elif timed_out:
                exit_code = 124
            else:
                exit_code = int(process.returncode or 0)
            if process.stdout is not None:
                process.stdout.close()
    except subprocess.TimeoutExpired:
        if process is not None:
            output = _terminate_process_group(process)
        else:
            output = ""
        exit_code = 124
        timed_out = True
    except KeyboardInterrupt:
        if process is not None:
            _terminate_process_group(process)
        raise
    redacted_output = _redact_text(output, secret_values)
    result = {
        "command": _redact_command(command),
        "cwd": str(cwd),
        "exitCode": exit_code,
        "timedOut": timed_out,
        "durationMs": int((time.monotonic() - started) * 1000),
        "outputSummary": summarize_output(redacted_output),
    }
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(redacted_output, encoding="utf-8")
        result["logPath"] = repo_relative(log_path)
    return result


def _terminate_process_group(process: subprocess.Popen[str]) -> str:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        output, _ = process.communicate(timeout=10)
        return output or ""
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        output, _ = process.communicate()
        return output or ""
