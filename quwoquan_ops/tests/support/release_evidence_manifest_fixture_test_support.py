"""发布证据清单用例的 fixture 构造 mixin。

把 build input、Provider conformance 逐格证据、application package payload、
receipt 与候选/可部署清单的构造集中在一处，让用例模块只留断言。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest import mock

from quwoquan_ops.ci.render_provider_conformance_source import (
    expected_required_cell_count_from_readiness,
)
from quwoquan_ops.cli.lib import provider_conformance
from quwoquan_ops.cli.prod import collect_mainline_image_descriptors as image_collector
from quwoquan_ops.cli.prod import collect_release_artifact_descriptors as evidence_collector
from quwoquan_ops.cli.prod import finalize_mainline_release_artifact as finalizer
from quwoquan_ops.cli.lib.app_identity import resolve_build_product
from quwoquan_ops.tests.support.app_artifact_manifest_test_support import (
    app_artifact_manifest,
)

DIGEST = "sha256:" + ("a" * 64)
APP_EVIDENCE_REF = "oci://ghcr.io/owner/repo/app-candidate@" + DIGEST
PROVIDER_EVIDENCE_DIGEST = "sha256:" + ("e" * 64)
PROVIDER_EVIDENCE_REF = (
    "oci://ghcr.io/owner/repo/provider-evidence@" + PROVIDER_EVIDENCE_DIGEST
)


class ReleaseEvidenceManifestFixtureMixin:
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
                "releaseTrainId": None,
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
                "environmentArtifacts": {
                    environment: {
                        "environment": environment,
                        "environmentArtifactDigest": None,
                        "images": {
                            "content-service": {
                                "repository": (
                                    "ghcr.io/owner/repo/content-service-"
                                    + ("prod" if environment == "prod" else "nonprod")
                                ),
                                "transportRef": (
                                    "ghcr.io/owner/repo/content-service-"
                                    + ("prod" if environment == "prod" else "nonprod")
                                    + ":sha-"
                                    + ("b" * 40)
                                ),
                            }
                        },
                        "configurationPackages": configuration_packages[environment],
                    }
                    for environment in finalizer.ENVIRONMENTS
                },
                "applicationPackages": {},
                "opsPortal": None,
                "contractGraphDigest": None,
                "requiredEvidence": {
                    "environmentArtifacts": {
                        environment: ["content-service"]
                        for environment in finalizer.ENVIRONMENTS
                    },
                    "configurationPackages": {
                        environment: ["content-service"]
                        for environment in finalizer.ENVIRONMENTS
                    },
                    "applicationPackages": list(finalizer.APPLICATION_PACKAGES),
                    "opsPortal": True,
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
                    *(
                        f"environmentArtifacts.{environment}.images.content-service.digest"
                        for environment in finalizer.ENVIRONMENTS
                    ),
                    *(
                        f"applicationPackages.{build_product_id}"
                        for build_product_id in finalizer.APPLICATION_PACKAGES
                    ),
                    "opsPortal",
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
        portal_payload = payloads / "opsPortal"
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
                    "schema": "client-app.web.official-release",
                    "sourceGitSha": source["gitSha"],
                    "sourceTreeDigest": source["treeDigest"],
                },
            ),
            "androidOfficialRelease": self._write_json(
                root / "sources/android.json",
                {
                    "schema": "client-app.android.official-release",
                    "sourceGitSha": source["gitSha"],
                    "sourceTreeDigest": source["treeDigest"],
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
                        "environmentArtifacts": {
                            environment: {
                                "environmentArtifactDigest": artifact[
                                    "environmentArtifactDigest"
                                ],
                                "images": {
                                    owner: descriptor["digest"]
                                    for owner, descriptor in artifact["images"].items()
                                },
                            }
                            for environment, artifact in manifest[
                                "environmentArtifacts"
                            ].items()
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
        application_material = {
            build_product_id: finalizer.application_package_digest(
                json.loads(source_path.read_text(encoding="utf-8"))
            )
            for build_product_id, source_path in application_sources.items()
        }
        test_payload = json.loads(sources["testEvidence"].read_text(encoding="utf-8"))
        test_payload["layers"]["user_acceptance"]["candidateMaterial"] = {
            "environmentArtifacts": {
                environment: {
                    "environmentArtifactDigest": artifact[
                        "environmentArtifactDigest"
                    ],
                    "images": {
                        owner: descriptor["digest"]
                        for owner, descriptor in artifact["images"].items()
                    },
                    "configurationPackages": {
                        service: descriptor["digest"]
                        for service, descriptor in artifact[
                            "configurationPackages"
                        ].items()
                    },
                }
                for environment, artifact in manifest[
                    "environmentArtifacts"
                ].items()
            },
            "applicationPackages": application_material,
            "opsPortal": finalizer.application_package_digest(
                json.loads(sources["opsPortal"].read_text(encoding="utf-8"))
            ),
            "contractGraphDigest": finalizer.sha256_file(contract_graph),
        }
        self._write_json(sources["testEvidence"], test_payload)
        return sources

    def _application_package_payloads(self, root: Path) -> Path:
        payloads = root / "application-payloads"
        for build_product_id in finalizer.APPLICATION_PACKAGES:
            package = payloads / build_product_id
            package.mkdir(parents=True, exist_ok=True)
            (package / "payload.bin").write_bytes(build_product_id.encode("utf-8"))
        portal = payloads / "opsPortal"
        self._write_json(portal / "manifest.json", {"name": "ops"})
        (portal / "dist").mkdir(exist_ok=True)
        (portal / "dist/index.html").write_text("ops portal", encoding="utf-8")
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
    ) -> dict[str, Path]:
        manifest = json.loads(
            (artifact / "manifest.json").read_text(encoding="utf-8")
        )
        source = manifest["source"]
        payloads = self._application_package_payloads(root)
        result: dict[str, Path] = {}
        for build_product_id in sorted(evidence_collector.GENERIC_APPLICATION_KEYS):
            package_digest = finalizer.sha256_tree(
                payloads / build_product_id
            )
            product = resolve_build_product(build_product_id)
            result[build_product_id] = self._write_json(
                root / "application-sources" / f"{build_product_id}.json",
                {
                    "schema": evidence_collector.GENERIC_APPLICATION_SCHEMA,
                    "buildProductId": build_product_id,
                    "buildProfile": product.build_profile,
                    "platform": product.platform,
                    "sourceGitSha": source["gitSha"],
                    "sourceTreeDigest": source["treeDigest"],
                    "packageDigest": package_digest,
                    "artifactManifest": app_artifact_manifest(
                        build_product_id=build_product_id,
                        source_git_sha=source["gitSha"],
                        source_tree_digest=source["treeDigest"],
                        artifact_digest=package_digest,
                    ),
                },
            )
        return result

    def _candidate_manifest(self, root: Path) -> tuple[Path, dict[str, object]]:
        artifact = self._build_input(root)
        image_descriptors = root / "image-descriptors"

        def resolve_digest(ref: str) -> str:
            return (
                f"sha256:{2:064x}"
                if "-prod:" in ref
                else f"sha256:{1:064x}"
            )

        with (
            mock.patch.object(
                image_collector,
                "resolve_registry_digest",
                side_effect=resolve_digest,
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
