# spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/zero-risk-production-readiness/spec.md
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from collections.abc import Callable
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from quwoquan_ops.ci import render_release_lifecycle_receipts as lifecycle
from quwoquan_ops.cli.lib import external_provider_governance, provider_conformance
from quwoquan_ops.cli.lib.environment_stability_final_acceptance import (
    GITHUB_ATTESTED_WORKFLOW_BY_KIND,
    REQUIRED_SOAK_CLAIMS,
    SCHEMA_PATH,
    FinalAcceptanceInputs,
    VerifiedAuthority,
    evaluate_final_acceptance,
)
from quwoquan_ops.cli.prod.finalize_mainline_release_artifact import (
    APPLICATION_PACKAGES,
    ENVIRONMENTS,
    RELEASE_CLOSURE_PATHS,
    canonical_candidate_digest,
    canonical_manifest_digest,
    sha256_file,
    validate_manifest_files,
)
from quwoquan_ops.gate import verify_environment_stability_final_acceptance as cli

NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
OBSERVED_AT = "2026-08-04T11:55:00Z"
COMMIT = "c" * 40
TREE = "sha1:" + "d" * 40
IMAGE = "sha256:" + "1" * 64
RELEASE_ID = "20260804--travel-golden-release--pilot-003"
RELEASE_DIGEST = "sha256:" + "3" * 64
ROLLBACK_ID = "20260728--travel-golden-release--pilot-002"
ROLLBACK_DIGEST = "sha256:" + "4" * 64
OCI_DIGEST = "sha256:" + "5" * 64
TEST_DIGEST = "sha256:" + "6" * 64


