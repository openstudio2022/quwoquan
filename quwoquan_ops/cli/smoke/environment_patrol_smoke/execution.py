"""Patrol 测试执行：命令运行、进程组终止与执行摘要/失败原因归因。

正文自 run_environment_patrol_smoke.py 逐字搬入。
"""

from __future__ import annotations

import hashlib
import os
import queue
import re
import signal
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

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

_COMMAND_CLEANUP_TIMEOUT_SECONDS = 10.0


def _secondary_command_failure(stage: str, error: Exception) -> dict[str, str]:
    diagnostic = f"{type(error).__name__}\0{error}".encode("utf-8", errors="replace")
    return {
        "stage": stage,
        "causeType": type(error).__name__,
        "diagnosticDigest": "sha256:" + hashlib.sha256(diagnostic).hexdigest(),
    }


def _cleanup_interrupted_process(process: subprocess.Popen[str]) -> None:
    """Keep KeyboardInterrupt primary even when managed cleanup also fails."""

    try:
        _terminate_process_group(process)
    except (OSError, subprocess.SubprocessError) as error:
        _secondary_command_failure("process-group-cleanup", error)


def _remaining_command_seconds(deadline: float | None) -> float | None:
    if deadline is None:
        return None
    return max(0.0, deadline - time.monotonic())


def _wait_for_process(
    process: subprocess.Popen[str],
    *,
    deadline: float | None,
) -> None:
    process.wait(timeout=_remaining_command_seconds(deadline))


