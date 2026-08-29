"""Online App dependency fetches recover only typed transient network failures."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from quwoquan_ops.cli.commands import app_dependency_sync_builder as builder
from quwoquan_ops.cli.lib.package_reuse import dependency_network_command as network

# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001.t9


def _run(
    tmp_path: Path,
    *,
    retry: bool,
) -> subprocess.CompletedProcess[str]:
    return builder._run_checked(
        command=["pod", "install", "--deployment"],
        cwd=tmp_path,
        environment={"CP_HOME_DIR": str(tmp_path / "home")},
        log_path=tmp_path / "pod.log",
        phase="production CocoaPods network sync",
        retry_transient_network=retry,
    )


@pytest.mark.parametrize(
    "failure_output",
    [
        "curl: (35) LibreSSL SSL_connect: SSL_ERROR_SYSCALL",
        "javax.net.ssl.SSLHandshakeException: Remote host terminated the handshake",
        "Received status code 503 from server",
        "curl: (22) The requested URL returned error: 503",
    ],
)
def test_online_sync_retries_transient_failure_in_the_same_private_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_output: str,
) -> None:
    calls: list[tuple[Path, dict[str, str]]] = []
    sleeps: list[float] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        calls.append((Path(kwargs["cwd"]), environment))
        marker = Path(environment["CP_HOME_DIR"]) / "partial"
        marker.parent.mkdir(exist_ok=True)
        if len(calls) == 1:
            marker.write_text("retained", encoding="utf-8")
            return subprocess.CompletedProcess(command, 1, stdout=failure_output)
        assert marker.read_text(encoding="utf-8") == "retained"
        return subprocess.CompletedProcess(command, 0, stdout="recovered")

    monkeypatch.setattr(builder, "run_managed_subprocess", fake_run)
    monkeypatch.setattr(builder.time, "sleep", sleeps.append)
    completed = _run(tmp_path, retry=True)

    assert completed.stdout == "recovered"
    assert len(calls) == 2
    assert calls[0] == calls[1]
    assert sleeps == [1.0]
    log = (tmp_path / "pod.log").read_text(encoding="utf-8")
    assert "result=transient_failure" in log
    assert "result=success" in log
    assert failure_output not in log
    assert "recovered" not in log


@pytest.mark.parametrize(
    "failure_output",
    [
        "Received status code 404 from server",
        "curl: (22) The requested URL returned error: 404",
        "SSLHandshakeException: PKIX path building failed",
        "SSL_connect: certificate verify failed",
        "Unable to find a specification for `MissingPod`",
    ],
)
def test_online_sync_does_not_retry_deterministic_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_output: str,
) -> None:
    calls = 0

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(command, 1, stdout=failure_output)

    monkeypatch.setattr(builder, "run_managed_subprocess", fake_run)
    with pytest.raises(ValueError, match="APP.DEPENDENCY.sync_failed") as caught:
        _run(tmp_path, retry=True)
    assert failure_output in str(caught.value)
    assert calls == 1


def test_online_sync_transient_then_deterministic_returns_current_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outputs = [
        "SSL_ERROR_SYSCALL transient-first",
        "Received status code 404 deterministic-second",
    ]
    sleeps: list[float] = []

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, stdout=outputs.pop(0))

    monkeypatch.setattr(builder, "run_managed_subprocess", fake_run)
    monkeypatch.setattr(builder.time, "sleep", sleeps.append)
    with pytest.raises(ValueError, match="APP.DEPENDENCY.sync_failed") as caught:
        _run(tmp_path, retry=True)

    assert "deterministic-second" in str(caught.value)
    assert "transient-first" not in str(caught.value)
    assert outputs == []
    assert sleeps == [1.0]
    log = (tmp_path / "pod.log").read_text(encoding="utf-8")
    assert "result=transient_failure" in log
    assert "deterministic-second" in log
    assert "transient-first" not in log


def test_online_sync_exhaustion_preserves_first_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outputs = [
        "SSL_ERROR_SYSCALL first",
        "Received status code 503 second",
        "SSLHandshakeException: EOF third",
    ]
    sleeps: list[float] = []

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, stdout=outputs.pop(0))

    monkeypatch.setattr(builder, "run_managed_subprocess", fake_run)
    monkeypatch.setattr(builder.time, "sleep", sleeps.append)
    with pytest.raises(ValueError) as caught:
        _run(tmp_path, retry=True)
    assert "first" in str(caught.value)
    assert "second" not in str(caught.value)
    assert outputs == []
    assert sleeps == [1.0, 2.0]


def test_online_sync_timeout_has_process_and_total_wall_clock_bounds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [0.0]
    timeouts: list[float] = []
    sleeps: list[float] = []
    monkeypatch.setattr(builder, "_SYNC_TIMEOUT_SECONDS", 4)
    monkeypatch.setattr(builder, "_SYNC_NETWORK_DEADLINE_SECONDS", 10)
    monkeypatch.setattr(builder.time, "monotonic", lambda: clock[0])
    def fake_sleep(delay: float) -> None:
        sleeps.append(delay)
        clock[0] += delay

    monkeypatch.setattr(builder.time, "sleep", fake_sleep)

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        timeouts.append(float(kwargs["timeout"]))
        clock[0] += float(kwargs["timeout"])
        raise subprocess.TimeoutExpired(command, kwargs["timeout"], output="timed out")

    monkeypatch.setattr(builder, "run_managed_subprocess", fake_run)
    with pytest.raises(ValueError, match="APP.DEPENDENCY.sync_timeout"):
        _run(tmp_path, retry=True)
    assert timeouts == [4.0, 4.0]
    assert sleeps == [1.0, 1.0]
    assert clock[0] == 10.0


def test_non_network_phase_is_single_attempt_even_for_tls_shaped_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(command, 1, stdout="SSL_ERROR_SYSCALL")

    monkeypatch.setattr(builder, "run_managed_subprocess", fake_run)
    with pytest.raises(ValueError, match="APP.DEPENDENCY.sync_failed"):
        _run(tmp_path, retry=False)
    assert calls == 1


def test_process_group_cleanup_failure_is_never_retried(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        raise network.DependencyProcessGroupCleanupError(
            "APP.DEPENDENCY.process_group_cleanup_failed"
        )

    monkeypatch.setattr(builder, "run_managed_subprocess", fake_run)
    with pytest.raises(
        network.DependencyProcessGroupCleanupError,
        match="APP.DEPENDENCY.process_group_cleanup_failed",
    ):
        _run(tmp_path, retry=True)
    assert calls == 1
