"""场景：gamma down 只信 runtime receipt——parse 输入、精确 composition、
prepared/stopped 受限拆除、receipt candidate 加载与漂移/跨环境拒绝。"""

from __future__ import annotations

import argparse
import contextlib
import inspect
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
    def test_gamma_down_parse_inputs_do_not_synthesize_image_identity(self) -> None:
        environment: dict[str, str] = {}

        stackctl._bind_gamma_down_parse_environment(environment)

        for suffix in (
            "ENDPOINT",
            "BUCKET",
            "REGION",
            "ACCESS_KEY_ID",
            "ACCESS_KEY_SECRET",
            "CDN_SIGN_KEY",
            "TLS_DIR",
        ):
            source = environment[f"LOCAL_GAMMA_OBJECT_STORAGE_{suffix}"]
            alias = environment[f"QWQ_COMPOSE_OBJECT_STORAGE_{suffix}"]
            self.assertTrue(source)
            self.assertEqual(alias, source)
        self.assertNotIn("LOCAL_GAMMA_IMAGE_VERSION", environment)
        self.assertNotIn("QWQ_COMPOSE_IMAGE_VERSION", environment)
        self.assertEqual(environment["RTC_MEDIA_API_KEY"], "down-not-used")
        self.assertEqual(environment["RTC_MEDIA_API_SECRET"], "down-not-used")
        for service, local_key in stackctl.GAMMA_PACKAGED_SERVICE_IMAGE_ENVIRONMENTS:
            self.assertNotIn(local_key, environment, service)
            self.assertNotIn(
                stackctl.compose_image_environment_key(service),
                environment,
                service,
            )

    def test_gamma_down_runtime_receipt_preserves_exact_started_composition(
        self,
    ) -> None:
        refs = {
            service: self._packaged_service_source_ref(service, f"{index:064x}")
            for index, (service, _) in enumerate(
                stackctl.GAMMA_PACKAGED_SERVICE_IMAGE_ENVIRONMENTS,
                start=1,
            )
        }
        version = stackctl.immutable_image_digest(refs)
        full_refs = {
            **refs,
            "provider-protocol-substitute": "sha256:" + "e" * 64,
        }
        transport_tag = stackctl.immutable_image_digest(full_refs)
        configuration_digest = "sha256:" + "f" * 64
        composition = {
            "imageVersion": transport_tag,
            "images": {
                service: {"ref": ref}
                for service, ref in full_refs.items()
            },
        }
        receipt = {
            "schema": "stackctl-local-startup-attempt",
            "status": "running",
            "target": "gamma-local",
            "env": "gamma",
            "composeProject": "quwoquan_gamma_release_current_1",
            "configurationDigest": configuration_digest,
            "imageTransportTag": transport_tag,
            "imageComposition": composition,
        }
        with mock.patch.object(
            stackctl,
            "load_startup_attempt",
            return_value=receipt,
        ):
            loaded = stackctl._load_gamma_runtime_image_composition("gamma-local")

        expected_composition = {
            "imageVersion": version,
            "images": {
                service: {"ref": ref, "digest": ref}
                for service, ref in refs.items()
            },
            "configurationDigest": configuration_digest,
        }
        self.assertEqual(
            loaded,
            (expected_composition, "quwoquan_gamma_release_current_1"),
        )
        self.assertNotIn(
            "provider-protocol-substitute",
            expected_composition["images"],
        )

    def test_prepared_attempt_down_skips_provider_compose_colima_and_app(self) -> None:
        prepared = {
            "status": "prepared",
            "workload": "full",
            "attemptId": "attempt-prepared",
        }
        environment = {
            "QWQ_LOCAL_RELEASE_ENV": "gamma",
            "QWQ_LOCAL_RELEASE_TARGET": "gamma-local",
            "LOCAL_GAMMA_COMPOSE_PROJECT_NAME": "quwoquan_gamma_release_test",
        }
        with tempfile.TemporaryDirectory() as temporary_dir:
            report_dir = Path(temporary_dir) / "report"
            with (
                mock.patch.dict(
                    os.environ,
                    {stackctl.PACKAGE_ROOT_OVERRIDE_ENV: "/staging/poison"},
                    clear=False,
                ),
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
                    "_local_stack_operation_lock",
                    return_value=contextlib.nullcontext(),
                ),
                mock.patch.object(
                    stackctl,
                    "active_consumer_leases",
                    return_value=[],
                ),
                mock.patch.object(
                    stackctl,
                    "_gamma_env_from_port_manifest",
                    return_value=environment,
                ),
                mock.patch.object(
                    stackctl,
                    "load_startup_attempt",
                    return_value=prepared,
                ),
                mock.patch.object(
                    stackctl,
                    "_active_provider_runtime",
                ) as active_provider,
                mock.patch.object(
                    stackctl,
                    "_active_observability_log_sink",
                ) as active_observability,
                mock.patch.object(
                    stackctl,
                    "_load_gamma_runtime_image_composition",
                ) as load_runtime_composition,
                mock.patch.object(
                    stackctl,
                    "_bind_gamma_packaged_service_image_refs",
                ) as bind_package_composition,
                mock.patch.object(stackctl, "_bind_gamma_down_parse_environment"),
                mock.patch.object(
                    stackctl,
                    "run",
                    return_value=CompletedProcess([], 0, stdout="", stderr=""),
                ) as run,
                mock.patch.object(
                    stackctl,
                    "_wait_for_network_ports_released",
                ) as wait_for_ports,
                mock.patch.object(
                    stackctl,
                    "transition_startup_attempt",
                    return_value={"status": "stopped"},
                ),
                mock.patch.object(stackctl, "_write_summary_bundle"),
            ):
                result = stackctl.command_down(
                    argparse.Namespace(target="gamma-local", report_dir="")
                )

        self.assertEqual(result["exitCode"], 0, result)
        self.assertEqual(len(run.call_args_list), 1)
        self.assertEqual(
            run.call_args.args[0],
            [
                "bash",
                "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh",
                "--down",
            ],
        )
        self.assertEqual(
            run.call_args.kwargs["env"]["QWQ_PREPARED_ATTEMPT_ONLY"],
            "1",
        )
        self.assertEqual(
            run.call_args.kwargs["env"][stackctl.PACKAGE_ROOT_OVERRIDE_ENV],
            "",
        )
        active_provider.assert_not_called()
        active_observability.assert_not_called()
        load_runtime_composition.assert_not_called()
        bind_package_composition.assert_not_called()
        wait_for_ports.assert_not_called()

        script = Path(
            "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"
        ).read_text(encoding="utf-8")
        down_block = script.split('if [[ "$down" == "1" ]]; then', 1)[1].split(
            "prepare_config_root",
            1,
        )[0]
        self.assertLess(
            down_block.index("QWQ_PREPARED_ATTEMPT_ONLY"),
            down_block.index("stop_colima_tunnels"),
        )
        self.assertLess(
            down_block.index("QWQ_PREPARED_ATTEMPT_ONLY"),
            down_block.index("docker compose"),
        )

    def test_missing_or_stopped_receipt_never_executes_local_teardown(self) -> None:
        for receipt in (None, {"status": "stopped", "workload": "full"}):
            with self.subTest(receipt=receipt), tempfile.TemporaryDirectory() as temporary_dir:
                report_dir = Path(temporary_dir) / "report"
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
                        "_local_stack_operation_lock",
                        return_value=contextlib.nullcontext(),
                    ),
                    mock.patch.object(
                        stackctl,
                        "active_consumer_leases",
                        return_value=[],
                    ),
                    mock.patch.object(
                        stackctl,
                        "_gamma_env_from_port_manifest",
                        return_value={
                            "QWQ_LOCAL_RELEASE_ENV": "gamma",
                            "QWQ_LOCAL_RELEASE_TARGET": "gamma-local",
                        },
                    ),
                    mock.patch.object(
                        stackctl,
                        "load_startup_attempt",
                        return_value=receipt,
                    ),
                    mock.patch.object(
                        stackctl,
                        "_candidate_provider_runtime",
                    ) as candidate_provider,
                    mock.patch.object(
                        stackctl,
                        "_candidate_observability_log_sink",
                    ) as candidate_observability,
                    mock.patch.object(stackctl, "run") as run,
                    mock.patch.object(stackctl, "_write_summary_bundle"),
                ):
                    result = stackctl.command_down(
                        argparse.Namespace(target="gamma-local", report_dir="")
                    )

            self.assertEqual(result["exitCode"], 2, result)
            self.assertIn(
                "non-stopped canonical startup receipt",
                "\n".join(result["details"]),
            )
            candidate_provider.assert_not_called()
            candidate_observability.assert_not_called()
            run.assert_not_called()

    def test_teardown_loads_provider_and_es_from_receipt_candidate(self) -> None:
        receipt_candidate = "sha256:" + "1" * 64
        switched_active_candidate = "sha256:" + "2" * 64
        provider_digest = "sha256:" + "3" * 64
        observability_digest = "sha256:" + "4" * 64
        attempt = {
            "status": "running",
            "workload": "full",
            "candidateDigest": receipt_candidate,
            "providerRuntimeDigest": provider_digest,
            "observabilityLogSinkDigest": observability_digest,
        }
        runtime_composition = {
            "imageVersion": "sha256:" + "5" * 64,
            "images": {"api-edge": {"ref": "sha256:" + "6" * 64}},
            "configurationDigest": "sha256:" + "7" * 64,
        }
        environment: dict[str, str] = {}
        with tempfile.TemporaryDirectory() as temporary_dir:
            candidate_root = (Path(temporary_dir) / "receipt-candidate").resolve()
            provider_binding = {
                "candidateRoot": candidate_root,
                "providerRuntime": {"composition": {}},
            }
            observability_binding = {
                "candidateRoot": candidate_root,
                "composition": {},
            }
            with (
                mock.patch.object(
                    stackctl,
                    "load_startup_attempt",
                    return_value=attempt,
                ),
                mock.patch.object(
                    stackctl,
                    "active_deployment_candidate",
                    return_value={"baselineId": switched_active_candidate},
                ) as active_candidate,
                mock.patch.object(
                    stackctl,
                    "load_candidate_manifest",
                    return_value={"baselineId": receipt_candidate},
                ),
                mock.patch.object(
                    stackctl,
                    "deployment_candidate_dir",
                    return_value=candidate_root,
                ),
                mock.patch.object(
                    stackctl,
                    "_candidate_provider_runtime",
                    return_value=provider_binding,
                ) as candidate_provider,
                mock.patch.object(
                    stackctl,
                    "_provider_runtime_launch_environment",
                    return_value={"QWQ_PROVIDER_RUNTIME_DIGEST": provider_digest},
                ),
                mock.patch.object(
                    stackctl,
                    "_candidate_observability_log_sink",
                    return_value=observability_binding,
                ) as candidate_observability,
                mock.patch.object(
                    stackctl,
                    "_observability_log_sink_launch_environment",
                    return_value={
                        "QWQ_OBSERVABILITY_LOG_SINK_DIGEST": observability_digest
                    },
                ),
                mock.patch.object(
                    stackctl,
                    "_load_gamma_runtime_image_composition",
                    return_value=(runtime_composition, "quwoquan_gamma_release_old"),
                ),
                mock.patch.object(stackctl, "_apply_gamma_image_composition"),
            ):
                bound = stackctl._bind_local_teardown_runtime(
                    env_name="gamma",
                    target_name="gamma-local",
                    environment=environment,
                    purge_rebuildable_state=False,
                )

        self.assertEqual(
            bound,
            (
                runtime_composition,
                "runtime-receipt",
                "quwoquan_gamma_release_old",
                False,
            ),
        )
        candidate_provider.assert_called_once_with(
            "gamma",
            "gamma-local",
            receipt_candidate,
            candidate_manifest={"baselineId": receipt_candidate},
            candidate_root=candidate_root,
        )
        candidate_observability.assert_called_once_with(
            "gamma",
            "gamma-local",
            receipt_candidate,
            candidate_manifest={"baselineId": receipt_candidate},
            candidate_root=candidate_root,
        )
        active_candidate.assert_not_called()
        self.assertNotEqual(receipt_candidate, switched_active_candidate)

    def test_missing_receipt_candidate_blocks_without_active_fallback(self) -> None:
        receipt_candidate = "sha256:" + "1" * 64
        attempt = {
            "status": "partial",
            "workload": "full",
            "candidateDigest": receipt_candidate,
            "providerRuntimeDigest": "sha256:" + "2" * 64,
            "observabilityLogSinkDigest": "sha256:" + "3" * 64,
        }
        with tempfile.TemporaryDirectory() as temporary_dir:
            candidate_root = (Path(temporary_dir) / "receipt-candidate").resolve()
            candidate_manifest = {"baselineId": receipt_candidate}
            with (
                mock.patch.object(
                    stackctl,
                    "load_startup_attempt",
                    return_value=attempt,
                ),
                mock.patch.object(
                    stackctl,
                    "load_candidate_manifest",
                    return_value=candidate_manifest,
                ),
                mock.patch.object(
                    stackctl,
                    "deployment_candidate_dir",
                    return_value=candidate_root,
                ),
                mock.patch.object(
                    stackctl,
                    "_candidate_provider_runtime",
                    side_effect=ValueError("receipt candidate package is missing"),
                ) as candidate_provider,
                mock.patch.object(
                    stackctl,
                    "active_deployment_candidate",
                    return_value={"baselineId": "sha256:" + "9" * 64},
                ) as active_candidate,
                mock.patch.object(
                    stackctl,
                    "_candidate_observability_log_sink",
                ) as candidate_observability,
                self.assertRaisesRegex(
                    ValueError,
                    "receipt candidate package is missing",
                ),
            ):
                stackctl._bind_local_teardown_runtime(
                    env_name="gamma",
                    target_name="gamma-local",
                    environment={},
                    purge_rebuildable_state=False,
                )

        candidate_provider.assert_called_once_with(
            "gamma",
            "gamma-local",
            receipt_candidate,
            candidate_manifest=candidate_manifest,
            candidate_root=candidate_root,
        )
        candidate_observability.assert_not_called()
        active_candidate.assert_not_called()

    def test_gamma_down_rejects_runtime_receipt_from_other_environment_project(
        self,
    ) -> None:
        receipt = {
            "schema": "stackctl-local-startup-attempt",
            "status": "running",
            "target": "gamma-local",
            "env": "gamma",
            "composeProject": "quwoquan_beta_release_old_1",
            "configurationDigest": "sha256:" + "f" * 64,
            "imageTransportTag": "unused",
            "imageComposition": {"images": {}},
        }
        with (
            mock.patch.object(
                stackctl,
                "load_startup_attempt",
                return_value=receipt,
            ),
            self.assertRaisesRegex(ValueError, "Compose project mismatch"),
        ):
            stackctl._load_gamma_runtime_image_composition("gamma-local")

    def test_stopped_attempt_does_not_fall_back_to_environment_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            process_dir = Path(temporary_dir)
            (process_dir / "stack_status.json").write_text(
                '{"status":"passed","runtimeEnv":"alpha"}',
                encoding="utf-8",
            )
            with mock.patch.object(
                stackctl,
                "load_startup_attempt",
                return_value={
                    "schema": "stackctl-local-startup-attempt",
                    "status": "stopped",
                    "target": "alpha-local",
                    "env": "alpha",
                },
            ):
                loaded = stackctl._load_gamma_runtime_image_composition(
                    "alpha-local"
                )

        self.assertIsNone(loaded)

    def test_runtime_composition_loader_has_no_environment_receipt_fallback(
        self,
    ) -> None:
        source = inspect.getsource(stackctl._load_gamma_runtime_image_composition)

        self.assertNotIn("stack_status.json", source)
        self.assertNotIn("runtimeEnv", source)
        self.assertNotIn("startup_attempt_path", source)

    def test_gamma_down_rejects_drifted_runtime_receipt(self) -> None:
        receipt = {
            "schema": "stackctl-local-startup-attempt",
            "status": "running",
            "target": "gamma-local",
            "env": "gamma",
            "composeProject": "quwoquan_gamma_release_current_1",
            "configurationDigest": "sha256:" + "f" * 64,
            "imageTransportTag": "0.1.2",
            "imageComposition": {
                "imageVersion": "0.1.2",
                "images": {},
            },
        }
        with (
            mock.patch.object(
                stackctl,
                "load_startup_attempt",
                return_value=receipt,
            ),
            self.assertRaisesRegex(ValueError, "composition is missing"),
        ):
            stackctl._load_gamma_runtime_image_composition("gamma-local")

    def test_gamma_down_projects_receipt_bindings_before_interpolation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            report_dir = Path(temporary_dir)
            compose_environment = {"GAMMA_PORT": "19000"}

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
                    "load_startup_attempt",
                    return_value=self._running_attempt("gamma"),
                ),
                mock.patch.object(
                    stackctl,
                    "_provider_runtime_launch_environment",
                    return_value=self._provider_runtime_environment("gamma"),
                ),
                mock.patch.object(
                    stackctl,
                    "_load_gamma_runtime_image_composition",
                    return_value=(
                        {
                            "imageVersion": "sha256:" + "1" * 64,
                            "images": {"api-edge": {"ref": "sha256:" + "2" * 64}},
                            "configurationDigest": "sha256:" + "3" * 64,
                        },
                        "quwoquan_gamma_release_receipt",
                    ),
                ),
                mock.patch.object(
                    stackctl,
                    "_bind_gamma_packaged_service_image_refs",
                ) as bind_package_composition,
                mock.patch.object(
                    stackctl,
                    "_apply_gamma_image_composition",
                    side_effect=lambda _composition, environment: environment.update(
                        {
                            "LOCAL_GAMMA_IMAGE_VERSION": "sha256:" + "1" * 64,
                            "QWQ_COMPOSE_IMAGE_VERSION": "sha256:" + "1" * 64,
                        }
                    ),
                ) as apply_composition,
                mock.patch.object(
                    stackctl,
                    "_bind_gamma_down_parse_environment",
                    side_effect=lambda environment: environment.update(
                        {"QWQ_COMPOSE_OBJECT_STORAGE_ACCESS_KEY_ID": "unused"}
                    ),
                ) as bind_environment,
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
                mock.patch.object(stackctl, "_write_summary_bundle"),
            ):
                result = stackctl.command_down(
                    argparse.Namespace(
                        target="gamma-local",
                        report_dir="",
                    )
                )

        self.assertEqual(result["exitCode"], 0)
        bind_package_composition.assert_not_called()
        apply_composition.assert_called_once()
        bind_environment.assert_called_once_with(compose_environment)
        self.assertEqual(
            run.call_args_list[0].kwargs["env"][
                "QWQ_COMPOSE_OBJECT_STORAGE_ACCESS_KEY_ID"
            ],
            "unused",
        )