def _canonical_digest(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _write(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, (dict, list)):
        content = json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"
    else:
        content = str(payload)
    path.write_text(content, encoding="utf-8")
    return path


def _checksummed(payload: dict[str, Any]) -> dict[str, Any]:
    value = deepcopy(payload)
    value["verificationChecksum"] = _canonical_digest(value)
    return value


def _trusted_attestation(
    path: Path,
    kind: str,
    manifest: dict[str, Any],
) -> VerifiedAuthority:
    repository = manifest["source"]["repository"]
    workflow = GITHUB_ATTESTED_WORKFLOW_BY_KIND[kind]
    return VerifiedAuthority(
        authority="github-actions-oidc",
        subject_digest=sha256_file(path),
        verification_digest=TEST_DIGEST,
        claims=frozenset(
            {
                "receipt_bytes",
                kind,
                f"repository:{repository}",
                f"workflow:{repository}/{workflow}",
                "issuer:https://token.actions.githubusercontent.com",
                f"candidate:{manifest['candidateId']}",
            }
        ),
    )


def _trusted_soak(
    path: Path,
    rollout_receipt: dict[str, Any],
    manifest: dict[str, Any],
) -> VerifiedAuthority:
    assert rollout_receipt["toCandidateDigest"] == manifest["candidateId"]
    return VerifiedAuthority(
        authority=lifecycle.HOSTED_AUTHORITY,
        subject_digest=sha256_file(path),
        verification_digest=TEST_DIGEST,
        claims=REQUIRED_SOAK_CLAIMS,
    )


def _reject_attestation(
    path: Path,
    kind: str,
    manifest: dict[str, Any],
) -> VerifiedAuthority:
    del path, kind, manifest
    raise RuntimeError("no trusted attestation")


def _trusted_provider(
    artifact_root: Path,
    payload: dict[str, Any],
    evidence: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> VerifiedAuthority:
    compiled, governance_issues = external_provider_governance.load_and_compile()
    assert governance_issues == []
    expected_count = len(provider_conformance.expected_required_cell_keys(compiled))
    assert len(evidence) == expected_count
    assert payload["evidenceCount"] == expected_count
    return VerifiedAuthority(
        authority="canonical-provider-conformance",
        subject_digest=sha256_file(
            artifact_root / manifest["providerEvidence"]["path"]
        ),
        verification_digest=TEST_DIGEST,
        claims=frozenset({"provider_readiness", "all_required_cells"}),
    )


class FinalAcceptanceFixture:
    def __init__(
        self,
        root: Path,
        *,
        provider_mode: str = "full",
        pilot_recorded_at: str = OBSERVED_AT,
    ) -> None:
        self.root = root
        self.artifact = root / "release-artifact"
        self.paths: dict[str, Path] = {}
        self.payloads: dict[str, dict[str, Any]] = {}
        self.provider_mode = provider_mode
        self.pilot_recorded_at = pilot_recorded_at
        self._build_bound_acceptance_inputs()
        self._build_artifact()
        self._build_external_evidence()

    def _store(
        self,
        label: str,
        path: Path,
        payload: dict[str, Any],
    ) -> Path:
        result = _write(path, payload)
        self.paths[label] = result
        self.payloads[label] = payload
        return result

    def rewrite(
        self,
        label: str,
        change: Callable[[dict[str, Any]], None],
    ) -> None:
        payload = deepcopy(self.payloads[label])
        change(payload)
        self._store(label, self.paths[label], payload)

    def _build_bound_acceptance_inputs(self) -> None:
        self._store(
            "pilot_release",
            self.artifact / "evidence/release/pilot-release-attestation.json",
            {
                "schema": "quwoquan_data.release_attestation",
                "releaseId": RELEASE_ID,
                "payloadSha256": RELEASE_DIGEST,
                "releaseClass": "commercial",
                "productLifecycleState": "commercial",
                "containsUnverifiedAssets": False,
                "authorizationRequiredAssetIds": [],
                "recordedAt": self.pilot_recorded_at,
            },
        )
        self._store(
            "pilot_rollback",
            self.artifact / "evidence/release/pilot-rollback-attestation.json",
            {
                "schema": "quwoquan_data.release_attestation",
                "releaseId": ROLLBACK_ID,
                "payloadSha256": ROLLBACK_DIGEST,
                "recordedAt": self.pilot_recorded_at,
            },
        )
        for environment in ("alpha", "beta", "gamma"):
            self._store(
                f"content_{environment}",
                self.artifact
                / f"evidence/release/lifecycle-exit-{environment}.json",
                _checksummed(
                    {
                        "schema": "quwoquan_data.environment_release_lifecycle_exit",
                        "sourceOwner": "qwq_data",
                        "environment": environment,
                        "originalReleaseId": RELEASE_ID,
                        "originalManifestDigest": RELEASE_DIGEST,
                        "originalVerifyChecksum": TEST_DIGEST,
                        "rollbackReleaseId": f"rollback-{environment}",
                        "rollbackManifestDigest": TEST_DIGEST,
                        "rollbackVerifyChecksum": TEST_DIGEST,
                        "rollbackToReleaseId": ROLLBACK_ID,
                        "rollbackToManifestDigest": ROLLBACK_DIGEST,
                        "rollbackToVerifyChecksum": TEST_DIGEST,
                        "replayReleaseId": f"replay-{environment}",
                        "replayManifestDigest": RELEASE_DIGEST,
                        "replayVerifyChecksum": TEST_DIGEST,
                        "passed": True,
                        "recordedAt": OBSERVED_AT,
                    }
                ),
            )
        self._store(
            "green_matrix",
            self.artifact
            / "evidence/release/alpha-beta-gamma-green-matrix.json",
            {
                "schema": "quwoquan.test.case-result",
                "caseId": "stackctl.local-env-gate.alpha-beta-gamma",
                "status": "passed",
                "claim": "ALPHA_BETA_GAMMA_LOCAL_GREEN",
                "executionClass": "live",
                "targets": ["alpha-local", "beta-local", "gamma-local"],
                "baselineId": TEST_DIGEST,
                "releaseId": RELEASE_ID,
                "releaseDigest": RELEASE_DIGEST,
                "executed": 60,
                "skipped": 0,
                "failureCategory": "",
                "phases": [
                    {"name": environment, "status": "passed"}
                    for environment in ("alpha", "beta", "gamma")
                ],
                "generatedAt": OBSERVED_AT,
            },
        )

    def _build_provider(self) -> tuple[Path, dict[str, Any]]:
        compiled, issues = external_provider_governance.load_and_compile()
        assert issues == []
        capability_ids = sorted(
            provider_conformance.provider_conformance_capability_ids(compiled)
        )
        cells = sorted(provider_conformance.expected_required_cell_keys(compiled))
        if self.provider_mode == "three":
            cells = cells[:3]
        elif self.provider_mode == "missing_alpha":
            cells.remove((capability_ids[0], "alpha", "local_contract"))
        elif self.provider_mode == "missing_prod":
            cells.remove((capability_ids[0], "prod", "user_acceptance"))
        elif self.provider_mode == "duplicate":
            cells.append(cells[0])
        raw_files: dict[str, str] = {}
        for index, (capability_id, environment, layer) in enumerate(cells):
            payload = {
                "schema": "provider-conformance-evidence",
                "status": "passed",
                "capabilityId": capability_id,
                "environment": environment,
                "testLayer": layer,
                "nonPromotable": False,
                "sourceTreeState": "clean",
                "commitReview": "reviewed",
                "candidateStatus": "active_immutable",
                "attestationAuthority": "ci",
                "commit": COMMIT,
                "contractGraphDigest": self.contract_digest,
                "executedAt": OBSERVED_AT,
            }
            for field in provider_conformance.REQUIRED_FIELDS:
                payload.setdefault(field, "fixture")
            relative = f"evidence/raw/provider/{index:03d}.evidence.json"
            path = _write(self.artifact / relative, payload)
            raw_files[relative] = sha256_file(path)
        readiness = {
            environment: {
                capability_id: {
                    "required": True,
                    "capability_ready": True,
                }
                for capability_id in capability_ids
            }
            for environment in ("alpha", "beta", "gamma", "prod")
        }
        provider = {
            "schema": "provider-conformance-readiness",
            "status": "passed",
            "generatedAt": OBSERVED_AT,
            "sourceEvidence": {
                "ref": f"oci://ghcr.io/owner/provider@{OCI_DIGEST}",
                "digest": OCI_DIGEST,
                "files": raw_files,
            },
            "evidenceCount": len(cells),
            "sourceCoverageIssues": [],
            "readiness": readiness,
            "issues": [],
        }
        path = _write(self.artifact / "evidence/provider/readiness.json", provider)
        return path, provider

    def _build_applications(self) -> dict[str, dict[str, dict[str, str]]]:
        applications: dict[str, dict[str, dict[str, str]]] = {}
        source_ref = f"oci://ghcr.io/owner/app-evidence@{OCI_DIGEST}"
        for environment in ENVIRONMENTS:
            applications[environment] = {}
            for surface in APPLICATION_PACKAGES[environment]:
                if environment == "prod" and surface == "web":
                    payload = {
                        "schema": "qwq.public-web.release",
                        "sourceGitSha": COMMIT,
                        "sourceTreeDigest": TREE,
                        "contentSHA256": TEST_DIGEST.removeprefix("sha256:"),
                    }
                elif environment == "prod" and surface == "android":
                    payload = {
                        "schema": "qwq.android.official-release",
                        "sourceGitSha": COMMIT,
                        "sourceTreeDigest": TREE,
                        "packagedAPK": "quwoquan.apk",
                        "apkSHA256": TEST_DIGEST.removeprefix("sha256:"),
                    }
                elif environment == "prod" and surface == "opsPortal":
                    payload = {
                        "schema": "qwq.ops_portal_package",
                        "sourceGitSha": COMMIT,
                        "sourceTreeDigest": TREE,
                        "packageDigest": TEST_DIGEST,
                    }
                else:
                    payload = {
                        "schema": "release-application-package",
                        "environment": environment,
                        "surface": surface,
                        "sourceGitSha": COMMIT,
                        "sourceTreeDigest": TREE,
                        "packageDigest": TEST_DIGEST,
                    }
                relative = (
                    f"packages/applications/{environment}/{surface}/receipt.json"
                )
                path = _write(self.artifact / relative, payload)
                applications[environment][surface] = {
                    "path": relative,
                    "digest": sha256_file(path),
                    "packageDigest": TEST_DIGEST,
                    "sourceRef": source_ref,
                }
        return applications

    def _build_configs(self) -> dict[str, dict[str, dict[str, str]]]:
        configurations: dict[str, dict[str, dict[str, str]]] = {}
        for environment in ENVIRONMENTS:
            relative = (
                f"packages/environments/{environment}/"
                "services/content-service/config/config.yaml"
            )
            path = _write(
                self.artifact / relative,
                f"environment: {environment}\nservice: content-service\n",
            )
            configurations[environment] = {
                "content-service": {
                    "path": relative,
                    "digest": sha256_file(path),
                }
            }
        return configurations

    def _receipt(
        self,
        manifest: dict[str, Any],
        *,
        kind: str,
        environment: str,
        status: str,
        evidence: dict[str, Any],
        filename: str,
    ) -> dict[str, Any]:
        payload = {
            "schema": f"release-{kind}-receipt",
            "environment": environment,
            "status": status,
            "candidateId": manifest["candidateId"],
            "sourceGitSha": COMMIT,
            "sourceTreeDigest": TREE,
            "evidenceDigest": _canonical_digest(evidence),
            "evidence": evidence,
            "verifiedAt": OBSERVED_AT,
        }
        relative = f"evidence/receipts/{kind}/{filename}.json"
        path = _write(self.artifact / relative, payload)
        return {
            **payload,
            "path": relative,
            "digest": sha256_file(path),
        }

    def _hosted_readbacks(
        self,
        candidate_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any], str]:
        receipt = {
            "schema": lifecycle.HOSTED_RECEIPT_SCHEMA,
            "authority": lifecycle.HOSTED_AUTHORITY,
            "service": "prod-stack",
            "fromCandidateDigest": "sha256:" + "f" * 64,
            "toCandidateDigest": candidate_id,
            "step": "100",
            "stage": "full",
            "triggerStage": "full",
            "fromReleaseEvidenceRef": (
                "ghcr.io/owner/quwoquan/release-artifact@sha256:" + "f" * 64
            ),
            "toReleaseEvidenceRef": (
                f"ghcr.io/owner/quwoquan/release-artifact@{candidate_id}"
            ),
            "fromImageTransportTag": "sha-before",
            "toImageTransportTag": "sha-candidate",
            "decision": "continue",
            "rollbackOutcome": "not_triggered",
            "rollbackEvidence": {"triggered": False},
            "artifactDigest": TEST_DIGEST,
            "imageDigest": IMAGE,
            "configDigest": TEST_DIGEST,
            "contractGraphDigest": self.contract_digest,
            "adapterDigest": TEST_DIGEST,
            "expectedGeneration": 2,
            "committedGeneration": 3,
            "sloReadback": {"sampleCount": 100},
            "postChecks": [
                {
                    "name": "health",
                    "status": "passed",
                    "receiptDigest": TEST_DIGEST,
                }
            ],
            "lastGoodCandidateDigest": candidate_id,
            "verifiedAt": OBSERVED_AT,
        }
        receipt["receiptId"] = lifecycle._receipt_id(receipt)
        receipt_id = receipt["receiptId"]
        receipt_readback = {
            "schema": lifecycle.HOSTED_RECEIPT_READBACK_SCHEMA,
            "authority": lifecycle.HOSTED_AUTHORITY,
            "receipt": receipt,
            "receiptRef": f"receipt:hosted:{receipt_id}",
        }
        state = {
            "schema": lifecycle.HOSTED_STATE_SCHEMA,
            "authority": lifecycle.HOSTED_AUTHORITY,
            "service": "prod-stack",
            "from_candidate_digest": receipt["fromCandidateDigest"],
            "to_candidate_digest": candidate_id,
            "step": "100",
            "stage": "full",
            "trigger_stage": "full",
            "from_release_evidence_ref": receipt["fromReleaseEvidenceRef"],
            "to_release_evidence_ref": receipt["toReleaseEvidenceRef"],
            "from_image_transport_tag": "sha-before",
            "to_image_transport_tag": "sha-candidate",
            "decision": "continue",
            "rollback_outcome": "not_triggered",
            "artifact_digest": TEST_DIGEST,
            "image_digest": IMAGE,
            "config_digest": TEST_DIGEST,
            "contract_graph_digest": self.contract_digest,
            "adapter_digest": TEST_DIGEST,
            "last_good_candidate_digest": candidate_id,
            "gray_initial_receipt_id": "a" * 64,
            "carry_on_receipt_id": "b" * 64,
            "full_receipt_id": receipt_id,
            "generation": "3",
            "receipt_id": receipt_id,
            "updated_at": OBSERVED_AT,
        }
        ledger_readback = {
            "schema": lifecycle.HOSTED_READBACK_SCHEMA,
            "authority": lifecycle.HOSTED_AUTHORITY,
            "state": state,
            "receipt": receipt,
            "receiptRef": f"receipt:hosted:{receipt_id}",
        }
        return receipt_readback, ledger_readback, receipt_id

    def _build_artifact(self) -> None:
        contract_path = _write(
            self.artifact / "evidence/contractGraph.json",
            {"schema": "qwq.contract-graph", "operations": []},
        )
        contract_digest = sha256_file(contract_path)
        self.contract_digest = contract_digest
        provider_path, provider_payload = self._build_provider()
        green_path = self.paths["green_matrix"]
        test_path = _write(
            self.artifact / "evidence/tests/three-layer.json",
            {
                "schema": "qwq.three-layer-case-results",
                "status": "passed",
                "layers": {
                    layer: {"status": "passed", "artifactDigest": TEST_DIGEST}
                    for layer in (
                        "local_contract",
                        "api_integration",
                        "user_acceptance",
                    )
                },
                "evidence": {
                    "files": {
                        "pilot-release": {
                            "path": self.paths["pilot_release"]
                            .relative_to(self.artifact)
                            .as_posix(),
                            "digest": sha256_file(self.paths["pilot_release"]),
                        },
                        "pilot-rollback": {
                            "path": self.paths["pilot_rollback"]
                            .relative_to(self.artifact)
                            .as_posix(),
                            "digest": sha256_file(self.paths["pilot_rollback"]),
                        },
                        **{
                            f"content-lifecycle-{environment}": {
                                "path": self.paths[f"content_{environment}"]
                                .relative_to(self.artifact)
                                .as_posix(),
                                "digest": sha256_file(
                                    self.paths[f"content_{environment}"]
                                ),
                            }
                            for environment in ("alpha", "beta", "gamma")
                        },
                        "green-matrix": {
                            "path": green_path.relative_to(self.artifact).as_posix(),
                            "digest": sha256_file(green_path),
                        }
                    }
                },
            },
        )

        configurations = self._build_configs()
        applications = self._build_applications()
        manifest: dict[str, Any] = {
            "schema": "release-evidence-manifest",
            "candidateId": None,
            "status": "candidate-ready",
            "generatedAt": OBSERVED_AT,
            "source": {
                "gitSha": COMMIT,
                "treeDigest": TREE,
                "repository": "owner/quwoquan",
                "workflowRunId": "100",
                "sourceArchiveDigest": TEST_DIGEST,
            },
            "artifactDigest": None,
            "images": {
                "content-service": {
                    "repository": "ghcr.io/owner/content-service",
                    "transportRef": "ghcr.io/owner/content-service:candidate-100",
                    "digest": IMAGE,
                    "ref": f"ghcr.io/owner/content-service@{IMAGE}",
                    "attestations": {
                        "spdxSbom": (
                            f"oci://ghcr.io/owner/content-service@{IMAGE}#spdxSbom"
                        ),
                        "slsaProvenance": (
                            f"oci://ghcr.io/owner/content-service@{IMAGE}#slsaProvenance"
                        ),
                    },
                }
            },
            "configurationPackages": configurations,
            "applicationPackages": applications,
            "contractGraphDigest": contract_digest,
            "requiredEvidence": {
                "images": ["content-service"],
                "configurationPackages": {
                    environment: ["content-service"] for environment in ENVIRONMENTS
                },
                "applicationPackages": {
                    environment: list(APPLICATION_PACKAGES[environment])
                    for environment in ENVIRONMENTS
                },
                "contractGraphDigest": True,
                "providerEvidence": True,
                "testEvidence": [
                    "local_contract",
                    "api_integration",
                    "user_acceptance",
                ],
                "environmentReceipts": list(ENVIRONMENTS),
                "rolloutReceipt": True,
                "rollbackReceipt": True,
            },
            "providerEvidence": {
                "path": "evidence/provider/readiness.json",
                "digest": sha256_file(provider_path),
                "status": "passed",
                "evidenceCount": provider_payload["evidenceCount"],
            },
            "testEvidence": {
                "path": "evidence/tests/three-layer.json",
                "digest": sha256_file(test_path),
                "status": "passed",
                "evidence": {
                    "files": {
                    label: {
                        "path": relative_path,
                        "digest": sha256_file(self.artifact / relative_path),
                        }
                    for label, relative_path in RELEASE_CLOSURE_PATHS.items()
                    }
                },
                "layers": {
                    layer: {
                        "status": "passed",
                        "artifactDigest": TEST_DIGEST,
                    }
                    for layer in (
                        "local_contract",
                        "api_integration",
                        "user_acceptance",
                    )
                },
            },
            "environmentReceipts": {},
            "rolloutReceipt": None,
            "rollbackReceipt": None,
            "blockers": [],
            "missingEvidence": [],
        }
        manifest["candidateId"] = canonical_candidate_digest(manifest)

        receipt_readback, ledger_readback, receipt_id = self._hosted_readbacks(
            manifest["candidateId"]
        )
        full_readback_path = self._store(
            "prod_rollout_readback",
            self.artifact / "evidence/raw/prod/full-readback.json",
            receipt_readback,
        )
        self._store(
            "prod_rollback_readback",
            self.root / "hosted-ledger-readback.json",
            ledger_readback,
        )
        report_path = _write(
            self.artifact / "evidence/raw/prod/full-report.json",
            {"status": "passed", "receiptId": receipt_id},
        )
        stage = {
            "report": {
                "path": report_path.relative_to(self.artifact).as_posix(),
                "digest": sha256_file(report_path),
            },
            "readback": {
                "path": full_readback_path.relative_to(self.artifact).as_posix(),
                "digest": sha256_file(full_readback_path),
            },
            "receiptId": receipt_id,
        }
        for environment in ENVIRONMENTS:
            raw_path = _write(
                self.artifact / f"evidence/raw/environment/{environment}.json",
                {"environment": environment, "passed": True},
            )
            evidence = {
                "proof": {
                    "path": raw_path.relative_to(self.artifact).as_posix(),
                    "digest": sha256_file(raw_path),
                },
            }
            if environment in {"alpha", "beta", "gamma"}:
                content_path = self.paths[f"content_{environment}"]
                evidence["contentLifecycle"] = {
                    "path": content_path.relative_to(self.artifact).as_posix(),
                    "digest": sha256_file(content_path),
                }
                for label, field in (
                    ("pilot_release", "pilotRelease"),
                    ("pilot_rollback", "pilotRollback"),
                ):
                    attestation_path = self.paths[label]
                    evidence[field] = {
                        "path": attestation_path.relative_to(self.artifact).as_posix(),
                        "digest": sha256_file(attestation_path),
                    }
            manifest["environmentReceipts"][environment] = self._receipt(
                manifest,
                kind="environment",
                environment=environment,
                status="passed",
                evidence=evidence,
                filename=environment,
            )
        outcome = {
            "candidateId": manifest["candidateId"],
            "outcome": "not_triggered",
            "stages": {"full": stage},
        }
        manifest["rolloutReceipt"] = self._receipt(
            manifest,
            kind="rollout",
            environment="prod",
            status="passed",
            evidence={**outcome, "receiptKind": "rollout"},
            filename="passed",
        )
        manifest["rollbackReceipt"] = self._receipt(
            manifest,
            kind="rollback",
            environment="prod",
            status="not_triggered",
            evidence={**outcome, "receiptKind": "rollback"},
            filename="not_triggered",
        )
        manifest["status"] = "released"
        manifest["blockers"] = []
        manifest["missingEvidence"] = []
        manifest["artifactDigest"] = canonical_manifest_digest(manifest)
        manifest_path = self._store(
            "candidate",
            self.artifact / "manifest.json",
            manifest,
        )
        self.paths["candidate"] = manifest_path
        self.manifest = manifest

    def _build_external_evidence(self) -> None:
        common = {
            "schema": "quwoquan.test.case-result",
            "status": "passed",
            "candidateId": self.manifest["candidateId"],
            "commit": COMMIT,
            "artifactDigest": TEST_DIGEST,
            "releaseId": RELEASE_ID,
            "releaseDigest": RELEASE_DIGEST,
            "executed": 12,
            "skipped": 0,
            "executedAt": OBSERVED_AT,
        }
        for platform in ("ios", "android"):
            self._store(
                f"recovery_{platform}",
                self.root / f"recovery-{platform}.json",
                {
                    **common,
                    "caseId": f"environment-stability.recovery.{platform}",
                    "platform": platform,
                },
            )
        self._store(
            "nightly",
            self.root / "nightly.json",
            {
                **common,
                "caseId": "environment-stability.nightly_full",
                "profile": "nightly_full",
            },
        )
        self._store(
            "prod_sim",
            self.root / "prod-sim.json",
            {
                "schema": "prod-hosted-first-party-prevalidation-report",
                "target": "prod-hosted",
                "mode": "prevalidate",
                "dataMode": "isolated",
                "scope": "first-party",
                "dryRun": False,
                "releaseEvidence": {
                    "candidateId": self.manifest["candidateId"],
                    "artifactDigest": TEST_DIGEST,
                    "source": {"gitSha": COMMIT},
                },
                "releaseId": RELEASE_ID,
                "releaseDigest": RELEASE_DIGEST,
                "containerDeployment": {"status": "passed"},
                "releaseEligibility": {
                    "status": "GATE_BLOCK",
                    "promotable": False,
                    "ledgerWritten": False,
                    "receiptWritten": False,
                },
                "issues": [],
                "endedAt": OBSERVED_AT,
            },
        )
        self._store(
            "prod_soak",
            self.root / "prod-soak-readback.json",
            {
                "schema": "future-canonical-hosted-soak-readback",
                "candidateId": self.manifest["candidateId"],
                "verifiedAt": OBSERVED_AT,
            },
        )

    def inputs(self, **changes: Any) -> FinalAcceptanceInputs:
        values: dict[str, Path | None] = {
            "artifact_root": self.artifact,
            "candidate_manifest": self.paths["candidate"],
            "pilot_release_attestation": self.paths["pilot_release"],
            "pilot_rollback_attestation": self.paths["pilot_rollback"],
            "content_lifecycle_alpha": self.paths["content_alpha"],
            "content_lifecycle_beta": self.paths["content_beta"],
            "content_lifecycle_gamma": self.paths["content_gamma"],
            "local_env_green_matrix": self.paths["green_matrix"],
            "ios_recovery_uat": self.paths["recovery_ios"],
            "android_recovery_uat": self.paths["recovery_android"],
            "nightly_artifact": self.paths["nightly"],
            "prod_sim_receipt": self.paths["prod_sim"],
            "prod_rollout_readback": self.paths["prod_rollout_readback"],
            "prod_rollback_readback": self.paths["prod_rollback_readback"],
            "prod_soak_readback": self.paths["prod_soak"],
        }
        values.update(changes)
        return FinalAcceptanceInputs(**values)


def _evaluate(
    fixture: FinalAcceptanceFixture,
    *,
    trusted: bool = True,
    attestation_verifier: Any = None,
    provider_verifier: Any = None,
    soak_verifier: Any = None,
    **changes: Any,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if trusted:
        kwargs["attestation_verifier"] = attestation_verifier or _trusted_attestation
        kwargs["provider_readiness_verifier"] = provider_verifier or _trusted_provider
        kwargs["soak_authority_verifier"] = soak_verifier or _trusted_soak
    elif attestation_verifier is not None:
        kwargs["attestation_verifier"] = attestation_verifier
    payload = evaluate_final_acceptance(
        fixture.inputs(**changes),
        max_age_seconds=3600,
        now=NOW,
        **kwargs,
    )
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
    ).validate(payload)
    return payload


def _codes(payload: dict[str, Any]) -> set[str]:
    return {blocker["code"] for blocker in payload["blockers"]}


def test_cli_empty_inputs_exit_one_with_typed_receipt() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        output = Path(temporary) / "final.json"
        with patch.object(
            sys,
            "argv",
            ["verify_environment_stability_final_acceptance.py", "--output", str(output)],
        ):
            assert cli.main() == 1
        payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload["verdict"] == "GATE_BLOCK"
    assert "MISSING_INPUT" in _codes(payload)


def test_trusted_producer_verifiers_accept_compiled_cells_and_closed_artifact() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary))
        validate_manifest_files(fixture.artifact, fixture.manifest)
        payload = _evaluate(fixture, trusted=True)

    assert payload["verdict"] == "PROMOTABLE"
    assert payload["blockers"] == []
    assert payload["artifactClosure"]["candidateId"] == fixture.manifest["candidateId"]
    assert payload["inputs"]["recoveryUat"]["ios"]["authority"]["kind"] == (
        "github-actions-oidc"
    )


