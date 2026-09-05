# spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/zero-risk-production-readiness/spec.md
"""environment stability final acceptance 测试共享 fixture 与求值 helper
（自 test_environment_stability_final_acceptance__local_contract_test 拆分）。
"""
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
from quwoquan_ops.tests.support.app_artifact_manifest_test_support import (
    app_artifact_manifest,
)
from quwoquan_ops.tests.support.rollout_stage_promotion_evidence_test_support import (
    promotion_evidence,
)
from quwoquan_ops.cli.lib import external_provider_governance, provider_conformance
from quwoquan_ops.cli.lib.app_identity import resolve_build_product
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
    DISTRIBUTION_EVIDENCE_PATHS,
    ENVIRONMENTS,
    RELEASE_CLOSURE_PATHS,
    canonical_release_composition_id,
    canonical_environment_artifact_digest,
    canonical_evidence_set_digest,
    canonical_manifest_digest,
    canonical_release_train_digest,
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


def _environment_image_descriptor(
    owner: str,
    environment: str,
    index: int,
) -> dict[str, Any]:
    """构造由环境视图引用的信任域不可变镜像描述符。

    alpha/beta/gamma 共享 nonprod 字节，prod 使用独立字节；环境差异只进入配置包。
    """

    trust_domain = "prod" if environment == "prod" else "nonprod"
    repository = f"ghcr.io/owner/{owner}-{trust_domain}"
    digest = f"sha256:{(2 if environment == 'prod' else 1):064x}"
    return {
        "repository": repository,
        "transportRef": f"{repository}:candidate-100",
        "digest": digest,
        "ref": f"{repository}@{digest}",
        "attestations": {
            "spdxSbom": f"oci://{repository}@{digest}#spdxSbom",
            "slsaProvenance": f"oci://{repository}@{digest}#slsaProvenance",
        },
    }


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
                f"candidate:{manifest['releaseCompositionId']}",
            }
        ),
    )


