"""deployment candidate manifest 本地契约的共享 fixture。

由 test_deployment_candidate_manifest__contract__local_contract_test.py
（Python 1000 行硬顶治理）下沉：三个场景文件共享同一 alpha-local 候选
目录、release attestation、provider runtime 与 observability 物料。
setUpClass/setUp 逐字搬移。
"""

from __future__ import annotations

import json
import hashlib
import unittest
from contextlib import ExitStack
from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest import mock

from quwoquan_ops.cli.lib import deployment_candidate_manifest as subject
from quwoquan_ops.cli.lib.deployment_candidate_manifest import provider_binding_overlay


@lru_cache(maxsize=1)
def _compiled_provider_bindings() -> dict[str, Any]:
    """Compile the Provider binding capsule once for the whole test process.

    Compilation reads the immutable capsule, so every candidate in this fixture
    would get identical bytes; doing it per test would add seconds per case.
    """

    return provider_binding_overlay.compile_single_environment_bindings(
        environment="alpha",
        target="alpha-local",
        source_root=subject.ROOT,
    )


class DeploymentCandidateManifestContractBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        compiled = {
            "schema": "compiled-external-provider-bindings",
            "issues": [],
            "selectedBindings": {
                "alpha": {
                    "identity.sms.otp": {
                        "state": "enabled",
                        "adapter_id": "ext.sms.local_capture",
                        "endpoint_ref": "local_topology:sms-provider-substitute",
                        "endpoint_envs": {
                            "endpoint": "INTEGRATION_SMS_ENDPOINT",
                        },
                        "secret_refs": ["INTEGRATION_SMS_TOKEN"],
                    },
                    "runtime.log.sink": {
                        "state": "enabled",
                        "adapter_id": "ext.obs.elasticsearch",
                        "endpoint_ref": "local_topology:alpha.elasticsearch",
                        "endpoint_envs": {
                            "endpoint": "PRODUCT_OPS_ELASTICSEARCH_ENDPOINT",
                        },
                        "secret_refs": [],
                    },
                },
            },
        }
        cls.provider_runtime_fixture = subject.compile_provider_runtime_composition(
            environment="alpha",
            target="alpha-local",
            compiled=compiled,
        )

    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        # Production candidate paths are canonicalized by output_paths before
        # this module performs its descriptor-by-descriptor nofollow walk.
        self.root = Path(self.temporary.name).resolve()
        self.candidate = self.root / "candidate"
        self.app = self.candidate / "packages/app"
        self.shared = self.candidate / "packages/runtime-shared"
        self.legal = self.candidate / "packages/legal-static"
        self.app.mkdir(parents=True)
        self.shared.mkdir(parents=True)
        legal_current = self.legal / "current"
        (legal_current / "public/legal").mkdir(parents=True)
        for relative in (
            "release_metadata.json",
            "checksums.json",
            "public/legal/manifest.json",
        ):
            (legal_current / relative).write_text("{}\n", encoding="utf-8")
        digest = "sha256:" + "a" * 64
        self.configuration_digest = "sha256:" + "1" * 64
        self.runtime_config_digest = "sha256:" + "2" * 64
        self.workspace_digest = digest
        self.environment_artifact_schema = json.loads(
            (
                subject.ROOT
                / "quwoquan_service/contracts/metadata/_schemas"
                / "environment_artifact_identity.schema.json"
            ).read_text(encoding="utf-8")
        )
        self.contract_graph = self.root / "contract_graph.json"
        self.contract_graph.write_text(
            json.dumps({"objects": [], "operations": []}) + "\n",
            encoding="utf-8",
        )
        self.contract_graph_digest = "sha256:" + hashlib.sha256(
            self.contract_graph.read_bytes()
        ).hexdigest()
        self.snapshot = {
            "baselineId": "sha256:" + "b" * 64,
            "sourceRevision": "c" * 40,
            "workspaceStatusDigest": "sha256:" + "d" * 64,
        }
        self.graphql_read_registry = {
            "schema": "stackctl-graphql-read-registry-package",
            "candidateDigest": self.snapshot["baselineId"],
        }
        (self.app / "environment_runtime.yaml").write_text(
            json.dumps(
                {
                    "schema": "environment-runtime-package",
                    "environment": "alpha",
                    "target": "alpha-local",
                    "publicBases": {
                        "api": "https://api.alpha.example",
                        "publicWeb": "https://www.alpha.example",
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (self.app / "report.json").write_text(
            json.dumps({"runtimeConfigDigest": self.runtime_config_digest}) + "\n",
            encoding="utf-8",
        )
        (self.app / "package-fingerprint.json").write_text(
            json.dumps(
                {
                    "candidateType": subject.RUNTIME_CANDIDATE_TYPE,
                    "environment": "alpha",
                    "target": "alpha-local",
                    "includeServices": True,
                    "baselineId": self.snapshot["baselineId"],
                    "sourceRevision": self.snapshot["sourceRevision"],
                    "workspaceStatusDigest": self.snapshot["workspaceStatusDigest"],
                    "releaseInputClassification": "commercial_inputs",
                    "contractGraphDigest": self.contract_graph_digest,
                    "graphqlReadRegistry": self.graphql_read_registry,
                    "deploymentInputs": {"digest": digest},
                    "packageContent": {"digest": digest},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (self.shared / "oci-images.json").write_text(
            json.dumps(
                {
                    "buildInputDigest": digest,
                    "imageDigest": "sha256:" + "e" * 64,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        self.runtime_topology_path = (
            self.shared / "runtime-topology" / "manifest.json"
        )
        self.runtime_topology_path.parent.mkdir(parents=True)
        self.runtime_topology_path.write_text(
            json.dumps(
                {
                    "schema": "qwq.runtime_topology_package.v3",
                    "environment": "alpha",
                    "target": "alpha-local",
                    "topologyDigest": "sha256:" + "f" * 64,
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        self.release = self.root / "candidate-release.json"
        self.rollback = self.root / "rollback-release.json"
        for path, release_id, release_digest, release_class in (
            (
                self.release,
                "west-lake-canonical-20260729",
                "8" * 64,
                "commercial",
            ),
            (self.rollback, "pilot-002", "5" * 64, "commercial"),
        ):
            path.write_text(
                json.dumps(
                    {
                        "schema": "quwoquan_data.release_attestation",
                        "releaseId": release_id,
                        "releaseClass": release_class,
                        "productLifecycleState": release_class,
                        "payloadSha256": "sha256:" + release_digest,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        self.patches.enter_context(
            mock.patch.object(
                subject,
                "CONTRACT_GRAPH_PATH",
                self.contract_graph,
                create=True,
            )
        )
        self.patches.enter_context(
            mock.patch.object(
                subject,
                "validate_packaged_graphql_read_registry",
                return_value=self.graphql_read_registry,
            )
        )
        self.patches.enter_context(
            mock.patch.object(
                subject,
                "app_deployment_package_dir",
                return_value=self.app,
            )
        )
        self.patches.enter_context(
            mock.patch.object(
                subject,
                "runtime_shared_deployment_package_dir",
                return_value=self.shared,
            )
        )
        self.patches.enter_context(
            mock.patch.object(
                subject,
                "legal_static_deployment_package_dir",
                return_value=self.legal,
            )
        )
        self.provider_runtime = self.provider_runtime_fixture
        self.patches.enter_context(
            mock.patch.object(
                subject,
                "compile_provider_runtime_composition",
                return_value=self.provider_runtime,
            )
        )
        self.observability_log_sink = (
            subject.materialize_observability_log_sink_package(
                "alpha",
                "alpha-local",
                self.provider_runtime,
            )
        )
        subject.materialize_provider_runtime_package(
            "alpha",
            "alpha-local",
            source_root=subject.ROOT,
        )
        self.patches.enter_context(
            mock.patch.object(
                provider_binding_overlay,
                "compile_single_environment_bindings",
                return_value=_compiled_provider_bindings(),
            )
        )
        self.provider_binding_overlay = subject.materialize_provider_binding_overlay(
            "alpha",
            "alpha-local",
            source_root=subject.ROOT,
        )
        self.provider_images = {}
        for index, workload in enumerate(self.provider_runtime["workloads"], start=4):
            role = str(workload["role"])
            build_input_digest = "sha256:" + str(index) * 64
            self.provider_images[role] = {
                "buildInputDigest": build_input_digest,
                "ref": (
                    f"quwoquan/provider-runtime-{role}:"
                    f"{build_input_digest.removeprefix('sha256:')}"
                ),
                "imageDigest": "sha256:" + str(index + 2) * 64,
            }
        subject.seal_provider_runtime_package_images(
            "alpha",
            "alpha-local",
            self.candidate,
            self.provider_images,
        )
        first_party_images: dict[str, dict[str, str]] = {}
        first_party_refs: dict[str, str] = {}
        for index, service in enumerate(subject.first_party_service_names(), start=20):
            ref = (
                "localhost/quwoquan_service_"
                + service.replace("-", "_")
                + ":"
                + f"{index:064x}"
            )
            first_party_refs[service] = ref
            first_party_images[service] = {
                "ref": ref,
                "imageDigest": "sha256:" + f"{index + 40:064x}",
            }
        images = {**first_party_images, **self.provider_images}
        provider_refs = {
            role: {
                "buildInputDigest": descriptor["buildInputDigest"],
                "ref": descriptor["ref"],
            }
            for role, descriptor in sorted(self.provider_images.items())
        }
        oci = {
            "schema": "stackctl-package-oci-images",
            "environment": "alpha",
            "target": "alpha-local",
            "configurationDigest": self.configuration_digest,
            "buildInputDigest": subject._sha256_json(
                {
                    "firstPartyImageVersion": subject.immutable_image_digest(
                        first_party_refs
                    ),
                    "providerRuntimeDigest": self.provider_runtime[
                        "runtimeCompositionDigest"
                    ],
                    "providerBindingManifestDigest": self.provider_binding_overlay[
                        "bindingManifestDigest"
                    ],
                    "providerImageRefs": provider_refs,
                }
            ),
            "imageDigest": subject._sha256_json(images),
            "images": images,
        }
        (self.shared / "oci-images.json").write_text(
            json.dumps(oci) + "\n",
            encoding="utf-8",
        )
