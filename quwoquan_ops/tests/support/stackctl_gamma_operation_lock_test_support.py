"""stackctl gamma operation lock 场景族共享测试基座。

由 test_stackctl_gamma_operation_lock__*__local_contract_test.py 各场景文件继承；
setUpClass/setUp 与 helper 逐字来自拆分前的单文件套件，行为保持不变。
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib.provider_runtime_composition import (
    compile_provider_runtime_composition,
)
from quwoquan_ops.tests.support.provider_binding_overlay_fixture import (
    packaged_service_build_ref,
)


class StackctlGammaOperationLockContractTestBase(unittest.TestCase):
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
            "endpointRef": "local_topology:elasticsearch",
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
                "releaseInputClassification": "commercial_inputs",
                "contractGraphDigest": "sha256:" + "8" * 64,
                "release": {
                    "candidate": {
                        "releaseId": "candidate-commercial",
                        "releaseDigest": "sha256:" + "4" * 64,
                        "attestationRef": "/candidate-commercial.json",
                        "attestationDigest": "sha256:" + "5" * 64,
                        "releaseClass": "commercial",
                        "productLifecycleState": "commercial",
                    },
                    "rollback": {
                        "releaseId": "rollback-commercial",
                        "releaseDigest": "sha256:" + "6" * 64,
                        "attestationRef": "/rollback-commercial.json",
                        "attestationDigest": "sha256:" + "7" * 64,
                        "releaseClass": "commercial",
                        "productLifecycleState": "commercial",
                    },
                },
            },
        }

    @staticmethod
    def _packaged_service_source_ref(service: str, digest: str) -> str:
        repository = (
            "core"
            if service == stackctl.SERVICE_CORE_WORKLOAD
            else service.replace("-", "_")
        )
        return f"localhost/quwoquan_service_{repository}:{digest}"

    _packaged_service_build_ref = staticmethod(packaged_service_build_ref)

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
        candidate_manifest = mock.patch.object(
            stackctl,
            "load_candidate_manifest",
            side_effect=lambda environment_name, _target, _digest, **_kwargs: (
                self._candidate_snapshot(environment_name)["manifest"]
            ),
        )
        candidate_manifest.start()
        self.addCleanup(candidate_manifest.stop)
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
