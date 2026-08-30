from __future__ import annotations

import fcntl
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlparse

from quwoquan_ops.cli.lib.environment_topology import (
    get_target,
    load_environment_topology,
    validate_environment_topology,
)
from quwoquan_ops.cli.lib.local_runtime_reservation import (
    acquire_local_runtime_use_lock,
    active_conflicting_local_targets,
    assert_local_runtime_available,
    local_runtime_peer_targets,
)


class LocalRuntimeReservationContractTest(unittest.TestCase):
    def test_local_targets_share_one_metadata_owned_resource_group(self) -> None:
        topology = load_environment_topology()

        self.assertEqual(validate_environment_topology(topology), [])
        self.assertEqual(
            {
                get_target(topology, target)["localResourceGroup"]
                for target in (
                    "alpha-local",
                    "beta-local",
                    "gamma-local",
                    "prod-sim",
                )
            },
            {"workstation-commercial-runtime"},
        )

    def test_beta_start_rejects_an_active_alpha_runtime(self) -> None:
        topology = load_environment_topology()
        alpha_port = urlparse(
            get_target(topology, "alpha-local")["origins"]["contentService"]
        ).port

        def probe(host: str, port: int) -> bool:
            self.assertIn(host, {"127.0.0.1", "localhost"})
            return port == alpha_port

        with self.assertRaisesRegex(
            RuntimeError,
            "stackctl.py down --target alpha-local",
        ):
            assert_local_runtime_available(
                topology,
                "beta-local",
                port_probe=probe,
            )

    def test_running_requested_target_does_not_conflict_with_itself(self) -> None:
        topology = load_environment_topology()
        beta_port = urlparse(
            get_target(topology, "beta-local")["origins"]["contentService"]
        ).port

        conflicts = active_conflicting_local_targets(
            topology,
            "beta-local",
            port_probe=lambda _host, port: port == beta_port,
        )

        self.assertEqual(conflicts, ())

    def test_runtime_peer_targets_follow_metadata_resource_group(self) -> None:
        topology = load_environment_topology()

        self.assertEqual(
            local_runtime_peer_targets(topology, "beta-local"),
            ("alpha-local", "gamma-local", "prod-sim"),
        )

    def test_patrol_use_lease_blocks_destructive_runtime_operation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            lock_path = Path(temporary_dir) / "local-runtime.lock"
            lease = acquire_local_runtime_use_lock(
                target="beta-local",
                purpose="environment-patrol-smoke",
                lock_path=lock_path,
            )
            contender = lock_path.open("a+", encoding="utf-8")
            try:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(
                        contender.fileno(),
                        fcntl.LOCK_EX | fcntl.LOCK_NB,
                    )
            finally:
                contender.close()
                lease.close()

    def test_concurrent_use_leases_each_keep_and_remove_only_their_own_record(
        self,
    ) -> None:
        """共享租约是多持有者的：写入不得覆盖别人，释放不得连带删除别人。"""
        with tempfile.TemporaryDirectory() as temporary_dir:
            lock_path = Path(temporary_dir) / "local-runtime.lock"
            first = acquire_local_runtime_use_lock(
                target="beta-local",
                purpose="environment-patrol-smoke",
                lock_path=lock_path,
            )
            second = acquire_local_runtime_use_lock(
                target="gamma-local",
                purpose="app-content-uat",
                lock_path=lock_path,
            )
            try:
                holders = lock_path.read_text(encoding="utf-8").splitlines()
                self.assertIn(first.record, holders)
                self.assertIn(second.record, holders)
                self.assertEqual(len(holders), 2)

                first.close()
                remaining = lock_path.read_text(encoding="utf-8").splitlines()
                self.assertEqual(remaining, [second.record])
            finally:
                second.close()

            self.assertEqual(lock_path.read_text(encoding="utf-8").strip(), "")

    def test_use_lease_close_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            lock_path = Path(temporary_dir) / "local-runtime.lock"
            lease = acquire_local_runtime_use_lock(
                target="alpha-local",
                purpose="provider-conformance",
                lock_path=lock_path,
            )
            lease.close()
            lease.close()
            self.assertEqual(lock_path.read_text(encoding="utf-8").strip(), "")

    def test_dead_holder_records_are_reclaimed_and_live_ones_survive(self) -> None:
        """硬杀的持有者不走 close()，其记录必须被回收，否则诊断会指向不存在的进程。"""
        with tempfile.TemporaryDirectory() as temporary_dir:
            lock_path = Path(temporary_dir) / "local-runtime.lock"
            dead = (
                "pid=2147483646 target=gamma-local purpose=runtime-package-build "
                "startedAt=2026-08-28T05:19:54.388693Z lease=" + "0" * 32
            )
            unparseable = "target=gamma-local purpose=no-pid-recorded"
            lock_path.write_text(f"{dead}\n{unparseable}\n", encoding="utf-8")

            lease = acquire_local_runtime_use_lock(
                target="alpha-local",
                purpose="provider-conformance",
                lock_path=lock_path,
            )
            try:
                holders = lock_path.read_text(encoding="utf-8").splitlines()
                self.assertNotIn(dead, holders)
                # 解析不出 pid 的记录按存活处理：宁可多报持有者，也不静默丢事实。
                self.assertIn(unparseable, holders)
                self.assertIn(lease.record, holders)
            finally:
                lease.close()

            self.assertEqual(
                lock_path.read_text(encoding="utf-8").splitlines(),
                [unparseable],
            )

    def test_exclusive_locks_also_report_only_live_holders(self) -> None:
        """排他锁的阻断诊断同样只报存活持有者。

        本轮实测到的死记录事故（`purpose=runtime-package-build` 的 pid 已死）走的正是
        排他路径；只在共享租约路径过滤会让「阻塞诊断只报存活持有者」这句话大于实现覆盖。
        """
        from quwoquan_ops.cli.lib.local_runtime_reservation import (
            global_local_operation_lock,
            local_stack_operation_lock,
        )

        dead = "pid=2147483646 target=gamma-local purpose=runtime-package-build"
        for enter_lock in (
            lambda path: local_stack_operation_lock("gamma-local", lock_path=path),
            lambda path: global_local_operation_lock(
                scope="build-cache",
                affected_targets=("gamma-local",),
                lock_path=path,
            ),
        ):
            with tempfile.TemporaryDirectory() as temporary_dir:
                lock_path = Path(temporary_dir) / "local-runtime.lock"
                lock_path.write_text(dead + "\n", encoding="utf-8")
                blocker = lock_path.open("a+", encoding="utf-8")
                try:
                    fcntl.flock(blocker.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    with self.assertRaises(RuntimeError) as raised:
                        with enter_lock(lock_path):
                            pass
                finally:
                    fcntl.flock(blocker.fileno(), fcntl.LOCK_UN)
                    blocker.close()

                self.assertIn("unknown", str(raised.exception))
                self.assertNotIn("runtime-package-build", str(raised.exception))

    def test_dead_holder_is_not_reported_as_the_blocking_owner(self) -> None:
        """阻塞诊断只报存活持有者，避免让操作员去等一个早已退出的进程。"""
        with tempfile.TemporaryDirectory() as temporary_dir:
            lock_path = Path(temporary_dir) / "local-runtime.lock"
            lock_path.write_text(
                "pid=2147483646 target=gamma-local purpose=runtime-package-build\n",
                encoding="utf-8",
            )
            blocker = lock_path.open("a+", encoding="utf-8")
            try:
                fcntl.flock(blocker.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaises(RuntimeError) as raised:
                    acquire_local_runtime_use_lock(
                        target="alpha-local",
                        purpose="provider-conformance",
                        lock_path=lock_path,
                    )
            finally:
                fcntl.flock(blocker.fileno(), fcntl.LOCK_UN)
                blocker.close()

            self.assertIn("unknown", str(raised.exception))
            self.assertNotIn("runtime-package-build", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
