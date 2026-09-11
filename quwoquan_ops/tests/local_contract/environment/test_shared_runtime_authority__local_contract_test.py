# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/multi-environment-instance-isolation/spec.md#gwt-003
from __future__ import annotations

from pathlib import Path

import pytest

from quwoquan_ops.cli.lib import output_paths, host_locks
from quwoquan_ops.cli.lib.local_runtime_reservation import local_stack_operation_lock, LocalOperationLockBusyError


def test_default_receipt_and_runs_are_shared_across_worktrees(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QWQ_OUTPUT_ROOT")
    monkeypatch.setattr(output_paths, "DEFAULT_LOCAL_RUNTIME_OUTPUT_ROOT", tmp_path / "host")
    monkeypatch.setattr(output_paths, "DEFAULT_OUTPUT_ROOT", tmp_path / "worktree-a" / ".qwq_output")
    first = output_paths.target_process_dir("beta-local")
    runs = output_paths.env_runs_root("beta")
    monkeypatch.setattr(output_paths, "DEFAULT_OUTPUT_ROOT", tmp_path / "worktree-b" / ".qwq_output")
    assert output_paths.target_process_dir("beta-local") == first
    assert output_paths.env_runs_root("beta") == runs
    assert first != output_paths.target_process_dir("gamma-local")


def test_legacy_receipt_blocks_without_migration_or_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QWQ_OUTPUT_ROOT")
    monkeypatch.setattr(output_paths, "DEFAULT_OUTPUT_ROOT", tmp_path / "old")
    legacy = tmp_path / "old/env/beta/local/beta-local/process/startup_attempt.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("{}")
    with pytest.raises(ValueError, match="reconcile_required"):
        output_paths.target_process_dir("beta-local")
    assert legacy.read_text() == "{}"


def test_live_cli_rejects_custom_authority_roots() -> None:
    with pytest.raises(ValueError, match="authority_override"):
        host_locks.require_canonical_runtime_authority()


def test_exception_retains_executor_fence(tmp_path: Path) -> None:
    path = tmp_path / "beta.lock"
    with pytest.raises(RuntimeError, match="child status unknown"):
        with local_stack_operation_lock("beta-local", lock_path=path):
            raise RuntimeError("child status unknown")
    with pytest.raises(LocalOperationLockBusyError, match="executor_reconcile_required"):
        with local_stack_operation_lock("beta-local", lock_path=path):
            pytest.fail("unknown executor must not be replaced")
    with local_stack_operation_lock("gamma-local", lock_path=tmp_path / "gamma.lock"):
        pass


def test_capacity_rejects_only_new_target_and_requires_exact_release(monkeypatch: pytest.MonkeyPatch) -> None:
    from quwoquan_ops.cli.lib import local_runtime_capacity as capacity
    monkeypatch.setattr(capacity, "observe_reservation_capacity", lambda: {
        "hostCpu": 8, "hostMemory": 32 * 2**30, "vmCpu": 8,
        "vmMemory": 32 * 2**30, "disk": 100 * 2**30,
    })
    update = capacity.update_runtime_capacity_reservation
    update(target="beta-local", generation="beta-1", status="prepared")
    with pytest.raises(capacity.LocalRuntimeCapacityError, match="reservation_exhausted"):
        update(target="gamma-local", generation="gamma-1", status="prepared")
    with pytest.raises(capacity.LocalRuntimeCapacityError, match="generation_conflict"):
        update(target="beta-local", generation="old", status="stopped")
    update(target="beta-local", generation="beta-1", status="running")
    update(target="gamma-local", generation="gamma-1", status="prepared")
    update(target="beta-local", generation="beta-1", status="stopped")
    with pytest.raises(capacity.LocalRuntimeCapacityError, match="generation_conflict"):
        update(target="gamma-local", generation="other", status="prepared")


def _reserve_in_process(root: str, target: str, start: object, result: object) -> None:
    import os
    from quwoquan_ops.cli.lib import local_runtime_capacity as capacity
    os.environ["QWQ_HOST_LOCK_ROOT"] = root
    capacity.observe_reservation_capacity = lambda: {
        "hostCpu": 8, "hostMemory": 32 * 2**30, "vmCpu": 8,
        "vmMemory": 32 * 2**30, "disk": 100 * 2**30,
    }
    assert start.wait(10)
    try:
        capacity.update_runtime_capacity_reservation(target=target, generation=target + "-1", status="prepared")
        result.put("reserved")
    except capacity.LocalRuntimeCapacityError as exc:
        result.put(str(exc))


def test_concurrent_capacity_reservations_have_one_winner(tmp_path: Path) -> None:
    import multiprocessing
    ctx = multiprocessing.get_context("spawn")
    start, result = ctx.Event(), ctx.Queue()
    processes = [ctx.Process(target=_reserve_in_process, args=(str(tmp_path), target, start, result))
                 for target in ("beta-local", "gamma-local")]
    for process in processes:
        process.start()
    try:
        start.set()
        outcomes = [result.get(timeout=15) for _ in processes]
        assert outcomes.count("reserved") == 1
        assert sum("reservation_exhausted" in outcome for outcome in outcomes) == 1
    finally:
        for process in processes:
            process.join(10)
            if process.is_alive():
                process.terminate()
                process.join(5)
    assert all(process.exitcode == 0 for process in processes)
