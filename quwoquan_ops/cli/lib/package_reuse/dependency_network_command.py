"""Bounded, exact-environment subprocesses for dependency network resolution."""

from __future__ import annotations

import os
import re
import signal
import subprocess
import tempfile
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

_PROCESS_GROUP_GRACE_SECONDS = 2.0
_PROCESS_GROUP_KILL_GRACE_SECONDS = 2.0
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


class DependencyProcessGroupCleanupError(RuntimeError):
    """The exact dependency subprocess group did not converge after SIGKILL."""


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
) -> subprocess.CompletedProcess[str]:
    """Run one command in its own process group and reap the entire tree on timeout."""

    if not text or stdout != subprocess.PIPE or stderr != subprocess.STDOUT:
        raise ValueError("managed dependency subprocess requires combined text capture")
    with tempfile.TemporaryFile() as output_file:
        process = subprocess.Popen(
            list(command),
            cwd=str(cwd),
            env=dict(env),
            stdout=output_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            returncode = process.wait(timeout=timeout)
        except KeyboardInterrupt:
            _stop_process_group(process)
            raise
        except subprocess.TimeoutExpired as error:
            _stop_process_group(process)
            output_file.seek(0)
            captured = output_file.read().decode("utf-8", errors="replace")
            raise subprocess.TimeoutExpired(command, timeout, output=captured) from error
        output_file.seek(0)
        captured = output_file.read().decode("utf-8", errors="replace")
    completed = subprocess.CompletedProcess(command, returncode, stdout=captured)
    if check and returncode != 0:
        raise subprocess.CalledProcessError(returncode, command, output=captured)
    return completed
