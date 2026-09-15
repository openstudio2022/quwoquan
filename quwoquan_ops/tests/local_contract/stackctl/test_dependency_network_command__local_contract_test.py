"""Dependency network subprocess deadlines own and reap their process trees."""

from __future__ import annotations

import fcntl
import os
import signal
import subprocess
import stat
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



@pytest.mark.skipif(os.name != "posix", reason="canonical dependency sync is POSIX-only")
def test_outer_timeout_reaps_nested_child_that_created_its_own_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identities = tmp_path / "nested-session-identities"
    staging = tmp_path / "package-staging"
    lock = tmp_path / "package.lock"
    nested_program = (
        "import fcntl,os,pathlib,sys,time\n"
        "lock=open(sys.argv[2], 'w'); fcntl.flock(lock.fileno(), fcntl.LOCK_EX)\n"
        "staging=pathlib.Path(sys.argv[3]); staging.write_text('started\\n')\n"
        "pathlib.Path(sys.argv[1]).write_text(f'{os.getpid()} {os.getpgid(0)}', encoding='ascii')\n"
        "while True:\n"
        "    with staging.open('a') as output: output.write('write\\n')\n"
        "    time.sleep(.02)\n"
    )
    manager_program = (
        "import os,subprocess,sys\n"
        "from quwoquan_ops.cli.lib.package_reuse.dependency_network_command import run_managed_subprocess\n"
        "run_managed_subprocess([sys.executable, '-c', *sys.argv[1:5]], "
        "cwd=sys.argv[5], env=dict(os.environ), check=True, text=True, "
        "stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)\n"
    )
    monkeypatch.setattr(network, "_PROCESS_GROUP_GRACE_SECONDS", 0.4)
    monkeypatch.setattr(network, "_PROCESS_GROUP_KILL_GRACE_SECONDS", 0.4)
    with pytest.raises(subprocess.TimeoutExpired):
        network.run_managed_subprocess(
            [
                sys.executable,
                "-c",
                manager_program,
                nested_program,
                str(identities),
                str(lock),
                str(staging),
                str(tmp_path),
            ],
            cwd=tmp_path,
            env={
                **os.environ,
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONPATH": str(Path(__file__).resolve().parents[4]),
            },
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=1.5,
        )
    nested_pid, nested_pgid = (int(item) for item in identities.read_text().split())
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            os.kill(nested_pid, 0)
            os.killpg(nested_pgid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.02)
    with pytest.raises(ProcessLookupError):
        os.kill(nested_pid, 0)
    with pytest.raises(ProcessLookupError):
        os.killpg(nested_pgid, 0)
    stable_size = staging.stat().st_size
    time.sleep(0.1)
    assert staging.stat().st_size == stable_size
    with lock.open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def test_ambient_capability_environment_cannot_bypass_management(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(network._MANAGED_PARENT_CONTROL_FD_ENV, "999999")
    assert not network.has_managed_parent_capability()

def test_managed_subprocess_streams_stderr_before_exit_and_preserves_capture(
    tmp_path: Path,
) -> None:
    acknowledgement = tmp_path / "stderr-observed"
    chunks: list[str] = []

    def observe(chunk: str) -> None:
        chunks.append(chunk)
        acknowledgement.write_text("observed\n", encoding="ascii")

    completed = network.run_managed_subprocess(
        [
            sys.executable,
            "-c",
            (
                "import pathlib,sys,time\n"
                "ack=pathlib.Path(sys.argv[1])\n"
                "print('phase=one', file=sys.stderr, flush=True)\n"
                "deadline=time.monotonic()+3\n"
                "while not ack.exists() and time.monotonic()<deadline:\n"
                "    time.sleep(.02)\n"
                "if not ack.exists(): raise SystemExit(7)\n"
            ),
            str(acknowledgement),
        ],
        cwd=tmp_path,
        env={"PYTHONDONTWRITEBYTECODE": "1"},
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=5,
        on_stderr=observe,
    )

    assert acknowledgement.is_file()
    assert "".join(chunks) == "phase=one\n"
    assert completed.stderr == "phase=one\n"


@pytest.mark.skipif(os.name != "posix", reason="canonical dependency sync is POSIX-only")
def test_sigterm_interrupt_reaps_nested_session_process_group(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identities = tmp_path / "nested-identities"
    program = (
        "import os,pathlib,signal,subprocess,sys,time\n"
        "child=subprocess.Popen([sys.executable, '-c', "
        "'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)'])\n"
        "pathlib.Path(sys.argv[1]).write_text(f'{os.getpid()} {child.pid}', encoding='ascii')\n"
        "time.sleep(60)\n"
    )
    monkeypatch.setattr(network, "_PROCESS_GROUP_GRACE_SECONDS", 0.1)

    def terminate(_signum: int, _frame: object) -> None:
        raise InterruptedError("fixture SIGTERM")

    previous = signal.signal(signal.SIGTERM, terminate)
    try:
        with pytest.raises(InterruptedError, match="fixture SIGTERM"):
            subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    (
                        "import os,signal,time\n"
                        "deadline=time.monotonic()+3\n"
                        "while not os.path.exists(os.environ['IDENTITIES']) and time.monotonic()<deadline: time.sleep(.02)\n"
                        "os.kill(os.getppid(), signal.SIGTERM)\n"
                    ),
                ],
                env={**os.environ, "IDENTITIES": str(identities)},
            )
            network.run_managed_subprocess(
                [sys.executable, "-c", program, str(identities)],
                cwd=tmp_path,
                env={"PYTHONDONTWRITEBYTECODE": "1"},
                check=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=5,
            )
    finally:
        signal.signal(signal.SIGTERM, previous)
    parent_pid, _child_pid = (int(item) for item in identities.read_text().split())
    with pytest.raises(ProcessLookupError):
        os.killpg(parent_pid, 0)