def test_immutable_release_attestations_do_not_expire_with_runtime_evidence() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(
            Path(temporary),
            pilot_recorded_at="2025-01-01T00:00:00Z",
        )
        validate_manifest_files(fixture.artifact, fixture.manifest)
        payload = _evaluate(fixture, trusted=True)

    assert payload["verdict"] == "PROMOTABLE"
    assert payload["blockers"] == []


def test_immutable_release_attestations_cannot_be_future_dated() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(
            Path(temporary),
            pilot_recorded_at="2026-08-05T00:00:00Z",
        )
        payload = _evaluate(fixture, trusted=True)

    assert payload["verdict"] == "GATE_BLOCK"
    assert "STALE_EVIDENCE" in _codes(payload)


def test_completely_local_synthetic_fixture_is_gate_block() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary))
        payload = _evaluate(fixture, trusted=False)

    assert payload["verdict"] == "GATE_BLOCK"
    assert "UNVERIFIABLE_AUTHORITY" in _codes(payload)


def test_three_cell_provider_bundle_is_gate_block() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary), provider_mode="three")
        payload = _evaluate(fixture)

    assert payload["verdict"] == "GATE_BLOCK"
    assert "ARTIFACT_CLOSURE_INVALID" in _codes(payload)


def test_provider_bundle_missing_one_alpha_cell_is_gate_block() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(
            Path(temporary),
            provider_mode="missing_alpha",
        )
        payload = _evaluate(fixture)

    assert payload["verdict"] == "GATE_BLOCK"
    assert "ARTIFACT_CLOSURE_INVALID" in _codes(payload)


