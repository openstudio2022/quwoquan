# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/multi-environment-instance-isolation/spec.md#gwt-003
from __future__ import annotations

import multiprocessing
import os
from pathlib import Path

import pytest

from quwoquan_ops.cli.lib.local_runtime_reservation import (
    acquire_local_runtime_use_lock, global_local_operation_lock,
    local_stack_operation_lock, LocalOperationLockBusyError,
)


def _hold(root: str, target: str, shared: bool, ready: object, finish: object) -> None:
    os.environ["QWQ_HOST_LOCK_ROOT"] = root
    if shared:
        lease = acquire_local_runtime_use_lock(target=target, purpose="multiprocess-contract")
        try:
            ready.set()
            assert finish.wait(10)
        finally:
            lease.close()
    else:
        with local_stack_operation_lock(target):
            ready.set()
            assert finish.wait(10)


@pytest.mark.parametrize("shared", [True, False])
def test_target_isolation_and_global_maintenance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, shared: bool) -> None:
    monkeypatch.setenv("QWQ_HOST_LOCK_ROOT", str(tmp_path))
    ctx = multiprocessing.get_context("spawn")
    ready, finish = ctx.Event(), ctx.Event()
    process = ctx.Process(target=_hold, args=(str(tmp_path), "beta-local", shared, ready, finish))
    process.start()
    try:
        assert ready.wait(8)
        with local_stack_operation_lock("gamma-local"):
            pass
        with pytest.raises(LocalOperationLockBusyError):
            with local_stack_operation_lock("beta-local", wait_seconds=0.1):
                pass
        with pytest.raises(LocalOperationLockBusyError):
            with global_local_operation_lock(scope="gc", affected_targets=("beta-local", "gamma-local")):
                pass
    finally:
        finish.set()
        process.join(10)
        if process.is_alive():
            process.terminate()
            process.join(5)
    assert process.exitcode == 0
    with global_local_operation_lock(scope="gc", affected_targets=("beta-local", "gamma-local")):
        with pytest.raises(LocalOperationLockBusyError):
            with local_stack_operation_lock("gamma-local"):
                pass
        with pytest.raises(LocalOperationLockBusyError):
            acquire_local_runtime_use_lock(target="beta-local", purpose="late-consumer")


def _executor_with_child(root: str, deploy: str, ready: object) -> None:
    import subprocess
    import sys
    os.environ["QWQ_HOST_LOCK_ROOT"] = root
    os.environ["QWQ_DEPLOY_WORK_ROOT"] = deploy
    with local_stack_operation_lock("beta-local"):
        child = subprocess.Popen([sys.executable, "-B", "-c", "import time; time.sleep(3)"], start_new_session=True)
        ready.put(child.pid)
        child.wait()


def test_parent_death_never_reopens_target_while_child_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import signal
    root, deploy = tmp_path / "locks", tmp_path / "deploy"
    monkeypatch.setenv("QWQ_HOST_LOCK_ROOT", str(root))
    monkeypatch.setenv("QWQ_DEPLOY_WORK_ROOT", str(deploy))
    ctx = multiprocessing.get_context("spawn")
    ready = ctx.Queue()
    parent = ctx.Process(target=_executor_with_child, args=(str(root), str(deploy), ready))
    parent.start()
    child_pid = ready.get(timeout=10)
    try:
        parent.kill()
        parent.join(5)
        assert parent.exitcode != 0
        os.kill(child_pid, 0)
        with pytest.raises(LocalOperationLockBusyError, match="executor_reconcile_required"):
            with local_stack_operation_lock("beta-local"):
                pytest.fail("surviving child must fence takeover")
        with local_stack_operation_lock("gamma-local"):
            pass
    finally:
        if parent.is_alive():
            parent.kill()
            parent.join(5)
        try:
            os.kill(child_pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
