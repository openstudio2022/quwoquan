"""场景：alpha down 停止 release/app 双运行时、按 receipt 限定 purge 范围，
以及 down 对 canonical 端口释放的等待与失败语义。"""

from __future__ import annotations

import argparse
import contextlib
import json
import tempfile
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
    def test_alpha_down_stops_release_and_app_runtimes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            report_dir = Path(temporary_dir)
            with (
                mock.patch.object(
                    stackctl,
                    "resolve_report_dir",
                    return_value=report_dir,
                ),
                mock.patch.object(
                    stackctl,
                    "run",
                    return_value=CompletedProcess([], 0, stdout="", stderr=""),
                ) as run,
                mock.patch.object(
                    stackctl,
                    "_gamma_env_from_port_manifest",
                    return_value={
                        "QWQ_LOCAL_RELEASE_ENV": "alpha",
                        "QWQ_LOCAL_RELEASE_TARGET": "alpha-local",
                        "LOCAL_GAMMA_COMPOSE_PROJECT_NAME": "quwoquan_alpha_release_new_2",
                    },
                ),
                mock.patch.object(
                    stackctl,
                    "load_startup_attempt",
                    return_value=self._running_attempt("alpha"),
                ),
                mock.patch.object(
                    stackctl,
                    "_active_provider_runtime",
                    return_value=self._provider_runtime_binding(
                        "alpha", Path(temporary_dir)
                    ),
                ),
                mock.patch.object(
                    stackctl,
                    "_provider_runtime_launch_environment",
                    return_value=self._provider_runtime_environment("alpha"),
                ),
                mock.patch.object(
                    stackctl,
                    "_load_gamma_runtime_image_composition",
                    return_value=(
                        {"images": {}},
                        "quwoquan_alpha_release_old_1",
                    ),
                ),
                mock.patch.object(stackctl, "_apply_gamma_image_composition"),
                mock.patch.object(stackctl, "_bind_gamma_down_parse_environment"),
                mock.patch.object(
                    stackctl,
                    "_local_stack_operation_lock",
                    return_value=contextlib.nullcontext(),
                ),
                mock.patch.object(
                    stackctl,
                    "_wait_for_network_ports_released",
                    return_value=[],
                ),
                mock.patch.object(stackctl, "_write_summary_bundle"),
            ):
                result = stackctl.command_down(
                    argparse.Namespace(
                        target="alpha-local",
                        report_dir="",
                    )
                )

        self.assertEqual(result["exitCode"], 0)
        self.assertEqual(
            run.call_args_list[0].kwargs["env"][
                "LOCAL_GAMMA_COMPOSE_PROJECT_NAME"
            ],
            "quwoquan_alpha_release_old_1",
        )
        self.assertEqual(
            [call.args[0] for call in run.call_args_list],
            [
                [
                    "bash",
                    "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh",
                    "--down",
                ],
                [
                    "bash",
                    "quwoquan_app/scripts/device/run_stop_app_instance.sh",
                    "--env",
                    "alpha",
                    "--quiet",
                ],
            ],
        )

    def test_alpha_down_purges_only_runtime_receipt_bound_compose_volumes(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            report_dir = Path(temporary_dir)
            target_cache = Path(temporary_dir) / "target-cache"
            target_cache.mkdir()
            environment = {
                "QWQ_LOCAL_RELEASE_ENV": "alpha",
                "QWQ_LOCAL_RELEASE_TARGET": "alpha-local",
                "LOCAL_GAMMA_COMPOSE_PROJECT_NAME": "quwoquan_alpha_release_new_2",
            }
            with (
                mock.patch.object(
                    stackctl,
                    "load_environment_topology",
                    return_value={},
                ),
                mock.patch.object(
                    stackctl,
                    "get_target",
                    return_value={"env": "alpha"},
                ),
                mock.patch.object(
                    stackctl,
                    "resolve_report_dir",
                    return_value=report_dir,
                ),
                mock.patch.object(
                    stackctl,
                    "_gamma_env_from_port_manifest",
                    return_value=environment,
                ),
                mock.patch.object(
                    stackctl,
                    "load_startup_attempt",
                    return_value=self._running_attempt("alpha"),
                ),
                mock.patch.object(
                    stackctl,
                    "_active_provider_runtime",
                    return_value=self._provider_runtime_binding(
                        "alpha", Path(temporary_dir)
                    ),
                ),
                mock.patch.object(
                    stackctl,
                    "_provider_runtime_launch_environment",
                    return_value=self._provider_runtime_environment("alpha"),
                ),
                mock.patch.object(
                    stackctl,
                    "_load_gamma_runtime_image_composition",
                    return_value=(
                        {"images": {}},
                        "quwoquan_alpha_release_old_1",
                    ),
                ),
                mock.patch.object(stackctl, "_apply_gamma_image_composition"),
                mock.patch.object(stackctl, "_bind_gamma_down_parse_environment"),
                mock.patch.object(
                    stackctl,
                    "run",
                    return_value=CompletedProcess([], 0, stdout="", stderr=""),
                ) as run,
                mock.patch.object(
                    stackctl,
                    "_local_stack_operation_lock",
                    return_value=contextlib.nullcontext(),
                ),
                mock.patch.object(
                    stackctl,
                    "_wait_for_network_ports_released",
                    return_value=[],
                ),
                mock.patch.object(
                    stackctl,
                    "target_cache_dir",
                    return_value=target_cache,
                ),
                mock.patch.object(stackctl, "_write_summary_bundle"),
            ):
                result = stackctl.command_down(
                    argparse.Namespace(
                        target="alpha-local",
                        report_dir="",
                        formal_release=False,
                        purge_rebuildable_state=True,
                    )
                )
            report = json.loads((report_dir / "report.json").read_text())

        self.assertEqual(result["exitCode"], 0)
        self.assertEqual(
            run.call_args_list[0].args[0],
            [
                "bash",
                "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh",
                "--down",
                "--purge-rebuildable-state",
            ],
        )
        self.assertEqual(
            run.call_args_list[0].kwargs["env"][
                "LOCAL_GAMMA_COMPOSE_PROJECT_NAME"
            ],
            "quwoquan_alpha_release_old_1",
        )
        self.assertTrue(report["destructiveRepairPerformed"])
        self.assertEqual(
            report["destructiveActions"],
            [
                "purge-compose-volumes:quwoquan_alpha_release_old_1",
                "purge-target-cache:alpha-local",
            ],
        )
        self.assertFalse(target_cache.exists())

    def test_alpha_down_fails_when_canonical_port_remains_occupied(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            report_dir = Path(temporary_dir)
            with (
                mock.patch.object(
                    stackctl,
                    "resolve_report_dir",
                    return_value=report_dir,
                ),
                mock.patch.object(
                    stackctl,
                    "run",
                    return_value=CompletedProcess([], 0, stdout="", stderr=""),
                ),
                mock.patch.object(
                    stackctl,
                    "_gamma_env_from_port_manifest",
                    return_value={
                        "QWQ_LOCAL_RELEASE_ENV": "alpha",
                        "QWQ_LOCAL_RELEASE_TARGET": "alpha-local",
                        "LOCAL_GAMMA_COMPOSE_PROJECT_NAME": "quwoquan_alpha_release",
                    },
                ),
                mock.patch.object(
                    stackctl,
                    "load_startup_attempt",
                    return_value=self._running_attempt("alpha"),
                ),
                mock.patch.object(
                    stackctl,
                    "_active_provider_runtime",
                    return_value=self._provider_runtime_binding(
                        "alpha", Path(temporary_dir)
                    ),
                ),
                mock.patch.object(
                    stackctl,
                    "_provider_runtime_launch_environment",
                    return_value=self._provider_runtime_environment("alpha"),
                ),
                mock.patch.object(
                    stackctl,
                    "_load_gamma_runtime_image_composition",
                    return_value=({"images": {}}, "quwoquan_alpha_release"),
                ),
                mock.patch.object(stackctl, "_apply_gamma_image_composition"),
                mock.patch.object(stackctl, "_bind_gamma_down_parse_environment"),
                mock.patch.object(
                    stackctl,
                    "_wait_for_network_ports_released",
                    return_value=[
                        {"name": "media-origin", "port": 17110, "open": True}
                    ],
                ),
                mock.patch.object(
                    stackctl,
                    "_local_stack_operation_lock",
                    return_value=contextlib.nullcontext(),
                ),
                mock.patch.object(stackctl, "_write_summary_bundle"),
            ):
                result = stackctl.command_down(
                    argparse.Namespace(target="alpha-local", report_dir="")
                )

        self.assertEqual(result["exitCode"], 2)
        self.assertIn("canonical port remains occupied", result["details"][0])

    def test_down_waits_for_host_port_forward_release(self) -> None:
        reports = iter(
            [
                {"ports": [{"name": "mongodb", "port": 17410, "open": True}]},
                {"ports": [{"name": "mongodb", "port": 17410, "open": False}]},
            ]
        )
        with (
            mock.patch.object(stackctl, "_network_report", side_effect=reports),
            mock.patch.object(stackctl.time, "sleep") as sleep,
        ):
            occupied = stackctl._wait_for_network_ports_released(
                "alpha-local",
                timeout_seconds=1.0,
                poll_interval_seconds=0.01,
            )

        self.assertEqual(occupied, [])
        sleep.assert_called_once_with(0.01)
