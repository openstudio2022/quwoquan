"""App launch supervisor signal lifecycle test support."""

from __future__ import annotations

import signal
import subprocess
import threading
from pathlib import Path
from typing import Callable

from quwoquan_ops.cli.lib.app_launch_attempt import read_app_launch_attempt

SIGNAL_PHASE_CASES = (
    ("compiling", "APP.LAUNCH.compile_failed"),
    ("compiled", "APP.LAUNCH.install_failed"),
    ("installing", "APP.LAUNCH.install_failed"),
    ("installed", "APP.LAUNCH.runtime_config_missing"),
    ("configuring", "APP.LAUNCH.runtime_config_activation_failed"),
    ("configured", "APP.LAUNCH.launch_failed"),
    ("launching", "APP.LAUNCH.launch_failed"),
    ("launched", ""),
)
SUPPORTED_SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)


def signal_supervisor_at_phase(
    receipt: Path,
    *,
    phase: str,
    signum: signal.Signals,
    argv_factory: Callable[[Path, str], list[str]],
) -> tuple[int, dict[str, object]]:
    emitted_phases = (
        "compiled",
        "installing",
        "installed",
        "configuring",
        "configured",
        "launching",
        "launched",
    )
    phase_count = 0 if phase == "compiling" else emitted_phases.index(phase) + 1
    marker = f"signal-ready:{phase}"
    child = (
        "import time; "
        f"phases={emitted_phases[:phase_count]!r}; "
        "[print(f'QWQ_APP_LAUNCH_PHASE status={item}', flush=True) "
        "for item in phases]; "
        f"print({marker!r}, flush=True); time.sleep(30)"
    )
    process = subprocess.Popen(
        argv_factory(receipt, child),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    assert process.stdout is not None
    watchdog_fired = threading.Event()

    def stop_watchdog() -> None:
        if process.poll() is None:
            watchdog_fired.set()
            # A watchdog is not a second lifecycle signal.  SIGKILL cannot be
            # mistaken for the supervisor handling the signal under test and
            # therefore cannot manufacture a typed terminal receipt.
            process.kill()

    watchdog = threading.Timer(30.0, stop_watchdog)
    watchdog.start()
    try:
        for line in process.stdout:
            if line.strip() == marker:
                break
        else:
            raise AssertionError(
                f"supervisor exited before signal synchronization at {phase}"
            )
        assert read_app_launch_attempt(receipt)["status"] == phase
        process.send_signal(signum)
        process.communicate(timeout=30)
        if watchdog_fired.is_set():
            raise AssertionError(
                f"supervisor did not settle {signum.name} at {phase} before watchdog"
            )
    finally:
        watchdog.cancel()
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=5)
    return process.returncode, read_app_launch_attempt(receipt)
