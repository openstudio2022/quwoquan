"""Managed process lifecycle for ReliableTask fleets."""

from __future__ import annotations

from content.execution.queue.reliabletask.fleet import (
    Mapping,
    Path,
    os,
    signal,
    subprocess,
)


def _terminate_fleet_process(process: subprocess.Popen[object]) -> None:
    """Stop the service worker and all of its children after controller cancellation."""
    if process.poll() is not None:
        return
    from core.runtime_policy import active_runtime_policy

    grace_seconds = active_runtime_policy().process_termination_timeout_seconds
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except OSError:
        return
    try:
        process.wait(timeout=grace_seconds)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except OSError:
        return
    process.wait()


def _run_fleet_process(
    command: list[str],
    *,
    cwd: Path,
    environment: Mapping[str, str],
) -> int:
    """Run one owned worker process group so an interrupted execution cannot leak it."""
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=dict(environment),
        start_new_session=True,
    )
    try:
        return process.wait()
    except BaseException:
        _terminate_fleet_process(process)
        raise
