from __future__ import annotations

import argparse
import contextlib
import os
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest import mock

from quwoquan_ops.cli import stackctl


class StackctlGammaOperationLockContractTest(unittest.TestCase):
    def test_gamma_lock_rejects_overlapping_stack_operations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            process_dir = Path(temporary_dir) / "process"
            with mock.patch.object(
                stackctl,
                "target_process_dir",
                return_value=process_dir,
            ):
                with stackctl._local_stack_operation_lock("gamma-local"):
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "gamma-local stack operation is already running",
                    ):
                        with stackctl._local_stack_operation_lock("gamma-local"):
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
                        "beta-local stack operation is already running: pid=42",
                    ),
                ) as operation_lock,
                mock.patch.object(stackctl, "_write_summary_bundle"),
                mock.patch.object(stackctl, "relpath", side_effect=str),
                mock.patch.object(stackctl, "run") as run,
            ):
                result = stackctl.command_up(args)

        self.assertEqual(result["exitCode"], 2)
        self.assertIn(
            "wait for the active beta-local operation to finish",
            result["details"],
        )
        operation_lock.assert_called_once_with("beta-local")
        run.assert_not_called()

    def test_beta_external_provider_environment_requires_controlled_values(self) -> None:
        environment: dict[str, str] = {}
        with mock.patch.dict(
            os.environ,
            {
                "CONTENT_EMBEDDING_ENDPOINT": "",
                "CONTENT_EMBEDDING_API_KEY": "",
            },
        ):
            error = stackctl._bind_beta_external_provider_environment(environment)

        self.assertEqual(environment, {})
        self.assertEqual(
            error,
            "beta-local external provider prerequisite is missing: "
            "CONTENT_EMBEDDING_ENDPOINT, CONTENT_EMBEDDING_API_KEY",
        )

    def test_beta_full_workload_blocks_before_background_spawn_without_provider_binding(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            report_dir = Path(temporary_dir) / "report"
            args = argparse.Namespace(
                env="beta",
                target=None,
                workload="full",
                skip_app=True,
                skip_build=False,
                build_only=False,
                build_services="",
                device_id="",
            )
            with (
                mock.patch.dict(
                    os.environ,
                    {
                        "CONTENT_EMBEDDING_ENDPOINT": "",
                        "CONTENT_EMBEDDING_API_KEY": "",
                    },
                ),
                mock.patch.object(
                    stackctl,
                    "resolve_report_dir",
                    return_value=report_dir,
                ),
                mock.patch.object(
                    stackctl,
                    "load_product_telemetry_sls",
                    return_value=mock.Mock(),
                ),
                mock.patch.object(
                    stackctl,
                    "_local_stack_operation_lock",
                    return_value=contextlib.nullcontext(),
                ),
                mock.patch.object(
                    stackctl,
                    "_beta_env_from_port_manifest",
                    return_value={},
                ),
                mock.patch.object(
                    stackctl,
                    "_optional_product_telemetry_environment",
                    return_value=({}, ""),
                ),
                mock.patch.object(stackctl, "_write_summary_bundle"),
                mock.patch.object(stackctl, "relpath", side_effect=str),
                mock.patch.object(stackctl, "run") as run,
            ):
                result = stackctl.command_up(args)

        self.assertEqual(result["exitCode"], 2)
        self.assertIn(
            "CONTENT_EMBEDDING_ENDPOINT",
            "\n".join(result["details"]),
        )
        run.assert_not_called()

    def test_beta_content_release_starts_without_embedding_provider_binding(
        self,
    ) -> None:
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
                mock.patch.dict(
                    os.environ,
                    {
                        "CONTENT_EMBEDDING_ENDPOINT": "",
                        "CONTENT_EMBEDDING_API_KEY": "",
                    },
                ),
                mock.patch.object(
                    stackctl,
                    "resolve_report_dir",
                    return_value=report_dir,
                ),
                mock.patch.object(
                    stackctl,
                    "_local_stack_operation_lock",
                    return_value=contextlib.nullcontext(),
                ),
                mock.patch.object(
                    stackctl,
                    "_beta_env_from_port_manifest",
                    return_value={},
                ),
                mock.patch.object(
                    stackctl,
                    "_optional_product_telemetry_environment",
                    return_value=({}, ""),
                ),
                mock.patch.object(
                    stackctl,
                    "_bind_beta_external_provider_environment",
                    side_effect=AssertionError(
                        "content-release must not request embedding provider binding"
                    ),
                ),
                mock.patch.object(
                    stackctl,
                    "_run_with_live_output",
                    return_value=CompletedProcess([], 0, "", ""),
                ) as run,
                mock.patch.object(
                    stackctl,
                    "_tail_multiple_logs_for_startup",
                    return_value={},
                ),
                mock.patch.object(stackctl, "canonical_port", return_value=18080),
                mock.patch.object(
                    stackctl,
                    "fetch_url",
                    return_value=(True, 200, "{}", "application/json"),
                ),
                mock.patch.object(stackctl, "_write_summary_bundle"),
                mock.patch.object(stackctl, "relpath", side_effect=str),
            ):
                result = stackctl.command_up(args)

        self.assertEqual(result["exitCode"], 0)
        run.assert_called_once()

    def test_gamma_up_checks_start_script_syntax_before_packaging(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            report_dir = Path(temporary_dir) / "report"
            argv_calls: list[list[str]] = []

            def fail_syntax(
                argv: list[str],
                *,
                env: dict[str, str] | None = None,
            ) -> CompletedProcess[str]:
                del env
                argv_calls.append(argv)
                return CompletedProcess(argv, 2, stdout="", stderr="syntax error")

            args = argparse.Namespace(
                env="gamma",
                target=None,
                workload="content-release",
                skip_app=True,
                skip_build=True,
                device_id="",
            )
            with (
                mock.patch.object(
                    stackctl,
                    "resolve_report_dir",
                    return_value=report_dir,
                ),
                mock.patch.object(stackctl, "_gamma_env_from_port_manifest", return_value={}),
                mock.patch.object(
                    stackctl,
                    "_optional_product_telemetry_environment",
                    return_value=({}, ""),
                ),
                mock.patch.object(
                    stackctl,
                    "_local_stack_operation_lock",
                    return_value=contextlib.nullcontext(),
                ),
                mock.patch.object(stackctl, "run", side_effect=fail_syntax),
                mock.patch.object(stackctl, "_write_summary_bundle"),
                mock.patch.object(stackctl, "relpath", side_effect=str),
            ):
                result = stackctl.command_up(args)

        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(
            argv_calls,
            [["bash", "-n", "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"]],
        )

    def test_gamma_binds_all_compose_service_images_to_package_provenance(self) -> None:
        environment: dict[str, str] = {}
        with mock.patch.object(
            stackctl,
            "_packaged_service_source_image_ref",
            side_effect=lambda env_name, service: f"{env_name}/{service}",
        ) as source_image:
            stackctl._bind_gamma_packaged_service_image_refs("gamma", environment)

        self.assertEqual(
            environment,
            {
                environment_key: f"gamma/{service}"
                for service, environment_key in stackctl.GAMMA_PACKAGED_SERVICE_IMAGE_ENVIRONMENTS
            },
        )
        self.assertEqual(
            source_image.call_args_list,
            [
                mock.call("gamma", service)
                for service, _ in stackctl.GAMMA_PACKAGED_SERVICE_IMAGE_ENVIRONMENTS
            ],
        )

    def test_gamma_external_provider_environment_requires_controlled_values(self) -> None:
        environment: dict[str, str] = {}
        with mock.patch.dict(
            os.environ,
            {
                "LOCAL_GAMMA_EMBEDDING_ENDPOINT": "",
                "LOCAL_GAMMA_EMBEDDING_API_KEY": "",
            },
        ):
            error = stackctl._bind_gamma_external_provider_environment(environment)

        self.assertEqual(environment, {})
        self.assertEqual(
            error,
            "gamma-local external provider prerequisite is missing: "
            "LOCAL_GAMMA_EMBEDDING_ENDPOINT, LOCAL_GAMMA_EMBEDDING_API_KEY",
        )

    def test_gamma_full_workload_blocks_before_packaging_without_provider_binding(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            report_dir = Path(temporary_dir) / "report"
            argv_calls: list[list[str]] = []

            def successful_syntax_check(
                argv: list[str],
                *,
                env: dict[str, str] | None = None,
            ) -> CompletedProcess[str]:
                del env
                argv_calls.append(argv)
                return CompletedProcess(argv, 0, stdout="", stderr="")

            args = argparse.Namespace(
                env="gamma",
                target=None,
                workload="full",
                skip_app=True,
                skip_build=True,
                device_id="",
            )
            with (
                mock.patch.dict(
                    os.environ,
                    {
                        "LOCAL_GAMMA_EMBEDDING_ENDPOINT": "",
                        "LOCAL_GAMMA_EMBEDDING_API_KEY": "",
                    },
                ),
                mock.patch.object(
                    stackctl,
                    "resolve_report_dir",
                    return_value=report_dir,
                ),
                mock.patch.object(stackctl, "_gamma_env_from_port_manifest", return_value={}),
                mock.patch.object(
                    stackctl,
                    "_optional_product_telemetry_environment",
                    return_value=({}, ""),
                ),
                mock.patch.object(stackctl, "load_product_telemetry_sls"),
                mock.patch.object(
                    stackctl,
                    "_local_stack_operation_lock",
                    return_value=contextlib.nullcontext(),
                ),
                mock.patch.object(stackctl, "run", side_effect=successful_syntax_check),
                mock.patch.object(stackctl, "_write_summary_bundle"),
                mock.patch.object(stackctl, "relpath", side_effect=str),
            ):
                result = stackctl.command_up(args)

        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(
            argv_calls,
            [["bash", "-n", "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"]],
        )
        self.assertIn(
            "LOCAL_GAMMA_EMBEDDING_ENDPOINT",
            "\n".join(result["details"]),
        )

    def test_gamma_content_release_reuses_packages_without_assistant_provider(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            report_dir = Path(temporary_dir) / "report"
            argv_calls: list[list[str]] = []

            def successful_syntax_check(
                argv: list[str],
                *,
                env: dict[str, str] | None = None,
            ) -> CompletedProcess[str]:
                del env
                argv_calls.append(argv)
                return CompletedProcess(argv, 0, stdout="", stderr="")

            args = argparse.Namespace(
                env="gamma",
                target=None,
                workload="content-release",
                skip_app=True,
                skip_build=True,
                build_only=False,
                build_services="",
                device_id="",
                rollout_mode="",
            )
            with (
                mock.patch.object(
                    stackctl,
                    "resolve_report_dir",
                    return_value=report_dir,
                ),
                mock.patch.object(stackctl, "_gamma_env_from_port_manifest", return_value={}),
                mock.patch.object(
                    stackctl,
                    "_optional_product_telemetry_environment",
                    return_value=({}, ""),
                ),
                mock.patch.object(
                    stackctl,
                    "_local_stack_operation_lock",
                    return_value=contextlib.nullcontext(),
                ),
                mock.patch.object(
                    stackctl,
                    "_bind_gamma_external_provider_environment",
                    side_effect=AssertionError("content-release must not bind assistant provider"),
                ) as bind_external_provider,
                mock.patch.object(
                    stackctl,
                    "_bind_gamma_packaged_service_image_refs",
                ),
                mock.patch.object(stackctl, "run", side_effect=successful_syntax_check),
                mock.patch.object(
                    stackctl,
                    "_run_with_live_output",
                    return_value=CompletedProcess(["gamma-start"], 0, stdout="", stderr=""),
                ),
                mock.patch.object(stackctl, "_write_summary_bundle"),
                mock.patch.object(stackctl, "relpath", side_effect=str),
            ):
                result = stackctl.command_up(args)

        self.assertEqual(result["exitCode"], 0)
        self.assertEqual(
            argv_calls,
            [["bash", "-n", "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"]],
        )
        bind_external_provider.assert_not_called()

    def test_gamma_build_only_cli_forwards_requested_service_slice(self) -> None:
        args = stackctl.build_parser().parse_args(
            [
                "up",
                "--env",
                "gamma",
                "--build-only",
                "--build-services",
                "chat-service,user-service",
                "--workload",
                "content-release",
            ]
        )

        self.assertTrue(args.build_only)
        self.assertEqual(args.build_services, "chat-service,user-service")
        self.assertEqual(
            stackctl._gamma_start_command(args),
            [
                "bash",
                "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh",
                "--build-only",
                "--build-services",
                "chat-service,user-service",
            ],
        )
