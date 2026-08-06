# spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md#sit-004
from __future__ import annotations

import json
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.ci.render_provider_conformance_source import (
    expected_required_cell_count_from_readiness,
)
from quwoquan_ops.cli.lib import provider_conformance
from quwoquan_ops.cli.prod import collect_mainline_image_descriptors as image_collector
from quwoquan_ops.cli.prod import collect_release_artifact_descriptors as evidence_collector
from quwoquan_ops.cli.prod import finalize_mainline_release_artifact as finalizer
from quwoquan_ops.cli.prod import load_prod_plane_images


DIGEST = "sha256:" + ("a" * 64)
APP_EVIDENCE_REF = "oci://ghcr.io/owner/repo/app-candidate@" + DIGEST
PROVIDER_EVIDENCE_DIGEST = "sha256:" + ("e" * 64)
PROVIDER_EVIDENCE_REF = (
    "oci://ghcr.io/owner/repo/provider-evidence@" + PROVIDER_EVIDENCE_DIGEST
)


class ReleaseEvidenceManifestCanonicalContractTest(unittest.TestCase):
    def _write_json(self, path: Path, payload: dict[str, object]) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return path

    def _provider_raw_dir(self, root: Path) -> Path:
        return root / "provider-raw"

    def _build_input(self, root: Path) -> Path:
        artifact = root / "release"
        configuration_packages: dict[str, dict[str, dict[str, str]]] = {}
        for environment in finalizer.ENVIRONMENTS:
            config = (
                artifact
                / "packages/environments"
                / environment
                / "services/content-service/config/config.yaml"
            )
            config.parent.mkdir(parents=True, exist_ok=True)
            config.write_text(
                f"config:\n  environment: {environment}\n", encoding="utf-8"
            )
            configuration_packages[environment] = {
                "content-service": {
                    "path": config.relative_to(artifact).as_posix(),
                    "digest": finalizer.sha256_file(config),
                }
            }
        manifest = finalizer.seal_manifest(
            {
                "schema": finalizer.SCHEMA,
                "candidateId": None,
                "status": "build-input",
                "generatedAt": "2026-07-28T00:00:00Z",
                "source": {
                    "gitSha": "b" * 40,
                    "treeDigest": "sha1:" + ("c" * 40),
                    "repository": "owner/repo",
                    "workflowRunId": "42",
                    "sourceArchiveDigest": None,
                },
                "artifactDigest": None,
                "images": {
                    "content-service": {
                        "repository": "ghcr.io/owner/repo/content-service",
                        "transportRef": (
                            "ghcr.io/owner/repo/content-service:sha-" + ("b" * 40)
                        ),
                    }
                },
                "configurationPackages": configuration_packages,
                "applicationPackages": {
                    environment: {} for environment in finalizer.ENVIRONMENTS
                },
                "contractGraphDigest": None,
                "requiredEvidence": {
                    "images": ["content-service"],
                    "configurationPackages": {
                        environment: ["content-service"]
                        for environment in finalizer.ENVIRONMENTS
                    },
                    "applicationPackages": {
                        environment: list(finalizer.APPLICATION_PACKAGES[environment])
                        for environment in finalizer.ENVIRONMENTS
                    },
                    "contractGraphDigest": True,
                    "providerEvidence": True,
                    "testEvidence": list(finalizer.TEST_LAYERS),
                    "environmentReceipts": list(finalizer.ENVIRONMENTS),
                    "rolloutReceipt": True,
                    "rollbackReceipt": True,
                },
                "testEvidence": {},
                "providerEvidence": {},
                "environmentReceipts": {},
                "rolloutReceipt": None,
                "rollbackReceipt": None,
                "blockers": [
                    "immutable-image-evidence-pending",
                    "whole-application-evidence-pending",
                ],
                "missingEvidence": [
                    "images.content-service.digest",
                    *(
                        f"applicationPackages.{environment}.{surface}"
                        for environment in finalizer.ENVIRONMENTS
                        for surface in finalizer.APPLICATION_PACKAGES[environment]
                    ),
                    "contractGraphDigest",
                    "providerEvidence",
                    "testEvidence",
                    *(f"environmentReceipts.{environment}" for environment in finalizer.ENVIRONMENTS),
                    "rollbackReceipt.ready",
                    "rolloutReceipt",
                    "rollbackReceipt.outcome",
                ],
            }
        )
        finalizer.validate_manifest(manifest, allowed_statuses={"build-input"})
        self._write_json(artifact / "manifest.json", manifest)
        return artifact

    def _evidence_sources(self, root: Path) -> dict[str, Path]:
        payloads = self._application_package_payloads(root)
        web_payload = payloads / "prod/web"
        android_payload = payloads / "prod/android"
        portal_payload = payloads / "prod/opsPortal"
        manifest = json.loads(
            (root / "release/manifest.json").read_text(encoding="utf-8")
        )
        source = manifest["source"]
        contract_graph = self._write_json(
            root / "sources/contract-graph.json",
            {
                "schema": "qwq.contract-graph",
                "sources": [],
                "documents": [],
                "objects": [],
                "operations": [],
                "projections": [],
            },
        )
        provider_readiness = {
            environment: {
                capability_id: {
                    "required": True,
                    "capability_ready": True,
                }
                for capability_id in ("search", "fixture-message-transport")
            }
            for environment in provider_conformance.READINESS_ENVIRONMENTS
        }
        provider_cells = sorted(
            provider_conformance.expected_required_cell_keys(
                {
                    "providerConformanceCapabilityIds": sorted(
                        provider_readiness["prod"]
                    )
                }
            )
        )
        provider_evidence_count = expected_required_cell_count_from_readiness(
            provider_readiness
        )
        self.assertEqual(len(provider_cells), provider_evidence_count)
        provider_files: dict[str, str] = {}
        for index, (capability_id, environment, layer) in enumerate(provider_cells):
            relative = (
                f"env/{environment}/runs/provider-check-{index:03d}/"
                "provider-conformance.evidence.json"
            )
            provider_raw = self._write_json(
                self._provider_raw_dir(root) / relative,
                {
                    "provider": capability_id,
                    "environment": environment,
                    "testLayer": layer,
                    "status": "passed",
                },
            )
            provider_files[f"evidence/raw/provider/{relative}"] = (
                finalizer.sha256_file(provider_raw)
            )
        release_closure_files: dict[str, dict[str, str]] = {}
        for index, (label, relative) in enumerate(
            sorted(evidence_collector.RELEASE_CLOSURE_PATHS.items())
        ):
            closure_path = self._write_json(
                root / "sources" / relative,
                {"label": label, "sequence": index},
            )
            release_closure_files[label] = {
                "path": relative,
                "digest": finalizer.sha256_file(closure_path),
            }
        sources = {
            "publicWeb": self._write_json(
                root / "sources/public-web.json",
                {
                    "schema": "qwq.public-web.release",
                    "sourceGitSha": source["gitSha"],
                    "sourceTreeDigest": source["treeDigest"],
                    "contentSHA256": finalizer.sha256_tree(web_payload).removeprefix(
                        "sha256:"
                    ),
                },
            ),
            "androidOfficialRelease": self._write_json(
                root / "sources/android.json",
                {
                    "schema": "qwq.android.official-release",
                    "sourceGitSha": source["gitSha"],
                    "sourceTreeDigest": source["treeDigest"],
                    "packagedAPK": "quwoquan.apk",
                    "apkSHA256": finalizer.sha256_file(
                        android_payload / "quwoquan.apk"
                    ).removeprefix("sha256:"),
                },
            ),
            "opsPortal": self._write_json(
                root / "sources/portal.json",
                {
                    "schema": "qwq.ops_portal_package",
                    "sourceGitSha": source["gitSha"],
                    "sourceTreeDigest": source["treeDigest"],
                    "packageDigest": finalizer.sha256_ops_portal_tree(
                        portal_payload / "dist"
                    ),
                    "digests": {
                        "manifest": finalizer.sha256_file(
                            portal_payload / "manifest.json"
                        ),
                        "distTree": finalizer.sha256_ops_portal_tree(
                            portal_payload / "dist"
                        ),
                    },
                },
            ),
            "contractGraph": contract_graph,
            "providerEvidence": self._write_json(
                root / "sources/providers.json",
                {
                    "schema": "provider-conformance-readiness",
                    "status": "passed",
                    "generatedAt": "2026-07-28T00:00:00Z",
                    "source": {
                        key: source[key]
                        for key in (
                            "gitSha",
                            "treeDigest",
                            "repository",
                            "workflowRunId",
                        )
                    },
                    "candidateMaterial": {
                        "images": {
                            service: descriptor["digest"]
                            for service, descriptor in manifest["images"].items()
                        },
                        "contractGraphDigest": finalizer.sha256_file(contract_graph),
                    },
                    "sourceEvidence": {
                        "ref": PROVIDER_EVIDENCE_REF,
                        "digest": PROVIDER_EVIDENCE_DIGEST,
                        "files": provider_files,
                    },
                    "evidenceCount": provider_evidence_count,
                    "sourceCoverageIssues": [],
                    "readiness": provider_readiness,
                    "issues": [],
                },
            ),
            "testEvidence": self._write_json(
                root / "sources/tests.json",
                {
                    "schema": "qwq.three-layer-case-results",
                    "status": "passed",
                    "layers": {
                        layer: {"status": "passed", "artifactDigest": DIGEST}
                        for layer in finalizer.TEST_LAYERS
                    },
                    "evidence": {"files": release_closure_files},
                },
            ),
        }
        application_sources = self._application_package_sources(
            root, root / "release"
        )
        special_sources = {
            target: artifact_id
            for artifact_id, target in evidence_collector.APPLICATION_SOURCE_TARGETS.items()
        }
        application_material: dict[str, dict[str, str]] = {
            environment: {} for environment in finalizer.ENVIRONMENTS
        }
        for environment in finalizer.ENVIRONMENTS:
            for surface in finalizer.APPLICATION_PACKAGES[environment]:
                key = (environment, surface)
                artifact_id = special_sources.get(key)
                source_path = (
                    sources[artifact_id]
                    if artifact_id is not None
                    else application_sources[key]
                )
                application_material[environment][surface] = (
                    finalizer.application_package_digest(
                        json.loads(source_path.read_text(encoding="utf-8")),
                        environment=environment,
                        surface=surface,
                    )
                )
        test_payload = json.loads(sources["testEvidence"].read_text(encoding="utf-8"))
        test_payload["layers"]["user_acceptance"]["candidateMaterial"] = {
            "images": {
                service: descriptor["digest"]
                for service, descriptor in manifest["images"].items()
            },
            "configurationPackages": {
                environment: {
                    service: descriptor["digest"]
                    for service, descriptor in packages.items()
                }
                for environment, packages in manifest[
                    "configurationPackages"
                ].items()
            },
            "applicationPackages": application_material,
            "contractGraphDigest": finalizer.sha256_file(contract_graph),
        }
        self._write_json(sources["testEvidence"], test_payload)
        return sources

    def _application_package_payloads(self, root: Path) -> Path:
        payloads = root / "application-payloads"
        for environment in finalizer.ENVIRONMENTS:
            for surface in finalizer.APPLICATION_PACKAGES[environment]:
                package = payloads / environment / surface
                package.mkdir(parents=True, exist_ok=True)
                if environment == "prod" and surface == "android":
                    (package / "quwoquan.apk").write_bytes(b"signed-apk")
                elif environment == "prod" and surface == "opsPortal":
                    self._write_json(package / "manifest.json", {"name": "ops"})
                    (package / "dist").mkdir(exist_ok=True)
                    (package / "dist/index.html").write_text(
                        "ops portal", encoding="utf-8"
                    )
                else:
                    (package / "payload.bin").write_bytes(
                        f"{environment}/{surface}".encode("utf-8")
                    )
        return payloads

    def _receipt(
        self,
        root: Path,
        manifest: dict[str, object],
        *,
        kind: str,
        environment: str,
        status: str = "passed",
    ) -> Path:
        schema = {
            "environment": finalizer.ENVIRONMENT_RECEIPT_SCHEMA,
            "rollout": finalizer.ROLLOUT_RECEIPT_SCHEMA,
            "rollback": finalizer.ROLLBACK_RECEIPT_SCHEMA,
        }[kind]
        source = manifest["source"]
        assert isinstance(source, dict)
        raw = self._write_json(
            root
            / "release/evidence/raw/test"
            / f"{kind}-{environment}-{status}.json",
            {"kind": kind, "environment": environment, "status": status},
        )
        evidence = {
            "files": {
                "test": {
                    "path": raw.relative_to(root / "release").as_posix(),
                    "digest": finalizer.sha256_file(raw),
                }
            }
        }
        evidence_digest = "sha256:" + hashlib.sha256(
            json.dumps(
                evidence,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        return self._write_json(
            root / "receipt-inputs" / f"{kind}-{environment}-{status}.json",
            {
                "schema": schema,
                "environment": environment,
                "status": status,
                "candidateId": manifest["candidateId"],
                "sourceGitSha": source["gitSha"],
                "sourceTreeDigest": source["treeDigest"],
                "evidenceDigest": evidence_digest,
                "evidence": evidence,
                "verifiedAt": "2026-07-28T00:05:00Z",
            },
        )

    def _application_package_sources(
        self, root: Path, artifact: Path
    ) -> dict[tuple[str, str], Path]:
        manifest = json.loads(
            (artifact / "manifest.json").read_text(encoding="utf-8")
        )
        source = manifest["source"]
        payloads = self._application_package_payloads(root)
        result: dict[tuple[str, str], Path] = {}
        for environment, surface in sorted(
            evidence_collector.GENERIC_APPLICATION_KEYS
        ):
            result[(environment, surface)] = self._write_json(
                root / "application-sources" / f"{environment}--{surface}.json",
                {
                    "schema": evidence_collector.GENERIC_APPLICATION_SCHEMA,
                    "environment": environment,
                    "surface": surface,
                    "sourceGitSha": source["gitSha"],
                    "sourceTreeDigest": source["treeDigest"],
                    "packageDigest": finalizer.sha256_tree(
                        payloads / environment / surface
                    ),
                },
            )
        return result

    def _candidate_manifest(self, root: Path) -> tuple[Path, dict[str, object]]:
        artifact = self._build_input(root)
        image_descriptors = root / "image-descriptors"
        with (
            mock.patch.object(
                image_collector,
                "resolve_registry_digest",
                return_value=DIGEST,
            ),
            mock.patch.object(image_collector, "verify_oci_supply_chain"),
        ):
            image_collector.collect(
                json.loads((artifact / "manifest.json").read_text(encoding="utf-8")),
                image_descriptors,
            )
        finalizer.finalize(artifact, image_descriptors)
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
        return artifact, finalizer.finalize(artifact, None, evidence_descriptors)

    def _deployable_manifest(
        self, root: Path, artifact: Path, candidate: dict[str, object]
    ) -> dict[str, object]:
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
        return finalizer.finalize(
            artifact,
            None,
            environment_receipts_dir=preprod_receipts,
            rollback_receipt_path=rollback_ready,
        )

    def test_candidate_identity_is_stable_across_real_release_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = self._build_input(root)
            image_descriptors = root / "image-descriptors"
            with (
                mock.patch.object(
                    image_collector,
                    "resolve_registry_digest",
                    return_value=DIGEST,
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
            changed_configuration["configurationPackages"]["gamma"][
                "content-service"
            ]["digest"] = "sha256:" + ("d" * 64)
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

            transport_tag = deployable["images"]["content-service"][
                "transportRef"
            ].rsplit(":", 1)[1]
            digest, images = load_prod_plane_images._release_image_sources(
                artifact / "manifest.json",
                services=["content-service"],
                image_transport_tag=transport_tag,
            )
            self.assertEqual(digest, deployable["artifactDigest"])
            self.assertEqual(
                images["content-service"],
                deployable["images"]["content-service"]["ref"],
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
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
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
            repository = manifest["images"]["content-service"]["repository"]
            transport = manifest["images"]["content-service"]["transportRef"]
            ref = f"{repository}@{digest}"
            descriptor_dir = root / "images"
            self._write_json(
                descriptor_dir / "content-service.json",
                {
                    "service": "content-service",
                    "repository": repository,
                    "transportRef": transport,
                    "digest": digest,
                    "ref": ref,
                    "attestations": {
                        "spdxSbom": f"oci://{ref}#spdxSbom",
                        "slsaProvenance": f"oci://{ref}#slsaProvenance",
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
            repository = manifest["images"]["content-service"]["repository"]
            transport = manifest["images"]["content-service"]["transportRef"]
            ref = f"{repository}@{DIGEST}"
            descriptor_dir = root / "images"
            self._write_json(
                descriptor_dir / "content-service.json",
                {
                    "service": "content-service",
                    "repository": repository,
                    "transportRef": transport,
                    "digest": DIGEST,
                    "ref": ref,
                    "attestations": {
                        "spdxSbom": f"oci://{ref}#spdxSbom",
                        "slsaProvenance": f"oci://{ref}#slsaProvenance",
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
            config = artifact / manifest["configurationPackages"]["alpha"][
                "content-service"
            ]["path"]
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
