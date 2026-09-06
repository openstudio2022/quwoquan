"""场景：gamma up workload 装配——external provider substitute 拓扑绑定与失败
上报、full workload 固定包物化、build-only 从 up 退役及 CLI service slice 转发。"""

from __future__ import annotations

import argparse
import contextlib
import os
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
    def test_gamma_external_provider_environment_binds_substitute_topology(
        self,
    ) -> None:
        environment: dict[str, str] = {}
        storage = mock.Mock(
            environment={
                "LOCAL_GAMMA_OBJECT_STORAGE_ENDPOINT": "https://minio:19000",
            },
            host_endpoint="https://upload.gamma.quwoquan.com:19000",
        )
        values = {
            "RTC_MEDIA_CONNECTION_URL": "wss://rtc.nonprod.test",
            "RTC_MEDIA_API_KEY": "rtc-key",
            "RTC_MEDIA_API_SECRET": "rtc-secret",
        }
        with (
            mock.patch.object(
                stackctl,
                "prepare_local_gamma_object_storage",
                return_value=storage,
            ),
            mock.patch.object(
                stackctl,
                "_active_provider_runtime",
                return_value=self._provider_runtime_binding(
                    "gamma", Path(self.deploy_root.name)
                ),
            ),
            mock.patch.object(
                stackctl,
                "load_nonprod_provider_environment",
                return_value=values,
            ) as prepare,
        ):
            error = stackctl._bind_gamma_external_provider_environment(environment)

        self.assertIsNone(error)
        prepare.assert_called_once_with(
            environment="gamma",
            target_name="gamma-local",
            source=environment,
            debug_local=True,
            runtime_composition=self.provider_compositions["gamma"],
        )
        self.assertEqual(
            environment["CONTENT_OSS_ENDPOINT"],
            storage.environment["LOCAL_GAMMA_OBJECT_STORAGE_ENDPOINT"],
        )
        self.assertNotIn("CONTENT_OSS_CA_FILE", environment)
        self.assertEqual(
            environment["QWQ_COMPOSE_OBJECT_STORAGE_ENDPOINT"],
            storage.environment["LOCAL_GAMMA_OBJECT_STORAGE_ENDPOINT"],
        )
        self.assertEqual(
            environment["LOCAL_GAMMA_MEDIA_UPLOAD_BASE_URL"],
            storage.host_endpoint,
        )
        self.assertEqual(
            environment["CONTENT_MEDIA_DELIVERY_BASE_URL"],
            "https://cdn.gamma.quwoquan.com:19100",
        )
        self.assertEqual(
            environment["CONTENT_MEDIA_UPLOAD_BASE_URL"],
            "https://upload.gamma.quwoquan.com:19130",
        )
        self.assertNotIn("QWQ_COMPOSE_EMBEDDING_ENDPOINT", environment)
        self.assertNotIn("QWQ_COMPOSE_EMBEDDING_API_KEY", environment)
        self.assertIn("RTC_MEDIA_API_KEY", environment)
        self.assertNotIn("PRODUCT_OPS_SLS_ENDPOINT", environment)
        self.assertNotIn("ALIBABA_CLOUD_ACCESS_KEY_ID", environment)

    def test_gamma_external_provider_environment_reports_materialization_failure(
        self,
    ) -> None:
        with mock.patch.object(
            stackctl,
            "prepare_local_gamma_object_storage",
            side_effect=RuntimeError("materializer unavailable"),
        ):
            error = stackctl._bind_gamma_external_provider_environment({})

        self.assertIn(
            "gamma-local object storage materialization failed",
            error or "",
        )

    def test_gamma_full_workload_uses_fixed_package_and_materializes_providers(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            report_dir = Path(temporary_dir) / "report"
            work_root = Path(temporary_dir) / "deploy-work"
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
                build_only=False,
                build_services="",
                device_id="",
                rollout_mode="",
            )
            telemetry = mock.Mock()
            telemetry.environment = {
                "PRODUCT_OPS_ELASTICSEARCH_ENDPOINT": "http://elasticsearch:9200",
            }
            telemetry.redacted_receipt.return_value = {
                "source": "gamma-local-elasticsearch-topology",
                "status": "ready",
                "redactedDigest": "digest",
            }
            provider_composition = {
                "runtimeCompositionDigest": "sha256:" + "8" * 64
            }
            with (
                mock.patch.dict(
                    os.environ,
                    {
                        "QWQ_DEPLOY_WORK_ROOT": str(work_root),
                        stackctl.PACKAGE_ROOT_OVERRIDE_ENV: "/staging/poison",
                    },
                    clear=False,
                ),
                mock.patch.object(
                    stackctl,
                    "resolve_report_dir",
                    return_value=report_dir,
                ),
                mock.patch.object(
                    stackctl,
                    "validate_up_report_dir",
                    side_effect=lambda path, **_kwargs: Path(path),
                ),
                mock.patch.object(
                    stackctl,
                    "local_runtime_capacity_evidence",
                    return_value={"issues": []},
                ),
                mock.patch.object(stackctl, "_gamma_env_from_port_manifest", return_value={}),
                mock.patch.object(
                    stackctl,
                    "_optional_product_telemetry_environment",
                    return_value=({}, ""),
                ),
                mock.patch.object(
                    stackctl,
                    "_load_active_product_telemetry_log_sink",
                    return_value=telemetry,
                ),
                mock.patch.object(
                    stackctl,
                    "_local_stack_operation_lock",
                    return_value=contextlib.nullcontext(),
                ),
                mock.patch.object(
                    stackctl,
                    "_candidate_bindings_from_snapshot",
                    return_value=(
                        {
                            "candidateRoot": Path(temporary_dir),
                            "providerRuntime": {
                                "composition": provider_composition
                            },
                            "composition": provider_composition,
                        },
                        {
                            "candidateRoot": Path(temporary_dir),
                            "composition": {},
                        },
                    ),
                ),
                mock.patch.object(
                    stackctl,
                    "_provider_runtime_launch_environment",
                    return_value={
                        "QWQ_PROVIDER_RUNTIME_DIGEST": (
                            provider_composition["runtimeCompositionDigest"]
                        )
                    },
                ),
                mock.patch.object(
                    stackctl,
                    "_bind_formal_local_release_provider_environment",
                    return_value=None,
                ) as bind_release_providers,
                mock.patch.object(
                    stackctl,
                    "_bind_gamma_packaged_service_image_refs",
                    return_value={
                        "imageVersion": "sha256:" + "a" * 64,
                        "images": {},
                    },
                ),
                mock.patch.object(
                    stackctl,
                    "activate_search_experiment_policy",
                    return_value={"status": "passed"},
                ),
                mock.patch.object(stackctl, "run", side_effect=successful_syntax_check),
                mock.patch.object(
                    stackctl,
                    "_run_with_live_output",
                    return_value=CompletedProcess(["gamma-start"], 0, stdout="", stderr=""),
                ) as run_runtime,
                mock.patch.object(stackctl, "_write_summary_bundle"),
                mock.patch.object(stackctl, "relpath", side_effect=str),
            ):
                result = stackctl.command_up(args)

        self.assertEqual(result["exitCode"], 0, result)
        self.assertTrue(
            any("package" in " ".join(argv) for argv in argv_calls)
            or any("start_local_gamma_mirror" in " ".join(argv) for argv in argv_calls)
        )
        bind_release_providers.assert_called_once_with(
            mock.ANY,
            environment_name="gamma",
            target_name="gamma-local",
            workload="full",
            runtime_composition=provider_composition,
        )
        self.assertEqual(
            run_runtime.call_args.kwargs["env"][stackctl.PACKAGE_ROOT_OVERRIDE_ENV],
            "",
        )

    def test_gamma_build_only_is_retired_from_up(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            report_dir = Path(temporary_dir) / "report"
            args = argparse.Namespace(
                env="gamma",
                target=None,
                workload="full",
                skip_app=True,
                skip_build=False,
                build_only=True,
                build_services="assistant-service",
                device_id="",
                rollout_mode="",
            )
            with (
                mock.patch.object(
                    stackctl,
                    "resolve_report_dir",
                    return_value=report_dir,
                ),
                mock.patch.object(
                    stackctl,
                    "validate_up_report_dir",
                    side_effect=lambda path, **_kwargs: Path(path),
                ),
                mock.patch.object(
                    stackctl,
                    "local_runtime_capacity_evidence",
                    return_value={"issues": []},
                ),
                mock.patch.object(
                    stackctl,
                    "_gamma_env_from_port_manifest",
                    return_value={},
                ),
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
                    "_bind_gamma_object_storage_environment",
                    return_value=None,
                ) as bind_object_storage,
                mock.patch.object(
                    stackctl,
                    "_bind_formal_local_release_provider_environment",
                ) as bind_external_provider,
                mock.patch.object(
                    stackctl,
                    "_bind_gamma_packaged_service_image_refs",
                ),
                mock.patch.object(
                    stackctl,
                    "run",
                    return_value=CompletedProcess([], 0, stdout="", stderr=""),
                ),
                mock.patch.object(
                    stackctl,
                    "_run_with_live_output",
                    return_value=CompletedProcess([], 0, stdout="", stderr=""),
                ),
                mock.patch.object(stackctl, "_write_summary_bundle"),
                mock.patch.object(stackctl, "relpath", side_effect=str),
            ):
                result = stackctl.command_up(args)

        self.assertEqual(result["exitCode"], 2)
        self.assertIn("build-only is retired", result["summary"])
        bind_object_storage.assert_not_called()
        bind_external_provider.assert_not_called()

    def test_gamma_content_release_blocks_without_package_bound_provider_runtime(
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
                mock.patch.object(
                    stackctl,
                    "validate_up_report_dir",
                    side_effect=lambda path, **_kwargs: Path(path),
                ),
                mock.patch.object(
                    stackctl,
                    "local_runtime_capacity_evidence",
                    return_value={"issues": []},
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
                    "_candidate_bindings_from_snapshot",
                    side_effect=ValueError(
                        "package-bound Provider runtime is missing"
                    ),
                ),
                mock.patch.object(
                    stackctl,
                    "_bind_formal_local_release_provider_environment",
                    return_value=(
                        "gamma-local external provider materialization failed: "
                        "fixture service unavailable"
                    ),
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

        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(
            argv_calls,
            [["bash", "-n", "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"]],
        )
        self.assertIn(
            "package-bound Provider runtime failed",
            "\n".join(result["details"]),
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
