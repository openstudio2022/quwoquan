from __future__ import annotations

import argparse
import contextlib
import inspect
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib.provider_runtime_composition import (
    compile_provider_runtime_composition,
)


class StackctlGammaOperationLockContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.provider_compositions = {
            environment: compile_provider_runtime_composition(
                environment=environment,
                target=f"{environment}-local",
            )
            for environment in ("alpha", "beta", "gamma")
        }

    def _provider_runtime_binding(
        self,
        environment: str,
        candidate_root: Path,
    ) -> dict[str, object]:
        composition = self.provider_compositions[environment]
        return {
            "candidateRoot": candidate_root,
            "providerRuntime": {"composition": composition},
            "composition": composition,
        }

    def _provider_runtime_environment(self, environment: str) -> dict[str, str]:
        return {
            "QWQ_PROVIDER_RUNTIME_DIGEST": str(
                self.provider_compositions[environment][
                    "runtimeCompositionDigest"
                ]
            ),
            "QWQ_PROVIDER_RUNTIME_COMPOSE_FILES": "",
            "QWQ_PROVIDER_RUNTIME_COMPOSE_DIGESTS": "",
            "QWQ_PROVIDER_RUNTIME_COMPOSE_PROFILES": "",
        }

    def _observability_runtime_binding(
        self,
        environment: str,
        candidate_root: Path,
    ) -> dict[str, object]:
        digest = "sha256:" + "a" * 64
        target = f"{environment}-local"
        composition = {
            "schema": "stackctl-observability-log-sink-package",
            "adapterId": "ext.obs.elasticsearch",
            "bindingDigest": digest,
            "endpointRef": f"local_topology:{environment}.elasticsearch",
            "endpointEnvironmentKey": "PRODUCT_OPS_ELASTICSEARCH_ENDPOINT",
            "secretEnvironmentKeys": [],
            "deploymentMode": "package-bound-local",
            "platform": "arm64",
            "runtimeEndpoint": "http://elasticsearch:9200",
            "imageDigest": digest,
            "sourceComposeDigest": digest,
            "composeRef": (
                "packages/runtime-shared/observability-log-sink/"
                "elasticsearch.compose.yaml"
            ),
            "composeDigest": digest,
            "clusterRef": f"target:{target}/product-ops/elasticsearch",
        }
        return {
            "candidateRoot": candidate_root,
            "composition": composition,
        }

    def _observability_runtime_environment(self) -> dict[str, str]:
        return {
            "QWQ_OBSERVABILITY_LOG_SINK_COMPOSE_FILE": "/candidate/elasticsearch.compose.yaml",
            "QWQ_OBSERVABILITY_LOG_SINK_DIGEST": "sha256:" + "a" * 64,
            "PRODUCT_OPS_ELASTICSEARCH_ENDPOINT": "http://elasticsearch:9200",
        }

    def _running_attempt(self, environment: str) -> dict[str, object]:
        image_composition = {
            "configurationDigest": "sha256:" + "d" * 64,
            "buildInputDigest": "sha256:" + "e" * 64,
            "imageDigest": "sha256:" + "f" * 64,
            "imageVersion": "sha256:" + "1" * 64,
            "images": {"api-edge": {"ref": "sha256:" + "2" * 64}},
            "ociImages": {
                "api-edge": {
                    "ref": "quwoquan/api-edge:build",
                    "imageDigest": "sha256:" + "2" * 64,
                }
            },
        }
        return {
            "status": "running",
            "env": environment,
            "target": f"{environment}-local",
            "workload": "full",
            "attemptId": f"attempt-{environment}",
            "candidateDigest": "sha256:" + "c" * 64,
            "configurationDigest": image_composition["configurationDigest"],
            "providerRuntimeDigest": str(
                self.provider_compositions[environment][
                    "runtimeCompositionDigest"
                ]
            ),
            "observabilityLogSinkDigest": "sha256:" + "a" * 64,
            "imageComposition": image_composition,
        }

    def _candidate_snapshot(self, environment: str) -> dict[str, object]:
        target = f"{environment}-local"
        baseline_id = "sha256:" + "c" * 64
        candidate_root = stackctl.deployment_candidate_dir(target, baseline_id)
        return {
            "schema": "stackctl-active-deployment-candidate",
            "candidateType": "runtime-full",
            "target": target,
            "baselineId": baseline_id,
            "candidateDir": str(candidate_root),
            "manifest": {
                "environment": environment,
                "target": target,
                "baselineId": baseline_id,
            },
        }

    def setUp(self) -> None:
        self.deploy_root = tempfile.TemporaryDirectory()
        self.addCleanup(self.deploy_root.cleanup)
        deploy_root = Path(self.deploy_root.name).resolve()
        environment = mock.patch.dict(
            os.environ,
            {
                "QWQ_DEPLOY_WORK_ROOT": str(deploy_root / "deploy"),
                "QWQ_OUTPUT_ROOT": str(deploy_root / "output"),
            },
        )
        environment.start()
        self.addCleanup(environment.stop)
        availability = mock.patch.object(
            stackctl,
            "assert_local_runtime_available",
        )
        self.availability = availability.start()
        self.addCleanup(availability.stop)
        package_reuse = mock.patch.object(
            stackctl,
            "can_reuse_package",
            return_value=(True, "fixed candidate ready"),
        )
        self.package_reuse = package_reuse.start()
        self.addCleanup(package_reuse.stop)
        candidate_snapshot = mock.patch.object(
            stackctl,
            "active_deployment_candidate_snapshot",
            side_effect=lambda target: self._candidate_snapshot(
                target.removesuffix("-local")
            ),
        )
        candidate_snapshot.start()
        self.addCleanup(candidate_snapshot.stop)
        snapshot_check = mock.patch.object(
            stackctl,
            "assert_active_deployment_candidate_snapshot",
        )
        snapshot_check.start()
        self.addCleanup(snapshot_check.stop)
        fixed_runtime_identity = mock.patch.object(
            stackctl,
            "_fixed_candidate_runtime_identity",
            side_effect=lambda _snapshot, *, environment_name, target_name: {
                field: self._running_attempt(environment_name)[field]
                for field in (
                    "candidateDigest",
                    "configurationDigest",
                    "providerRuntimeDigest",
                    "observabilityLogSinkDigest",
                    "imageComposition",
                )
            },
        )
        fixed_runtime_identity.start()
        self.addCleanup(fixed_runtime_identity.stop)
        tls = mock.patch.object(
            stackctl,
            "tls_profile",
            return_value=("local-managed", "local-managed", {}),
        )
        tls.start()
        self.addCleanup(tls.stop)
        certificate = mock.patch.object(
            stackctl,
            "verify_certificate",
            return_value={"target": "local", "status": "ready"},
        )
        certificate.start()
        self.addCleanup(certificate.stop)
        handoff = mock.patch.object(
            stackctl,
            "materialize_handoff",
            return_value={"target": "local", "status": "ready"},
        )
        handoff.start()
        self.addCleanup(handoff.stop)
        active_observability = mock.patch.object(
            stackctl,
            "_active_observability_log_sink",
            side_effect=lambda environment_name, _target_name: (
                self._observability_runtime_binding(
                    environment_name,
                    Path(self.deploy_root.name),
                )
            ),
        )
        active_observability.start()
        self.addCleanup(active_observability.stop)
        observability_environment = mock.patch.object(
            stackctl,
            "_observability_log_sink_launch_environment",
            return_value=self._observability_runtime_environment(),
        )
        observability_environment.start()
        self.addCleanup(observability_environment.stop)
        startup_attempt = mock.patch.object(
            stackctl,
            "load_startup_attempt",
            return_value=None,
        )
        startup_attempt.start()
        self.addCleanup(startup_attempt.stop)
        candidate_provider = mock.patch.object(
            stackctl,
            "_candidate_provider_runtime",
            side_effect=lambda environment_name, _target_name, _candidate_digest, **_kwargs: (
                self._provider_runtime_binding(
                    environment_name,
                    Path(self.deploy_root.name).resolve(),
                )
            ),
        )
        candidate_provider.start()
        self.addCleanup(candidate_provider.stop)
        candidate_observability = mock.patch.object(
            stackctl,
            "_candidate_observability_log_sink",
            side_effect=lambda environment_name, _target_name, _candidate_digest, **_kwargs: (
                self._observability_runtime_binding(
                    environment_name,
                    Path(self.deploy_root.name).resolve(),
                )
            ),
        )
        candidate_observability.start()
        self.addCleanup(candidate_observability.stop)
        transition = mock.patch.object(
            stackctl,
            "transition_startup_attempt",
            return_value={"status": "stopped"},
        )
        transition.start()
        self.addCleanup(transition.stop)

    def test_bounded_content_workloads_do_not_materialize_unrelated_providers(
        self,
    ) -> None:
        auth = mock.Mock(environment={"AUTH_JWT_SECRET": "protected"})
        storage = mock.Mock(
            environment={"LOCAL_GAMMA_OBJECT_STORAGE_BUCKET": "alpha-bucket"},
            host_endpoint="https://upload.alpha.quwoquan.com:17100",
        )
        integration_mtls = mock.Mock(
            environment={
                "INTEGRATION_SERVICE_MTLS_CA_FILE": "/protected/ca.crt",
                "INTEGRATION_SERVICE_MTLS_CLIENT_CERT_FILE": "/protected/client.crt",
                "INTEGRATION_SERVICE_MTLS_CLIENT_KEY_FILE": "/protected/client.key",
            }
        )
        topology = {
            "targets": {
                "alpha-local": {
                    "portProfile": "alpha-local",
                    "publicBases": {
                        "mediaImage": "https://cdn.alpha.quwoquan.com:17100/media/image",
                        "mediaUpload": "https://upload.alpha.quwoquan.com:17100/media/upload",
                    },
                }
            }
        }
        for workload in ("content-release", "content-commercial"):
            environment: dict[str, str] = {}
            with self.subTest(workload=workload):
                with (
                    mock.patch.object(
                        stackctl,
                        "prepare_local_environment_auth",
                        return_value=auth,
                    ),
                    mock.patch.object(
                        stackctl,
                        "prepare_local_environment_object_storage",
                        return_value=storage,
                    ),
                    mock.patch.object(
                        stackctl,
                        "prepare_local_integration_service_mtls",
                        return_value=integration_mtls,
                    ),
                    mock.patch.object(
                        stackctl,
                        "load_environment_topology",
                        return_value=topology,
                    ),
                    mock.patch.object(stackctl, "load_port_manifest", return_value={}),
                    mock.patch.object(
                        stackctl,
                        "profile_ports",
                        return_value={"object-storage-edge": 17100},
                    ),
                    mock.patch.object(stackctl, "_sync_object_storage_binding_aliases"),
                    mock.patch.object(
                        stackctl,
                        "_bind_local_external_provider_environment",
                    ) as bind_external,
                ):
                    error = stackctl._bind_formal_local_release_provider_environment(
                        environment,
                        environment_name="alpha",
                        target_name="alpha-local",
                        workload=workload,
                        runtime_composition=self.provider_compositions["alpha"],
                    )

                self.assertIsNone(error)
                self.assertEqual(environment["AUTH_JWT_SECRET"], "protected")
                self.assertEqual(
                    environment["INTEGRATION_SERVICE_MTLS_CA_FILE"],
                    "/protected/ca.crt",
                )
                bind_external.assert_not_called()

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
            service: (
                f"localhost/quwoquan_service_{service.replace('-', '_')}:"
                + f"{index:064x}"
            )
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
            candidate_root = Path(temporary_dir) / "receipt-candidate"
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
        )
        candidate_observability.assert_called_once_with(
            "gamma",
            "gamma-local",
            receipt_candidate,
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
        with (
            mock.patch.object(
                stackctl,
                "load_startup_attempt",
                return_value=attempt,
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
            self.assertRaisesRegex(ValueError, "receipt candidate package is missing"),
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

    def test_reclaim_build_cache_accepts_failed_pre_inventory_after_recovery(
        self,
    ) -> None:
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
            "gamma-local unused Docker build cache reclaimed",
        )

    def test_reclaim_build_cache_is_available_from_each_local_target(self) -> None:
        for target in ("alpha-local", "beta-local", "gamma-local"):
            args = argparse.Namespace(
                target=target,
                fix="reclaim-build-cache",
                report_dir="",
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
                mock.patch.object(stackctl, "run") as run,
            ):
                run.side_effect = [
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
                f"{target} unused Docker build cache reclaimed",
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

    def test_alpha_full_workload_requires_fixed_package_without_reading_run_state(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            report_dir = Path(temporary_dir) / "report"
            telemetry = mock.Mock(environment={})
            telemetry.redacted_receipt.return_value = {
                "source": "test",
                "status": "ready",
                "redactedDigest": "sha256:" + "a" * 64,
            }
            args = argparse.Namespace(
                env="alpha",
                target=None,
                workload="full",
                skip_app=True,
                skip_build=True,
                formal_release=False,
                release_manifest="",
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
                    "can_reuse_package",
                    return_value=(False, "candidate fingerprint mismatch"),
                ),
                mock.patch.object(
                    stackctl,
                    "probe_migration_drift",
                    return_value=mock.Mock(has_drift=False),
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
                    "_local_runtime_log_root",
                    side_effect=AssertionError(
                        "unsupported workload must not read local run state"
                    ),
                ),
                mock.patch.object(stackctl, "_write_summary_bundle"),
                mock.patch.object(stackctl, "relpath", side_effect=str),
                mock.patch.object(stackctl, "run") as run,
            ):
                result = stackctl.command_up(args)

        self.assertEqual(result["exitCode"], 2)
        self.assertIn(
            "candidate fingerprint mismatch",
            "\n".join(result["details"]),
        )
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
                    side_effect=RuntimeError(
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

    def test_beta_external_provider_environment_binds_substitute_topology(self) -> None:
        environment: dict[str, str] = {}
        values = {
            "CONTENT_EMBEDDING_ENDPOINT": (
                "https://provider-protocol-substitute:18089/v1/embeddings"
            ),
        }
        with (
            mock.patch.object(
                stackctl,
                "_active_provider_runtime",
                return_value=self._provider_runtime_binding(
                    "beta", Path(self.deploy_root.name)
                ),
            ),
            mock.patch.object(
                stackctl,
                "load_nonprod_provider_environment",
                return_value=values,
            ),
        ):
            error = stackctl._bind_beta_external_provider_environment(environment)

        self.assertIsNone(error)
        self.assertIn("CONTENT_EMBEDDING_ENDPOINT", environment)
        self.assertEqual(
            environment["QWQ_COMPOSE_EMBEDDING_ENDPOINT"],
            values["CONTENT_EMBEDDING_ENDPOINT"],
        )
        self.assertNotIn("QWQ_COMPOSE_EMBEDDING_API_KEY", environment)

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
                    "_active_provider_runtime",
                    return_value=self._provider_runtime_binding(
                        "beta", Path(temporary_dir)
                    ),
                ),
                mock.patch.object(
                    stackctl,
                    "_provider_runtime_launch_environment",
                    return_value=self._provider_runtime_environment("beta"),
                ),
                mock.patch.object(
                    stackctl,
                    "_bind_formal_local_release_provider_environment",
                    return_value=(
                        "beta-local external provider materialization failed: boom"
                    ),
                ),
                mock.patch.object(stackctl, "_write_summary_bundle"),
                mock.patch.object(stackctl, "relpath", side_effect=str),
                mock.patch.object(
                    stackctl,
                    "run",
                    return_value=CompletedProcess([], 0, "", ""),
                ) as run,
            ):
                result = stackctl.command_up(args)

        self.assertEqual(result["exitCode"], 2)
        self.assertIn(
            "external provider materialization failed",
            "\n".join(result["details"]),
        )
        run.assert_called_once()

    def test_beta_content_release_blocks_when_provider_materialization_fails(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            report_dir = Path(temporary_dir) / "report"
            provider_composition = {
                "runtimeCompositionDigest": "sha256:" + "8" * 64
            }
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
                    return_value=(
                        "beta-local external provider materialization failed: boom"
                    ),
                ) as bind_release_providers,
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
        bind_release_providers.assert_called_once_with(
            mock.ANY,
            environment_name="beta",
            target_name="beta-local",
            workload="content-release",
            runtime_composition=provider_composition,
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

    def test_package_reuses_one_source_digest_image_set_across_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            shared = root / "runtime-shared"
            shared.mkdir()
            composition = {
                "imageVersion": "sha256:" + "b" * 64,
                "configurationDigest": "sha256:" + "c" * 64,
                "images": {
                    "api-edge": {"ref": "localhost/api-edge:source"},
                    "user-service": {"ref": "localhost/user-service:source"},
                },
            }
            provider_digest = "sha256:" + "d" * 64
            provider_build_digest = "sha256:" + "e" * 64
            provider_images = {
                "provider-runtime": {
                    "buildInputDigest": provider_build_digest,
                    "ref": (
                        "quwoquan/provider-runtime-provider-runtime:"
                        + provider_build_digest.removeprefix("sha256:")
                    ),
                    "imageDigest": "sha256:" + "f" * 64,
                }
            }
            provider_runtime = {
                "composition": {"runtimeCompositionDigest": provider_digest},
                "images": {},
            }

            def inspect_only(
                argv: list[str],
                *,
                env: dict[str, str] | None = None,
            ) -> CompletedProcess[str]:
                del env
                self.assertEqual(argv[:4], ["docker", "image", "inspect", "--format"])
                digest = "1" if "api-edge" in argv[-1] else "2"
                return CompletedProcess(argv, 0, f"sha256:{digest * 64}\n", "")

            with (
                mock.patch.object(stackctl, "load_environment_topology", return_value={}),
                mock.patch.object(stackctl, "_gamma_env_from_port_manifest", return_value={}),
                mock.patch.object(
                    stackctl,
                    "_provider_runtime_launch_environment",
                    return_value={},
                ),
                mock.patch.object(stackctl, "_bind_gamma_down_parse_environment"),
                mock.patch.object(stackctl, "_sync_object_storage_binding_aliases"),
                mock.patch.object(stackctl, "_bind_package_provider_reference_environment"),
                mock.patch.object(
                    stackctl,
                    "_bind_gamma_build_service_image_refs",
                    return_value=composition,
                ),
                mock.patch.object(
                    stackctl,
                    "_build_provider_runtime_images",
                    return_value=provider_images,
                ),
                mock.patch.object(
                    stackctl,
                    "seal_provider_runtime_package_images",
                    return_value={
                        "composition": {
                            "runtimeCompositionDigest": provider_digest
                        },
                        "images": provider_images,
                    },
                ),
                mock.patch.object(stackctl, "target_cache_dir", return_value=root / "cache"),
                mock.patch.object(
                    stackctl,
                    "runtime_shared_deployment_package_dir",
                    return_value=shared,
                ),
                mock.patch.object(stackctl, "run", side_effect=inspect_only) as run,
            ):
                _, manifest = stackctl._build_package_bound_local_images(
                    "alpha",
                    "alpha-local",
                    report_dir=root / "report",
                    provider_runtime=provider_runtime,
                    observability_log_sink=(
                        self._observability_runtime_binding("alpha", root)[
                            "composition"
                        ]
                    ),
                    candidate_root=root,
                )

        self.assertEqual(run.call_count, 2)
        self.assertRegex(manifest["buildInputDigest"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(
            set(manifest["images"]),
            {"api-edge", "user-service", "provider-runtime"},
        )

    def test_provider_image_tag_changes_with_complete_build_context(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir).resolve()
            provider_root = root / "provider"
            deploy = provider_root / "deploy"
            deploy.mkdir(parents=True)
            dockerfile = deploy / "Dockerfile"
            dockerfile.write_text("FROM ${GO_BASE_IMAGE}\n", encoding="utf-8")
            source = provider_root / "main.go"
            source.write_text("package main\n", encoding="utf-8")
            compose = deploy / "compose.yaml"
            compose.write_text(
                "services:\n"
                "  provider-runtime:\n"
                "    image: provider-runtime:local\n"
                "    build:\n"
                "      context: ..\n"
                "      dockerfile: deploy/Dockerfile\n"
                "      args:\n"
                "        GO_BASE_IMAGE: ${QWQ_COMPOSE_GO_BASE_IMAGE:?required}\n",
                encoding="utf-8",
            )
            validated = {
                "runtimeCompositionDigest": "sha256:" + "a" * 64,
                "workloads": [
                    {
                        "role": "provider-runtime",
                        "composeRef": "provider/deploy/compose.yaml",
                        "composeDigest": stackctl._sha256_file(compose),
                    }
                ],
            }
            environment = {
                "LOCAL_GAMMA_GO_BASE_IMAGE": "golang@sha256:" + "b" * 64
            }
            with (
                mock.patch.object(stackctl, "ROOT", root),
                mock.patch.object(
                    stackctl,
                    "validate_provider_runtime_composition",
                    return_value=validated,
                ),
            ):
                before = stackctl._provider_runtime_build_specs(
                    {"composition": {"environment": "alpha", "target": "alpha-local"}},
                    environment,
                )[0]
                source.write_text("package main\n// changed\n", encoding="utf-8")
                after = stackctl._provider_runtime_build_specs(
                    {"composition": {"environment": "alpha", "target": "alpha-local"}},
                    environment,
                )[0]

        self.assertNotEqual(before["buildInputDigest"], after["buildInputDigest"])
        self.assertNotEqual(before["ref"], after["ref"])
        self.assertTrue(before["ref"].endswith(before["buildInputDigest"][7:]))

    def test_provider_runtime_projects_exact_image_id_from_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            candidate_root = Path(temporary_dir).resolve()
            compose_path = candidate_root / "packages/provider.compose.yaml"
            compose_path.parent.mkdir(parents=True)
            compose_path.write_text("services: {}\n", encoding="utf-8")
            compose_digest = stackctl._sha256_file(compose_path)
            build_input_digest = "sha256:" + "a" * 64
            image_digest = "sha256:" + "b" * 64
            composition = {
                "environment": "alpha",
                "target": "alpha-local",
            }
            validated = {
                "runtimeCompositionDigest": "sha256:" + "c" * 64,
                "workloads": [
                    {
                        "role": "provider-runtime",
                        "composeProfiles": ["provider-runtime"],
                    }
                ],
            }
            provider_runtime = {
                "composition": composition,
                "workloads": [
                    {
                        "role": "provider-runtime",
                        "composeRef": "packages/provider.compose.yaml",
                        "composeDigest": compose_digest,
                    }
                ],
                "images": {
                    "provider-runtime": {
                        "buildInputDigest": build_input_digest,
                        "ref": (
                            "quwoquan/provider-runtime-provider-runtime:"
                            + build_input_digest.removeprefix("sha256:")
                        ),
                        "imageDigest": image_digest,
                    }
                },
            }
            with mock.patch.object(
                stackctl,
                "validate_provider_runtime_composition",
                return_value=validated,
            ):
                projected = stackctl._provider_runtime_launch_environment(
                    provider_runtime,
                    candidate_root=candidate_root,
                    workload="full",
                )

        self.assertEqual(
            projected["QWQ_PROVIDER_RUNTIME_PROVIDER_RUNTIME_IMAGE"],
            image_digest,
        )
        self.assertEqual(
            projected["QWQ_PROVIDER_RUNTIME_COMPOSE_DIGESTS"],
            compose_digest,
        )
        self.assertNotIn(
            provider_runtime["images"]["provider-runtime"]["ref"],
            projected.values(),
        )

    def test_package_build_never_receives_protected_provider_values(self) -> None:
        environment = {
            "ASSISTANT_MODEL_API_KEY": "protected-real-value",
            "LOCAL_GAMMA_SMS_SUBSTITUTE_PORT": "17080",
        }
        with mock.patch.object(
            stackctl,
            "validate_provider_runtime_composition",
            return_value={
                "materialKeys": {
                    "endpoint": ["ASSISTANT_MODEL_COMPLETION_URL"],
                    "secret": [
                        "ASSISTANT_MODEL_API_KEY",
                        "INTEGRATION_PUSH_APNS_KEY_FILE",
                    ],
                }
            },
        ):
            stackctl._bind_package_provider_reference_environment(
                environment,
                environment_name="alpha",
                runtime_composition={},
            )

        self.assertEqual(
            environment["ASSISTANT_MODEL_COMPLETION_URL"],
            "https://127.0.0.1",
        )
        self.assertEqual(
            environment["ASSISTANT_MODEL_API_KEY"],
            "package-build-not-runtime",
        )
        self.assertEqual(
            environment["INTEGRATION_PUSH_APNS_KEY_FILE"],
            "/tmp/qwq-package-build-not-runtime",
        )

    def test_gamma_build_binds_all_compose_service_images_to_package_provenance(self) -> None:
        environment: dict[str, str] = {}
        with (
            mock.patch.object(
                stackctl,
                "_packaged_service_source_image_ref",
                side_effect=lambda _env_name, service: (
                    f"localhost/quwoquan_service_{service.replace('-', '_')}:"
                    + "a" * 64
                ),
            ) as source_image,
            mock.patch.object(
                stackctl,
                "packaged_configuration_digest",
                return_value="sha256:" + "b" * 64,
            ),
        ):
            stackctl._bind_gamma_build_service_image_refs("gamma", environment)

        for service, environment_key in (
            stackctl.GAMMA_PACKAGED_SERVICE_IMAGE_ENVIRONMENTS
        ):
            expected = (
                f"localhost/quwoquan_service_{service.replace('-', '_')}:"
                + "a" * 64
            )
            self.assertEqual(environment[environment_key], expected)
            self.assertEqual(
                environment[
                    stackctl.compose_image_environment_key(service)
                ],
                expected,
            )
        self.assertEqual(
            environment["LOCAL_GAMMA_IMAGE_VERSION"],
            environment["QWQ_COMPOSE_IMAGE_VERSION"],
        )
        self.assertEqual(
            environment["LOCAL_GAMMA_CONFIG_VERSION"],
            "sha256:" + "b" * 64,
        )
        self.assertRegex(
            environment["QWQ_COMPOSE_IMAGE_VERSION"],
            r"^sha256:[0-9a-f]{64}$",
        )
        self.assertEqual(
            source_image.call_args_list,
            [
                mock.call("gamma", service)
                for service, _ in stackctl.GAMMA_PACKAGED_SERVICE_IMAGE_ENVIRONMENTS
            ],
        )

    def test_gamma_runtime_binds_exact_package_image_ids_not_build_tags(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            candidate_root = Path(temporary_dir) / "candidate"
            shared = candidate_root / "packages/runtime-shared"
            shared.mkdir(parents=True)
            build_refs = {
                service: f"localhost/{service}:build"
                for service, _ in stackctl.GAMMA_PACKAGED_SERVICE_IMAGE_ENVIRONMENTS
            }
            images = {
                service: {
                    "ref": build_refs[service],
                    "imageDigest": "sha256:"
                    + format(index + 1, "064x"),
                }
                for index, (service, _) in enumerate(
                    stackctl.GAMMA_PACKAGED_SERVICE_IMAGE_ENVIRONMENTS
                )
            }
            provider_role = "provider-protocol-substitute"
            provider_descriptor = {
                "buildInputDigest": "sha256:" + "d" * 64,
                "ref": "quwoquan/provider-protocol-substitute:build",
                "imageDigest": "sha256:" + "e" * 64,
            }
            images[provider_role] = provider_descriptor
            image_set_digest = "sha256:" + stackctl.hashlib.sha256(
                json.dumps(
                    images,
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest()
            (shared / "oci-images.json").write_text(
                json.dumps(
                    {
                        "schema": stackctl.PACKAGE_OCI_IMAGES_SCHEMA,
                        "environment": "gamma",
                        "target": "gamma-local",
                        "configurationDigest": "sha256:" + "c" * 64,
                        "buildInputDigest": "sha256:" + "b" * 64,
                        "imageDigest": image_set_digest,
                        "images": images,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            environment = {"QWQ_LOCAL_RELEASE_TARGET": "gamma-local"}
            candidate = {
                "baselineId": "sha256:" + "f" * 64,
                "imageDigest": image_set_digest,
                "buildInputDigest": "sha256:" + "b" * 64,
                "runtimeConfigDigest": "sha256:" + "c" * 64,
                "providerRuntime": {
                    "images": {provider_role: provider_descriptor}
                },
            }
            with (
                mock.patch.object(
                    stackctl,
                    "deployment_candidate_dir",
                    return_value=candidate_root,
                ),
                mock.patch.object(
                    stackctl,
                    "_packaged_service_source_image_ref",
                    side_effect=lambda _env, service: build_refs[service],
                ),
                mock.patch.object(
                    stackctl,
                    "packaged_configuration_digest",
                    return_value="sha256:" + "c" * 64,
                ),
                mock.patch.object(
                    stackctl,
                    "active_deployment_candidate",
                    return_value={"baselineId": candidate["baselineId"]},
                ),
                mock.patch.object(
                    stackctl,
                    "load_candidate_manifest",
                    return_value=candidate,
                ),
            ):
                composition = stackctl._bind_gamma_packaged_service_image_refs(
                    "gamma",
                    environment,
                )

            self.assertEqual(composition["imageDigest"], image_set_digest)
            self.assertEqual(composition["candidateId"], candidate["baselineId"])
            self.assertEqual(
                environment["QWQ_STARTUP_IMAGE_COMPOSITION_FILE"],
                str(shared / "oci-images.json"),
            )
            full_runtime_refs = {
                role: descriptor["imageDigest"]
                for role, descriptor in images.items()
            }
            self.assertEqual(
                environment["QWQ_STARTUP_IMAGE_TRANSPORT_TAG"],
                stackctl.immutable_image_digest(full_runtime_refs),
            )
            self.assertEqual(
                environment["LOCAL_GAMMA_IMAGE_VERSION"],
                composition["imageVersion"],
            )
            self.assertNotEqual(
                environment["LOCAL_GAMMA_IMAGE_VERSION"],
                environment["QWQ_STARTUP_IMAGE_TRANSPORT_TAG"],
            )
            for service, environment_key in (
                stackctl.GAMMA_PACKAGED_SERVICE_IMAGE_ENVIRONMENTS
            ):
                self.assertEqual(
                    environment[environment_key],
                    images[service]["imageDigest"],
                )
                self.assertNotEqual(environment[environment_key], build_refs[service])

    def test_gamma_runtime_refuses_a_package_that_is_not_the_active_candidate(
        self,
    ) -> None:
        for active, candidate, expected in (
            (None, None, "package OCI runtime has no active deployment candidate"),
            (
                {"baselineId": "sha256:" + "1" * 64},
                {
                    "baselineId": "sha256:" + "1" * 64,
                    "imageDigest": "sha256:" + "9" * 64,
                    "buildInputDigest": "sha256:" + "b" * 64,
                    "runtimeConfigDigest": "sha256:" + "c" * 64,
                    "providerRuntime": {"images": {}},
                },
                "package OCI runtime differs from the active candidate",
            ),
        ):
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temporary_dir:
                candidate_root = Path(temporary_dir) / "candidate"
                shared = candidate_root / "packages/runtime-shared"
                shared.mkdir(parents=True)
                build_refs = {
                    service: f"localhost/{service}:build"
                    for service, _ in stackctl.GAMMA_PACKAGED_SERVICE_IMAGE_ENVIRONMENTS
                }
                images = {
                    service: {
                        "ref": build_refs[service],
                        "imageDigest": "sha256:" + format(index + 1, "064x"),
                    }
                    for index, (service, _) in enumerate(
                        stackctl.GAMMA_PACKAGED_SERVICE_IMAGE_ENVIRONMENTS
                    )
                }
                image_set_digest = "sha256:" + stackctl.hashlib.sha256(
                    json.dumps(
                        images,
                        ensure_ascii=True,
                        separators=(",", ":"),
                        sort_keys=True,
                    ).encode("utf-8")
                ).hexdigest()
                (shared / "oci-images.json").write_text(
                    json.dumps(
                        {
                            "schema": stackctl.PACKAGE_OCI_IMAGES_SCHEMA,
                            "environment": "gamma",
                            "target": "gamma-local",
                            "configurationDigest": "sha256:" + "c" * 64,
                            "buildInputDigest": "sha256:" + "b" * 64,
                            "imageDigest": image_set_digest,
                            "images": images,
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )
                with (
                    mock.patch.object(
                        stackctl,
                        "deployment_candidate_dir",
                        return_value=candidate_root,
                    ),
                    mock.patch.object(
                        stackctl,
                        "_packaged_service_source_image_ref",
                        side_effect=lambda _env, service: build_refs[service],
                    ),
                    mock.patch.object(
                        stackctl,
                        "packaged_configuration_digest",
                        return_value="sha256:" + "c" * 64,
                    ),
                    mock.patch.object(
                        stackctl,
                        "active_deployment_candidate",
                        return_value=active,
                    ),
                    mock.patch.object(
                        stackctl,
                        "load_candidate_manifest",
                        return_value=candidate,
                    ),
                ):
                    with self.assertRaises(ValueError) as raised:
                        stackctl._bind_gamma_packaged_service_image_refs(
                            "gamma",
                            {"QWQ_LOCAL_RELEASE_TARGET": "gamma-local"},
                        )

                self.assertIn(expected, str(raised.exception))

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
