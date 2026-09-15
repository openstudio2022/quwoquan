"""Bounded, exact-environment subprocesses for dependency network resolution."""

from __future__ import annotations

import codecs
import os
import re
import select
import signal
import stat
import subprocess
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

_PROCESS_GROUP_GRACE_SECONDS = 2.0
_PROCESS_GROUP_KILL_GRACE_SECONDS = 2.0
_MANAGED_PARENT_CONTROL_FD_ENV = "QWQ_INTERNAL_MANAGED_PARENT_CONTROL_FD"
_MANAGED_DEADLINE_ENV = "QWQ_INTERNAL_MANAGED_DEADLINE_MONOTONIC"
_DETERMINISTIC_TLS_MARKERS = (
    "certificate verify failed",
    "hostname mismatch",
    "hostname verification failed",
    "peer not authenticated",
    "pkix path building failed",
    "self-signed certificate",
    "unable to find valid certification path",
    "unable to get local issuer certificate",
)
_TRANSIENT_MARKER_CAUSES = (
    ("ssl_error_syscall", "tls_transport_close"),
    ("ssl peer shut down incorrectly", "tls_remote_close"),
    ("remote host terminated the handshake", "tls_remote_close"),
    ("unexpected end of file from server", "remote_eof"),
    ("connection reset", "connection_reset"),
    ("recv failure", "connection_reset"),
    ("sockettimeoutexception", "network_timeout"),
    ("connect timed out", "network_timeout"),
    ("connection timed out", "network_timeout"),
    ("operation timed out", "network_timeout"),
    ("read timed out", "network_timeout"),
)
_TRANSIENT_HTTP_STATUS = re.compile(
    r"(?:status(?:\s+code)?|http\s+response\s+code|"
    r"requested\s+url\s+returned\s+error:)\s*[:=]?\s*"
    r"(?P<status>408|429|5\d\d)\b",
    flags=re.IGNORECASE,
)
_TLS_EOF = re.compile(r"(?:tls|ssl).*\beof\b|\beof\b.*(?:tls|ssl)", re.IGNORECASE)
_CURL_PARTIAL_FILE = re.compile(
    r"\bcurl:\s*\(18\)\s+transferred a partial file\b", re.IGNORECASE
)
_HTTP2_STREAM_CLOSE = re.compile(
    r"\bhttp/2 stream\b[^\r\n]*(?:was not closed cleanly|\bcancel\b)",
    re.IGNORECASE,
)
_GIT_RPC_CURL_TRANSPORT = re.compile(
    r"\brpc failed\b[^\r\n]*\bcurl\s+\d+\b", re.IGNORECASE
)
_GIT_EARLY_EOF = re.compile(r"\bfatal:\s*early eof\b", re.IGNORECASE)
_GIT_FETCH_CONTEXT = re.compile(
    r"\b(?:git\s+fetch|fetch-pack|index-pack)\b", re.IGNORECASE
)


class DependencyProcessGroupCleanupError(RuntimeError):
    """The exact dependency subprocess group did not converge after SIGKILL."""


class ManagedSubprocessCancelled(BaseException):
    """The owning process vanished or was terminated; children are already reaped."""

    def __init__(self, *, signum: int = signal.SIGTERM) -> None:
        super().__init__(f"managed subprocess cancelled by signal {signum}")
        self.signum = signum


def process_group_cleanup_grace() -> dict[str, float]:
    return {
        "termSeconds": _PROCESS_GROUP_GRACE_SECONDS,
        "killSeconds": _PROCESS_GROUP_KILL_GRACE_SECONDS,
    }


def _managed_parent_control_fd() -> int | None:
    raw = str(os.environ.get(_MANAGED_PARENT_CONTROL_FD_ENV) or "").strip()
    try:
        descriptor = int(raw)
    except ValueError:
        return None
    if descriptor < 3:
        return None
    try:
        metadata = os.fstat(descriptor)
    except OSError:
        return None
    return descriptor if stat.S_ISFIFO(metadata.st_mode) else None


def has_managed_parent_capability() -> bool:
    """Accept only an inherited live pipe, never an ambient environment claim."""

    descriptor = _managed_parent_control_fd()
    if descriptor is None:
        return False
    readable, _, _ = select.select([descriptor], [], [], 0)
    if not readable:
        return True
    try:
        return os.read(descriptor, 1) != b""
    except OSError:
        return False