def test_provider_bundle_missing_one_prod_cell_is_gate_block() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(
            Path(temporary),
            provider_mode="missing_prod",
        )
        payload = _evaluate(fixture)

    assert payload["verdict"] == "GATE_BLOCK"
    assert "ARTIFACT_CLOSURE_INVALID" in _codes(payload)


def test_provider_bundle_duplicate_cell_is_gate_block() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(
            Path(temporary),
            provider_mode="duplicate",
        )
        payload = _evaluate(fixture)

    assert payload["verdict"] == "GATE_BLOCK"
    assert "ARTIFACT_CLOSURE_INVALID" in _codes(payload)


def test_forged_source_authority_does_not_establish_trust() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary))
        fixture.rewrite(
            "nightly",
            lambda value: value.__setitem__(
                "sourceAuthority",
                "github-actions-oidc",
            ),
        )
        payload = _evaluate(
            fixture,
            trusted=False,
            attestation_verifier=_reject_attestation,
        )

    assert payload["verdict"] == "GATE_BLOCK"
    assert "UNVERIFIABLE_AUTHORITY" in _codes(payload)


def test_forged_hosted_refs_are_rejected() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary))
        fixture.rewrite(
            "prod_rollback_readback",
            lambda value: value.__setitem__(
                "receiptRef",
                "receipt:hosted:" + "0" * 64,
            ),
        )
        payload = _evaluate(fixture)

    assert payload["verdict"] == "GATE_BLOCK"
    assert "HOSTED_READBACK_INVALID" in _codes(payload)


