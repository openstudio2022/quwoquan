# spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md#sit-004
# spec_ref: specs/feature-tree/chat-conversation/realtime-call/media-infrastructure/spec.md#gwt-004
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
import unittest
import argparse
import hashlib
from pathlib import Path
from unittest.mock import patch

from quwoquan_ops.ci.render_provider_conformance_source import (
    expected_required_cell_count_from_readiness,
)
from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib import provider_conformance
from quwoquan_ops.cli.prod import collect_release_artifact_descriptors as evidence_collector
from quwoquan_ops.cli.prod import finalize_mainline_release_artifact as finalizer
from quwoquan_ops.cli.prod import generate_mainline_release_artifact as generator
from quwoquan_ops.cli.prod import hosted_release_ledger
from quwoquan_ops.tests.local_contract.rollout_stage_promotion_evidence_test_support import (
    promotion_evidence,
)


ROOT = Path(__file__).resolve().parents[3]
APP_EVIDENCE_REF = "oci://ghcr.io/example/quwoquan/app-candidate@sha256:" + ("a" * 64)
PROVIDER_EVIDENCE_DIGEST = "sha256:" + ("e" * 64)
PROVIDER_EVIDENCE_REF = (
    "oci://ghcr.io/example/quwoquan/provider-evidence@" + PROVIDER_EVIDENCE_DIGEST
)


