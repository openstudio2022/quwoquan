"""Local readiness state-storage security contracts."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))
sys.path.insert(0, str(ROOT))

from lib.local_readiness.core import (  # noqa: E402
    LocalReadinessError,
    _atomic_json,
    _state_root,
    enqueue_paths,
    plan_readiness,
    resource_lock,
    run_readiness,
    verify_receipt,
)


def _repo() -> tempfile.TemporaryDirectory[str]:
    return tempfile.TemporaryDirectory()


def _init(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "checkout", "-qb", "dev1.0"], cwd=path, check=True)
    (path / "docs").mkdir()
    (path / "docs/source.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "add", "docs/source.txt"], cwd=path, check=True)
    subprocess.run(
        [
            "git", "-c", "user.name=Fixture",
            "-c", "user.email=fixture@example.invalid",
            "commit", "-qm", "base",
        ],
        cwd=path,
        check=True,
    )


# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-002.t1
def test_state_root_rejects_symlink_components_and_secures_temp_repo_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    state = repo / "state"
    assert _state_root(state) == state.absolute()
    assert state.is_dir()
    assert state.stat().st_mode & 0o077 == 0

    target = repo / "target"
    target.mkdir()
    linked = repo / "linked"
    linked.symlink_to(target, target_is_directory=True)
    with pytest.raises(LocalReadinessError, match="symlink component"):
        _state_root(linked / "state")
    monkeypatch.setenv("QWQ_LOCAL_READINESS_ROOT", str(linked / "override"))
    with pytest.raises(LocalReadinessError, match="symlink component"):
        _state_root()


def test_empty_legacy_queue_is_safely_projected_to_current_schema(tmp_path: Path) -> None:
    from lib.local_readiness.queue import read_queue

    queue = tmp_path / "queue.json"
    queue.write_text('{"schema":"local-readiness-queue-v1","items":[]}\n', encoding="utf-8")
    assert read_queue(queue) == {"schema": "local-readiness-queue-v2", "items": []}
    queue.write_text('{"schema":"local-readiness-queue-v1","items":[{}]}\n', encoding="utf-8")
    with pytest.raises(LocalReadinessError, match="queue schema"):
        read_queue(queue)


def test_queue_corruption_symlink_and_extra_fields_fail_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init(repo)
    monkeypatch.setattr("lib.local_readiness.core.ROOT", repo)
    state = repo / "state"
    queue = state / "process/deferred-queue.json"
    enqueue_paths(["docs/source.txt"], state_root=state)

    corruptions = [
        {"schema": "local-readiness-queue-v2", "items": [], "extra": True},
        {"schema": "local-readiness-queue-v2", "items": [{**json.loads(queue.read_text())["items"][0], "extra": True}]},
        {"schema": "wrong", "items": []},
    ]
    for value in corruptions:
        queue.write_text(json.dumps(value), encoding="utf-8")
        with pytest.raises(LocalReadinessError, match="queue"):
            enqueue_paths(["docs/source.txt"], state_root=state)

    external = repo / "external-queue.json"
    external.write_text('{"schema":"local-readiness-queue-v2","items":[]}', encoding="utf-8")
    queue.unlink()
    queue.symlink_to(external)
    with pytest.raises(LocalReadinessError, match="regular file|symlink"):
        enqueue_paths(["docs/source.txt"], state_root=state)
    queue.unlink()
    queue.mkdir()
    with pytest.raises(LocalReadinessError, match="regular file"):
        enqueue_paths(["docs/source.txt"], state_root=state)


def test_atomic_write_and_resource_lock_reject_destination_symlinks(tmp_path: Path) -> None:
    state = tmp_path / "state"
    external = tmp_path / "external.json"
    external.write_text("unchanged\n", encoding="utf-8")
    destination = state / "process/value.json"
    destination.parent.mkdir(parents=True)
    destination.symlink_to(external)
    with pytest.raises(LocalReadinessError, match="destination"):
        _atomic_json(destination, {"status": "PASS"})
    assert external.read_text(encoding="utf-8") == "unchanged\n"

    locks = state / "process/locks"
    locks.mkdir()
    locks.rmdir()
    lock_target = tmp_path / "external-locks"
    lock_target.mkdir()
    locks.symlink_to(lock_target, target_is_directory=True)
    with pytest.raises(LocalReadinessError, match="symlink"):
        with resource_lock("runner", state_root=state):
            pass

    locks.unlink()
    locks.mkdir()
    external_lock = tmp_path / "external.lock"
    external_lock.touch()
    (locks / "runner.lock").symlink_to(external_lock)
    with pytest.raises(LocalReadinessError, match="lock|regular file"):
        with resource_lock("runner", state_root=state):
            pass


def test_cache_read_rejects_symlink_before_reuse(tmp_path: Path) -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        state = repo / "state"
        plan = plan_readiness(level="fast", paths=["docs/source.txt"], repo_root=repo, mode="workspace", state_root=state)
        receipt = run_readiness(plan, repo_root=repo, state_root=state)
        cache = state / "cache/exact-input" / f"{receipt['fingerprint']['digest'].removeprefix('sha256:')}.json"
        external = Path(tempfile.mkdtemp()) / "external-cache.json"
        external.write_bytes(cache.read_bytes())
        cache.unlink()
        cache.symlink_to(external)
        with pytest.raises(LocalReadinessError, match="cache.*regular file|cache.*symlink"):
            run_readiness(plan, repo_root=repo, state_root=state)
        cache.unlink()
        cache.mkdir()
        with pytest.raises(LocalReadinessError, match="cache.*regular file"):
            run_readiness(plan, repo_root=repo, state_root=state)


def test_pointer_receipt_path_is_confined_and_reads_reject_symlinks(tmp_path: Path) -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        state = repo / "state"
        plan = plan_readiness(level="fast", paths=["docs/source.txt"], repo_root=repo, mode="workspace", state_root=state)
        receipt = run_readiness(plan, repo_root=repo, state_root=state)
        pointer = next((state / "process/receipts/current").glob("*.json"))
        immutable = state / "process/receipts/by-fingerprint" / f"{receipt['fingerprint']['digest'].removeprefix('sha256:')}.json"
        external = repo / "external-receipt.json"
        external.write_text(immutable.read_text(encoding="utf-8"), encoding="utf-8")

        for raw in (str(external), "../../../../external-receipt.json"):
            value = json.loads(pointer.read_text(encoding="utf-8"))
            value["receipt"] = raw
            pointer.write_text(json.dumps(value), encoding="utf-8")
            with pytest.raises(LocalReadinessError, match="canonical|receipt"):
                verify_receipt(level="fast", paths=["docs/source.txt"], repo_root=repo, mode="workspace", state_root=state)

        value = {"schema": "local-readiness-current-pointer-v1", "receipt": str(immutable), "fingerprint": receipt["fingerprint"]["ref"]}
        pointer.write_text(json.dumps(value), encoding="utf-8")
        pointer_target = repo / "pointer-target.json"
        pointer.replace(pointer_target)
        pointer.symlink_to(pointer_target)
        with pytest.raises(LocalReadinessError, match="pointer.*regular file|pointer.*symlink"):
            verify_receipt(level="fast", paths=["docs/source.txt"], repo_root=repo, mode="workspace", state_root=state)

        pointer.unlink()
        pointer.mkdir()
        with pytest.raises(LocalReadinessError, match="pointer.*regular file"):
            verify_receipt(level="fast", paths=["docs/source.txt"], repo_root=repo, mode="workspace", state_root=state)
        pointer.rmdir()
        pointer_target.replace(pointer)
        receipt_target = repo / "receipt-target.json"
        immutable.replace(receipt_target)
        immutable.symlink_to(receipt_target)
        with pytest.raises(LocalReadinessError, match="receipt.*regular file|receipt.*symlink"):
            verify_receipt(level="fast", paths=["docs/source.txt"], repo_root=repo, mode="workspace", state_root=state)
        immutable.unlink()
        immutable.mkdir()
        with pytest.raises(LocalReadinessError, match="receipt.*regular file"):
            verify_receipt(level="fast", paths=["docs/source.txt"], repo_root=repo, mode="workspace", state_root=state)
