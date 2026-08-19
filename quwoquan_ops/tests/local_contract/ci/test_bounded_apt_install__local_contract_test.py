from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
RUNNER = ROOT / "quwoquan_ops/ci/run_bounded_apt_install.sh"


def _write_executable(path: Path, source: str) -> None:
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)


def _run_real_timeout(
    tmp_path: Path, *, hanging_attempts: int
) -> tuple[subprocess.CompletedProcess[str], int, list[int], float]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    counter = tmp_path / "attempt-count"
    pid_log = tmp_path / "hang-pids"

    _write_executable(bin_dir / "sudo", '#!/bin/sh\nexec "$@"\n')
    timeout_binary = shutil.which("timeout")
    assert timeout_binary is not None, "GNU timeout is required for the contract test"
    (bin_dir / "timeout").symlink_to(timeout_binary)
    _write_executable(
        bin_dir / "apt-get",
        """#!/bin/sh
case " $* " in
  *" update "*)
    count=0
    if [ -f "$APT_TEST_COUNTER" ]; then count="$(cat "$APT_TEST_COUNTER")"; fi
    count=$((count + 1))
    printf '%s\n' "$count" > "$APT_TEST_COUNTER"
    if [ "$count" -le "$APT_TEST_HANGING_ATTEMPTS" ]; then
      printf '%s\n' "$$" >> "$APT_TEST_PID_LOG"
      exec sleep 30
    fi
    ;;
esac
exit 0
""",
    )

    started = time.monotonic()
    completed = subprocess.run(
        ["bash", str(RUNNER), "tesseract-ocr"],
        cwd=ROOT,
        env={
            **os.environ,
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "APT_TEST_COUNTER": str(counter),
            "APT_TEST_HANGING_ATTEMPTS": str(hanging_attempts),
            "APT_TEST_PID_LOG": str(pid_log),
            "QWQ_CI_APT_COMMAND_TIMEOUT_SECONDS": "2",
            "QWQ_CI_APT_KILL_GRACE_SECONDS": "1",
            "QWQ_CI_APT_RETRY_DELAY_SECONDS": "0",
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=12,
    )
    elapsed = time.monotonic() - started
    attempts = int(counter.read_text(encoding="utf-8"))
    pids = [int(value) for value in pid_log.read_text(encoding="utf-8").splitlines()]
    return completed, attempts, pids, elapsed


def _assert_processes_are_gone(pids: list[int]) -> None:
    for pid in pids:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            continue
        except PermissionError as exc:  # pragma: no cover - would be a host fault
            raise AssertionError(f"cannot inspect timed-out apt pid={pid}") from exc
        raise AssertionError(f"timed-out apt process survived: pid={pid}")


def test_first_real_hang_is_killed_then_second_attempt_succeeds(tmp_path: Path) -> None:
    completed, attempts, pids, elapsed = _run_real_timeout(
        tmp_path, hanging_attempts=1
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert attempts == 2
    assert len(pids) == 1
    assert elapsed < 7
    assert "attempt 1/2 failed status=124" in completed.stderr
    _assert_processes_are_gone(pids)


def test_two_real_hangs_leave_no_process_and_return_typed_blocker(
    tmp_path: Path,
) -> None:
    completed, attempts, pids, elapsed = _run_real_timeout(
        tmp_path, hanging_attempts=2
    )

    assert completed.returncode == 2
    assert attempts == 2
    assert len(pids) == 2
    assert elapsed < 10
    assert "CI.DEPENDENCY.APT_INSTALL_RETRY_EXHAUSTED" in completed.stderr
    assert "fix=inspect-attempt-log-repair-mirror-lock-or-package" in completed.stderr
    _assert_processes_are_gone(pids)


def test_production_envelope_invokes_exact_timeout_and_sleep_arguments(
    tmp_path: Path,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    invocation_log = tmp_path / "invocations"
    attempt_counter = tmp_path / "attempt-count"
    _write_executable(bin_dir / "sudo", '#!/bin/sh\nexec "$@"\n')
    _write_executable(
        bin_dir / "timeout",
        """#!/bin/sh
printf 'timeout:%s|%s|%s\n' "$1" "$2" "$3" >> "$APT_TEST_INVOCATION_LOG"
count=0
if [ -f "$APT_TEST_ATTEMPT_COUNTER" ]; then count="$(cat "$APT_TEST_ATTEMPT_COUNTER")"; fi
count=$((count + 1))
printf '%s\n' "$count" > "$APT_TEST_ATTEMPT_COUNTER"
if [ "$count" -eq 1 ]; then exit 124; fi
exit 0
""",
    )
    _write_executable(
        bin_dir / "sleep",
        '#!/bin/sh\nprintf "sleep:%s\\n" "$*" >> "$APT_TEST_INVOCATION_LOG"\n',
    )

    completed = subprocess.run(
        ["bash", str(RUNNER), "prometheus", "tesseract-ocr"],
        cwd=ROOT,
        env={
            **os.environ,
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "APT_TEST_INVOCATION_LOG": str(invocation_log),
            "APT_TEST_ATTEMPT_COUNTER": str(attempt_counter),
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    invocations = invocation_log.read_text(encoding="utf-8").splitlines()
    assert len([line for line in invocations if line.startswith("timeout:")]) == 2
    timeout_invocations = [
        line for line in invocations if line.startswith("timeout:")
    ]
    assert timeout_invocations == [
        "timeout:--kill-after=10s|80s|bash",
        "timeout:--kill-after=10s|80s|bash",
    ]
    assert invocations == [timeout_invocations[0], "sleep:10", timeout_invocations[1]]
    assert 2 * (80 + 10) + 10 == 190


def test_invalid_package_and_removed_internal_attempt_flag_fail_before_sudo(
    tmp_path: Path,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    sudo_marker = tmp_path / "sudo-called"
    _write_executable(
        bin_dir / "sudo",
        '#!/bin/sh\ntouch "$APT_TEST_SUDO_MARKER"\nexit 99\n',
    )
    environment = {
        **os.environ,
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "APT_TEST_SUDO_MARKER": str(sudo_marker),
    }
    for arguments in (("Bad/Package",), ("--attempt", "1", "tesseract-ocr")):
        completed = subprocess.run(
            ["bash", str(RUNNER), *arguments],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 2
        assert "CI.DEPENDENCY.APT_PACKAGE_INVALID" in completed.stderr
    assert not sudo_marker.exists()


def test_bounds_reject_values_above_production_envelope() -> None:
    completed = subprocess.run(
        ["bash", str(RUNNER), "tesseract-ocr"],
        cwd=ROOT,
        env={**os.environ, "QWQ_CI_APT_COMMAND_TIMEOUT_SECONDS": "81"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "CI.DEPENDENCY.APT_BOUND_INVALID" in completed.stderr