def _inherited_deadline() -> float | None:
    raw = str(os.environ.get(_MANAGED_DEADLINE_ENV) or "").strip()
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def remaining_managed_deadline_seconds(default_seconds: float) -> float:
    deadline = time.monotonic() + default_seconds
    inherited = _inherited_deadline()
    if inherited is not None:
        deadline = min(deadline, inherited)
    return max(0.001, deadline - time.monotonic())


def transient_network_cause(output: object) -> str | None:
    """Return a closed transient cause; certificate/trust failures stay deterministic."""

    text = str(output or "")
    lowered = text.lower()
    if any(marker in lowered for marker in _DETERMINISTIC_TLS_MARKERS):
        return None
    if (
        "verification of gradle distribution failed" in lowered
        and "actual checksum: 'e3b0c44298fc1c149afbf4c8996fb924"
        "27ae41e4649b934ca495991b7852b855'" in lowered
    ):
        return "empty_download"
    status = _TRANSIENT_HTTP_STATUS.search(text)
    if status is not None:
        return f"http_{status.group('status')}"
    for marker, cause in _TRANSIENT_MARKER_CAUSES:
        if marker in lowered:
            return cause
    if _CURL_PARTIAL_FILE.search(text) is not None:
        return "curl_partial_file"
    if _HTTP2_STREAM_CLOSE.search(text) is not None:
        return "http2_stream_close"
    if _GIT_RPC_CURL_TRANSPORT.search(text) is not None:
        return "git_rpc_curl_transport"
    if "unexpected disconnect while reading sideband packet" in lowered:
        return "git_sideband_disconnect"
    if "fetch-pack: invalid index-pack output" in lowered:
        return "git_invalid_index_pack"
    if (
        _GIT_EARLY_EOF.search(text) is not None
        and _GIT_FETCH_CONTEXT.search(text) is not None
    ):
        return "git_early_eof"
    if _TLS_EOF.search(text) is not None:
        return "tls_eof"
    return None


def retry_event(*, attempt: int, result: str, cause: str | None = None, backoff: float = 0) -> str:
    """Render non-sensitive retry metadata for persisted process logs."""

    fields = [f"attempt={attempt}", f"result={result}"]
    if cause:
        fields.append(f"cause={cause}")
    if backoff:
        fields.append(f"backoffSeconds={backoff:g}")
    return "[dependency-network-attempt] " + " ".join(fields)


def _signal_group(process: subprocess.Popen[bytes], sig: signal.Signals) -> None:
    try:
        os.killpg(process.pid, sig)
    except ProcessLookupError:
        return
    except PermissionError as error:
        raise DependencyProcessGroupCleanupError(
            "APP.DEPENDENCY.process_group_cleanup_failed: signal permission denied"
        ) from error


def _group_exists(process: subprocess.Popen[bytes]) -> bool:
    try:
        os.killpg(process.pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # EPERM still proves that the PGID exists; keep waiting fail-closed
        # until ProcessLookupError or the bounded cleanup deadline.
        return True
    return True


def _wait_group_absent(process: subprocess.Popen[bytes], *, deadline: float) -> bool:
    while _group_exists(process):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(0.02, remaining))
    return True


