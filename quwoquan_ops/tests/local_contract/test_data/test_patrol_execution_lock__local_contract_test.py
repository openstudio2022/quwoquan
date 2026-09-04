from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli.lib.host_locks import (
    HOST_LOCK_ROOT_ENV,
    acquire_host_lock,
    app_dependency_sync_lock_path,
)
from quwoquan_ops.cli.lib import patrol_execution_lock
from quwoquan_ops.cli.lib.patrol_execution_lock import (
    PATROL_EXECUTION_LOCK_NAME,
    PATROL_EXECUTION_LOCK_NAMESPACE,
    acquire_patrol_execution_lock,
    patrol_execution_lock_path,
)


def _git(path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _worktree_pair(root: Path) -> tuple[Path, Path]:
    repository = root / "source"
    other = root / "other"
    _git(root, "init", "-b", "lane/ops", str(repository))
    _git(repository, "config", "user.email", "local-contract@example.invalid")
    _git(repository, "config", "user.name", "Local Contract")
    (repository / "tracked.txt").write_text("baseline\n", encoding="utf-8")
    _git(repository, "add", "tracked.txt")
    _git(repository, "commit", "-m", "baseline")
    _git(repository, "branch", "lane/small-fix")
    _git(repository, "worktree", "add", str(other), "lane/small-fix")
    return repository, other


class PatrolExecutionLockContractTest(unittest.TestCase):
    def test_default_lock_uses_late_bound_host_root_without_repo_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            worktree, _other = _worktree_pair(root)
            lock_root = root / "host-locks"
            with (
                mock.patch.dict(
                    os.environ,
                    {HOST_LOCK_ROOT_ENV: str(lock_root)},
                ),
                mock.patch.object(patrol_execution_lock, "REPO_ROOT", worktree),
            ):
                expected = (
                    lock_root.resolve()
                    / PATROL_EXECUTION_LOCK_NAMESPACE
                    / PATROL_EXECUTION_LOCK_NAME
                )
                self.assertEqual(patrol_execution_lock_path(), expected)
                with acquire_patrol_execution_lock(
                    env_name="alpha-local",
                    target="homepage-feed",
                ) as held:
                    self.assertEqual(held.path, expected)
                    self.assertIn(f"worktree={worktree.resolve()}", held.record)
                self.assertEqual(expected.read_text(encoding="utf-8"), "")
                self.assertFalse((worktree / ".qwq_output").exists())

    def test_default_lock_is_shared_across_worktree_identities(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            first_worktree, second_worktree = _worktree_pair(root)
            lock_root = root / "host-locks"
            first = None
            with mock.patch.dict(
                os.environ,
                {HOST_LOCK_ROOT_ENV: str(lock_root)},
            ):
                try:
                    with mock.patch.object(
                        patrol_execution_lock,
                        "REPO_ROOT",
                        first_worktree,
                    ):
                        first = acquire_patrol_execution_lock(
                            env_name="alpha-local",
                            target="direct-flutter-run:SIMULATOR",
                        )
                    with mock.patch.object(
                        patrol_execution_lock,
                        "REPO_ROOT",
                        second_worktree,
                    ):
                        with self.assertRaisesRegex(
                            RuntimeError,
                            "Patrol build workspace is already in use",
                        ) as raised:
                            acquire_patrol_execution_lock(
                                env_name="alpha-local",
                                target="homepage-feed",
                            )
                    self.assertIn(str(first_worktree.resolve()), str(raised.exception))
                    self.assertIn("lane=lane/ops", str(raised.exception))

                    first.close()
                    first = None
                    with mock.patch.object(
                        patrol_execution_lock,
                        "REPO_ROOT",
                        second_worktree,
                    ):
                        second = acquire_patrol_execution_lock(
                            env_name="alpha-local",
                            target="homepage-feed",
                        )
                    self.assertEqual(
                        second.path,
                        lock_root.resolve()
                        / PATROL_EXECUTION_LOCK_NAMESPACE
                        / PATROL_EXECUTION_LOCK_NAME,
                    )
                    second.close()
                    second.close()
                finally:
                    if first is not None:
                        first.close()

    def test_dependency_sync_host_lock_blocks_flutter_workspace_consumer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            worktree, _other = _worktree_pair(root)
            lock_root = root / "host-locks"
            with (
                mock.patch.dict(
                    os.environ,
                    {HOST_LOCK_ROOT_ENV: str(lock_root)},
                ),
                mock.patch.object(patrol_execution_lock, "REPO_ROOT", worktree),
                acquire_host_lock(
                    app_dependency_sync_lock_path(),
                    fields={"resource": "flutter-cocoapods-gradle"},
                    worktree_path=worktree,
                ),
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "dependency-sync.*lane=lane/ops",
                ):
                    acquire_patrol_execution_lock(
                        env_name="alpha-local",
                        target="homepage-feed",
                    )

    def test_dependency_sync_cannot_enter_between_patrol_admission_and_workspace_lock(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            worktree, _other = _worktree_pair(root)
            lock_root = root / "host-locks"
            real_acquire = patrol_execution_lock.acquire_host_lock
            dependency_attempts = []

            def acquire_with_race_probe(path: Path, **kwargs: object):
                if path == patrol_execution_lock_path():
                    try:
                        dependency_attempts.append(
                            real_acquire(
                                app_dependency_sync_lock_path(),
                                fields={"resource": "dependency-sync-race-probe"},
                                worktree_path=worktree,
                            )
                        )
                    except patrol_execution_lock.HostLockBusyError:
                        pass
                return real_acquire(path, **kwargs)

            with (
                mock.patch.dict(
                    os.environ,
                    {HOST_LOCK_ROOT_ENV: str(lock_root)},
                ),
                mock.patch.object(patrol_execution_lock, "REPO_ROOT", worktree),
                mock.patch.object(
                    patrol_execution_lock,
                    "acquire_host_lock",
                    side_effect=acquire_with_race_probe,
                ),
            ):
                patrol_lock = acquire_patrol_execution_lock(
                    env_name="alpha-local",
                    target="homepage-feed",
                )
                self.addCleanup(patrol_lock.close)
                dependency_path = app_dependency_sync_lock_path()

            self.assertEqual(dependency_attempts, [])
            with self.assertRaises(patrol_execution_lock.HostLockBusyError):
                real_acquire(
                    dependency_path,
                    fields={"resource": "dependency-sync-after-admission"},
                    worktree_path=worktree,
                )
            patrol_lock.close()
            dependency_lock = real_acquire(
                dependency_path,
                fields={"resource": "dependency-sync-after-patrol"},
                worktree_path=worktree,
            )
            dependency_lock.close()

    def test_explicit_lock_path_preserves_independent_mutex_injection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            worktree, _other = _worktree_pair(root)
            lock_path = root / "injected" / "patrol.lock"
            lock_root = root / "unused-host-locks"
            with (
                mock.patch.dict(
                    os.environ,
                    {HOST_LOCK_ROOT_ENV: str(lock_root)},
                ),
                mock.patch.object(patrol_execution_lock, "REPO_ROOT", worktree),
            ):
                first = acquire_patrol_execution_lock(
                    env_name="alpha-local",
                    target="direct-flutter-run:SIMULATOR",
                    lock_path=lock_path,
                )
                self.addCleanup(first.close)
                self.assertEqual(first.path, lock_path)

                with self.assertRaisesRegex(
                    RuntimeError,
                    "Patrol build workspace is already in use",
                ):
                    acquire_patrol_execution_lock(
                        env_name="alpha-local",
                        target="homepage-feed",
                        lock_path=lock_path,
                    )

                first.close()
                replacement = acquire_patrol_execution_lock(
                    env_name="alpha-local",
                    target="homepage-feed",
                    lock_path=lock_path,
                )
                replacement.close()
                self.assertFalse(lock_root.exists())


if __name__ == "__main__":
    unittest.main()
