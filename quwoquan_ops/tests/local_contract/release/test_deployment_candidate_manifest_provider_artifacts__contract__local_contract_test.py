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
        self.assertIn(self.observability_log_sink["image"], packaged)

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