@pytest.mark.skipif(os.name != "posix", reason="canonical dependency sync is POSIX-only")
def test_sigint_interrupt_reaps_owned_process_group(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = tmp_path / "sigint-identity"
    program = (
        "import os,pathlib,sys,time\n"
        "pathlib.Path(sys.argv[1]).write_text(str(os.getpid()), encoding='ascii')\n"
        "time.sleep(60)\n"
    )
    monkeypatch.setattr(network, "_PROCESS_GROUP_GRACE_SECONDS", 0.1)
    sender = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import os,signal,time\n"
                "deadline=time.monotonic()+3\n"
                "while not os.path.exists(os.environ['IDENTITY']) and time.monotonic()<deadline: time.sleep(.02)\n"
                "os.kill(os.getppid(), signal.SIGINT)\n"
            ),
        ],
        env={**os.environ, "IDENTITY": str(identity)},
    )
    with pytest.raises(KeyboardInterrupt):
        network.run_managed_subprocess(
            [sys.executable, "-c", program, str(identity)],
            cwd=tmp_path,
            env={"PYTHONDONTWRITEBYTECODE": "1"},
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=5,
        )
    sender.wait(timeout=2)
    with pytest.raises(ProcessLookupError):
        os.killpg(int(identity.read_text()), 0)


def test_managed_subprocess_streams_stdout_before_exit(tmp_path: Path) -> None:
    acknowledgement = tmp_path / "stdout-observed"
    chunks: list[str] = []

    def observe(chunk: str) -> None:
        chunks.append(chunk)
        acknowledgement.write_text("observed\n", encoding="ascii")

    completed = network.run_managed_subprocess(
        [
            sys.executable,
            "-c",
            (
                "import pathlib,sys,time\n"
                "ack=pathlib.Path(sys.argv[1])\n"
                "print('host=app tasks=assemble', flush=True)\n"
                "deadline=time.monotonic()+3\n"
                "while not ack.exists() and time.monotonic()<deadline: time.sleep(.02)\n"
                "if not ack.exists(): raise SystemExit(7)\n"
            ),
            str(acknowledgement),
        ],
        cwd=tmp_path,
        env={"PYTHONDONTWRITEBYTECODE": "1"},
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=5,
        on_stdout=observe,
    )
    assert acknowledgement.is_file()
    assert "".join(chunks) == "host=app tasks=assemble\n"
    assert completed.stdout == "host=app tasks=assemble\n"


def test_dependency_failure_cause_classifies_network_output() -> None:
    diagnostics = __import__(
        "quwoquan_ops.cli.lib.app_dependency_sync_diagnostics",
        fromlist=["dependency_failure_cause"],
    )
    unreachable = subprocess.CalledProcessError(
        1, ["gradle"], output="java.net.UnknownHostException: repo.maven.apache.org"
    )
    timeout = subprocess.CalledProcessError(
        124, ["gradle"], output="Android Gradle process exceeded its bounded timeout."
    )
    assert diagnostics.dependency_failure_cause(unreachable) == "network_unreachable"
    assert diagnostics.dependency_failure_cause(timeout) == "network_timeout"
    assert diagnostics.dependency_failure_cause(
        ValueError("APP.DEPENDENCY.android_sync_failed: cause=network_unreachable")
    ) == "network_unreachable"


def test_private_log_append_keeps_one_private_file(
    tmp_path: Path,
) -> None:
    from quwoquan_ops.cli.lib.app_dependency_sync_diagnostics import write_private_log

    path = tmp_path / "android-gradle-online-app.log"
    write_private_log(path, "host=app tasks=assemble\nfirst\n")
    write_private_log(path, "authorization=Bearer secret\nsecond\n", append=True)
    assert path.read_text() == (
        "host=app tasks=assemble\nfirst\nauthorization=[REDACTED]\nsecond\n"
    )
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert path.stat().st_nlink == 1