def test_manifest_unsealed_receipt_bytes_are_rejected() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary))
        rollout_path = Path(fixture.manifest["rolloutReceipt"]["path"])
        _write(
            fixture.artifact / rollout_path,
            {"schema": "release-rollout-receipt", "status": "passed"},
        )
        payload = _evaluate(fixture)

    assert payload["verdict"] == "GATE_BLOCK"
    assert "ARTIFACT_CLOSURE_INVALID" in _codes(payload)


@pytest.mark.parametrize("environment", ("alpha", "beta", "gamma"))
def test_local_copy_of_lifecycle_receipt_is_not_authoritative(
    environment: str,
) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary))
        forged = _write(
            Path(temporary) / f"forged-{environment}-lifecycle.json",
            fixture.payloads[f"content_{environment}"],
        )
        payload = _evaluate(
            fixture,
            **{f"content_lifecycle_{environment}": forged},
        )

    assert payload["verdict"] == "GATE_BLOCK"
    assert "UNVERIFIABLE_AUTHORITY" in _codes(payload)


def test_local_copy_of_green_matrix_is_not_authoritative() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary))
        forged = _write(
            Path(temporary) / "forged-green-matrix.json",
            fixture.payloads["green_matrix"],
        )
        payload = _evaluate(fixture, local_env_green_matrix=forged)

    assert payload["verdict"] == "GATE_BLOCK"
    assert "UNVERIFIABLE_AUTHORITY" in _codes(payload)