def _git_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _write_build_input(
    artifact: Path,
    *,
    services: tuple[str, ...],
) -> dict[str, object]:
    configuration_packages: dict[str, dict[str, dict[str, str]]] = {
        environment: {} for environment in finalizer.ENVIRONMENTS
    }
    transport_tag = "sha-" + _git_head()
    images: dict[str, dict[str, str]] = {}
    for environment in finalizer.ENVIRONMENTS:
        for service in services:
            relative = (
                Path("packages/environments")
                / environment
                / "services"
                / service
                / "config/config.yaml"
            )
            path = artifact / relative
            generator.write_release_snapshot(
                path,
                generator.render_release_snapshot(service, environment),
            )
            configuration_packages[environment][service] = {
                "path": relative.as_posix(),
                "digest": generator.sha256_file(path),
            }
    for service in services:
        repository = f"ghcr.io/example/quwoquan/{service}"
        images[service] = {
            "repository": repository,
            "transportRef": f"{repository}:{transport_tag}",
        }
    manifest = finalizer.seal_manifest(
        {
            "schema": finalizer.SCHEMA,
            "candidateId": None,
            "status": "build-input",
            "generatedAt": "2026-07-28T00:00:00Z",
            "source": {
                "gitSha": _git_head(),
                "treeDigest": generator.resolve_tree_digest(_git_head()),
                "repository": "example/quwoquan",
                "workflowRunId": "1",
                "sourceArchiveDigest": None,
            },
            "artifactDigest": None,
            "images": images,
            "configurationPackages": configuration_packages,
            "applicationPackages": {
                environment: {} for environment in finalizer.ENVIRONMENTS
            },
            "contractGraphDigest": None,
            "requiredEvidence": {
                "images": list(services),
                "configurationPackages": {
                    environment: list(services)
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
                *(f"images.{service}.digest" for service in services),
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
    generator.write_json(artifact / "manifest.json", manifest)
    return manifest


def _write_image_descriptors(
    directory: Path,
    manifest: dict[str, object],
) -> None:
    for index, (service, image_value) in enumerate(
        manifest["images"].items(),
        start=1,
    ):
        image = dict(image_value)
        repository = str(image["repository"])
        digest = f"sha256:{index:064x}"
        ref = f"{repository}@{digest}"
        generator.write_json(
            directory / f"{service}.json",
            {
                "service": service,
                "repository": repository,
                "transportRef": image["transportRef"],
                "digest": digest,
                "ref": ref,
                "attestations": {
                    "spdxSbom": f"oci://{ref}#spdxSbom",
                    "slsaProvenance": f"oci://{ref}#slsaProvenance",
                },
            },
        )


def _application_package_payloads(root: Path) -> Path:
    payloads = root / "application-payloads"
    for environment in finalizer.ENVIRONMENTS:
        for surface in finalizer.APPLICATION_PACKAGES[environment]:
            package = payloads / environment / surface
            package.mkdir(parents=True, exist_ok=True)
            if environment == "prod" and surface == "android":
                (package / "quwoquan.apk").write_bytes(b"signed-apk")
            elif environment == "prod" and surface == "opsPortal":
                generator.write_json(package / "manifest.json", {"name": "ops"})
                (package / "dist").mkdir(exist_ok=True)
                (package / "dist/index.html").write_text(
                    "ops portal", encoding="utf-8"
                )
            else:
                (package / "payload.bin").write_bytes(
                    f"{environment}/{surface}".encode("utf-8")
                )
    return payloads


def _provider_raw_dir(root: Path) -> Path:
    return root / "provider-raw"


def _evidence_sources(
    root: Path, manifest: dict[str, object]
) -> dict[str, Path]:
    sources = root / "sources"
    payload_root = _application_package_payloads(root)
    source = manifest["source"]
    assert isinstance(source, dict)
    contract_graph_path = sources / "contractGraph.json"
    generator.write_json(
        contract_graph_path,
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
    if len(provider_cells) != provider_evidence_count:
        raise AssertionError("Provider fixture cell count does not match readiness")
    provider_files: dict[str, str] = {}
    for index, (capability_id, environment, layer) in enumerate(provider_cells):
        relative = (
            f"env/{environment}/runs/provider-check-{index:03d}/"
            "provider-conformance.evidence.json"
        )
        provider_raw = _provider_raw_dir(root) / relative
        generator.write_json(
            provider_raw,
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
    payloads: dict[str, dict[str, object]] = {
        "publicWeb": {
            "schema": "client-app.web.official-release",
            "sourceGitSha": source["gitSha"],
            "sourceTreeDigest": source["treeDigest"],
            "contentSHA256": finalizer.sha256_tree(
                payload_root / "prod/web"
            ).removeprefix("sha256:"),
        },
        "androidOfficialRelease": {
            "schema": "client-app.android.official-release",
            "sourceGitSha": source["gitSha"],
            "sourceTreeDigest": source["treeDigest"],
            "packagedAPK": "quwoquan.apk",
            "apkSHA256": finalizer.sha256_file(
                payload_root / "prod/android/quwoquan.apk"
            ).removeprefix("sha256:"),
        },
        "opsPortal": {
            "schema": "qwq.ops_portal_package",
            "sourceGitSha": source["gitSha"],
            "sourceTreeDigest": source["treeDigest"],
            "packageDigest": finalizer.sha256_ops_portal_tree(
                payload_root / "prod/opsPortal/dist"
            ),
            "digests": {
                "manifest": finalizer.sha256_file(
                    payload_root / "prod/opsPortal/manifest.json"
                ),
                "distTree": finalizer.sha256_ops_portal_tree(
                    payload_root / "prod/opsPortal/dist"
                ),
            },
        },
        "contractGraph": {
            "schema": "qwq.contract-graph",
            "sources": [],
            "documents": [],
            "objects": [],
            "operations": [],
            "projections": [],
        },
        "providerEvidence": {
            "schema": "provider-conformance-readiness",
            "status": "passed",
            "generatedAt": "2026-07-28T00:00:00Z",
            "source": {
                key: source[key]
                for key in ("gitSha", "treeDigest", "repository", "workflowRunId")
            },
            "candidateMaterial": {
                "images": {
                    service: descriptor["digest"]
                    for service, descriptor in manifest["images"].items()
                },
                "contractGraphDigest": finalizer.sha256_file(contract_graph_path),
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
    }
    application_material: dict[str, dict[str, str]] = {
        environment: {} for environment in finalizer.ENVIRONMENTS
    }
    for environment, surface in sorted(evidence_collector.ALL_APPLICATION_KEYS):
        special_source = next(
            (
                artifact_id
                for artifact_id, target in evidence_collector.APPLICATION_SOURCE_TARGETS.items()
                if target == (environment, surface)
            ),
            None,
        )
        application_payload = (
            payloads[special_source]
            if special_source is not None
            else {
                "packageDigest": finalizer.sha256_tree(
                    payload_root / environment / surface
                )
            }
        )
        application_material[environment][surface] = (
            evidence_collector.application_package_digest(
                application_payload,
                environment=environment,
                surface=surface,
            )
        )
    release_closure_files: dict[str, dict[str, str]] = {}
    for index, (label, relative) in enumerate(
        sorted(evidence_collector.RELEASE_CLOSURE_PATHS.items())
    ):
        closure_path = sources / relative
        generator.write_json(
            closure_path,
            {"label": label, "sequence": index},
        )
        release_closure_files[label] = {
            "path": relative,
            "digest": finalizer.sha256_file(closure_path),
        }
    payloads["testEvidence"] = {
        "schema": "qwq.three-layer-case-results",
        "status": "passed",
        "layers": {
            layer: {
                "status": "passed",
                "artifactDigest": "sha256:" + ("f" * 64),
                **(
                    {
                        "candidateMaterial": {
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
                            "contractGraphDigest": finalizer.sha256_file(
                                contract_graph_path
                            ),
                        }
                    }
                    if layer == "user_acceptance"
                    else {}
                ),
            }
            for layer in finalizer.TEST_LAYERS
        },
        "evidence": {"files": release_closure_files},
    }
    result: dict[str, Path] = {}
    for key, payload in payloads.items():
        path = contract_graph_path if key == "contractGraph" else sources / f"{key}.json"
        generator.write_json(path, payload)
        result[key] = path
    return result


def _application_package_sources(
    root: Path,
    manifest: dict[str, object],
) -> dict[tuple[str, str], Path]:
    source = manifest["source"]
    assert isinstance(source, dict)
    payloads = _application_package_payloads(root)
    result: dict[tuple[str, str], Path] = {}
    for environment, surface in sorted(evidence_collector.GENERIC_APPLICATION_KEYS):
        path = root / "application-sources" / f"{environment}--{surface}.json"
        generator.write_json(
            path,
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
        result[(environment, surface)] = path
    return result


def _write_receipt(
    path: Path,
    manifest: dict[str, object],
    *,
    kind: str,
    environment: str,
    status: str,
) -> Path:
    source = manifest["source"]
    assert isinstance(source, dict)
    fixture_root = (
        path.parent.parent if path.parent.name == "preprod-receipts" else path.parent
    )
    raw = fixture_root / "artifact/evidence/raw/release-proof.json"
    generator.write_json(raw, {"status": "passed"})
    evidence = {
        "files": {
            "releaseProof": {
                "path": raw.relative_to(fixture_root / "artifact").as_posix(),
                "digest": finalizer.sha256_file(raw),
            }
        }
    }
    evidence_digest = "sha256:" + hashlib.sha256(
        json.dumps(evidence, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    generator.write_json(
        path,
        {
            "schema": {
                "environment": finalizer.ENVIRONMENT_RECEIPT_SCHEMA,
                "rollback": finalizer.ROLLBACK_RECEIPT_SCHEMA,
            }[kind],
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
    return path


def _qualify_for_prod(
    root: Path,
    artifact: Path,
    candidate: dict[str, object],
) -> dict[str, object]:
    receipts = root / "preprod-receipts"
    for environment in finalizer.PRE_PROD_ENVIRONMENTS:
        _write_receipt(
            receipts / f"{environment}.json",
            candidate,
            kind="environment",
            environment=environment,
            status="passed",
        )
    rollback_ready = _write_receipt(
        root / "rollback-ready.json",
        candidate,
        kind="rollback",
        environment="prod",
        status="ready",
    )
    return finalizer.finalize(
        artifact,
        None,
        environment_receipts_dir=receipts,
        rollback_receipt_path=rollback_ready,
    )


class ProdReleaseTransactionContractTest(unittest.TestCase):
    def test_prod_registry_attestations_are_verified_concurrently(self) -> None:
        rendezvous = threading.Barrier(2, timeout=2)
        manifest = {
            "source": {"repository": "owner/repo"},
            "images": {
                "content-service": {
                    "ref": "ghcr.io/owner/repo/content-service@sha256:" + ("a" * 64)
                },
                "user-service": {
                    "ref": "ghcr.io/owner/repo/user-service@sha256:" + ("b" * 64)
                },
            },
        }

        def verify(*_args: object, **_kwargs: object) -> None:
            rendezvous.wait()

        with (
            patch.object(
                stackctl.oci_supply_chain,
                "verify_oci_supply_chain",
                side_effect=verify,
            ) as verify_mock,
            patch.object(stackctl, "_remaining_deadline_seconds", return_value=30),
        ):
            stackctl._verify_release_registry_attestations(
                manifest,
                deadline_epoch=100,
            )

        self.assertEqual(verify_mock.call_count, 2)

    def test_service_images_alone_are_not_marked_deployable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "artifact"
            descriptors = root / "image-descriptors"
            artifact.mkdir()
            descriptors.mkdir()
            manifest = _write_build_input(
                artifact,
                services=("content-service",),
            )
            _write_image_descriptors(descriptors, manifest)
            finalized = finalizer.finalize(artifact, descriptors)
            self.assertEqual(finalized["status"], "component-ready")
            self.assertEqual(
                finalized["applicationPackages"],
                {environment: {} for environment in finalizer.ENVIRONMENTS},
            )
            self.assertIn("whole-application-evidence-pending", finalized["blockers"])

    def test_manifest_requires_every_digest_and_attestation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "artifact"
            descriptors = root / "descriptors"
            artifact_descriptors = root / "artifact-descriptors"
            artifact.mkdir()
            descriptors.mkdir()
            artifact_descriptors.mkdir()
            manifest = _write_build_input(
                artifact,
                services=generator.DEPLOYED_SERVICES,
            )
            _write_image_descriptors(descriptors, manifest)
            component = finalizer.finalize(artifact, descriptors)
            self.assertEqual(component["status"], "component-ready")
            evidence_collector.collect(
                artifact_dir=artifact,
                descriptors_dir=artifact_descriptors,
                sources=_evidence_sources(root, component),
                application_package_sources=_application_package_sources(
                    root, component
                ),
                application_package_payloads=evidence_collector.load_application_package_payloads(
                    _application_package_payloads(root)
                ),
                application_evidence_ref=APP_EVIDENCE_REF,
                provider_raw_dir=_provider_raw_dir(root),
            )
            candidate = finalizer.finalize(artifact, None, artifact_descriptors)
            self.assertEqual(candidate["status"], "candidate-ready")
            finalized = _qualify_for_prod(root, artifact, candidate)
            self.assertEqual(finalized["status"], "deployable")
            self.assertEqual(
                set(finalized["applicationPackages"]),
                set(finalizer.ENVIRONMENTS),
            )
            generator.write_json(
                artifact / "governance-receipt.json",
                {
                    "schema": "prod-release-governance-receipt",
                    "repository": "example/quwoquan",
                    "gitSha": _git_head(),
                    "artifactDigest": finalized["artifactDigest"],
                    "approvers": ["reviewer"],
                    "distinctPrincipals": ["author", "reviewer"],
                },
            )
            path, digest, loaded = stackctl._deployable_release_manifest(
                str(artifact / "manifest.json"),
                candidate_digest=finalized["candidateId"],
            )
            self.assertEqual(path, (artifact / "manifest.json").resolve())
            self.assertEqual(digest, finalized["artifactDigest"])
            self.assertEqual(set(loaded["images"]), set(generator.DEPLOYED_SERVICES))

            first_config = artifact / next(
                iter(finalized["configurationPackages"]["prod"].values())
            )["path"]
            first_config.write_text("tampered: true\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "config digest mismatch"):
                stackctl._deployable_release_manifest(
                    str(artifact / "manifest.json"),
                    candidate_digest=finalized["candidateId"],
                )

    def test_release_ledger_is_cas_ordered_and_receipted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary).resolve()
            from_digest = "sha256:" + ("a" * 64)
            to_digest = "sha256:" + ("b" * 64)
            request = {
                "schema": hosted_release_ledger.REQUEST_SCHEMA,
                "service": "prod-stack",
                "fromCandidateDigest": from_digest,
                "toCandidateDigest": to_digest,
                "step": "0",
                "stage": "canary",
                "triggerStage": "canary",
                "fromReleaseEvidenceRef": (
                    f"ghcr.io/owner/repo/release-artifact@{from_digest}"
                ),
                "toReleaseEvidenceRef": (
                    f"ghcr.io/owner/repo/release-artifact@{to_digest}"
                ),
                "fromImageTransportTag": "sha-source",
                "toImageTransportTag": "sha-target",
                "decision": "continue",
                "rollbackOutcome": "not_triggered",
                "rollbackEvidence": {"triggered": False},
                "artifactDigest": to_digest,
                "imageDigest": to_digest,
                "configDigest": to_digest,
                "contractGraphDigest": to_digest,
                "adapterDigest": to_digest,
                "expectedGeneration": 0,
                "sloReadback": {
                    "source": "prometheus",
                    "promotionEvidence": promotion_evidence(
                        candidate_id=to_digest,
                        artifact_digest=to_digest,
                        stage="canary",
                    ),
                },
                "postChecks": [
                    {
                        "name": "health",
                        "status": "passed",
                        "receiptDigest": to_digest,
                    }
                ],
                "lastGoodCandidateDigest": from_digest,
                "verifiedAt": "2026-07-26T00:00:00+00:00",
            }
            readback = hosted_release_ledger.commit(state_dir, request)
            self.assertEqual(readback["state"]["generation"], "1")
            self.assertRegex(readback["receiptRef"], r"^receipt:hosted:[0-9a-f]{64}$")
            self.assertEqual(
                hosted_release_ledger.fetch(state_dir, "prod-stack"),
                readback,
            )
            action, generation = stackctl._validate_release_transition(
                readback["state"],
                from_candidate_digest=from_digest,
                to_candidate_digest=to_digest,
                stage="5",
            )
            self.assertEqual((action, generation), ("advance", 1))
            with self.assertRaisesRegex(RuntimeError, "CAS conflict"):
                hosted_release_ledger.commit(state_dir, request)

            receipt_path = state_dir / "receipts" / (
                readback["receipt"]["receiptId"] + ".json"
            )
            receipt_path.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "digest or ledger binding"):
                hosted_release_ledger.fetch(state_dir, "prod-stack")

    def test_release_ledger_serializes_advance_and_rollback_contention(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary).resolve()
            source = "sha256:" + ("a" * 64)
            candidate = "sha256:" + ("b" * 64)
            check = {
                "name": "health",
                "status": "passed",
                "receiptDigest": candidate,
            }
            initial = {
                "schema": hosted_release_ledger.REQUEST_SCHEMA,
                "service": "prod-stack",
                "fromCandidateDigest": source,
                "toCandidateDigest": candidate,
                "step": "0",
                "stage": "canary",
                "triggerStage": "canary",
                "fromReleaseEvidenceRef": f"ghcr.io/owner/release@{source}",
                "toReleaseEvidenceRef": f"ghcr.io/owner/release@{candidate}",
                "fromImageTransportTag": "sha-source",
                "toImageTransportTag": "sha-candidate",
                "decision": "continue",
                "rollbackOutcome": "not_triggered",
                "rollbackEvidence": {"triggered": False},
                "artifactDigest": candidate,
                "imageDigest": candidate,
                "configDigest": candidate,
                "contractGraphDigest": candidate,
                "adapterDigest": candidate,
                "expectedGeneration": 0,
                "sloReadback": {
                    "source": "prometheus",
                    "promotionEvidence": promotion_evidence(
                        candidate_id=candidate,
                        artifact_digest=candidate,
                        stage="canary",
                    ),
                },
                "postChecks": [check],
                "lastGoodCandidateDigest": source,
                "verifiedAt": "2026-07-26T00:00:00+00:00",
            }
            hosted_release_ledger.commit(state_dir, initial)

            advance = dict(initial)
            advance.update(
                {
                    "step": "5",
                    "stage": "5",
                    "triggerStage": "5",
                    "expectedGeneration": 1,
                    "verifiedAt": "2026-07-26T00:00:01+00:00",
                    "sloReadback": {
                        "source": "prometheus",
                        "promotionEvidence": promotion_evidence(
                            candidate_id=candidate,
                            artifact_digest=candidate,
                            stage="5",
                        ),
                    },
                }
            )
            rollback = dict(initial)
            rollback.update(
                {
                    "fromCandidateDigest": candidate,
                    "toCandidateDigest": source,
                    "step": "100",
                    "stage": "100",
                    "triggerStage": "canary",
                    "fromReleaseEvidenceRef": f"ghcr.io/owner/release@{candidate}",
                    "toReleaseEvidenceRef": f"ghcr.io/owner/release@{source}",
                    "fromImageTransportTag": "sha-candidate",
                    "toImageTransportTag": "sha-source",
                    "decision": "rolled_back",
                    "rollbackOutcome": "rolled_back",
                    "rollbackEvidence": {
                        "triggered": True,
                        "startedAt": "2026-07-26T00:00:00+00:00",
                        "endedAt": "2026-07-26T00:00:01+00:00",
                        "durationMs": 1000,
                        "postChecks": [check],
                    },
                    "expectedGeneration": 1,
                    "lastGoodCandidateDigest": source,
                    "verifiedAt": "2026-07-26T00:00:01+00:00",
                }
            )

            barrier = threading.Barrier(2)
            successes: list[dict[str, object]] = []
            failures: list[Exception] = []

            def contend(request: dict[str, object]) -> None:
                barrier.wait()
                try:
                    successes.append(hosted_release_ledger.commit(state_dir, request))
                except Exception as error:  # asserted as the losing CAS below
                    failures.append(error)

            threads = [
                threading.Thread(target=contend, args=(advance,)),
                threading.Thread(target=contend, args=(rollback,)),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=5)

            self.assertTrue(all(not thread.is_alive() for thread in threads))
            self.assertEqual(len(successes), 1)
            self.assertEqual(len(failures), 1)
            self.assertRegex(str(failures[0]), "CAS conflict")
            readback = hosted_release_ledger.fetch(state_dir, "prod-stack")
            self.assertEqual(readback["state"]["generation"], "2")
            self.assertIn(
                readback["state"]["decision"],
                {"continue", "rolled_back"},
            )
            self.assertEqual(len(list((state_dir / "receipts").glob("*.json"))), 2)

    def test_warning_slo_pauses_gray_but_rolls_back_full(self) -> None:
        self.assertEqual(
            stackctl._decision_from_slo_output(
                "decision=pause reason=warning_threshold",
                "canary",
            ),
            ("pause", "slo gate decision=pause"),
        )

    def test_insufficient_samples_pause_even_at_full_without_false_rollback(self) -> None:
        decision, reason = stackctl._decision_from_slo_output(
            "decision=pause reason=insufficient_samples",
            "100",
        )
        self.assertEqual(decision, "pause")
        self.assertIn("insufficient", reason)

    def test_operator_receipt_readback_accepts_only_hosted_candidate_binding(self) -> None:
        from_digest = "sha256:" + ("a" * 64)
        digest = "sha256:" + ("b" * 64)
        receipt = {
            "schema": hosted_release_ledger.RECEIPT_SCHEMA,
            "authority": hosted_release_ledger.AUTHORITY,
            "service": "prod-stack",
            "fromCandidateDigest": from_digest,
            "toCandidateDigest": digest,
            "step": "100",
            "stage": "100",
            "triggerStage": "100",
            "fromReleaseEvidenceRef": (
                f"ghcr.io/owner/repo/release-artifact@{from_digest}"
            ),
            "toReleaseEvidenceRef": (
                f"ghcr.io/owner/repo/release-artifact@{digest}"
            ),
            "fromImageTransportTag": "sha-source",
            "toImageTransportTag": "sha-target",
            "decision": "continue",
            "rollbackOutcome": "not_triggered",
            "rollbackEvidence": {"triggered": False},
            "artifactDigest": digest,
            "imageDigest": digest,
            "configDigest": digest,
            "contractGraphDigest": digest,
            "adapterDigest": digest,
            "expectedGeneration": 2,
            "committedGeneration": 3,
            "sloReadback": {
                "promotionEvidence": promotion_evidence(
                    candidate_id=digest,
                    artifact_digest=digest,
                    stage="100",
                )
            },
            "postChecks": [],
            "lastGoodCandidateDigest": digest,
            "verifiedAt": "2026-07-26T00:00:00+00:00",
        }
        receipt_id = hosted_release_ledger._receipt_id(receipt)
        receipt["receiptId"] = receipt_id
        readback = {
            "schema": hosted_release_ledger.RECEIPT_READBACK_SCHEMA,
            "authority": hosted_release_ledger.AUTHORITY,
            "receipt": receipt,
            "receiptRef": f"receipt:hosted:{receipt_id}",
        }
        args = argparse.Namespace(
            service="prod-stack",
            receipt_id=receipt_id,
            purpose="last-good",
            image_digest=digest,
            config_digest=digest,
            contract_graph_digest=digest,
            adapter_digest=digest,
            candidate_digest=digest,
        )
        with patch.object(
            stackctl,
            "_run_hosted_release_ledger",
            return_value=readback,
        ):
            result = stackctl.command_hosted_release_receipt(args)
        self.assertEqual(result["exitCode"], 0)
        self.assertEqual(result["receiptRef"], f"receipt:hosted:{receipt_id}")

        rollback_receipt = dict(receipt)
        rollback_receipt.update(
            {
                "fromCandidateDigest": digest,
                "toCandidateDigest": from_digest,
                "decision": "rolled_back",
                "rollbackOutcome": "rolled_back",
                "rollbackEvidence": {
                    "triggered": True,
                    "startedAt": "2026-07-25T23:59:58Z",
                    "endedAt": "2026-07-25T23:59:59Z",
                    "durationMs": 1000,
                    "postChecks": [
                        {
                            "name": "rollback-health",
                            "status": "passed",
                            "receiptDigest": digest,
                        }
                    ],
                },
                "lastGoodCandidateDigest": from_digest,
            }
        )
        rollback_id = hosted_release_ledger._receipt_id(rollback_receipt)
        rollback_receipt["receiptId"] = rollback_id
        rollback_readback = {
            "schema": hosted_release_ledger.RECEIPT_READBACK_SCHEMA,
            "authority": hosted_release_ledger.AUTHORITY,
            "receipt": rollback_receipt,
            "receiptRef": f"receipt:hosted:{rollback_id}",
        }
        args.receipt_id = rollback_id
        args.purpose = "rollback"
        args.candidate_digest = from_digest
        with patch.object(
            stackctl,
            "_run_hosted_release_ledger",
            return_value=rollback_readback,
        ):
            result = stackctl.command_hosted_release_receipt(args)
        self.assertEqual(result["exitCode"], 0)

        args.receipt_id = receipt_id
        args.purpose = "last-good"
        args.candidate_digest = digest
        args.adapter_digest = "sha256:" + ("c" * 64)
        with patch.object(
            stackctl,
            "_run_hosted_release_ledger",
            return_value=readback,
        ):
            result = stackctl.command_hosted_release_receipt(args)
        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(
            stackctl._decision_from_slo_output(
                "decision=pause reason=warning_threshold",
                "100",
            ),
            ("rollback", "100 rollout cannot remain paused on warning SLO"),
        )

    def test_global_release_lock_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with patch.dict(
                os.environ,
                {"QWQ_PROD_RELEASE_STATE_DIR": str(Path(temporary).resolve())},
                clear=False,
            ):
                with stackctl._prod_release_lock():
                    with self.assertRaisesRegex(RuntimeError, "lock is held"):
                        with stackctl._prod_release_lock():
                            self.fail("nested release lock must not be acquired")


if __name__ == "__main__":
    unittest.main()
