"""管理 ``flutter attach --machine`` 会话及其进程生命周期。"""

from __future__ import annotations

import itertools
import json
import os
import queue
import select
import signal
import subprocess
import sys
import termios
import threading
import time
import tty
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Protocol

from canonical_app_instance.activation import CanonicalExecutorError

ATTACH_SIGNAL_GRACE_SECONDS = 5.0


class AttachPlatformDriver(Protocol):
    device_id: str
    application_id: str
    entrypoint: str

    def child_environment(
        self, environment: Mapping[str, str]
    ) -> dict[str, str]: ...

    def resolve_attach_debug_url(self, timeout_seconds: float) -> str | None: ...

    def validate_vm_service_info_file(self) -> Path | None: ...

    def startup_evidence_lines(self) -> tuple[str, ...]: ...


class AttachTerminationSignal(Exception):
    def __init__(self, signum: int) -> None:
        super().__init__(signum)
        self.signum = signum


def terminate_attach_process_group(
    process: subprocess.Popen[str],
    *,
    initial_signal: int,
) -> None:
    if initial_signal == signal.SIGINT:
        signals = (signal.SIGINT, signal.SIGTERM, signal.SIGKILL)
    elif initial_signal == signal.SIGHUP:
        signals = (signal.SIGHUP, signal.SIGTERM, signal.SIGKILL)
    else:
        signals = (signal.SIGTERM, signal.SIGKILL)
    for signum in signals:
        if process.poll() is not None:
            process.wait()
            return
        try:
            os.killpg(process.pid, signum)
        except ProcessLookupError:
            process.wait()
            return
        if signum == signal.SIGKILL:
            process.wait()
            return
        try:
            process.wait(timeout=ATTACH_SIGNAL_GRACE_SECONDS)
            return
        except subprocess.TimeoutExpired:
            continue