def test_emulator_only_green_matrix_cannot_close_final_acceptance() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary))
        emulator_only = {
            **fixture.payloads["green_matrix"],
            "claim": "ALPHA_BETA_GAMMA_EMULATOR_ONLY_FUNCTIONAL_GREEN",
            "deviceProfile": "emulator_only",
            "nonPromotable": True,
            "deviceCoverage": ["ios-simulator", "android-emulator"],
        }
        _write(fixture.paths["green_matrix"], emulator_only)
        payload = _evaluate(fixture)

    assert payload["verdict"] == "GATE_BLOCK"
    assert "NON_PROMOTABLE" in _codes(payload)
    assert "STATUS_NOT_PASSED" in _codes(payload)


@pytest.mark.parametrize(
    ("label", "argument"),
    (
        ("pilot_release", "pilot_release_attestation"),
        ("pilot_rollback", "pilot_rollback_attestation"),
    ),
)
def test_local_copy_of_pilot_attestation_is_not_authoritative(
    label: str,
    argument: str,
) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary))
        forged = _write(
            Path(temporary) / "forged-pilot.json",
            fixture.payloads[label],
        )
        payload = _evaluate(fixture, **{argument: forged})

    assert payload["verdict"] == "GATE_BLOCK"
    assert "UNVERIFIABLE_AUTHORITY" in _codes(payload)


