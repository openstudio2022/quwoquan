"""场景：alpha/beta workload 的 Provider 物化边界——有界 content workload 不
物化无关 Provider、固定包缺失即 BLOCK、substitute 拓扑绑定与物化失败阻断。"""

from __future__ import annotations

import argparse
import contextlib
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
