from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.commands import package_runtime
from quwoquan_ops.cli.lib import deployment_candidate_manifest as deployment_candidate
from quwoquan_ops.cli.lib.deployment_candidate_manifest import manifest as candidate_manifest
from quwoquan_ops.tests.support.deployment_candidate_manifest_test_support import (
    DeploymentCandidateManifestContractBase,
)


class ProdHostedPackageOciManifestContractTest(unittest.TestCase):
    source_revision = "c" * 40
    source_tree_digest = "sha1:" + "d" * 40
    artifact_digest = "sha256:" + "a" * 64
    candidate_id = "sha256:" + "b" * 64
    provider_digest = "sha256:" + "e" * 64
    services = ("content-service", "user-service")

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.candidate = self.root / "candidate"
        self.shared = self.candidate / "packages/runtime-shared"
        self.shared.mkdir(parents=True)
        self._write_json(
            self.candidate / "packages/app/package-fingerprint.json",
            {"servicePackages": list(self.services)},
        )
        self.release_root = self.root / "release"
        self.release_root.mkdir()
        self.release_manifest = self.release_root / "manifest.json"
        self.release_payload = self._release_payload()
        self._write_json(self.release_manifest, self.release_payload)
        self.release_manifest_digest = self._sha256_file(self.release_manifest)
        self.configuration_versions: dict[str, str] = {}
        for index, service in enumerate(self.services, start=1):
            service_root = self.candidate / "packages/services" / service
            config_path = service_root / "config/config.yaml"
            config_path.parent.mkdir(parents=True)
            config_path.write_text(
                f"config:\n  version: sha256:{index:064x}\n",
                encoding="utf-8",
            )
            config_digest = self._sha256_file(config_path)
            config_version = "sha256:" + f"{index:064x}"
            self.configuration_versions[service] = config_version
            self._write_json(
                service_root / "provenance.json",
                {
                    "schema": "qwq.service_package",
                    "service": service,
                    "environment": "prod",
                    "gitRevision": self.source_revision,
                    "configVersion": config_version,
                    "digests": {"config": config_digest},
                    "releaseEvidence": {
                        "manifest": str(self.release_manifest),
                        "evidenceFileDigest": self.release_manifest_digest,
                        "artifactDigest": self.artifact_digest,
                        "releaseCompositionId": self.candidate_id,
                        "verifiedConfigDigest": config_digest,
                    },
                },
            )
        self.provider_runtime = {
            "composition": {"runtimeCompositionDigest": self.provider_digest},
            "images": {},
        }
        self.release_identity = {
            "releaseCompositionId": self.candidate_id,
            "artifactDigest": self.artifact_digest,
            "sourceGitSha": self.source_revision,
            "sourceTreeDigest": self.source_tree_digest,
        }
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        self.patches.enter_context(
            mock.patch.dict(
                os.environ,
                {"QWQ_PROD_RELEASE_ARTIFACT_ROOT": str(self.release_root)},
            )
        )
        self.patches.enter_context(
            mock.patch.object(
                stackctl.finalize_mainline_release_artifact,
                "validate_manifest",
            )
        )
        self.patches.enter_context(
            mock.patch.object(
                stackctl.finalize_mainline_release_artifact,
                "validate_manifest_files",
            )
        )
        self.patches.enter_context(
            mock.patch.object(
                stackctl,
                "first_party_service_names",
                return_value=self.services,
            )
        )
        self.seal_provider_images = self.patches.enter_context(
            mock.patch.object(
                stackctl,
                "seal_provider_runtime_package_images",
                return_value=self.provider_runtime,
            )
        )
        self.patches.enter_context(
            mock.patch.object(
                stackctl,
                "runtime_shared_deployment_package_dir",
                return_value=self.shared,
            )
        )

    @staticmethod
    def _write_json(path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _sha256_file(path: Path) -> str:
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()

    def _release_payload(self) -> dict[str, object]:
        images: dict[str, dict[str, object]] = {}
        for index, service in enumerate(self.services, start=1):
            repository = f"ghcr.io/quwoquan/quwoquan/{service}"
            digest = "sha256:" + f"{index + 10:064x}"
            ref = f"{repository}@{digest}"
            images[service] = {
                "repository": repository,
                "transportRef": f"{repository}:sha-{self.source_revision}",
                "digest": digest,
                "ref": ref,
                "attestations": {
                    "spdxSbom": f"oci://{ref}#spdxSbom",
                    "slsaProvenance": f"oci://{ref}#slsaProvenance",
                },
            }
        return {
            "schema": "release-evidence-manifest",
            "status": "main-admitted",
            "releaseCompositionId": self.candidate_id,
            "artifactDigest": self.artifact_digest,
            "source": {
                "gitSha": self.source_revision,
                "treeDigest": self.source_tree_digest,
                "repository": "quwoquan/quwoquan",
                "workflowRunId": "123",
            },
            "requiredEvidence": {"images": list(self.services)},
            "images": images,
        }

    def _materialize(self) -> tuple[Path, dict[str, object]]:
        return candidate_manifest._materialize_prod_hosted_oci_manifest(
            "prod",
            "prod-hosted",
            provider_runtime=self.provider_runtime,
            candidate_root=self.candidate,
            package_snapshot={"sourceRevision": self.source_revision},
            materialized_release_evidence=self.release_identity,
            source_root=self.root,
        )

    def test_materializes_exact_hosted_image_descriptors_without_local_build(self) -> None:
        path, payload = self._materialize()

        self.assertEqual(path, self.shared / "oci-images.json")
        self.assertEqual(payload["environment"], "prod")
        self.assertEqual(payload["target"], "prod-hosted")
        self.assertEqual(set(payload["images"]), set(self.services))
        for service, descriptor in payload["images"].items():
            release_descriptor = self.release_payload["images"][service]
            self.assertEqual(descriptor["ref"], release_descriptor["ref"])
            self.assertEqual(
                descriptor["imageDigest"],
                release_descriptor["digest"],
            )
        self.seal_provider_images.assert_called_once_with(
            "prod",
            "prod-hosted",
            self.candidate,
            {},
        )

        candidate_manifest._validate_candidate_provider_oci_binding(
            {
                "environment": "prod",
                "target": "prod-hosted",
                "sourceRevision": self.source_revision,
                "configurationDigest": payload["configurationDigest"],
                "buildInputDigest": payload["buildInputDigest"],
                "imageDigest": payload["imageDigest"],
                "providerRuntime": self.provider_runtime,
            },
            candidate_root=self.candidate,
        )
        candidate_manifest._validate_prod_hosted_oci_binding(
            {
                "environment": "prod",
                "target": "prod-hosted",
                "sourceRevision": self.source_revision,
                "configurationDigest": payload["configurationDigest"],
                "buildInputDigest": payload["buildInputDigest"],
                "imageDigest": payload["imageDigest"],
                "providerRuntime": self.provider_runtime,
            },
            candidate_root=self.candidate,
        )

    def test_missing_or_drifted_hosted_release_evidence_is_rejected(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(
            FileNotFoundError,
            "hosted release artifact root",
        ):
            self._materialize()

        drifted = dict(self.release_identity)
        drifted["releaseCompositionId"] = "sha256:" + "f" * 64
        with self.assertRaisesRegex(ValueError, "hosted release evidence identity drifted"):
            candidate_manifest._materialize_prod_hosted_oci_manifest(
                "prod",
                "prod-hosted",
                provider_runtime=self.provider_runtime,
                candidate_root=self.candidate,
                package_snapshot={"sourceRevision": self.source_revision},
                materialized_release_evidence=drifted,
                source_root=self.root,
            )

        self.release_payload["source"]["gitSha"] = "f" * 40
        self._write_json(self.release_manifest, self.release_payload)
        with self.assertRaisesRegex(ValueError, "source revision"):
            self._materialize()

    def test_packaged_hosted_manifest_rejects_release_provenance_drift(self) -> None:
        _, payload = self._materialize()
        provenance_path = (
            self.candidate
            / "packages/services/content-service/provenance.json"
        )
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        provenance["releaseEvidence"]["artifactDigest"] = "sha256:" + "f" * 64
        self._write_json(provenance_path, provenance)

        with self.assertRaisesRegex(ValueError, "hosted release evidence.*drifted"):
            candidate_manifest._validate_prod_hosted_oci_binding(
                {
                    "environment": "prod",
                    "target": "prod-hosted",
                    "sourceRevision": self.source_revision,
                    "configurationDigest": payload["configurationDigest"],
                    "buildInputDigest": payload["buildInputDigest"],
                    "imageDigest": payload["imageDigest"],
                    "providerRuntime": self.provider_runtime,
                },
                candidate_root=self.candidate,
            )

    def test_package_identity_readback_rechecks_hosted_release_currentness(self) -> None:
        self._materialize()
        identity = {
            "releaseInputClassification": "commercial_inputs",
            "contractGraphDigest": "sha256:" + "9" * 64,
            "graphqlReadRegistry": {"schema": "test-registry"},
        }
        report_path = self.root / "report.json"
        fingerprint_path = (
            self.candidate / "packages/app/package-fingerprint.json"
        )
        candidate_path = self.candidate / "manifest.json"
        self._write_json(report_path, identity)
        self._write_json(
            fingerprint_path,
            {**identity, "servicePackages": list(self.services)},
        )
        self._write_json(
            candidate_path,
            {
                **identity,
                "target": "prod-hosted",
                "sourceRevision": self.source_revision,
            },
        )

        self.assertEqual(
            package_runtime._validate_runtime_package_identity_readback(
                report_path=report_path,
                fingerprint_path=fingerprint_path,
                manifest_path=candidate_path,
            ),
            {**identity, "appLaunchBundle": None},
        )
        with mock.patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(
            FileNotFoundError,
            "hosted release artifact root",
        ):
            package_runtime._validate_runtime_package_identity_readback(
                report_path=report_path,
                fingerprint_path=fingerprint_path,
                manifest_path=candidate_path,
            )


class LocalPackageOciRequirementContractTest(
    DeploymentCandidateManifestContractBase
):
    def test_local_candidate_still_requires_package_bound_oci_manifest(self) -> None:
        (self.shared / "oci-images.json").unlink()

        with self.assertRaisesRegex(
            ValueError,
            "full candidate has no safe package-bound OCI manifest",
        ):
            deployment_candidate.write_candidate_manifest(
                "alpha",
                "alpha-local",
                package_snapshot=self.snapshot,
                release_attestation=str(self.release),
                rollback_release_attestation=str(self.rollback),
            )


def test_package_receipt_redacts_assignment_shaped_process_output() -> None:
    raw = "failed to fetch anonymous token: Get https://registry.example/token"

    redacted = package_runtime._receipt_safe_text(raw)

    assert "token: <redacted>" in redacted
    assert "token: Get" not in redacted


if __name__ == "__main__":
    unittest.main()
