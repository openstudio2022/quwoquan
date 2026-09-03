"""Dependency network subprocess deadlines own and reap their process trees."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from quwoquan_ops.cli.lib.package_reuse import dependency_network_command as network

# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001.t9


def test_managed_subprocess_uses_only_the_explicit_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QWQ_MUST_NOT_LEAK", "secret")
    completed = network.run_managed_subprocess(
        [
            sys.executable,
            "-c",
            "import os; print(os.getenv('QWQ_MUST_NOT_LEAK'), os.getenv('EXPECTED'))",
        ],
        cwd=tmp_path,
        env={"EXPECTED": "present", "PYTHONDONTWRITEBYTECODE": "1"},
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=2,
    )
    assert completed.stdout.strip() == "None present"


def test_managed_subprocess_can_preserve_separate_stderr(tmp_path: Path) -> None:
    completed = network.run_managed_subprocess(
        [
            sys.executable,
            "-c",
            "import sys; print('payload'); print('warning', file=sys.stderr)",
        ],
        cwd=tmp_path,
        env={"PYTHONDONTWRITEBYTECODE": "1"},
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=2,
    )
    assert completed.stdout == "payload\n"
    assert completed.stderr == "warning\n"


def test_nonconvergent_process_group_returns_typed_cleanup_blocker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeProcess:
        pid = 424242

        @staticmethod
        def wait(*, timeout: float) -> int:
            assert timeout > 0
            return -15

        @staticmethod
        def poll() -> int:
            return -15

    clock = [0.0]
    signals: list[signal.Signals] = []
    monkeypatch.setattr(network, "_PROCESS_GROUP_GRACE_SECONDS", 0.1)
    monkeypatch.setattr(network, "_PROCESS_GROUP_KILL_GRACE_SECONDS", 0.1)
    monkeypatch.setattr(network, "_group_exists", lambda _process: True)
    monkeypatch.setattr(
        network, "_signal_group", lambda _process, sent: signals.append(sent)
    )
    monkeypatch.setattr(network.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        network.time, "sleep", lambda delay: clock.__setitem__(0, clock[0] + delay)
    )

    with pytest.raises(
        network.DependencyProcessGroupCleanupError,
        match="APP.DEPENDENCY.process_group_cleanup_failed",
    ):
        network._stop_process_group(FakeProcess())  # type: ignore[arg-type]
    assert signals == [signal.SIGTERM, signal.SIGKILL]


@pytest.mark.skipif(os.name != "posix", reason="canonical dependency sync is POSIX-only")
def test_timeout_reaps_the_entire_owned_process_group(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identities = tmp_path / "process-identities"
    program = (
        "import os, pathlib, signal, subprocess, sys, time; "
        "child=subprocess.Popen([sys.executable, '-c', "
        "'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)']); "
        "pathlib.Path(sys.argv[1]).write_text(f'{os.getpid()} {child.pid}', encoding='utf-8'); "
        "time.sleep(60)"
    )
    monkeypatch.setattr(network, "_PROCESS_GROUP_GRACE_SECONDS", 0.1)
    started_at = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        network.run_managed_subprocess(
            [sys.executable, "-c", program, str(identities)],
            cwd=tmp_path,
            env={"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"},
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=0.5,
        )
    elapsed = time.monotonic() - started_at
    parent_pid, _child_pid = (int(item) for item in identities.read_text().split())
    assert parent_pid > 1 and parent_pid != os.getpgrp()
    with pytest.raises(ProcessLookupError):
        os.killpg(parent_pid, 0)
    assert elapsed <= 0.8
