"""deployment candidate 内 provider/observability 工件身份的本地契约。

由 test_deployment_candidate_manifest__contract__local_contract_test.py
（Python 1000 行硬顶治理）按场景拆出：本地 Elasticsearch 镜像只认
digest pin、平台只解析一次、observability/provider runtime 工件与
镜像构建身份被篡改一律拒绝、runnable 校验必须携带 candidate_root。
测试逐字搬移，共享 fixture 见 tests/support。
"""

from __future__ import annotations

import json
import unittest

from quwoquan_ops.cli.lib import deployment_candidate_manifest as subject
from quwoquan_ops.tests.support.deployment_candidate_manifest_test_support import (
    DeploymentCandidateManifestContractBase,
)


class DeploymentCandidateManifestContractTest(
    DeploymentCandidateManifestContractBase
):
    def test_local_elasticsearch_image_accepts_only_pinned_package_forms(self) -> None:
        digest = "sha256:" + "1" * 64
        literal = "docker.elastic.co/elasticsearch/elasticsearch@" + digest

        self.assertEqual(
            subject.local_elasticsearch_image_digest(literal),
            digest,
        )
        self.assertEqual(
            subject.local_elasticsearch_image_digest(
                "${QWQ_COMPOSE_ELASTICSEARCH_IMAGE:-" + literal + "}"
            ),
            digest,
        )

        for invalid in (
            "docker.elastic.co/elasticsearch/elasticsearch:8.13.4",
            "${ELASTICSEARCH_IMAGE:-" + literal + "}",
            "${QWQ_COMPOSE_ELASTICSEARCH_IMAGE:-elasticsearch:8.13.4}",
            "${QWQ_COMPOSE_ELASTICSEARCH_IMAGE}",
        ):
            with (
                self.subTest(invalid=invalid),
                self.assertRaisesRegex(
                    ValueError,
                    "immutable digest",
                ),
            ):
                subject.local_elasticsearch_image_digest(invalid)

    def test_local_elasticsearch_package_resolves_platform_once(self) -> None:
        source = subject.yaml.safe_load(
            (
                subject.ROOT
                / "quwoquan_service/services/product-ops-service/deploy"
                / "local-elasticsearch.compose.yaml"
            ).read_text(encoding="utf-8")
        )
        arm = subject._local_elasticsearch_runtime_selection(
            source,
            machine="arm64",
        )
        amd = subject._local_elasticsearch_runtime_selection(
            source,
            machine="x86_64",
        )

        self.assertEqual(arm["platform"], "arm64")
        self.assertEqual(amd["platform"], "amd64")
        # 本地构建的 quwoquan/elasticsearch-cjk 双平台共享同一精确版本身份；
        # 推 registry 后按平台 digest pin 时二者可再次分化。
        for selection in (arm, amd):
            self.assertTrue(selection["imageDigest"])
        packaged = (
            self.candidate / self.observability_log_sink["composeRef"]
        ).read_text(encoding="utf-8")
        self.assertNotIn("x-qwq-package-elasticsearch", packaged)
        self.assertNotIn("QWQ_COMPOSE_ELASTICSEARCH_IMAGE", packaged)
        self.assertIn(selection["image"], packaged)

    def test_local_observability_composition_digest_is_canonical_and_drift_sensitive(
        self,
    ) -> None:
        source = (
            subject.ROOT
            / "quwoquan_service/services/product-ops-service/deploy"
            / "local-elasticsearch.compose.yaml"
        )
        canonical = subject.canonical_local_observability_log_sink_composition(
            source,
            machine="arm64",
        )
        reordered = json.loads(json.dumps(canonical["compose"], sort_keys=True))
        self.assertEqual(
            subject.observability_log_sink_composition_digest(reordered),
            canonical["composeDigest"],
        )

        drifted = json.loads(json.dumps(canonical["compose"]))
        drifted["services"]["elasticsearch"]["environment"]["ES_JAVA_OPTS"] += (
            " -Ddrift=true"
        )
        self.assertNotEqual(
            subject.observability_log_sink_composition_digest(drifted),
            canonical["composeDigest"],
        )

    def test_candidate_rejects_tampered_observability_artifact(self) -> None:
        path = subject.write_candidate_manifest(
            "alpha",
            "alpha-local",
            package_snapshot=self.snapshot,
            release_attestation=str(self.release),
            rollback_release_attestation=str(self.rollback),
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        compose_ref = payload["observabilityLogSink"]["composeRef"]
        (self.candidate / compose_ref).write_text("tampered\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "artifact drifted"):
            subject.validate_candidate_manifest(
                payload,
                expected_environment="alpha",
                expected_target="alpha-local",
                require_full=True,
                candidate_root=self.candidate,
            )

    def test_candidate_binds_two_canonical_log_sink_bindings(self) -> None:
        bindings = self.observability_log_sink["bindings"]
        self.assertEqual(
            [binding["capabilityId"] for binding in bindings],
            ["product.telemetry.sink", "runtime.log.sink"],
        )
        self.assertEqual(
            {
                binding["endpointEnvironmentKey"]
                for binding in bindings
            },
            {
                "PRODUCT_OPS_TELEMETRY_ELASTICSEARCH_ENDPOINT",
                "PRODUCT_OPS_RUNTIME_LOG_ELASTICSEARCH_ENDPOINT",
            },
        )
        self.assertEqual(
            self.observability_log_sink["bindingDigest"],
            subject._sha256_json(bindings),
        )
        serialized = json.dumps(self.observability_log_sink, sort_keys=True)
        self.assertNotIn("secretMaterial", serialized)
        self.assertNotIn("PRODUCT_OPS_ELASTICSEARCH_ENDPOINT", serialized)

    def test_candidate_rejects_missing_duplicate_or_tampered_log_sink_binding(
        self,
    ) -> None:
        canonical = self.observability_log_sink
        tampered_cases = []

        missing = {**canonical, "bindings": canonical["bindings"][:1]}
        missing["bindingDigest"] = subject._sha256_json(missing["bindings"])
        tampered_cases.append(missing)

        duplicate_bindings = [
            canonical["bindings"][0],
            canonical["bindings"][0],
        ]
        duplicate = {**canonical, "bindings": duplicate_bindings}
        duplicate["bindingDigest"] = subject._sha256_json(duplicate_bindings)
        tampered_cases.append(duplicate)

        role_mixed_bindings = json.loads(json.dumps(canonical["bindings"]))
        role_mixed_bindings[1]["endpointEnvironmentKey"] = (
            "PRODUCT_OPS_TELEMETRY_ELASTICSEARCH_ENDPOINT"
        )
        role_mixed = {**canonical, "bindings": role_mixed_bindings}
        role_mixed["bindingDigest"] = subject._sha256_json(role_mixed_bindings)
        tampered_cases.append(role_mixed)

        digest_tampered = {
            **canonical,
            "bindingDigest": "sha256:" + "9" * 64,
        }
        tampered_cases.append(digest_tampered)

        for payload in tampered_cases:
            with self.subTest(payload=payload), self.assertRaisesRegex(
                ValueError,
                "Binding closure|bindingDigest",
            ):
                subject.validate_observability_log_sink_package(
                    payload,
                    expected_environment="alpha",
                    expected_target="alpha-local",
                    candidate_root=self.candidate,
                )

    def test_legacy_single_binding_payload_is_rejected_for_every_purpose(
        self,
    ) -> None:
        canonical = self.observability_log_sink
        retired = {
            "schema": canonical["schema"],
            "adapterId": canonical["adapterId"],
            "bindingDigest": (
                "sha256:47135fea885dfc2985e2501621e606009"
                "b40f3b3e67fe21e348e3f6519735b1b"
            ),
            "endpointRef": "local_topology:elasticsearch",
            "endpointEnvironmentKey": "PRODUCT_OPS_ELASTICSEARCH_ENDPOINT",
            "secretEnvironmentKeys": [],
            "deploymentMode": canonical["deploymentMode"],
            "platform": canonical["platform"],
            "runtimeEndpoint": canonical["runtimeEndpoint"],
            "imageDigest": canonical["imageDigest"],
            "sourceComposeDigest": canonical["sourceComposeDigest"],
            "composeRef": canonical["composeRef"],
            "composeDigest": canonical["composeDigest"],
            "clusterRef": "target:alpha-local/product-ops/elasticsearch",
        }

        for purpose in ("self_verify", "currentness", "teardown"):
            with self.subTest(purpose=purpose), self.assertRaisesRegex(
                ValueError,
                "fields mismatch",
            ):
                subject.validate_observability_log_sink_package(
                    retired,
                    expected_environment="alpha",
                    expected_target="alpha-local",
                    candidate_root=self.candidate,
                    purpose=purpose,
                )

    def test_new_log_sink_package_accepts_every_validation_purpose(self) -> None:
        for purpose in ("self_verify", "teardown", "currentness"):
            with self.subTest(purpose=purpose):
                validated = subject.validate_observability_log_sink_package(
                    self.observability_log_sink,
                    expected_environment="alpha",
                    expected_target="alpha-local",
                    candidate_root=self.candidate,
                    purpose=purpose,
                )
                self.assertIs(validated, self.observability_log_sink)

    def test_candidate_rejects_tampered_provider_runtime_identity(self) -> None:
        path = subject.write_candidate_manifest(
            "alpha",
            "alpha-local",
            package_snapshot=self.snapshot,
            release_attestation=str(self.release),
            rollback_release_attestation=str(self.rollback),
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["providerRuntime"]["composition"]["bindings"][0]["adapterId"] = (
            "ext.invalid"
        )

        with self.assertRaisesRegex(
            ValueError,
            "canonical environment Bindings|bindingDigest mismatch|local substitute",
        ):
            subject.validate_candidate_manifest(
                payload,
                expected_environment="alpha",
                expected_target="alpha-local",
                require_full=True,
                candidate_root=self.candidate,
            )

    def test_candidate_rejects_tampered_provider_runtime_artifact(self) -> None:
        path = subject.write_candidate_manifest(
            "alpha",
            "alpha-local",
            package_snapshot=self.snapshot,
            release_attestation=str(self.release),
            rollback_release_attestation=str(self.rollback),
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        artifact_ref = payload["providerRuntime"]["workloads"][0]["composeRef"]
        (self.candidate / artifact_ref).write_text("tampered\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "artifact drifted"):
            subject.validate_candidate_manifest(
                payload,
                expected_environment="alpha",
                expected_target="alpha-local",
                require_full=True,
                candidate_root=self.candidate,
            )

    def test_candidate_rejects_tampered_provider_image_build_identity(self) -> None:
        path = subject.write_candidate_manifest(
            "alpha",
            "alpha-local",
            package_snapshot=self.snapshot,
            release_attestation=str(self.release),
            rollback_release_attestation=str(self.rollback),
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        role = next(iter(payload["providerRuntime"]["images"]))
        forged_digest = "sha256:" + "9" * 64
        payload["providerRuntime"]["images"][role]["buildInputDigest"] = forged_digest
        payload["providerRuntime"]["images"][role]["ref"] = (
            f"quwoquan/provider-runtime-{role}:"
            f"{forged_digest.removeprefix('sha256:')}"
        )
        provider_manifest = (
            self.candidate
            / "packages/runtime-shared/provider-runtime/manifest.json"
        )
        provider_manifest.write_text(
            json.dumps(payload["providerRuntime"], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "differ from canonical OCI"):
            subject.validate_candidate_manifest(
                payload,
                expected_environment="alpha",
                expected_target="alpha-local",
                require_full=True,
                candidate_root=self.candidate,
            )

    def test_runnable_candidate_validation_requires_candidate_root(self) -> None:
        path = subject.write_candidate_manifest(
            "alpha",
            "alpha-local",
            package_snapshot=self.snapshot,
            release_attestation=str(self.release),
            rollback_release_attestation=str(self.rollback),
        )
        payload = json.loads(path.read_text(encoding="utf-8"))

        with self.assertRaisesRegex(ValueError, "requires candidate_root"):
            subject.validate_candidate_manifest(
                payload,
                expected_environment="alpha",
                expected_target="alpha-local",
                require_full=True,
            )


if __name__ == "__main__":
    unittest.main()
