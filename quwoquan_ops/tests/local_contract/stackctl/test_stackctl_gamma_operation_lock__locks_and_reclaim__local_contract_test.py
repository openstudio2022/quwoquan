"""场景：本地栈操作锁互斥、Patrol 租约拒绝与 repair/reclaim 资源回收约束。"""

from __future__ import annotations

import argparse
import contextlib
import tempfile
import threading
from pathlib import Path
from subprocess import CompletedProcess
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.tests.support.stackctl_gamma_operation_lock_test_support import (
    StackctlGammaOperationLockContractTestBase,
)


class StackctlGammaOperationLockContractTest(
    StackctlGammaOperationLockContractTestBase
):
    def test_package_lock_serializes_one_target_and_allows_other_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            entered = threading.Event()

            def deployment_path(target: str, *parts: str) -> Path:
                return root / target / Path(*parts)

            def enter_same_target() -> None:
                with stackctl._target_package_lock("alpha-local"):
                    entered.set()

            with mock.patch.object(
                stackctl,
                "deployment_target_path",
                side_effect=deployment_path,
            ):
                with stackctl._target_package_lock("alpha-local"):
                    worker = threading.Thread(target=enter_same_target)
                    worker.start()
                    self.assertFalse(entered.wait(0.1))
                    with stackctl._target_package_lock("beta-local"):
                        pass
                self.assertTrue(entered.wait(1.0))
                worker.join(timeout=1.0)

        self.assertFalse(worker.is_alive())

    def test_orphan_repair_requires_explicit_confirmation(self) -> None:
        args = argparse.Namespace(
            target="alpha-local",
            fix="reclaim-orphaned-processes",
            confirm_orphaned_process_reclaim=False,
            report_dir="",
        )
        with (
            tempfile.TemporaryDirectory() as temporary_dir,
            mock.patch.object(
                stackctl,
                "resolve_report_dir",
                return_value=Path(temporary_dir),
            ),
            mock.patch.object(stackctl, "_write_summary_bundle"),
            mock.patch.object(
                stackctl.alpha_content_release_runtime,
                "reclaim_orphaned_managed_processes",
                side_effect=RuntimeError("explicit confirmation required"),
            ) as reclaim,
        ):
            result = stackctl.command_repair(args)

        self.assertEqual(result["exitCode"], 2)
        reclaim.assert_called_once_with(confirm=False)

    def test_reclaim_build_cache_only_prunes_unused_builder_cache(self) -> None:
        args = argparse.Namespace(
            target="gamma-local",
            fix="reclaim-build-cache",
            report_dir="",
            confirm_global_build_cache_reclaim=True,
        )
        with (
            tempfile.TemporaryDirectory() as temporary_dir,
            mock.patch.object(
                stackctl,
                "resolve_report_dir",
                return_value=Path(temporary_dir),
            ),
            mock.patch.object(stackctl, "_write_summary_bundle"),
            mock.patch.object(
                stackctl,
                "_global_local_build_cache_lock",
                return_value=contextlib.nullcontext({"mode": "exclusive"}),
            ),
            mock.patch.object(
                stackctl,
                "_local_build_cache_runtime_audit",
                return_value={"targets": [], "evidenceIssues": []},
            ),
            mock.patch.object(stackctl, "run") as run,
        ):
            run.side_effect = [
                CompletedProcess(["docker", "context", "show"], 0, "colima", ""),
                CompletedProcess(["docker", "info"], 0, "daemon", ""),
                CompletedProcess(["docker", "builder", "ls"], 0, "builder", ""),
                CompletedProcess(["docker", "system", "df"], 0, "before", ""),
                CompletedProcess(
                    ["docker", "builder", "prune", "--all", "--force"],
                    0,
                    "reclaimed",
                    "",
                ),
                CompletedProcess(["docker", "system", "df"], 0, "after", ""),
            ]
            payload = stackctl.command_repair(args)

        self.assertEqual(payload["exitCode"], 0)
        self.assertEqual(
            [call.args[0] for call in run.call_args_list],
            [
                ["docker", "context", "show"],
                ["docker", "info", "--format", "{{json .}}"],
                ["docker", "builder", "ls", "--format", "json"],
                ["docker", "system", "df"],
                ["docker", "builder", "prune", "--all", "--force"],
                ["docker", "system", "df"],
            ],
        )

    def test_reclaim_ports_inspects_canonical_block_without_active_candidate(self) -> None:
        args = argparse.Namespace(
            target="gamma-local",
            fix="reclaim-ports",
            report_dir="",
        )
        manifest = {
            "profiles": {"gamma-local": {"blockStart": 19000, "blockEnd": 19999}},
            "roles": {
                "api-edge": {"slotOffset": 0},
                "mongodb": {"slotOffset": 410},
            },
        }
        with (
            tempfile.TemporaryDirectory() as temporary_dir,
            mock.patch.object(stackctl, "load_environment_topology", return_value={}),
            mock.patch.object(
                stackctl,
                "get_target",
                return_value={"env": "gamma", "portProfile": "gamma-local"},
            ),
            mock.patch.object(
                stackctl,
                "resolve_report_dir",
                return_value=Path(temporary_dir),
            ),
            mock.patch.object(stackctl, "load_port_manifest", return_value=manifest),
            mock.patch.object(
                stackctl,
                "socket_probe",
                side_effect=lambda port: port == 19410,
            ),
            mock.patch.object(
                stackctl,
                "_network_report",
                side_effect=AssertionError("reclaim-ports must not load active candidate"),
            ),
            mock.patch.object(stackctl, "_write_summary_bundle"),
        ):
            payload = stackctl.command_repair(args)

        self.assertEqual(payload["exitCode"], 0)
        self.assertEqual(payload["details"], ["mongodb listens on 19410"])

    def test_reclaim_build_cache_accepts_failed_pre_inventory_after_recovery(
        self,
    ) -> None:
        args = argparse.Namespace(
            target="gamma-local",
            fix="reclaim-build-cache",
            report_dir="",
            confirm_global_build_cache_reclaim=True,
        )
        with (
            tempfile.TemporaryDirectory() as temporary_dir,
            mock.patch.object(
                stackctl,
                "resolve_report_dir",
                return_value=Path(temporary_dir),
            ),
            mock.patch.object(stackctl, "_write_summary_bundle"),
            mock.patch.object(
                stackctl,
                "_global_local_build_cache_lock",
                return_value=contextlib.nullcontext({"mode": "exclusive"}),
            ),
            mock.patch.object(
                stackctl,
                "_local_build_cache_runtime_audit",
                return_value={"targets": [], "evidenceIssues": []},
            ),
            mock.patch.object(stackctl, "run") as run,
        ):
            run.side_effect = [
                CompletedProcess(["docker", "context", "show"], 0, "colima", ""),
                CompletedProcess(["docker", "info"], 0, "daemon", ""),
                CompletedProcess(["docker", "builder", "ls"], 0, "builder", ""),
                CompletedProcess(
                    ["docker", "system", "df"],
                    1,
                    "",
                    "no space left on device",
                ),
                CompletedProcess(
                    ["docker", "builder", "prune", "--all", "--force"],
                    0,
                    "reclaimed",
                    "",
                ),
                CompletedProcess(
                    ["docker", "system", "df"],
                    0,
                    "Build Cache 0B",
                    "",
                ),
            ]
            payload = stackctl.command_repair(args)

        self.assertEqual(payload["exitCode"], 0)
        self.assertEqual(
            payload["summary"],
            "global unused Docker build cache reclaimed",
        )

    def test_reclaim_build_cache_is_available_from_each_local_target(self) -> None:
        for target in ("alpha-local", "beta-local", "gamma-local"):
            args = argparse.Namespace(
                target=target,
                fix="reclaim-build-cache",
                report_dir="",
                confirm_global_build_cache_reclaim=True,
            )
            with (
                self.subTest(target=target),
                tempfile.TemporaryDirectory() as temporary_dir,
                mock.patch.object(
                    stackctl,
                    "resolve_report_dir",
                    return_value=Path(temporary_dir),
                ),
                mock.patch.object(stackctl, "_write_summary_bundle"),
                mock.patch.object(
                    stackctl,
                    "_global_local_build_cache_lock",
                    return_value=contextlib.nullcontext({"mode": "exclusive"}),
                ),
                mock.patch.object(
                    stackctl,
                    "_local_build_cache_runtime_audit",
                    return_value={"targets": [], "evidenceIssues": []},
                ),
                mock.patch.object(stackctl, "run") as run,
            ):
                run.side_effect = [
                    CompletedProcess(["docker", "context", "show"], 0, "colima", ""),
                    CompletedProcess(["docker", "info"], 0, "daemon", ""),
                    CompletedProcess(["docker", "builder", "ls"], 0, "builder", ""),
                    CompletedProcess(
                        ["docker", "system", "df"],
                        0,
                        "before",
                        "",
                    ),
                    CompletedProcess(
                        ["docker", "builder", "prune", "--all", "--force"],
                        0,
                        "reclaimed",
                        "",
                    ),
                    CompletedProcess(
                        ["docker", "system", "df"],
                        0,
                        "after",
                        "",
                    ),
                ]
                payload = stackctl.command_repair(args)

            self.assertEqual(payload["exitCode"], 0)
            self.assertEqual(
                payload["summary"],
                "global unused Docker build cache reclaimed",
            )

    def test_gamma_lock_rejects_overlapping_stack_operations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            process_dir = Path(temporary_dir) / "process"
            with mock.patch.object(
                stackctl,
                "local_runtime_operation_lock_path",
                return_value=process_dir / ".stackctl-operation.lock",
            ):
                with stackctl._local_stack_operation_lock("gamma-local"):
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "local stack operation is already running",
                    ):
                        with stackctl._local_stack_operation_lock("beta-local"):
                            pass

            lock_path = process_dir / ".stackctl-operation.lock"
            self.assertTrue(lock_path.is_file())
            self.assertEqual(lock_path.read_text(encoding="utf-8"), "")

    def test_beta_up_rejects_overlapping_stack_operations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            report_dir = Path(temporary_dir) / "report"
            args = argparse.Namespace(
                env="beta",
                target=None,
                workload="content-release",
                skip_app=True,
                skip_build=False,
                build_only=False,
                build_services="",
                device_id="",
            )
            with (
                mock.patch.object(
                    stackctl,
                    "resolve_report_dir",
                    return_value=report_dir,
                ),
                mock.patch.object(
                    stackctl,
                    "_local_stack_operation_lock",
                    side_effect=RuntimeError(
                        "local stack operation is already running: pid=42 target=gamma-local",
                    ),
                ) as operation_lock,
                mock.patch.object(stackctl, "_write_summary_bundle"),
                mock.patch.object(stackctl, "relpath", side_effect=str),
                mock.patch.object(stackctl, "run") as run,
            ):
                result = stackctl.command_up(args)

            self.assertEqual(result["exitCode"], 2)
        self.assertEqual(result["summary"], "stackctl up is GATE_BLOCK for beta")
        self.assertIn(
            "wait for the active operation or stop the conflicting local runtime",
            result["details"],
        )
        operation_lock.assert_called_once_with("beta-local")
        run.assert_not_called()

    def test_beta_down_rejects_active_patrol_runtime_lease(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            report_dir = Path(temporary_dir) / "report"
            args = argparse.Namespace(target="beta-local", report_dir="")
            with (
                mock.patch.object(
                    stackctl,
                    "resolve_report_dir",
                    return_value=report_dir,
                ),
                mock.patch.object(
                    stackctl,
                    "_local_stack_operation_lock",
                    # 锁被占用是生产上的具名判否类型；替身若退回裸 RuntimeError，
                    # 就把「操作自身失败」的恢复动作误当成「等 lease 结束」验收。
                    side_effect=stackctl.LocalOperationLockBusyError(
                        "local stack operation is already running: "
                        "pid=42 target=beta-local purpose=environment-patrol-smoke"
                    ),
                ) as operation_lock,
                mock.patch.object(stackctl, "_write_summary_bundle"),
                mock.patch.object(stackctl, "relpath", side_effect=str),
                mock.patch.object(stackctl, "run") as run,
            ):
                result = stackctl.command_down(args)

        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(
            result["summary"],
            "stackctl down is GATE_BLOCK for beta-local",
        )
        self.assertIn(
            "wait for the active Patrol/UAT runtime lease to finish",
            result["details"],
        )
        operation_lock.assert_called_once_with("beta-local")
        run.assert_not_called()

    def test_beta_up_releases_operation_lock_when_alpha_is_active(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            report_dir = Path(temporary_dir) / "report"
            args = argparse.Namespace(
                env="beta",
                target=None,
                workload="content-release",
                skip_app=True,
                skip_build=False,
                build_only=False,
                build_services="",
                device_id="",
            )
            operation_lock = mock.MagicMock()
            operation_lock.__enter__.return_value = None
            self.availability.side_effect = RuntimeError(
                "beta-local cannot start while local runtime alpha-local is active"
            )
            with (
                mock.patch.object(
                    stackctl,
                    "resolve_report_dir",
                    return_value=report_dir,
                ),
                mock.patch.object(
                    stackctl,
                    "_local_stack_operation_lock",
                    return_value=operation_lock,
                ),
                mock.patch.object(stackctl, "_write_summary_bundle"),
                mock.patch.object(stackctl, "relpath", side_effect=str),
                mock.patch.object(stackctl, "run") as run,
            ):
                result = stackctl.command_up(args)

        self.assertEqual(result["exitCode"], 2)
        operation_lock.__exit__.assert_called_once()
        run.assert_not_called()
