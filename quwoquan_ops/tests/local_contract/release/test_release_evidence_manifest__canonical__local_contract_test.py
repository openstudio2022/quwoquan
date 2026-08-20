# spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md#sit-004
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli.prod import collect_mainline_image_descriptors as image_collector
from quwoquan_ops.cli.prod import collect_release_artifact_descriptors as evidence_collector
from quwoquan_ops.cli.prod import finalize_mainline_release_artifact as finalizer
from quwoquan_ops.cli.prod import load_prod_plane_images
from quwoquan_ops.tests.support.release_evidence_manifest_fixture_test_support import (
    APP_EVIDENCE_REF,
    DIGEST,
    ReleaseEvidenceManifestFixtureMixin,
)




class ReleaseEvidenceManifestCanonicalContractTest(
    ReleaseEvidenceManifestFixtureMixin, unittest.TestCase
):
    def test_candidate_identity_is_stable_across_real_release_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = self._build_input(root)
            image_descriptors = root / "image-descriptors"
            with (
                mock.patch.object(
                    image_collector,
                    "resolve_registry_digest",
                    side_effect=(
                        f"sha256:{index:064x}" for index in range(1, 5)
                    ),
                ),
                mock.patch.object(image_collector, "verify_oci_supply_chain"),
            ):
                image_collector.collect(
                    json.loads(
                        (artifact / "manifest.json").read_text(encoding="utf-8")
                    ),
                    image_descriptors,
                )
            component = finalizer.finalize(artifact, image_descriptors)
            self.assertEqual(component["schema"], "release-evidence-manifest")
            self.assertEqual(component["status"], "component-ready")
            self.assertNotEqual(component["generatedAt"], "2026-07-28T00:00:00Z")
            self.assertNotIn("versions", component)
            self.assertNotIn("manifestDigest", component)

            evidence_descriptors = root / "evidence-descriptors"
            evidence_collector.collect(
                artifact_dir=artifact,
                descriptors_dir=evidence_descriptors,
                sources=self._evidence_sources(root),
                application_package_sources=self._application_package_sources(
                    root, artifact
                ),
                application_package_payloads=evidence_collector.load_application_package_payloads(
                    self._application_package_payloads(root)
                ),
                application_evidence_ref=APP_EVIDENCE_REF,
                provider_raw_dir=self._provider_raw_dir(root),
            )
            candidate = finalizer.finalize(
                artifact,
                None,
                evidence_descriptors,
            )

            self.assertEqual(set(candidate), finalizer.ROOT_FIELDS)
            self.assertEqual(candidate["status"], "candidate-ready")
            self.assertNotEqual(candidate["generatedAt"], component["generatedAt"])
            self.assertNotEqual(candidate["candidateId"], candidate["artifactDigest"])
            self.assertEqual(
                candidate["candidateId"],
                finalizer.canonical_candidate_digest(candidate),
            )
            self.assertEqual(
                candidate["artifactDigest"],
                finalizer.canonical_manifest_digest(candidate),
            )
            self.assertEqual(
                set(candidate["applicationPackages"]),
                set(finalizer.ENVIRONMENTS),
            )
            for environment in finalizer.ENVIRONMENTS:
                self.assertEqual(
                    set(candidate["applicationPackages"][environment]),
                    set(finalizer.APPLICATION_PACKAGES[environment]),
                )
            changed_configuration = json.loads(json.dumps(candidate))
            changed_configuration["environmentArtifacts"]["gamma"][
                "configurationPackages"
            ]["content-service"]["digest"] = "sha256:" + ("d" * 64)
            changed_configuration["environmentArtifacts"]["gamma"][
                "environmentArtifactDigest"
            ] = finalizer.canonical_environment_artifact_digest(
                changed_configuration, "gamma"
            )
            self.assertNotEqual(
                finalizer.canonical_candidate_digest(changed_configuration),
                candidate["candidateId"],
            )
            changed_application = json.loads(json.dumps(candidate))
            changed_application["applicationPackages"]["beta"]["ios"][
                "digest"
            ] = "sha256:" + ("e" * 64)
            self.assertNotEqual(
                finalizer.canonical_candidate_digest(changed_application),
                candidate["candidateId"],
            )
            changed_payload = json.loads(json.dumps(candidate))
            changed_payload["applicationPackages"]["beta"]["ios"][
                "packageDigest"
            ] = "sha256:" + ("f" * 64)
            self.assertNotEqual(
                finalizer.canonical_candidate_digest(changed_payload),
                candidate["candidateId"],
            )
            changed_locator = json.loads(json.dumps(candidate))
            changed_locator["applicationPackages"]["beta"]["ios"][
                "sourceRef"
            ] = "oci://ghcr.io/owner/repo/other-app@" + DIGEST
            self.assertNotEqual(
                finalizer.canonical_candidate_digest(changed_locator),
                candidate["candidateId"],
            )
            self.assertEqual(candidate["providerEvidence"]["status"], "passed")
            self.assertEqual(candidate["testEvidence"]["status"], "passed")

            preprod_receipts = root / "preprod-receipts"
            for environment in finalizer.PRE_PROD_ENVIRONMENTS:
                receipt = self._receipt(
                    root, candidate, kind="environment", environment=environment
                )
                self._write_json(
                    preprod_receipts / f"{environment}.json",
                    json.loads(receipt.read_text(encoding="utf-8")),
                )
            rollback_ready = self._receipt(
                root,
                candidate,
                kind="rollback",
                environment="prod",
                status="ready",
            )
            deployable = finalizer.finalize(
                artifact,
                None,
                environment_receipts_dir=preprod_receipts,
                rollback_receipt_path=rollback_ready,
            )
            self.assertEqual(deployable["status"], "deployable")
            self.assertEqual(deployable["candidateId"], candidate["candidateId"])
            self.assertNotEqual(deployable["artifactDigest"], candidate["artifactDigest"])
            self.assertEqual(
                deployable["missingEvidence"],
                [
                    "environmentReceipts.prod",
                    "rolloutReceipt",
                    "rollbackReceipt.outcome",
                ],
            )

            all_keys: set[str] = set()

            def collect_keys(value: object) -> None:
                if isinstance(value, dict):
                    all_keys.update(str(key) for key in value)
                    for child in value.values():
                        collect_keys(child)
                elif isinstance(value, list):
                    for child in value:
                        collect_keys(child)

            collect_keys(deployable)
            self.assertTrue(all_keys.isdisjoint(finalizer.FORBIDDEN_FIELDS))

            transport_tag = deployable["environmentArtifacts"]["prod"]["images"][
                "content-service"
            ]["transportRef"].rsplit(":", 1)[1]
            digest, images = load_prod_plane_images._release_image_sources(
                artifact / "manifest.json",
                services=["content-service"],
                image_transport_tag=transport_tag,
            )
            self.assertEqual(digest, deployable["artifactDigest"])
            self.assertEqual(
                images["content-service"],
                deployable["environmentArtifacts"]["prod"]["images"][
                    "content-service"
                ]["ref"],
            )

            prod_receipts = root / "prod-receipts"
            prod_receipt = self._receipt(
                root, deployable, kind="environment", environment="prod"
            )
            self._write_json(
                prod_receipts / "prod.json",
                json.loads(prod_receipt.read_text(encoding="utf-8")),
            )
            rollout = self._receipt(
                root,
                deployable,
                kind="rollout",
                environment="prod",
            )
            rollback = self._receipt(
                root,
                deployable,
                kind="rollback",
                environment="prod",
                status="not_triggered",
            )
            released = finalizer.finalize(
                artifact,
                None,
                environment_receipts_dir=prod_receipts,
                rollout_receipt_path=rollout,
                rollback_receipt_path=rollback,
            )
            self.assertEqual(released["status"], "released")
            self.assertEqual(released["candidateId"], candidate["candidateId"])
            self.assertNotEqual(released["artifactDigest"], deployable["artifactDigest"])
            self.assertEqual(released["blockers"], [])
            self.assertEqual(released["missingEvidence"], [])

    def test_online_validator_rejects_forbidden_envelope_and_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            artifact = self._build_input(Path(temporary))
            manifest = json.loads(
                (artifact / "manifest.json").read_text(encoding="utf-8")
            )
            manifest["schema"] = "mainline-release-artifact"
            manifest["versions"] = {"imageVersion": "forbidden"}
            with self.assertRaisesRegex(ValueError, "release evidence manifest fields are forbidden"):
                finalizer.validate_manifest(manifest)

            canonical = json.loads(
                (artifact / "manifest.json").read_text(encoding="utf-8")
            )
            historical = json.loads(json.dumps(canonical))
            historical["source"]["sourceArchiveDigest"] = DIGEST
            historical = finalizer.seal_manifest(historical)
            finalizer.validate_manifest(historical)

            canonical["source"]["repository"] = "tampered/repo"
            with self.assertRaisesRegex(
                ValueError, "releaseTrainId mismatch|digest mismatch"
            ):
                finalizer.validate_manifest(canonical)

    def test_receipts_fail_closed_on_source_tree_and_lifecycle_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact, candidate = self._candidate_manifest(root)
            prod_dir = root / "prod-too-early"
            receipt = self._receipt(
                root, candidate, kind="environment", environment="prod"
            )
            self._write_json(
                prod_dir / "prod.json",
                json.loads(receipt.read_text(encoding="utf-8")),
            )
            with self.assertRaisesRegex(
                ValueError, "prod receipt requires a previously deployable snapshot"
            ):
                finalizer.finalize(
                    artifact,
                    None,
                    environment_receipts_dir=prod_dir,
                )
            self.assertFalse(
                (artifact / "evidence/receipts/environment/prod.json").exists()
            )

            alpha_dir = root / "wrong-tree"
            wrong_tree = json.loads(
                self._receipt(
                    root, candidate, kind="environment", environment="alpha"
                ).read_text(encoding="utf-8")
            )
            wrong_tree["sourceTreeDigest"] = "sha1:" + ("d" * 40)
            self._write_json(alpha_dir / "alpha.json", wrong_tree)
            with self.assertRaisesRegex(ValueError, "source tree mismatch"):
                finalizer.finalize(
                    artifact,
                    None,
                    environment_receipts_dir=alpha_dir,
                )
            self.assertFalse(
                (artifact / "evidence/receipts/environment/alpha.json").exists()
            )

    def test_real_rollback_has_independent_terminal_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact, candidate = self._candidate_manifest(root)
            deployable = self._deployable_manifest(root, artifact, candidate)
            prod_dir = root / "prod-receipts"
            prod = self._receipt(
                root, deployable, kind="environment", environment="prod"
            )
            self._write_json(
                prod_dir / "prod.json",
                json.loads(prod.read_text(encoding="utf-8")),
            )
            rollout = self._receipt(
                root,
                deployable,
                kind="rollout",
                environment="prod",
                status="failed",
            )
            rollback = self._receipt(
                root,
                deployable,
                kind="rollback",
                environment="prod",
                status="rolled_back",
            )
            rolled_back = finalizer.finalize(
                artifact,
                None,
                environment_receipts_dir=prod_dir,
                rollout_receipt_path=rollout,
                rollback_receipt_path=rollback,
            )
            self.assertEqual(rolled_back["status"], "rolled-back")
            self.assertEqual(rolled_back["candidateId"], candidate["candidateId"])
            self.assertEqual(rolled_back["missingEvidence"], [])
            self.assertEqual(rolled_back["blockers"], ["candidate-rolled-back"])

    def test_provider_evidence_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = self._build_input(root)
            manifest = json.loads(
                (artifact / "manifest.json").read_text(encoding="utf-8")
            )
            digest = DIGEST
            repository = manifest["environmentArtifacts"]["alpha"]["images"][
                "content-service"
            ]["repository"]
            transport = manifest["environmentArtifacts"]["alpha"]["images"][
                "content-service"
            ]["transportRef"]
            ref = f"{repository}@{digest}"
            descriptor_dir = root / "images"
            for index, environment in enumerate(finalizer.ENVIRONMENTS, start=1):
                image = manifest["environmentArtifacts"][environment]["images"][
                    "content-service"
                ]
                environment_digest = f"sha256:{index:064x}"
                environment_ref = f"{image['repository']}@{environment_digest}"
                self._write_json(
                    descriptor_dir / environment / "content-service.json",
                    {
                        "environment": environment,
                        "runtimeImageOwner": "content-service",
                        "repository": image["repository"],
                        "transportRef": image["transportRef"],
                        "digest": environment_digest,
                        "ref": environment_ref,
                        "attestations": {
                            "spdxSbom": f"oci://{environment_ref}#spdxSbom",
                            "slsaProvenance": f"oci://{environment_ref}#slsaProvenance",
                        },
                    },
                )
            finalizer.finalize(artifact, descriptor_dir)
            sources = self._evidence_sources(root)
            provider = json.loads(
                sources["providerEvidence"].read_text(encoding="utf-8")
            )
            provider["readiness"]["prod"]["search"]["capability_ready"] = False
            self._write_json(sources["providerEvidence"], provider)
            with self.assertRaisesRegex(
                ValueError, "readiness.prod must contain only required ready capabilities"
            ):
                evidence_collector.collect(
                    artifact_dir=artifact,
                    descriptors_dir=root / "evidence-descriptors",
                    sources=sources,
                    application_package_sources=self._application_package_sources(
                        root, artifact
                    ),
                    application_package_payloads=evidence_collector.load_application_package_payloads(
                        self._application_package_payloads(root)
                    ),
                    application_evidence_ref=APP_EVIDENCE_REF,
                    provider_raw_dir=self._provider_raw_dir(root),
                )

    def test_static_provider_governance_cannot_be_release_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = self._build_input(root)
            manifest = json.loads(
                (artifact / "manifest.json").read_text(encoding="utf-8")
            )
            descriptor_dir = root / "images"
            for index, environment in enumerate(finalizer.ENVIRONMENTS, start=1):
                image = manifest["environmentArtifacts"][environment]["images"][
                    "content-service"
                ]
                environment_digest = f"sha256:{index:064x}"
                environment_ref = f"{image['repository']}@{environment_digest}"
                self._write_json(
                    descriptor_dir / environment / "content-service.json",
                    {
                        "environment": environment,
                        "runtimeImageOwner": "content-service",
                        "repository": image["repository"],
                        "transportRef": image["transportRef"],
                        "digest": environment_digest,
                        "ref": environment_ref,
                        "attestations": {
                            "spdxSbom": f"oci://{environment_ref}#spdxSbom",
                            "slsaProvenance": f"oci://{environment_ref}#slsaProvenance",
                        },
                    },
                )
            finalizer.finalize(artifact, descriptor_dir)
            sources = self._evidence_sources(root)
            self._write_json(
                sources["providerEvidence"],
                {
                    "schema": "compiled-external-provider-bindings",
                    "capabilityCount": 1,
                    "adapterCount": 1,
                },
            )
            with self.assertRaisesRegex(ValueError, "providerEvidence schema mismatch"):
                evidence_collector.collect(
                    artifact_dir=artifact,
                    descriptors_dir=root / "evidence-descriptors",
                    sources=sources,
                    application_package_sources=self._application_package_sources(
                        root, artifact
                    ),
                    application_package_payloads=evidence_collector.load_application_package_payloads(
                        self._application_package_payloads(root)
                    ),
                    application_evidence_ref=APP_EVIDENCE_REF,
                    provider_raw_dir=self._provider_raw_dir(root),
                )

    def test_bound_evidence_files_reject_symlink_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = self._build_input(root)
            manifest = json.loads(
                (artifact / "manifest.json").read_text(encoding="utf-8")
            )
            config = artifact / manifest["environmentArtifacts"]["alpha"][
                "configurationPackages"
            ]["content-service"]["path"]
            outside = root / "outside.yaml"
            outside.write_text("config: escaped\n", encoding="utf-8")
            config.unlink()
            config.symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "escapes the release evidence root"):
                finalizer.validate_manifest_files(artifact, manifest)

    def test_provider_raw_archive_remains_digest_bound_after_candidate_sealing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact, manifest = self._candidate_manifest(root)
            raw_files = sorted((artifact / "evidence/raw/provider").rglob("*.json"))
            self.assertTrue(raw_files)
            raw_files[0].write_text('{"status":"tampered"}\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "raw file digest mismatch"):
                finalizer.validate_manifest_files(artifact, manifest)


if __name__ == "__main__":
    unittest.main()
