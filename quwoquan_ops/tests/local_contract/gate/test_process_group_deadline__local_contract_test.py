from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
RUNNER = ROOT / "quwoquan_ops/gate/lib/process_group_deadline.py"


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_deadline_terminates_the_entire_child_process_group(tmp_path: Path) -> None:
    child_pid_path = tmp_path / "child.pid"
    result_path = tmp_path / "result.json"
    fixture = (
        "import pathlib,subprocess,sys,time; "
        "child=subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']); "
        f"pathlib.Path({str(child_pid_path)!r}).write_text(str(child.pid)); "
        "time.sleep(30)"
    )
    started = time.monotonic()
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--deadline-epoch-seconds",
            str(time.time() + 0.35),
            "--grace-seconds",
            "0.1",
            "--result-json",
            str(result_path),
            "--",
            sys.executable,
            "-c",
            fixture,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )
    elapsed = time.monotonic() - started

    assert completed.returncode == 124
    assert elapsed < 3
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["outcome"] == "timeout"
    assert result["timedOut"] is True
    assert result["terminationSignal"] in {"SIGTERM", "SIGKILL"}
    child_pid = int(child_pid_path.read_text(encoding="utf-8"))
    for _ in range(50):
        if not _pid_exists(child_pid):
            break
        time.sleep(0.02)
    assert not _pid_exists(child_pid)


def test_timeout_does_not_signal_the_calling_process_group(tmp_path: Path) -> None:
    parent_pgid = os.getpgrp()
    result_path = tmp_path / "result.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--deadline-epoch-seconds",
            str(time.time() + 0.2),
            "--grace-seconds",
            "0.05",
            "--result-json",
            str(result_path),
            "--",
            sys.executable,
            "-c",
            "import time; time.sleep(30)",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )

    assert completed.returncode == 124
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["pid"] != parent_pgid
    assert os.getpgrp() == parent_pgid


def test_elapsed_deadline_never_starts_the_command(tmp_path: Path) -> None:
    marker = tmp_path / "must-not-exist"
    result_path = tmp_path / "result.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--deadline-epoch-seconds",
            str(time.time() - 1),
            "--result-json",
            str(result_path),
            "--",
            sys.executable,
            "-c",
            f"from pathlib import Path; Path({str(marker)!r}).touch()",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )

    assert completed.returncode == 124
    assert not marker.exists()
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["started"] is False
    assert result["timedOut"] is True
