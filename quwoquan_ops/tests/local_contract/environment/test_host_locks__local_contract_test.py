from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from quwoquan_ops.cli.lib.host_locks import (
    HOST_LOCK_ROOT_ENV,
    HostLockBusyError,
    HostLockOwner,
    acquire_device_lock,
    acquire_host_lock,
    acquire_host_lock_bounded,
    current_lock_owner,
    device_lock_path,
    holder_record_is_live,
    local_runtime_lock_path,
    named_host_lock_path,
    parse_holder_record,
    publish_declared_lock_owner,
)
from quwoquan_ops.cli.lib.worktree_identity import WorktreeIdentityError


def _git(path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _worktree_pair(tmp_path: Path) -> tuple[Path, Path]:
    repository = tmp_path / "source"
    other = tmp_path / "other"
    _git(tmp_path, "init", "-b", "lane/ops", str(repository))
    _git(repository, "config", "user.email", "local-contract@example.invalid")
    _git(repository, "config", "user.name", "Local Contract")
    (repository / "tracked.txt").write_text("baseline\n", encoding="utf-8")
    _git(repository, "add", "tracked.txt")
    _git(repository, "commit", "-m", "baseline")
    _git(repository, "branch", "lane/small-fix")
    _git(repository, "worktree", "add", str(other), "lane/small-fix")
    return repository, other


def test_device_lock_is_mutually_exclusive_across_worktrees(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    first_worktree, second_worktree = _worktree_pair(tmp_path)
    lock_root = tmp_path / "host-locks"
    monkeypatch.setenv(HOST_LOCK_ROOT_ENV, str(lock_root))
    first = acquire_device_lock(
        device="emulator-5554",
        app="com.quwoquan.app",
        worktree_path=first_worktree,
    )
    try:
        with pytest.raises(HostLockBusyError) as excinfo:
            acquire_device_lock(
                device="emulator-5554",
                app="com.quwoquan.app",
                worktree_path=second_worktree,
            )
        assert str(first_worktree.resolve()) in str(excinfo.value)
        assert "lane=lane/ops" in str(excinfo.value)
        holder = parse_holder_record(first.record)
        assert holder["lane"] == "lane/ops"
        assert holder["worktree"] == str(first_worktree.resolve())
        assert first.path == (
            lock_root / "device" / "emulator-5554" / "com.quwoquan.app.lock"
        )
    finally:
        first.close()

    second = acquire_device_lock(
        device="emulator-5554",
        app="com.quwoquan.app",
        worktree_path=second_worktree,
    )
    second.close()


def test_dead_pid_record_is_taken_over(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    worktree, _other = _worktree_pair(tmp_path)
    monkeypatch.setenv(HOST_LOCK_ROOT_ENV, str(tmp_path / "host-locks"))
    path = device_lock_path("ios-simulator", "com.quwoquan.app")
    path.parent.mkdir(parents=True)
    path.write_text(
        "pid=2147483646 worktree=/tmp/dead lane=lane/refactor headSha=dead\n",
        encoding="utf-8",
    )

    lock = acquire_device_lock(
        device="ios-simulator",
        app="com.quwoquan.app",
        worktree_path=worktree,
    )
    try:
        holder = parse_holder_record(path.read_text(encoding="utf-8").strip())
        assert holder["pid"] == str(os.getpid())
        assert holder["worktree"] == str(worktree.resolve())
        assert holder["lane"] == "lane/ops"
    finally:
        lock.close()


def test_declared_projection_owner_used_when_worktree_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    projection = tmp_path / "projection"
    projection.mkdir()
    (projection / "source-isolation.json").write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("QWQ_HOST_LOCK_OWNER_WORKTREE", "old")
    monkeypatch.setenv("QWQ_HOST_LOCK_OWNER_LANE", "old")
    monkeypatch.setenv("QWQ_HOST_LOCK_OWNER_HEAD_SHA", "old")
    publish_declared_lock_owner(
        HostLockOwner(
            pid=1,
            worktree=str(projection),
            lane="immutable-source-projection",
            head_sha="a" * 40,
            started_at="old",
        )
    )
    owner = current_lock_owner(worktree_path=tmp_path / "not-a-repo")
    assert os.environ["QWQ_HOST_LOCK_OWNER_WORKTREE"] == str(projection)
    assert owner.worktree == str(projection)
    assert owner.lane == "immutable-source-projection"
    assert owner.head_sha == "a" * 40
    assert owner.pid == os.getpid()


def test_declared_projection_owner_rejected_when_invalid(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    missing = tmp_path / "not-a-repo"
    monkeypatch.delenv("QWQ_HOST_LOCK_OWNER_WORKTREE", raising=False)
    monkeypatch.delenv("QWQ_HOST_LOCK_OWNER_LANE", raising=False)
    monkeypatch.delenv("QWQ_HOST_LOCK_OWNER_HEAD_SHA", raising=False)
    with pytest.raises(WorktreeIdentityError):
        current_lock_owner(worktree_path=missing)

    projection = tmp_path / "projection"
    projection.mkdir()
    (projection / "source-isolation.json").write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("QWQ_HOST_LOCK_OWNER_WORKTREE", str(projection))
    monkeypatch.setenv("QWQ_HOST_LOCK_OWNER_LANE", "lane/ops")
    monkeypatch.setenv("QWQ_HOST_LOCK_OWNER_HEAD_SHA", "a" * 40)
    with pytest.raises(WorktreeIdentityError):
        current_lock_owner(worktree_path=missing)

    monkeypatch.setenv("QWQ_HOST_LOCK_OWNER_LANE", "immutable-source-projection")
    monkeypatch.setenv("QWQ_HOST_LOCK_OWNER_HEAD_SHA", "not-a-sha")
    with pytest.raises(WorktreeIdentityError):
        current_lock_owner(worktree_path=missing)

    monkeypatch.setenv("QWQ_HOST_LOCK_OWNER_HEAD_SHA", "a" * 40)
    (projection / "source-isolation.json").unlink()
    with pytest.raises(WorktreeIdentityError):
        current_lock_owner(worktree_path=missing)


def test_live_worktree_ignores_declared_projection_owner(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    live, _other = _worktree_pair(tmp_path)
    projection = tmp_path / "projection"
    projection.mkdir()
    (projection / "source-isolation.json").write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("QWQ_HOST_LOCK_OWNER_WORKTREE", str(projection))
    monkeypatch.setenv("QWQ_HOST_LOCK_OWNER_LANE", "immutable-source-projection")
    monkeypatch.setenv("QWQ_HOST_LOCK_OWNER_HEAD_SHA", "a" * 40)
    owner = current_lock_owner(worktree_path=live)
    assert owner.worktree == str(live.resolve())
    assert owner.lane == "lane/ops"


def test_projection_lock_owner_retains_mutual_exclusion(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(HOST_LOCK_ROOT_ENV, str(tmp_path / "locks"))
    owner = HostLockOwner(
        pid=2147483646, worktree=str(tmp_path / "projection"),
        lane="immutable-source-projection", head_sha="a" * 40, started_at="old",
    )
    with acquire_device_lock(device="ios-device", app="app.id", identity=owner) as lock:
        record = parse_holder_record(lock.record)
        assert record["pid"] == str(os.getpid())
        assert record["headSha"] == "a" * 40
        with pytest.raises(HostLockBusyError):
            acquire_device_lock(device="ios-device", app="app.id", identity=owner)


def test_holder_liveness_recognizes_dead_pid() -> None:
    assert holder_record_is_live(
        "pid=2147483646 worktree=/tmp/dead lane=lane/refactor"
    ) is False


def test_host_lock_path_shapes_use_the_override(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(HOST_LOCK_ROOT_ENV, str(tmp_path / "locks"))

    assert device_lock_path("device-1", "app.id") == (
        tmp_path / "locks" / "device" / "device-1" / "app.id.lock"
    )
    assert local_runtime_lock_path("alpha-local") == (
        tmp_path / "locks" / "local-runtime" / "alpha-local.lock"
    )


def test_bounded_named_host_lock_waits_then_acquires_with_holder_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    first_worktree, second_worktree = _worktree_pair(tmp_path)
    monkeypatch.setenv(HOST_LOCK_ROOT_ENV, str(tmp_path / "host-locks"))
    path = named_host_lock_path("app-dependency-sync", "toolchain")
    first = acquire_host_lock(
        path,
        fields={"resource": "flutter-cocoapods-gradle"},
        worktree_path=first_worktree,
    )
    waits: list[tuple[str, float]] = []
    try:
        with pytest.raises(HostLockBusyError, match="host resource wait timed out"):
            acquire_host_lock_bounded(
                path,
                timeout_seconds=0.02,
                poll_seconds=0.005,
                worktree_path=second_worktree,
                on_wait=lambda holder, remaining: waits.append((holder, remaining)),
            )
        assert waits
        assert str(first_worktree.resolve()) in waits[0][0]
        assert "lane=lane/ops" in waits[0][0]
        assert waits[-1][1] == 0
    finally:
        first.close()

    second = acquire_host_lock_bounded(
        path,
        timeout_seconds=0.1,
        worktree_path=second_worktree,
    )
    second.close()
