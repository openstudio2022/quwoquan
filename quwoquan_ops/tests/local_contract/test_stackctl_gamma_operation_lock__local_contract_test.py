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
    def test_gamma_down_materializes_compose_bindings_before_interpolation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            report_dir = Path(temporary_dir)
            compose_environment = {"GAMMA_PORT": "19000"}

            def bind(environment: dict[str, str]) -> None:
                environment["LOCAL_GAMMA_OBJECT_STORAGE_ACCESS_KEY_ID"] = (
                    "local-access-key"
                )

            with (
                mock.patch.object(
                    stackctl,
                    "load_environment_topology",
                    return_value={},
                ),
                mock.patch.object(
                    stackctl,
                    "get_target",
                    return_value={"env": "gamma"},
                ),
                mock.patch.object(
                    stackctl,
                    "resolve_report_dir",
                    return_value=report_dir,
                ),
                mock.patch.object(
                    stackctl,
                    "_gamma_env_from_port_manifest",
                    return_value=compose_environment,
                ),
                mock.patch.object(
                    stackctl,
                    "_bind_gamma_object_storage_environment",
                    side_effect=bind,
                ) as bind_environment,
                mock.patch.object(
                    stackctl,
                    "run",
                    return_value=CompletedProcess([], 0, stdout="", stderr=""),
                ) as run,
                mock.patch.object(stackctl, "_write_summary_bundle"),
            ):
                result = stackctl.command_down(
                    argparse.Namespace(
                        target="gamma-local",
                        report_dir="",
                    )
                )

        self.assertEqual(result["exitCode"], 0)
        bind_environment.assert_called_once_with(compose_environment)
        self.assertEqual(
            run.call_args.kwargs["env"][
                "LOCAL_GAMMA_OBJECT_STORAGE_ACCESS_KEY_ID"
            ],
            "local-access-key",
        )

    def test_gamma_startup_timeouts_come_only_from_target_topology(self) -> None:
        topology = stackctl.load_environment_topology()
        target = stackctl.get_target(topology, "gamma-local")
        startup = target["startup"]
        build_images = target["buildImages"]

        environment = stackctl._gamma_env_from_port_manifest(
            topology,
            "gamma-local",
        )

        self.assertEqual(
            environment["LOCAL_GAMMA_COMPOSE_BUILD_TIMEOUT_SECONDS"],
            str(startup["composeBuildTimeoutSeconds"]),
        )
        self.assertEqual(
            environment["LOCAL_GAMMA_DOCKER_PROBE_TIMEOUT_SECONDS"],
            str(startup["dockerProbeTimeoutSeconds"]),
        )
        self.assertEqual(
            environment["LOCAL_GAMMA_COMPOSE_BUILD_NO_PROGRESS_TIMEOUT_SECONDS"],
            str(startup["composeBuildNoProgressTimeoutSeconds"]),
        )
        self.assertEqual(
            environment["LOCAL_GAMMA_COMPOSE_UP_TIMEOUT_SECONDS"],
            str(startup["composeUpTimeoutSeconds"]),
        )
        self.assertEqual(
            environment["LOCAL_GAMMA_GO_BASE_IMAGE"],
            build_images["goBaseImage"],
        )
        self.assertEqual(
            environment["LOCAL_GAMMA_ALPINE_BASE_IMAGE"],
            build_images["alpineBaseImage"],
        )
        self.assertEqual(
            environment["LOCAL_GAMMA_MEDIA_UPLOAD_BASE_URL"],
            target["publicBases"]["mediaUpload"],
        )
        self.assertEqual(
            environment["LOCAL_GAMMA_RTC_MEDIA_CONNECTION_URL"],
            target["publicBases"]["rtc"],
        )

    def test_gamma_service_builds_require_topology_owned_base_images(self) -> None:
        service_root = stackctl.ROOT / "quwoquan_service"
        compose_files = sorted(service_root.glob("services/*/deploy/compose.yaml"))
        compose_files.append(
            service_root / "control-plane/platform-ops/deploy/compose.yaml"
        )

        for compose_file in compose_files:
            compose = compose_file.read_text(encoding="utf-8")
            if "GO_BASE_IMAGE:" not in compose:
                continue
            self.assertIn("QWQ_COMPOSE_GO_BASE_IMAGE:?", compose, compose_file)
            self.assertIn("QWQ_COMPOSE_ALPINE_BASE_IMAGE:?", compose, compose_file)
            self.assertNotIn("GO_ALPINE_BASE_IMAGE", compose, compose_file)
            self.assertNotIn(":-golang:", compose, compose_file)
            self.assertNotIn(":-alpine:", compose, compose_file)

            dockerfile_ref = compose.split("dockerfile: ", 1)[1].splitlines()[0]
            dockerfile = next(
                candidate
                for candidate in (
                    stackctl.ROOT / dockerfile_ref,
                    service_root / dockerfile_ref,
                )
                if candidate.is_file()
            )
            dockerfile_text = dockerfile.read_text(encoding="utf-8")
            self.assertIn("ARG GO_BASE_IMAGE\n", dockerfile_text, dockerfile)
            self.assertIn("ARG ALPINE_BASE_IMAGE\n", dockerfile_text, dockerfile)

    def test_reclaim_build_cache_only_prunes_unused_builder_cache(self) -> None:
        args = argparse.Namespace(
            target="gamma-local",
            fix="reclaim-build-cache",
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
            mock.patch.object(stackctl, "run") as run,
        ):
            run.side_effect = [
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
                ["docker", "system", "df"],
                ["docker", "builder", "prune", "--all", "--force"],
                ["docker", "system", "df"],
            ],
        )

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
        self.assertEqual(result["summary"], "stackctl up is GATE_BLOCK for beta")
        self.assertIn(
            "wait for the active beta-local operation to finish",
            result["details"],
        )
        operation_lock.assert_called_once_with("beta-local")
        run.assert_not_called()

    def test_beta_external_provider_environment_materializes_local_substitutes(self) -> None:
        environment: dict[str, str] = {}
        with tempfile.TemporaryDirectory() as temporary_dir:
            with mock.patch.dict(
                os.environ,
                {"QWQ_DEPLOY_WORK_ROOT": temporary_dir},
                clear=False,
            ):
                error = stackctl._bind_beta_external_provider_environment(environment)

        self.assertIsNone(error)
        self.assertIn("CONTENT_EMBEDDING_FIXTURE_API_KEY", environment)
        self.assertIn("CONTENT_EMBEDDING_ENDPOINT", environment)
        self.assertTrue(environment["CONTENT_EMBEDDING_FIXTURE_API_KEY"])

    def test_beta_full_workload_blocks_when_provider_materialization_fails(
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
            telemetry = mock.Mock()
            telemetry.redacted_receipt.return_value = {
                "source": "service-config-postgres-telemetry",
                "status": "ready",
                "redactedDigest": "digest",
            }
            telemetry.environment = {}
            with (
                mock.patch.object(
                    stackctl,
                    "resolve_report_dir",
                    return_value=report_dir,
                ),
                mock.patch.object(
                    stackctl,
                    "load_product_telemetry_log_sink",
                    return_value=telemetry,
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
                    return_value=(
                        "beta-local external provider materialization failed: boom"
                    ),
                ),
                mock.patch.object(stackctl, "_write_summary_bundle"),
                mock.patch.object(stackctl, "relpath", side_effect=str),
                mock.patch.object(stackctl, "run") as run,
            ):
                result = stackctl.command_up(args)

        self.assertEqual(result["exitCode"], 2)
        self.assertIn(
            "external provider materialization failed",
            "\n".join(result["details"]),
        )
        run.assert_not_called()

    def test_beta_content_release_blocks_when_provider_materialization_fails(
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
                    return_value=(
                        "beta-local external provider materialization failed: boom"
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

        self.assertEqual(result["exitCode"], 2)
        self.assertIn(
            "external provider materialization failed",
            "\n".join(result["details"]),
        )
        run.assert_not_called()

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

    def test_gamma_external_provider_environment_materializes_local_substitutes(
        self,
    ) -> None:
        environment: dict[str, str] = {}
        storage = mock.Mock(
            environment={
                "LOCAL_GAMMA_OBJECT_STORAGE_ENDPOINT": "https://minio:19000",
                "LOCAL_GAMMA_OBJECT_STORAGE_CA_FILE": "/tmp/gamma-ca.crt",
            },
            host_endpoint="https://gamma-upload.quwoquan-env.test:19000",
        )
        values = {
            "CONTENT_EMBEDDING_FIXTURE_ENDPOINT": "http://fixture.local/embed",
            "CONTENT_EMBEDDING_FIXTURE_API_KEY": "fixture-key",
            "RTC_MEDIA_FIXTURE_CONNECTION_URL": "wss://fixture.local/rtc",
            "RTC_MEDIA_FIXTURE_API_KEY": "rtc-key",
            "RTC_MEDIA_FIXTURE_API_SECRET": "rtc-secret",
        }
        with (
            mock.patch.object(
                stackctl,
                "prepare_local_gamma_object_storage",
                return_value=storage,
            ),
            mock.patch.object(
                stackctl,
                "prepare_local_provider_credentials",
                return_value=values,
            ) as prepare,
        ):
            error = stackctl._bind_gamma_external_provider_environment(environment)

        self.assertIsNone(error)
        prepare.assert_called_once_with(
            environment="gamma",
            target_name="gamma-local",
        )
        self.assertEqual(
            environment["QWQ_COMPOSE_EMBEDDING_ENDPOINT"],
            values["CONTENT_EMBEDDING_FIXTURE_ENDPOINT"],
        )
        self.assertEqual(
            environment["CONTENT_OSS_ENDPOINT"],
            storage.environment["LOCAL_GAMMA_OBJECT_STORAGE_ENDPOINT"],
        )
        self.assertEqual(
            environment["CONTENT_OSS_CA_FILE"],
            storage.environment["LOCAL_GAMMA_OBJECT_STORAGE_CA_FILE"],
        )
        self.assertEqual(
            environment["QWQ_COMPOSE_OBJECT_STORAGE_ENDPOINT"],
            storage.environment["LOCAL_GAMMA_OBJECT_STORAGE_ENDPOINT"],
        )
        self.assertEqual(
            environment["LOCAL_GAMMA_MEDIA_UPLOAD_BASE_URL"],
            storage.host_endpoint,
        )
        self.assertIn("CONTENT_EMBEDDING_FIXTURE_API_KEY", environment)
        self.assertIn("RTC_MEDIA_FIXTURE_API_KEY", environment)
        self.assertNotIn("RTC_MEDIA_API_KEY", environment)
        self.assertEqual(environment["PRODUCT_OPS_SLS_ENDPOINT"], "")
        self.assertEqual(environment["ALIBABA_CLOUD_ACCESS_KEY_ID"], "")

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

    def test_gamma_full_workload_materializes_local_providers_before_packaging(
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
            with (
                mock.patch.dict(
                    os.environ,
                    {"QWQ_DEPLOY_WORK_ROOT": str(work_root)},
                    clear=False,
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
                mock.patch.object(
                    stackctl,
                    "load_product_telemetry_log_sink",
                    return_value=telemetry,
                ),
                mock.patch.object(
                    stackctl,
                    "_local_stack_operation_lock",
                    return_value=contextlib.nullcontext(),
                ),
                mock.patch.object(
                    stackctl,
                    "_bind_gamma_external_provider_environment",
                    return_value=None,
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
        self.assertTrue(
            any("package" in " ".join(argv) for argv in argv_calls)
            or any("start_local_gamma_mirror" in " ".join(argv) for argv in argv_calls)
        )
        bind_external_provider.assert_called_once()

    def test_gamma_content_release_blocks_when_provider_materialization_fails(
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
            "materialization failed",
            "\n".join(result["details"]),
        )
        bind_external_provider.assert_called_once()

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
