# spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md#sit-004
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from quwoquan_ops.cli.prod import collect_release_artifact_descriptors as collector
from quwoquan_ops.cli.prod import finalize_mainline_release_artifact as finalizer
from quwoquan_ops.cli import stackctl


DIGEST = "sha256:" + ("a" * 64)
APP_EVIDENCE_REF = "oci://ghcr.io/owner/repo/app-candidate@" + DIGEST


class ReleaseArtifactCollectionContractTest(unittest.TestCase):
    def _write_json(self, path: Path, payload: dict[str, object]) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return path

    def _fixture(self, root: Path) -> tuple[Path, dict[str, Path]]:
        artifact = root / "artifact"
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
        repository = "ghcr.io/owner/repo/content-service"
        ref = f"{repository}@{DIGEST}"
        manifest = finalizer.seal_manifest(
            {
                "schema": finalizer.SCHEMA,
                "candidateId": None,
                "status": "component-ready",
                "generatedAt": "2026-07-28T00:00:00Z",
                "source": {
                    "gitSha": "a" * 40,
                    "treeDigest": "sha1:" + ("b" * 40),
                    "repository": "owner/repo",
                    "workflowRunId": "42",
                    "sourceArchiveDigest": None,
                },
                "artifactDigest": None,
                "images": {
                    "content-service": {
                        "repository": repository,
                        "transportRef": repository + ":sha-candidate",
                        "digest": DIGEST,
                        "ref": ref,
                        "attestations": {
                            "spdxSbom": f"oci://{ref}#spdxSbom",
                            "slsaProvenance": f"oci://{ref}#slsaProvenance",
                        },
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
                "blockers": ["whole-application-evidence-pending"],
                "missingEvidence": [
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
        self._write_json(
            artifact / "manifest.json",
            manifest,
        )
        payloads = self._application_package_payloads(root)
        source_identity = manifest["source"]
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
        provider_raw = self._write_json(
            root / "provider-raw/env/prod/runs/fixture/provider.json",
            {"schema": "provider-conformance-evidence", "status": "passed"},
        )
        sources = {
            "publicWeb": self._write_json(
                root / "sources/web.json",
                {
                    "schema": "qwq.public-web.release",
                    "sourceGitSha": source_identity["gitSha"],
                    "sourceTreeDigest": source_identity["treeDigest"],
                    "contentSHA256": finalizer.sha256_tree(
                        payloads / "prod/web"
                    ).removeprefix("sha256:"),
                },
            ),
            "androidOfficialRelease": self._write_json(
                root / "sources/android.json",
                {
                    "schema": "qwq.android.official-release",
                    "sourceGitSha": source_identity["gitSha"],
                    "sourceTreeDigest": source_identity["treeDigest"],
                    "packagedAPK": "quwoquan.apk",
                    "apkSHA256": finalizer.sha256_file(
                        payloads / "prod/android/quwoquan.apk"
                    ).removeprefix("sha256:"),
                },
            ),
            "opsPortal": self._write_json(
                root / "sources/portal.json",
                {
                    "schema": "qwq.ops_portal_package",
                    "sourceGitSha": source_identity["gitSha"],
                    "sourceTreeDigest": source_identity["treeDigest"],
                    "packageDigest": finalizer.sha256_ops_portal_tree(
                        payloads / "prod/opsPortal/dist"
                    ),
                    "digests": {
                        "manifest": finalizer.sha256_file(
                            payloads / "prod/opsPortal/manifest.json"
                        ),
                        "distTree": finalizer.sha256_ops_portal_tree(
                            payloads / "prod/opsPortal/dist"
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
                        key: source_identity[key]
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
                        "ref": "oci://ghcr.io/owner/repo/provider-evidence@" + DIGEST,
                        "digest": DIGEST,
                        "files": {
                            "evidence/raw/provider/env/prod/runs/fixture/provider.json": finalizer.sha256_file(
                                provider_raw
                            )
                        },
                    },
                    "evidenceCount": 1,
                    "readiness": {
                        "prod": {
                            "search": {
                                "required": True,
                                "capability_ready": True,
                            }
                        }
                    },
                },
            ),
            "testEvidence": self._write_json(
                root / "sources/test-evidence.json",
                {
                    "schema": "qwq.three-layer-case-results",
                    "status": "passed",
                    "layers": {
                        layer: {"status": "passed", "artifactDigest": DIGEST}
                        for layer in (
                            "local_contract",
                            "api_integration",
                            "user_acceptance",
                        )
                    },
                },
            ),
        }
        application_sources = self._application_package_sources(root, artifact)
        application_material: dict[str, dict[str, str]] = {
            environment: {} for environment in finalizer.ENVIRONMENTS
        }
        special_sources = {
            target: artifact_id
            for artifact_id, target in collector.APPLICATION_SOURCE_TARGETS.items()
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
        return artifact, sources

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

    def _application_package_sources(
        self, root: Path, artifact: Path
    ) -> dict[tuple[str, str], Path]:
        manifest = json.loads(
            (artifact / "manifest.json").read_text(encoding="utf-8")
        )
        source = manifest["source"]
        payloads = self._application_package_payloads(root)
        return {
            (environment, surface): self._write_json(
                root / "application-sources" / f"{environment}--{surface}.json",
                {
                    "schema": collector.GENERIC_APPLICATION_SCHEMA,
                    "environment": environment,
                    "surface": surface,
                    "sourceGitSha": source["gitSha"],
                    "sourceTreeDigest": source["treeDigest"],
                    "packageDigest": finalizer.sha256_tree(
                        payloads / environment / surface
                    ),
                },
            )
            for environment, surface in sorted(collector.GENERIC_APPLICATION_KEYS)
        }

    def test_collects_complete_four_environment_evidence_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact, sources = self._fixture(root)
            descriptors = root / "descriptors"
            first = collector.collect(
                artifact_dir=artifact,
                descriptors_dir=descriptors,
                sources=sources,
                application_package_sources=self._application_package_sources(
                    root, artifact
                ),
                application_package_payloads=collector.load_application_package_payloads(
                    self._application_package_payloads(root)
                ),
                application_evidence_ref=APP_EVIDENCE_REF,
                provider_raw_dir=root / "provider-raw",
            )
            second = collector.collect(
                artifact_dir=artifact,
                descriptors_dir=descriptors,
                sources=sources,
                application_package_sources=self._application_package_sources(
                    root, artifact
                ),
                application_package_payloads=collector.load_application_package_payloads(
                    self._application_package_payloads(root)
                ),
                application_evidence_ref=APP_EVIDENCE_REF,
                provider_raw_dir=root / "provider-raw",
            )
            self.assertEqual(first, second)
            self.assertEqual(
                set(first),
                {
                    *finalizer.REQUIRED_RELEASE_EVIDENCE,
                    *(f"{environment}/{surface}" for environment in finalizer.ENVIRONMENTS for surface in finalizer.APPLICATION_PACKAGES[environment]),
                },
            )
            for artifact_id, descriptor in first.items():
                if "evidenceKey" in descriptor:
                    self.assertEqual(descriptor["evidenceKey"], artifact_id)
                else:
                    self.assertEqual(descriptor["sourceRef"], APP_EVIDENCE_REF)
                    self.assertRegex(
                        descriptor["packageDigest"], r"^sha256:[0-9a-f]{64}$"
                    )
                self.assertRegex(descriptor["digest"], r"^sha256:[0-9a-f]{64}$")
            finalized = finalizer.finalize(artifact, None, descriptors)
            self.assertEqual(finalized["status"], "candidate-ready")
            self.assertEqual(
                set(finalized["applicationPackages"]),
                set(finalizer.ENVIRONMENTS),
            )

    def test_rejects_mutable_application_evidence_locator(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact, sources = self._fixture(root)
            with self.assertRaisesRegex(ValueError, "immutable OCI digest ref"):
                collector.collect(
                    artifact_dir=artifact,
                    descriptors_dir=root / "descriptors",
                    sources=sources,
                    application_package_sources=self._application_package_sources(
                        root, artifact
                    ),
                    application_package_payloads=collector.load_application_package_payloads(
                        self._application_package_payloads(root)
                    ),
                    application_evidence_ref="oci://ghcr.io/owner/repo/app:latest",
                    provider_raw_dir=root / "provider-raw",
                )

    def test_rejects_failed_or_incomplete_test_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact, sources = self._fixture(root)
            self._write_json(
                sources["testEvidence"],
                {
                    "schema": "qwq.three-layer-case-results",
                    "status": "blocked",
                    "layers": {},
                },
            )
            with self.assertRaisesRegex(ValueError, "status must be passed"):
                collector.collect(
                    artifact_dir=artifact,
                    descriptors_dir=root / "descriptors",
                    sources=sources,
                    application_package_sources=self._application_package_sources(
                        root, artifact
                    ),
                    application_package_payloads=collector.load_application_package_payloads(
                        self._application_package_payloads(root)
                    ),
                    application_evidence_ref=APP_EVIDENCE_REF,
                    provider_raw_dir=root / "provider-raw",
                )

    def test_application_package_evidence_is_complete_and_source_bound(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact, sources = self._fixture(root)
            application_sources = self._application_package_sources(root, artifact)
            missing_key = ("beta", "ios")
            missing_source = application_sources.pop(missing_key)
            with self.assertRaisesRegex(
                ValueError, "generic application package set mismatch"
            ):
                collector.collect(
                    artifact_dir=artifact,
                    descriptors_dir=root / "descriptors",
                    sources=sources,
                    application_package_sources=application_sources,
                    application_package_payloads=collector.load_application_package_payloads(
                        self._application_package_payloads(root)
                    ),
                    application_evidence_ref=APP_EVIDENCE_REF,
                    provider_raw_dir=root / "provider-raw",
                )
            application_sources[missing_key] = missing_source
            payload = json.loads(missing_source.read_text(encoding="utf-8"))
            payload["sourceTreeDigest"] = "sha1:" + ("d" * 40)
            self._write_json(missing_source, payload)
            with self.assertRaisesRegex(ValueError, "tree mismatch"):
                collector.collect(
                    artifact_dir=artifact,
                    descriptors_dir=root / "descriptors",
                    sources=sources,
                    application_package_sources=application_sources,
                    application_package_payloads=collector.load_application_package_payloads(
                        self._application_package_payloads(root)
                    ),
                    application_evidence_ref=APP_EVIDENCE_REF,
                    provider_raw_dir=root / "provider-raw",
                )

    def test_stackctl_is_the_whole_app_assembly_entrypoint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact, sources = self._fixture(root)
            self._application_package_sources(root, artifact)
            args = stackctl.build_parser().parse_args(
                [
                    "package",
                    "--env",
                    "prod",
                    "--target",
                    "prod-hosted",
                    "--kind",
                    "release-manifest",
                    "--release-artifact-dir",
                    str(artifact),
                    "--application-packages-dir",
                    str(root / "application-sources"),
                    "--application-package-payloads-dir",
                    str(root / "application-payloads"),
                    "--public-web-manifest",
                    str(sources["publicWeb"]),
                    "--android-release-manifest",
                    str(sources["androidOfficialRelease"]),
                    "--ops-portal-provenance",
                    str(sources["opsPortal"]),
                    "--contract-graph",
                    str(sources["contractGraph"]),
                    "--provider-evidence",
                    str(sources["providerEvidence"]),
                    "--provider-raw-dir",
                    str(root / "provider-raw"),
                    "--application-evidence-ref",
                    APP_EVIDENCE_REF,
                    "--test-evidence",
                    str(sources["testEvidence"]),
                    "--report-dir",
                    str(root / "report"),
                ]
            )
            result = stackctl.command_package(args)
            self.assertEqual(result["exitCode"], 0, result)
            manifest = json.loads(
                (artifact / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["status"], "candidate-ready")
            self.assertIn(
                "environment-qualification-evidence-pending",
                manifest["blockers"],
            )

    def test_rejects_schema_drift_and_non_component_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact, sources = self._fixture(root)
            application_sources = self._application_package_sources(root, artifact)
            self._write_json(sources["publicWeb"], {"schema": "placeholder"})
            with self.assertRaisesRegex(ValueError, "publicWeb schema mismatch"):
                collector.collect(
                    artifact_dir=artifact,
                    descriptors_dir=root / "descriptors",
                    sources=sources,
                    application_package_sources=application_sources,
                    application_package_payloads=collector.load_application_package_payloads(
                        self._application_package_payloads(root)
                    ),
                    application_evidence_ref=APP_EVIDENCE_REF,
                    provider_raw_dir=root / "provider-raw",
                )
            self._write_json(
                artifact / "manifest.json",
                {"schema": "mainline-release-artifact", "status": "deployable"},
            )
            with self.assertRaisesRegex(ValueError, "fields mismatch"):
                collector.collect(
                    artifact_dir=artifact,
                    descriptors_dir=root / "descriptors",
                    sources=sources,
                    application_package_sources=application_sources,
                    application_package_payloads=collector.load_application_package_payloads(
                        self._application_package_payloads(root)
                    ),
                    application_evidence_ref=APP_EVIDENCE_REF,
                    provider_raw_dir=root / "provider-raw",
                )


if __name__ == "__main__":
    unittest.main()