def _finish_output_reader(
    *,
    process: subprocess.Popen[str],
    reader: threading.Thread,
    deadline: float | None,
    secondary_failures: list[dict[str, str]],
) -> bool:
    """Join and close the reader without starting a second timeout budget."""

    reader.join(timeout=_remaining_command_seconds(deadline))
    if reader.is_alive():
        secondary_failures.append(
            _secondary_command_failure(
                "output-reader-join",
                subprocess.TimeoutExpired("output reader", 0),
            )
        )
        return False
    if process.stdout is None:
        return True
    remaining = _remaining_command_seconds(deadline)
    if remaining is not None and remaining <= 0:
        secondary_failures.append(
            _secondary_command_failure(
                "stdout-close",
                subprocess.TimeoutExpired("stdout close", 0),
            )
        )
        return False
    close_error: list[Exception] = []

    def close_stdout() -> None:
        assert process.stdout is not None
        try:
            process.stdout.close()
        except Exception as error:  # noqa: BLE001
            close_error.append(error)

    closer = threading.Thread(target=close_stdout, daemon=True)
    closer.start()
    closer.join(timeout=_remaining_command_seconds(deadline))
    if closer.is_alive():
        secondary_failures.append(
            _secondary_command_failure(
                "stdout-close",
                subprocess.TimeoutExpired("stdout close", 0),
            )
        )
        return False
    if close_error:
        secondary_failures.append(
            _secondary_command_failure("stdout-close", close_error[0])
        )
    return deadline is None or time.monotonic() < deadline


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
    execution_failure = patrol_test_execution_failure_reason(result["testExecution"])
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
    timeout_seconds: float | None = None,
    log_path: Path | None = None,
    secret_values: tuple[str, ...] = (),
    output_line_handler: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    deadline = started + timeout_seconds if timeout_seconds is not None else None
    process: subprocess.Popen[str] | None = None
    secondary_failures: list[dict[str, str]] = []
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
            output, _ = process.communicate(
                timeout=_remaining_command_seconds(deadline)
            )
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
            chunks: list[str] = []
            handler_error: Exception | None = None
            timed_out = False
            stream_ended = False
            while not stream_ended:
                if deadline is not None and time.monotonic() >= deadline:
                    timed_out = True
                    break
                wait_seconds = (
                    min(0.25, max(0.0, deadline - time.monotonic()))
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

            cleanup_required = timed_out or handler_error is not None
            reader_finalized = False
            if not cleanup_required:
                try:
                    reader_finished = _finish_output_reader(
                        process=process,
                        reader=reader,
                        deadline=deadline,
                        secondary_failures=secondary_failures,
                    )
                    if not reader_finished:
                        timed_out = True
                        cleanup_required = True
                    else:
                        reader_finalized = True
                        _wait_for_process(process, deadline=deadline)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    cleanup_required = True
                except (OSError, subprocess.SubprocessError) as error:
                    secondary_failures.append(
                        _secondary_command_failure("process-wait", error)
                    )
                    cleanup_required = True

            active_deadline = deadline
            if cleanup_required:
                if active_deadline is None:
                    active_deadline = (
                        time.monotonic() + _COMMAND_CLEANUP_TIMEOUT_SECONDS
                    )
                try:
                    _terminate_process_group(
                        process,
                        deadline=active_deadline,
                        stream_owned_by_reader=True,
                    )
                except subprocess.TimeoutExpired as error:
                    timed_out = True
                    secondary_failures.append(
                        _secondary_command_failure("process-group-cleanup", error)
                    )
                except (OSError, subprocess.SubprocessError) as error:
                    secondary_failures.append(
                        _secondary_command_failure("process-group-cleanup", error)
                    )

                if not reader_finalized:
                    if not _finish_output_reader(
                        process=process,
                        reader=reader,
                        deadline=active_deadline,
                        secondary_failures=secondary_failures,
                    ):
                        timed_out = True

            while True:
                try:
                    line = output_queue.get_nowait()
                except queue.Empty:
                    break
                if line is not None:
                    chunks.append(line)
            output = "".join(chunks)
            if timed_out:
                exit_code = 124
            elif handler_error is not None:
                output += f"\ncontrolled output handler failed: {handler_error}\n"
                exit_code = 2
            else:
                exit_code = int(process.returncode or 0)
    except subprocess.TimeoutExpired as error:
        partial_output = error.output if isinstance(error.output, str) else ""
        if process is not None:
            try:
                cleanup_output = _terminate_process_group(process, deadline=deadline)
                output = cleanup_output or partial_output
            except (OSError, subprocess.SubprocessError) as cleanup_error:
                output = partial_output
                secondary_failures.append(
                    _secondary_command_failure("process-group-cleanup", cleanup_error)
                )
        else:
            output = partial_output
        exit_code = 124
        timed_out = True
    except KeyboardInterrupt:
        if process is not None:
            _cleanup_interrupted_process(process)
        raise
    redacted_output = _redact_text(output, secret_values)
    log_reference: str | None = None
    if log_path is not None:
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(redacted_output, encoding="utf-8")
            log_reference = repo_relative(log_path)
        except (OSError, ValueError) as error:
            secondary_failures.append(_secondary_command_failure("log-write", error))
            if exit_code == 0:
                exit_code = 2
    result: dict[str, Any] = {
        "command": _redact_command(command),
        "cwd": str(cwd),
        "exitCode": exit_code,
        "timedOut": timed_out,
        "durationMs": int((time.monotonic() - started) * 1000),
        "outputSummary": summarize_output(redacted_output),
    }
    if log_reference is not None:
        result["logPath"] = log_reference
    if secondary_failures:
        result["secondaryFailures"] = secondary_failures
    return result


def _terminate_process_group(
    process: subprocess.Popen[str],
    *,
    deadline: float | None = None,
    stream_owned_by_reader: bool = False,
) -> str:
    active_deadline = (
        deadline
        if deadline is not None
        else time.monotonic() + _COMMAND_CLEANUP_TIMEOUT_SECONDS
    )

    def wait_for_exit() -> str:
        if stream_owned_by_reader:
            _wait_for_process(process, deadline=active_deadline)
            return ""
        output, _ = process.communicate(
            timeout=_remaining_command_seconds(active_deadline)
        )
        return output or ""

    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        return wait_for_exit()
    except subprocess.TimeoutExpired as timeout_error:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        wait_for_exit()
        raise timeout_error