def _trusted_soak(
    path: Path,
    rollout_receipt: dict[str, Any],
    manifest: dict[str, Any],
) -> VerifiedAuthority:
    assert rollout_receipt["toCandidateDigest"] == manifest["releaseCompositionId"]
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
                "releaseClass": "commercial",
                "productLifecycleState": "commercial",
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

    def _build_applications(self) -> dict[str, dict[str, str]]:
        """App 包证据按 build product 身份组织，与环境无关（build once, promote many）。"""
        applications: dict[str, dict[str, str]] = {}
        source_ref = f"oci://ghcr.io/owner/app-evidence@{OCI_DIGEST}"
        for build_product_id in APPLICATION_PACKAGES:
            product = resolve_build_product(build_product_id)
            payload = {
                "schema": "release-application-package",
                "buildProductId": product.build_product_id,
                "buildProfile": product.build_profile,
                "platform": product.platform,
                "sourceGitSha": COMMIT,
                "sourceTreeDigest": TREE,
                "packageDigest": TEST_DIGEST,
                "artifactManifest": app_artifact_manifest(
                    build_product_id=product.build_product_id,
                    source_git_sha=COMMIT,
                    source_tree_digest=TREE,
                    artifact_digest=TEST_DIGEST,
                ),
            }
            relative = f"packages/applications/{build_product_id}/receipt.json"
            path = _write(self.artifact / relative, payload)
            applications[build_product_id] = {
                "path": relative,
                "digest": sha256_file(path),
                "packageDigest": TEST_DIGEST,
                "sourceRef": source_ref,
            }
        return applications

    def _build_ops_portal(self) -> dict[str, str]:
        """opsPortal 不是 App build product，独立成为一等证据面。"""
        payload = {
            "schema": "qwq.ops_portal_package",
            "sourceGitSha": COMMIT,
            "sourceTreeDigest": TREE,
            "packageDigest": TEST_DIGEST,
        }
        relative = "packages/applications/opsPortal/receipt.json"
        path = _write(self.artifact / relative, payload)
        return {
            "path": relative,
            "digest": sha256_file(path),
            "packageDigest": TEST_DIGEST,
            "sourceRef": f"oci://ghcr.io/owner/app-evidence@{OCI_DIGEST}",
        }

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
            "releaseCompositionId": manifest["releaseCompositionId"],
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
            "stage": "100",
            "triggerStage": "100",
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
            "environmentAcceptanceRef": "evidence/environment-acceptance.json",
            "environmentAcceptanceDigest": TEST_DIGEST,
            "environmentAcceptanceFactId": "environment-acceptance-fixture",
            "gammaPredecessorFactId": "gamma-predecessor-fixture",
            "gammaPredecessorDigest": TEST_DIGEST,
            "engineeringEligibilityRef": "evidence/engineering-eligibility.json",
            "engineeringEligibilityDigest": TEST_DIGEST,
            "durableApprovalRef": "evidence/durable-approval.json",
            "durableApprovalDigest": TEST_DIGEST,
            "imageDigest": IMAGE,
            "configDigest": TEST_DIGEST,
            "contractGraphDigest": self.contract_digest,
            "adapterDigest": TEST_DIGEST,
            "expectedGeneration": 2,
            "committedGeneration": 3,
            "sloReadback": {
                "sampleCount": 100,
                "promotionEvidence": promotion_evidence(
                    candidate_id=candidate_id,
                    artifact_digest=TEST_DIGEST,
                    stage="100",
                ),
            },
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
            "stage": "100",
            "trigger_stage": "100",
            "from_release_evidence_ref": receipt["fromReleaseEvidenceRef"],
            "to_release_evidence_ref": receipt["toReleaseEvidenceRef"],
            "from_image_transport_tag": "sha-before",
            "to_image_transport_tag": "sha-candidate",
            "decision": "continue",
            "rollback_outcome": "not_triggered",
            "artifact_digest": TEST_DIGEST,
            "environment_acceptance_ref": receipt["environmentAcceptanceRef"],
            "environment_acceptance_digest": receipt["environmentAcceptanceDigest"],
            "environment_acceptance_fact_id": receipt["environmentAcceptanceFactId"],
            "gamma_predecessor_fact_id": receipt["gammaPredecessorFactId"],
            "gamma_predecessor_digest": receipt["gammaPredecessorDigest"],
            "engineering_eligibility_ref": receipt["engineeringEligibilityRef"],
            "engineering_eligibility_digest": receipt["engineeringEligibilityDigest"],
            "durable_approval_ref": receipt["durableApprovalRef"],
            "durable_approval_digest": receipt["durableApprovalDigest"],
            "image_digest": IMAGE,
            "config_digest": TEST_DIGEST,
            "contract_graph_digest": self.contract_digest,
            "adapter_digest": TEST_DIGEST,
            "last_good_candidate_digest": candidate_id,
            "canary_receipt_id": "",
            "percent_5_receipt_id": "",
            "percent_20_receipt_id": "",
            "percent_50_receipt_id": "",
            "percent_100_receipt_id": receipt_id,
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
        ops_portal = self._build_ops_portal()
        distribution_descriptors: dict[str, dict[str, str]] = {}
        distribution_schemas = {
            "publicWeb": "client-app.web.official-release",
            "androidOfficialRelease": "client-app.android.official-release",
        }
        for evidence_key, relative in DISTRIBUTION_EVIDENCE_PATHS.items():
            distribution_path = _write(
                self.artifact / relative,
                {
                    "schema": distribution_schemas[evidence_key],
                    "sourceGitSha": COMMIT,
                    "sourceTreeDigest": TREE,
                },
            )
            distribution_descriptors[evidence_key] = {
                "path": relative,
                "digest": sha256_file(distribution_path),
            }
        manifest: dict[str, Any] = {
            "schema": "release-evidence-manifest",
            "releaseTrainId": None,
            "releaseCompositionId": None,
            "status": "qualified",
            "generatedAt": OBSERVED_AT,
            "source": {
                "gitSha": COMMIT,
                "treeDigest": TREE,
                "repository": "owner/quwoquan",
                "workflowRunId": "100",
                "sourceArchiveDigest": TEST_DIGEST,
            },
            "artifactDigest": None,
            "evidenceSetDigest": None,
            "environmentArtifacts": {
                environment: {
                    "environment": environment,
                    "environmentArtifactDigest": None,
                    "images": {
                        "content-service": _environment_image_descriptor(
                            "content-service",
                            environment,
                            index,
                        )
                    },
                    "configurationPackages": configurations[environment],
                }
                for index, environment in enumerate(ENVIRONMENTS, start=1)
            },
            "applicationPackages": applications,
            "publicWeb": distribution_descriptors["publicWeb"],
            "androidOfficialRelease": distribution_descriptors[
                "androidOfficialRelease"
            ],
            "opsPortal": ops_portal,
            "contractGraphDigest": contract_digest,
            "requiredEvidence": {
                "environmentArtifacts": {
                    environment: ["content-service"] for environment in ENVIRONMENTS
                },
                "configurationPackages": {
                    environment: ["content-service"] for environment in ENVIRONMENTS
                },
                "applicationPackages": list(APPLICATION_PACKAGES),
                "opsPortal": True,
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
        for environment in ENVIRONMENTS:
            manifest["environmentArtifacts"][environment][
                "environmentArtifactDigest"
            ] = canonical_environment_artifact_digest(manifest, environment)
        manifest["releaseTrainId"] = canonical_release_train_digest(manifest)
        manifest["releaseCompositionId"] = canonical_release_composition_id(manifest)

        receipt_readback, ledger_readback, receipt_id = self._hosted_readbacks(
            manifest["releaseCompositionId"]
        )
        percent_100_readback_path = self._store(
            "prod_rollout_readback",
            self.artifact / "evidence/raw/prod/100-readback.json",
            receipt_readback,
        )
        self._store(
            "prod_rollback_readback",
            self.root / "hosted-ledger-readback.json",
            ledger_readback,
        )
        report_path = _write(
            self.artifact / "evidence/raw/prod/100-report.json",
            {"status": "passed", "receiptId": receipt_id},
        )
        stage = {
            "report": {
                "path": report_path.relative_to(self.artifact).as_posix(),
                "digest": sha256_file(report_path),
            },
            "readback": {
                "path": percent_100_readback_path.relative_to(self.artifact).as_posix(),
                "digest": sha256_file(percent_100_readback_path),
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
            "releaseCompositionId": manifest["releaseCompositionId"],
            "outcome": "not_triggered",
            "stages": {"100": stage},
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
        manifest["evidenceSetDigest"] = canonical_evidence_set_digest(manifest)
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
            "releaseCompositionId": self.manifest["releaseCompositionId"],
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
                    "releaseCompositionId": self.manifest["releaseCompositionId"],
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
                "releaseCompositionId": self.manifest["releaseCompositionId"],
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