def _stop_process_group(process: subprocess.Popen[bytes]) -> None:
    term_deadline = time.monotonic() + _PROCESS_GROUP_GRACE_SECONDS
    _signal_group(process, signal.SIGTERM)
    try:
        process.wait(timeout=_PROCESS_GROUP_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        pass
    if not _wait_group_absent(process, deadline=term_deadline):
        _signal_group(process, signal.SIGKILL)
        kill_deadline = time.monotonic() + _PROCESS_GROUP_KILL_GRACE_SECONDS
        if process.poll() is None:
            try:
                process.wait(timeout=_PROCESS_GROUP_KILL_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                process.kill()
        if not _wait_group_absent(process, deadline=kill_deadline):
            raise DependencyProcessGroupCleanupError(
                "APP.DEPENDENCY.process_group_cleanup_failed: group remained after SIGKILL"
            )
    if process.poll() is None:
        try:
            process.wait(timeout=_PROCESS_GROUP_KILL_GRACE_SECONDS)
        except subprocess.TimeoutExpired as error:
            raise DependencyProcessGroupCleanupError(
                "APP.DEPENDENCY.process_group_cleanup_failed: parent remained"
            ) from error


def _read_output(stream: object) -> str:
    stream.seek(0)
    return stream.read().decode("utf-8", errors="replace")


def _read_output_since(stream: object, offset: int) -> tuple[bytes, int]:
    size = os.fstat(stream.fileno()).st_size
    encoded = os.pread(stream.fileno(), max(0, size - offset), offset)
    return encoded, offset + len(encoded)


def run_managed_subprocess(
    command: Sequence[str],
    *,
    cwd: str | Path,
    env: Mapping[str, str],
    check: bool,
    text: bool,
    stdout: int,
    stderr: int,
    timeout: float,
    on_stderr: Callable[[str], None] | None = None,
    on_stdout: Callable[[str], None] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run one owned session and propagate cancellation through nested sessions."""

    if (
        not text
        or stdout != subprocess.PIPE
        or stderr not in {subprocess.PIPE, subprocess.STDOUT}
    ):
        raise ValueError("managed dependency subprocess requires captured text output")
    inherited_control = _managed_parent_control_fd()
    inherited_deadline = _inherited_deadline()
    deadline = time.monotonic() + timeout
    if inherited_deadline is not None:
        deadline = min(deadline, inherited_deadline)
    child_control_read, child_control_write = os.pipe()
    child_env = dict(env)
    child_env[_MANAGED_PARENT_CONTROL_FD_ENV] = str(child_control_read)
    child_env[_MANAGED_DEADLINE_ENV] = repr(deadline)
    previous_sigterm = None
    installed_sigterm = False

    def cancel_on_sigterm(signum: int, _frame: object) -> None:
        raise ManagedSubprocessCancelled(signum=signum)

    if signal.getsignal(signal.SIGTERM) == signal.SIG_DFL:
        previous_sigterm = signal.signal(signal.SIGTERM, cancel_on_sigterm)
        installed_sigterm = True
    try:
        with (
            tempfile.TemporaryFile() as stdout_file,
            tempfile.TemporaryFile() as stderr_file,
        ):
            try:
                process = subprocess.Popen(
                    list(command),
                    cwd=str(cwd),
                    env=child_env,
                    stdout=stdout_file,
                    stderr=(stderr_file if stderr == subprocess.PIPE else subprocess.STDOUT),
                    start_new_session=True,
                    pass_fds=(child_control_read,),
                )
            finally:
                os.close(child_control_read)
            stdout_offset = 0
            stderr_offset = 0
            stdout_decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
            stderr_decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

            def emit_stdout(*, final: bool) -> None:
                nonlocal stdout_offset
                if on_stdout is None:
                    return
                encoded, stdout_offset = _read_output_since(stdout_file, stdout_offset)
                chunk = stdout_decoder.decode(encoded, final=final)
                if chunk:
                    on_stdout(chunk)

            def emit_stderr(*, final: bool) -> None:
                nonlocal stderr_offset
                if on_stderr is None or stderr != subprocess.PIPE:
                    return
                encoded, stderr_offset = _read_output_since(stderr_file, stderr_offset)
                chunk = stderr_decoder.decode(encoded, final=final)
                if chunk:
                    on_stderr(chunk)

            try:
                while True:
                    if inherited_control is not None:
                        readable, _, _ = select.select([inherited_control], [], [], 0)
                        if readable and os.read(inherited_control, 1) == b"":
                            raise ManagedSubprocessCancelled()
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        _stop_process_group(process)
                        emit_stdout(final=True)
                        emit_stderr(final=True)
                        raise subprocess.TimeoutExpired(
                            command,
                            timeout,
                            output=_read_output(stdout_file),
                            stderr=(
                                _read_output(stderr_file)
                                if stderr == subprocess.PIPE
                                else None
                            ),
                        )
                    try:
                        returncode = process.wait(timeout=min(0.1, remaining))
                    except subprocess.TimeoutExpired:
                        emit_stdout(final=False)
                        emit_stderr(final=False)
                        continue
                    break
                emit_stdout(final=True)
                emit_stderr(final=True)
                captured_stdout = _read_output(stdout_file)
                captured_stderr = (
                    _read_output(stderr_file) if stderr == subprocess.PIPE else None
                )
            except BaseException:
                _stop_process_group(process)
                raise
        completed = subprocess.CompletedProcess(
            command,
            returncode,
            stdout=captured_stdout,
            stderr=captured_stderr,
        )
        if check and returncode != 0:
            raise subprocess.CalledProcessError(
                returncode,
                command,
                output=captured_stdout,
                stderr=captured_stderr,
            )
        return completed
    finally:
        os.close(child_control_write)
        if installed_sigterm:
            signal.signal(signal.SIGTERM, previous_sigterm)