def attach_command_platform_driver(
    driver: AttachPlatformDriver,
    attach_arguments: tuple[str, ...],
    *,
    timeout_seconds: float,
    on_attached: Callable[[], None],
    app_dir: Path,
    flutter_executable: str,
    sanitize_attach_arguments: Callable[[Sequence[str]], list[str]],
    is_flutter_app_started_event: Callable[[str], bool],
    flutter_daemon_app_id: Callable[[str], str],
    redact_vm_service_tokens: Callable[[str], str],
    terminate_process_group: Callable[..., None],
) -> int:
    command = [
        flutter_executable,
        "attach",
        "--machine",
        "-d",
        driver.device_id,
        "--app-id",
        driver.application_id,
        "--target",
        driver.entrypoint,
        "--host-vmservice-port=0",
        "--dds-port=0",
    ]
    debug_url = driver.resolve_attach_debug_url(timeout_seconds)
    if debug_url is not None:
        command.append(f"--debug-url={debug_url}")
    vm_service_info_file = driver.validate_vm_service_info_file()
    if vm_service_info_file is not None:
        command.append(f"--write-service-info={vm_service_info_file}")
    command.extend(sanitize_attach_arguments(attach_arguments))
    # 前台 TTY 会话把 r/R/q 键桥接为 daemon JSON-RPC（app.restart/app.stop）；
    # flutter attach --machine 只讲 daemon 协议，没有键盘命令面。
    interactive_tty = os.isatty(0)
    try:
        process = subprocess.Popen(
            command,
            cwd=app_dir,
            env=driver.child_environment(os.environ),
            stdin=subprocess.PIPE if interactive_tty else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
    except OSError as error:
        raise CanonicalExecutorError(
            f"unable to start flutter attach: {error}"
        ) from error
    assert process.stdout is not None
    output: queue.Queue[str | None] = queue.Queue()

    def read_output() -> None:
        try:
            for line in process.stdout:
                output.put(line)
        finally:
            output.put(None)

    daemon_app_id_holder: dict[str, str] = {}
    daemon_request_counter = itertools.count(10_000)
    daemon_stdin_lock = threading.Lock()

    def send_daemon_line(line: str) -> None:
        if process.stdin is None:
            return
        with daemon_stdin_lock:
            try:
                process.stdin.write(line if line.endswith("\n") else line + "\n")
                process.stdin.flush()
            except (BrokenPipeError, OSError, ValueError):
                pass

    def send_daemon_request(method: str, params: dict[str, object]) -> None:
        app_id = daemon_app_id_holder.get("appId", "")
        if not app_id:
            print(
                "[run-instance] r/R/q keys become active after attach completes.",
                file=sys.stderr,
                flush=True,
            )
            return
        payload = dict(params)
        payload["appId"] = app_id
        send_daemon_line(
            json.dumps(
                [
                    {
                        "id": next(daemon_request_counter),
                        "method": method,
                        "params": payload,
                    }
                ]
            )
        )

    def bridge_terminal_keys() -> None:
        # 除单键 r/R/q 外，还把整行 JSON（daemon 请求）原样透传给
        # flutter attach，保持既有 PTY 驱动的 smoke/自动化协议不变。
        pending = bytearray()
        while process.poll() is None:
            try:
                ready, _, _ = select.select([0], [], [], 0.2)
            except (OSError, ValueError):
                return
            if not ready:
                continue
            try:
                chunk = os.read(0, 1024)
            except OSError:
                return
            if not chunk:
                return
            for byte in chunk:
                char = bytes((byte,))
                if pending:
                    pending.append(byte)
                    if char == b"\n":
                        send_daemon_line(pending.decode("utf-8", "replace"))
                        pending.clear()
                elif char in (b"[", b"{"):
                    pending.append(byte)
                elif char == b"r":
                    send_daemon_request("app.restart", {"fullRestart": False})
                elif char == b"R":
                    send_daemon_request("app.restart", {"fullRestart": True})
                elif char in (b"q", b"Q"):
                    send_daemon_request("app.stop", {})

    previous_signal_handlers: dict[int, signal.Handlers] = {}
    stdin_termios: list[object] | None = None

    def handle_termination(signum: int, _frame: object) -> None:
        raise AttachTerminationSignal(signum)

    try:
        for signum in (signal.SIGTERM, signal.SIGHUP):
            previous_signal_handlers[signum] = signal.signal(
                signum, handle_termination
            )
        threading.Thread(target=read_output, daemon=True).start()
        if interactive_tty:
            try:
                stdin_termios = termios.tcgetattr(0)
                # cbreak 保留 ISIG：Ctrl-C 仍走既有 SIGINT 收尾路径。
                tty.setcbreak(0)
            except (termios.error, OSError):
                stdin_termios = None
            threading.Thread(target=bridge_terminal_keys, daemon=True).start()
        deadline = time.monotonic() + timeout_seconds
        attached = False
        emitted_startup_evidence: set[str] = set()

        def emit_startup_evidence() -> None:
            for evidence_line in driver.startup_evidence_lines():
                if evidence_line not in emitted_startup_evidence:
                    emitted_startup_evidence.add(evidence_line)
                    print(evidence_line, flush=True)

        while True:
            if not attached and time.monotonic() >= deadline:
                raise CanonicalExecutorError(
                    "flutter attach did not establish a VM service session "
                    f"within {timeout_seconds:g}s"
                )
            try:
                line = output.get(timeout=0.1)
            except queue.Empty:
                if attached:
                    emit_startup_evidence()
                continue
            if line is None:
                break
            print(redact_vm_service_tokens(line), end="", flush=True)
            if not daemon_app_id_holder.get("appId"):
                candidate_app_id = flutter_daemon_app_id(line)
                if candidate_app_id:
                    daemon_app_id_holder["appId"] = candidate_app_id
            if not attached and is_flutter_app_started_event(line):
                driver.validate_vm_service_info_file()
                emit_startup_evidence()
                attached = True
                if interactive_tty:
                    print(
                        "[run-instance] keys: r=hot reload, R=hot restart, q=quit",
                        file=sys.stderr,
                        flush=True,
                    )
                on_attached()
        exit_code = process.wait()
    except KeyboardInterrupt:
        terminate_process_group(process, initial_signal=signal.SIGINT)
        return 130
    except AttachTerminationSignal as termination:
        terminate_process_group(process, initial_signal=termination.signum)
        return 128 + termination.signum
    except BaseException:
        if process.poll() is None:
            terminate_process_group(process, initial_signal=signal.SIGTERM)
        else:
            process.wait()
        raise
    finally:
        for signum, previous_handler in previous_signal_handlers.items():
            signal.signal(signum, previous_handler)
        if stdin_termios is not None:
            try:
                termios.tcsetattr(0, termios.TCSADRAIN, stdin_termios)
            except (termios.error, OSError):
                pass
    if not attached:
        driver.validate_vm_service_info_file()
        raise CanonicalExecutorError(
            f"flutter attach exited before VM service attachment (code {exit_code})"
        )
    driver.validate_vm_service_info_file()
    return exit_code