def test_forged_prod_sim_without_oidc_attestation_is_gate_block() -> None:
    def verifier(
        path: Path,
        kind: str,
        manifest: dict[str, Any],
    ) -> VerifiedAuthority:
        if kind == "prod_sim":
            raise RuntimeError("prod-sim signature missing")
        return _trusted_attestation(path, kind, manifest)

    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary))
        payload = _evaluate(
            fixture,
            attestation_verifier=verifier,
        )

    assert payload["verdict"] == "GATE_BLOCK"
    assert any(
        blocker["code"] == "UNVERIFIABLE_AUTHORITY"
        and blocker["input"] == "prod_sim"
        for blocker in payload["blockers"]
    )


def test_attestation_missing_workflow_repo_issuer_claims_is_gate_block() -> None:
    def incomplete(
        path: Path,
        kind: str,
        manifest: dict[str, Any],
    ) -> VerifiedAuthority:
        del manifest
        return VerifiedAuthority(
            authority="github-actions-oidc",
            subject_digest=sha256_file(path),
            verification_digest=TEST_DIGEST,
            claims=frozenset({"receipt_bytes", kind}),
        )

    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary))
        payload = _evaluate(
            fixture,
            attestation_verifier=incomplete,
        )

    assert payload["verdict"] == "GATE_BLOCK"
    assert "UNVERIFIABLE_AUTHORITY" in _codes(payload)


def test_attestation_verifier_failure_is_gate_block() -> None:
    def reject(
        path: Path,
        kind: str,
        manifest: dict[str, Any],
    ) -> VerifiedAuthority:
        del path, kind, manifest
        raise RuntimeError("signature verification failed")

    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary))
        payload = _evaluate(
            fixture,
            trusted=True,
            attestation_verifier=reject,
        )

    assert payload["verdict"] == "GATE_BLOCK"
    assert "UNVERIFIABLE_AUTHORITY" in _codes(payload)


def test_missing_canonical_soak_producer_remains_gate_block() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary))
        payload = _evaluate(
            fixture,
            trusted=False,
            attestation_verifier=_trusted_attestation,
        )

    assert payload["verdict"] == "GATE_BLOCK"
    assert any(
        blocker["code"] == "UNVERIFIABLE_AUTHORITY"
        and blocker["input"] == "prod.soak_readback"
        for blocker in payload["blockers"]
    )


def test_missing_alpha_is_typed_gate_block() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary))
        payload = _evaluate(fixture, content_lifecycle_alpha=None)

    assert payload["verdict"] == "GATE_BLOCK"
    assert "MISSING_INPUT" in _codes(payload)


def test_stale_commit_is_rejected_even_with_trusted_verifier() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary))
        fixture.rewrite(
            "recovery_ios",
            lambda value: value.__setitem__("commit", "f" * 40),
        )
        payload = _evaluate(fixture)

    assert payload["verdict"] == "GATE_BLOCK"
    assert "IDENTITY_MISMATCH" in _codes(payload)


def test_ci_artifact_digest_must_match_hosted_deployment() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary))
        fixture.rewrite(
            "recovery_android",
            lambda value: value.__setitem__(
                "artifactDigest",
                "sha256:" + "f" * 64,
            ),
        )
        payload = _evaluate(fixture)

    assert payload["verdict"] == "GATE_BLOCK"
    assert "DIGEST_MISMATCH" in _codes(payload)


def test_prod_sim_release_binding_must_match_pilot() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary))
        fixture.rewrite(
            "prod_sim",
            lambda value: value.__setitem__(
                "releaseDigest",
                "sha256:" + "f" * 64,
            ),
        )
        payload = _evaluate(fixture)

    assert payload["verdict"] == "GATE_BLOCK"
    assert "DIGEST_MISMATCH" in _codes(payload)


def test_prod_sim_artifact_digest_must_match_hosted_deployment() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary))
        fixture.rewrite(
            "prod_sim",
            lambda value: value["releaseEvidence"].__setitem__(
                "artifactDigest",
                "sha256:" + "f" * 64,
            ),
        )
        payload = _evaluate(fixture)

    assert payload["verdict"] == "GATE_BLOCK"
    assert "DIGEST_MISMATCH" in _codes(payload)


def test_mixed_release_digest_is_rejected() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary))

        def mix(value: dict[str, Any]) -> None:
            value["originalManifestDigest"] = "sha256:" + "f" * 64
            value.pop("verificationChecksum")
            value["verificationChecksum"] = _canonical_digest(value)

        fixture.rewrite("content_gamma", mix)
        payload = _evaluate(fixture)

    assert payload["verdict"] == "GATE_BLOCK"
    assert "DIGEST_MISMATCH" in _codes(payload)


def test_local_hmac_evidence_is_rejected() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary))
        fixture.rewrite(
            "nightly",
            lambda value: value.__setitem__(
                "artifactAttestation",
                "hmac-sha256:" + "0" * 64,
            ),
        )
        payload = _evaluate(fixture)

    assert payload["verdict"] == "GATE_BLOCK"
    assert "LOCAL_ATTESTATION" in _codes(payload)


def test_workflow_text_cannot_supply_typed_evidence() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary))
        workflow = Path(temporary) / "WORKFLOW.md"
        workflow.write_text("# PROMOTABLE\n", encoding="utf-8")
        payload = _evaluate(fixture, nightly_artifact=workflow)

    assert payload["verdict"] == "GATE_BLOCK"
    assert "UNSUPPORTED_INPUT" in _codes(payload)


def test_missing_prod_readback_fails_closed() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary))
        payload = _evaluate(fixture, prod_rollout_readback=None)

    assert payload["verdict"] == "GATE_BLOCK"
    assert "MISSING_INPUT" in _codes(payload)
