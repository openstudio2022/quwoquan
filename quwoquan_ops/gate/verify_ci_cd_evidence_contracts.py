#!/usr/bin/env python3
"""Verify the canonical, unversioned CI/CD evidence chain."""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CANONICAL_SCHEMAS = frozenset(
    {
        "ci-timing-summary",
        "release-evidence-manifest",
        "ai-ci-advisory",
    }
)
SCHEMA_SOURCES = {
    "quwoquan_ops/ci/render_ci_timing_summary.py": (
        "CANONICAL_SCHEMA",
        "ci-timing-summary",
    ),
    "quwoquan_ops/cli/prod/finalize_mainline_release_artifact.py": (
        "SCHEMA",
        "release-evidence-manifest",
    ),
    "quwoquan_ops/ci/ai_ci_advisory.py": (
        "CANONICAL_SCHEMA",
        "ai-ci-advisory",
    ),
}
CHAIN_FILES = (
    ".github/workflows/app_pipeline.yml",
    "quwoquan_ops/ci/render_ci_timing_summary.py",
    "quwoquan_ops/ci/github_actions_timing.py",
    "quwoquan_ops/ci/render_app_candidate_timing.py",
    "quwoquan_ops/ci/render_delivery_release_evidence.py",
    "quwoquan_ops/ci/render_environment_chain_timing_diagnostics.py",
    "quwoquan_ops/ci/ai_ci_advisory.py",
    "quwoquan_ops/ci/materialize_evidence_oci.py",
    "quwoquan_ops/ci/hosted_ci_timing_ledger.py",
    "quwoquan_ops/ci/sync_hosted_ci_timing_ledger.py",
    "quwoquan_ops/ci/ci_timing_summary.Dockerfile",
    "quwoquan_ops/ci/render_provider_conformance_source.py",
    "quwoquan_ops/ci/render_provider_release_evidence.py",
    "quwoquan_ops/ci/consume_released_release_evidence.py",
    "quwoquan_ops/ci/provider_release_evidence.py",
    "quwoquan_ops/ci/provider_conformance/run_prod_remote_uat.py",
    "quwoquan_ops/ci/provider_conformance/native_case_result.py",
    "quwoquan_ops/ci/provider_conformance/run_prod_remote_patrol_uat.py",
    "quwoquan_ops/cli/lib/provider_conformance.py",
    "quwoquan_ops/cli/provider_conformance_runner.py",
    "quwoquan_ops/environments/provider_conformance_evidence.schema.json",
    "quwoquan_ops/ci/render_release_application_package.py",
    "quwoquan_ops/ci/verify_release_governance.py",
    "quwoquan_ops/ci/render_beta_device_evidence.py",
    "quwoquan_ops/ci/device_runner_lease.py",
    "quwoquan_ops/ci/run_mobile_platform_matrix.sh",
    "quwoquan_ops/ci/render_environment_release_receipt.py",
    "quwoquan_ops/ci/render_release_lifecycle_receipts.py",
    "quwoquan_ops/ci/render_hosted_release_stage_report.py",
    "quwoquan_ops/ci/verify_workflow_release_candidate.py",
    "quwoquan_ops/cli/lib/android_official_release.py",
    "quwoquan_ops/cli/lib/official_distribution_release.py",
    "quwoquan_ops/cli/lib/web_official_release.py",
    "quwoquan_ops/cli/prod/generate_mainline_release_artifact.py",
    "quwoquan_ops/cli/prod/finalize_mainline_release_artifact.py",
    "quwoquan_ops/cli/prod/collect_mainline_image_descriptors.py",
    "quwoquan_ops/cli/prod/oci_supply_chain.py",
    "quwoquan_ops/cli/prod/collect_release_artifact_descriptors.py",
    "quwoquan_ops/cli/prod/fetch_mainline_release_artifact.py",
    "quwoquan_ops/cli/prod/load_prod_plane_images.py",
    "quwoquan_ops/cli/prod/prevalidate_android_distribution.py",
    "quwoquan_ops/cli/prod/build_portal_release.py",
    "quwoquan_ops/cli/prod/hosted_release_ledger.py",
    "quwoquan_ops/cli/prod/resolve_prod_release_state.py",
    "quwoquan_ops/gate/verify_environment_packaging_contract.py",
    "quwoquan_ops/policies/config-release/slo_thresholds.yaml",
    "quwoquan_service/scripts/runtime/packaging/build_service_env_package.sh",
    ".github/workflows/service_pipeline.yml",
    ".github/workflows/delivery-gate.yml",
    ".github/workflows/pre-release-gate.yml",
    ".github/workflows/app-env-device-matrix-self-hosted.yml",
    ".github/workflows/beta-device-platform.yml",
    ".github/workflows/provider-release-evidence.yml",
    ".github/workflows/prod-sim-manual-admission.yml",
    ".github/workflows/deploy-prod-auto.yml",
    "specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md",
    "specs/feature-tree/runtime/deliver-deploy-prod-pipeline/design.md",
    "specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md",
)
EXPLICIT_NEGATIVE_TESTS = frozenset(
    {
        "quwoquan_ops/tests/local_contract/test_ai_ci_advisory__contract__local_contract_test.py",
        "quwoquan_ops/tests/local_contract/test_ci_timing_summary__canonical__local_contract_test.py",
        "quwoquan_ops/tests/local_contract/test_hosted_ci_timing_ledger__local_contract_test.py",
        "quwoquan_ops/tests/local_contract/test_ci_cd_evidence_contracts__canonical__local_contract_test.py",
        "quwoquan_ops/tests/local_contract/test_release_evidence_manifest__canonical__local_contract_test.py",
        "quwoquan_ops/tests/local_contract/test_release_lifecycle_receipts__canonical__local_contract_test.py",
        "quwoquan_ops/tests/local_contract/test_release_workflow_convergence__contract__local_contract_test.py",
        "quwoquan_ops/tests/local_contract/test_automate_release_workflows__local_contract_test.py",
        "quwoquan_ops/tests/local_contract/test_provider_release_evidence__local_contract_test.py",
    }
)
SCOPED_FUNCTIONS = {
    "quwoquan_ops/cli/stackctl.py": frozenset(
        {
            "_command_package_ops_portal",
            "_sanitized_provider_readiness_report",
            "_materialize_release_evidence_configuration",
            "_archive_release_artifact",
            "_fetch_hosted_release_ledger_projection",
            "_sync_release_ledger_projection",
            "_hosted_receipt_id",
            "_validate_hosted_release_readback",
            "_run_hosted_release_ledger",
            "_cache_hosted_release_readback",
            "_release_check_receipts",
            "_commit_hosted_release_transition",
            "_command_package_release_manifest",
            "_deployable_release_manifest",
            "_materialize_prevalidation_release_manifest",
            "_prevalidation_release_manifest",
            "_verify_release_registry_attestations",
            "_command_deploy_distribution",
            "command_hosted_release_receipt",
        }
    )
}
SCOPED_REQUIRED_TOKENS = {
    "quwoquan_ops/cli/stackctl.py": {
        "_command_package_ops_portal": ('"schema": "qwq.ops_portal_package"',),
        "_sanitized_provider_readiness_report": (
            'parsed.get("schema") == "provider-conformance-readiness"',
            'parsed["evidenceCount"] > 0',
        ),
    }
}
SCHEMA_REGISTRIES = {
    "quwoquan_ops/cli/prod/collect_release_artifact_descriptors.py": (
        "EVIDENCE_SOURCE_SCHEMAS",
        {
            "publicWeb": "client-app.web.official-release",
            "androidOfficialRelease": "client-app.android.official-release",
            "opsPortal": "qwq.ops_portal_package",
            "contractGraph": "qwq.contract-graph",
            "providerEvidence": "provider-conformance-readiness",
            "testEvidence": "qwq.three-layer-case-results",
        },
    )
}
FORBIDDEN_TOP_LEVEL_ENVELOPES = {
    "quwoquan_ops/policies/config-release/slo_thresholds.yaml": re.compile(
        r"^version\s*:",
        re.MULTILINE,
    )
}
VALIDATOR_FIELD_CONSTANTS = {
    "quwoquan_ops/ci/ai_ci_advisory.py": frozenset({"FORBIDDEN_VERSION_FIELDS"}),
    "quwoquan_ops/cli/prod/finalize_mainline_release_artifact.py": frozenset(
        {"FORBIDDEN_FIELDS"}
    ),
}
REQUIRED_SOURCE_TOKENS = {
    "quwoquan_ops/ci/render_ci_timing_summary.py": (
        '"schema": CANONICAL_SCHEMA',
        'OFFICIAL_CRITICAL_PATH_SOURCE = "github_run_calendar"',
        '"criticalPath"',
        '"durations"',
        'durations["machineCriticalPathSeconds"] = machine_critical_path_seconds',
        '"durations.machineCriticalPathSeconds": machine_critical_path_seconds',
        "machine_critical_path_seconds: Optional[int]",
        'end_to_end_seconds = optional_durations.get("calendarLeadTimeSeconds")',
        'parser.add_argument("--missing-evidence"',
        "upstream_missing_evidence",
        '"budget"',
        '"missingEvidence"',
    ),
    "quwoquan_ops/ci/github_actions_timing.py": (
        "APPROVAL_EVIDENCE_REASON",
        'calendar_start = run_created',
        'result["machine_critical_path_seconds"]',
        '"calendar_lead_time_seconds": calendar_seconds',
        'result["approval_evidence_reason"] = APPROVAL_EVIDENCE_REASON',
        'result["missing_evidence"] = "githubJobs.createdAt"',
    ),
    "quwoquan_ops/ci/hosted_ci_timing_ledger.py": (
        'AUTHORITY = "prod-hosted-ci-timing"',
        'CANONICAL_SCHEMA = "ci-timing-summary"',
        "timing evidence ref must be an exact GHCR OCI digest ref",
        "hosted timing authority is missing",
        "hosted timing append-only binding conflicts",
        "def query(",
    ),
    "quwoquan_ops/ci/sync_hosted_ci_timing_ledger.py": (
        "def bind_and_readback(",
        'action="bind"',
        'action="query"',
        "query does not match exact OCI binding",
    ),
    "quwoquan_ops/ci/ci_timing_summary.Dockerfile": (
        "COPY ci-timing-summary.json /evidence/ci-timing-summary.json",
    ),
    ".github/workflows/delivery-gate.yml": (
        "outputs.machine_critical_path_seconds",
        '--machine-critical-path-seconds "${MACHINE_CRITICAL_PATH_SECONDS}"',
        "--critical-path-source github_run_calendar",
        'if [ "${CALENDAR_SECONDS}" -gt "${HARD_FAIL_SECONDS}" ]',
        "UPSTREAM_MISSING_EVIDENCE",
        '--missing-evidence "$UPSTREAM_MISSING_EVIDENCE"',
        "timing is historical_incomplete",
        "--require-file provider-candidate.json",
        "provider-release-evidence-binding",
        "QWQ_PROVIDER_CONFORMANCE_EXPECTED_IMAGE_DIGEST",
        "provider_component_evidence_ref",
        "executed Provider evidence set must be non-empty",
        "render_provider_conformance_source.py",
    ),
    ".github/workflows/service_pipeline.yml": (
        "outputs.machine_critical_path_seconds",
        '--machine-critical-path-seconds "${MACHINE_CRITICAL_PATH_SECONDS}"',
        "--critical-path-source github_run_calendar",
        'if [[ "$CALENDAR_SECONDS" -gt "$HARD_FAIL_SECONDS" ]]',
        "actions/attest@f7c74d28b9d84cb8768d0b8ca14a4bac6ef463e6",
        "oci_supply_chain.py extract-sbom",
        "attestations: write",
        "UPSTREAM_MISSING_EVIDENCE",
        '--missing-evidence "$UPSTREAM_MISSING_EVIDENCE"',
        "timing is historical_incomplete",
    ),
    ".github/workflows/app_pipeline.yml": (
        "outputs.machine_critical_path_seconds",
        "render_app_candidate_timing.py",
    ),
    ".github/workflows/app-env-device-matrix-self-hosted.yml": (
        "outputs.machine_critical_path_seconds",
        "--critical-path-source github_run_calendar",
        "Run immutable Beta formal runtime",
        "--formal-release",
        '--release-manifest "$QWQ_PROD_RELEASE_ARTIFACT_ROOT/manifest.json"',
        "--skip-build",
        "--skip-app",
        "stackctl.py down",
        "--target beta-local",
        'STACKCTL_AUTO_WIPE_MIGRATION_DRIFT: "0"',
        "--expected-host-digest",
        "--stack-ref \"$STACK_REF\"",
        "--archive-prefix evidence/raw/environments/beta/raw",
        'if [ "$calendar_lead_time_seconds" -gt 480 ]',
        '--missing-evidence "$missing_evidence"',
        "timing is historical_incomplete",
        'cron: \'0 18 * * *\'',
        'if [ "$EVENT_NAME" = "schedule" ]; then PROFILE="nightly_full"; fi',
        "Inspect and doctor the managed Gamma runtime before soak",
        "Inspect and doctor the managed Gamma runtime after soak",
        "managed_runtime_started",
        "vars.RELEASED_RELEASE_EVIDENCE_REF",
        "consume_released_release_evidence.py",
        "REQUIRED_STATUS=released",
        "steps.release.outputs.pilot_release_path",
        "steps.release.outputs.pilot_rollback_path",
    ),
    ".github/workflows/beta-device-platform.yml": (
        '"mobile-${{ inputs.platform }}"',
        "device_runner_lease.py acquire",
        "device_runner_lease.py release",
        "consume_released_release_evidence.py",
        "@${{ steps.evidence_bundle.outputs.digest }}",
    ),
    ".github/workflows/provider-release-evidence.yml": (
        "environment: production",
        "vars.RELEASED_RELEASE_EVIDENCE_REF",
        "consume_released_release_evidence.py",
        "--require-status released",
        "provider_release_evidence.py execute-nonprod",
        "provider_release_evidence.py execute-prod",
        "provider_release_evidence.py package",
        "Execute all compiled required nonprod Provider cells",
        "Publish executed Provider evidence OCI",
        "source-only conformance metadata",
        "QWQ_PROVIDER_CONFORMANCE_ATTESTATION_KEY",
    ),
    ".github/workflows/prod-sim-manual-admission.yml": (
        "environment: prod-sim-admission",
        "--target prod-hosted",
        "--mode prevalidate",
        "--data-mode isolated",
        "--prevalidate-scope first-party",
        '(report.get("releaseEligibility") or {}).get("status") != "GATE_BLOCK"',
        "retention-days: 1",
    ),
    ".github/workflows/deploy-prod-auto.yml": (
        "needs.service_pipeline.outputs.machine_critical_path_seconds",
        "needs.app_pipeline.outputs.machine_critical_path_seconds",
        "needs.delivery_gate.outputs.machine_critical_path_seconds",
        "needs.beta_device_matrix.outputs.machine_critical_path_seconds",
        '--machine-critical-path-seconds "${MACHINE_CRITICAL_PATH_SECONDS}"',
        "--critical-path-source github_run_calendar",
        'if [ "${CALENDAR_SECONDS}" -gt "${HARD_FAIL_SECONDS}" ]',
        "APPROVAL_EVIDENCE_REASON",
        "Canonical summary remains historical_incomplete",
        "Publish canonical CiTimingSummary to immutable OCI",
        "ghcr.io/${{ github.repository }}/ci-timing-summary@${TIMING_EVIDENCE_DIGEST}",
        "Bind exact timing OCI into hosted append-only authority",
        "Query hosted timing authority and verify readback",
        "Upload diagnostic timing copy (non-authoritative)",
        "UPSTREAM_MISSING_EVIDENCE",
        '--missing-evidence "$UPSTREAM_MISSING_EVIDENCE"',
        '--release-outcome "$RELEASE_OUTCOME"',
        "Preserve canonical failure-path timing without fabrication",
        'ref: ${{ needs.source_context.outputs.source_git_sha || github.sha }}',
        '--workflow-run-id "${{ github.run_id }}"',
        '--source-git-sha "${{ github.sha }}"',
        '--missing-evidence "workflowTiming.authoritativeDAG"',
        'if [[ -s "$SUMMARY" ]]',
        "PROD_RELEASE_STATUS",
        "render_hosted_release_stage_report.py",
        "canary_receipt_id",
        "percent_5_receipt_id",
        "percent_20_receipt_id",
        "percent_50_receipt_id",
        "percent_100_receipt_id",
        "PROD_EDGE_SSH_KEY_FILE=$EDGE_KEY_FILE",
        "PROD_SERVICE_SSH_KEY_FILE=$KEY_FILE",
        "PROD_PROVIDER_CANDIDATE_IMAGE_DIGEST",
        "needs.service_pipeline.outputs.component_evidence_ref",
        "inputs.provider_evidence_ref || vars.PROD_PROVIDER_EVIDENCE_REF",
        "Sign candidate release artifact provenance with GitHub OIDC",
        "Sign released terminal provenance with GitHub OIDC",
    ),
    "quwoquan_ops/ci/consume_released_release_evidence.py": (
        "verify_oci_supply_chain",
        "validate_manifest_files",
        "RELEASE_CLOSURE_PATHS",
        "allowed_statuses={require_status}",
        "derived {label} does not match the caller expectation",
    ),
    "quwoquan_ops/ci/provider_release_evidence.py": (
        'METADATA_SCHEMA = "provider-release-evidence-binding"',
        '"schema": "provider-conformance-prod-candidate-image-set"',
        "load_validate_and_derive",
        "exact_required_cell_issues",
        "provider_conformance.expected_required_cell_keys(compiled)",
        "command_execute_nonprod",
        "executed != len(expected_nonprod_cells)",
        "len(evidence_paths) != len(expected_cells)",
        "provider-conformance",
        "--execute",
        'print(f"provider_release_evidence: GATE_BLOCK: {error}", file=sys.stderr)',
    ),
    "quwoquan_ops/ci/ai_ci_advisory.py": (
        '"schema": CANONICAL_SCHEMA',
        "FORBIDDEN_VERSION_FIELDS",
    ),
    "quwoquan_ops/cli/prod/generate_mainline_release_artifact.py": (
        '"schema": SCHEMA',
        '"candidateId"',
        '"artifactDigest"',
    ),
    "quwoquan_ops/cli/prod/finalize_mainline_release_artifact.py": (
        'SCHEMA = "release-evidence-manifest"',
        '"candidateId"',
        '"artifactDigest"',
    ),
    "quwoquan_ops/cli/lib/android_official_release.py": (
        '"schema": "client-app.android.official-release"',
    ),
    "quwoquan_ops/cli/lib/web_official_release.py": (
        '"schema": "client-app.web.official-release"',
    ),
    "quwoquan_ops/cli/lib/official_distribution_release.py": (
        '"client-app.web.official-release"',
        '"client-app.android.official-release"',
    ),
    "quwoquan_ops/cli/prod/prevalidate_android_distribution.py": (
        '"schema": "client-app.android.distribution-prevalidation"',
    ),
    "quwoquan_ops/cli/prod/build_portal_release.py": (
        '"schema": "qwq.ops_portal_application"',
        '"packageDigest": package_digest',
        '"sourceTreeDigest": "sha1:" + source_tree',
    ),
    "quwoquan_ops/gate/verify_environment_packaging_contract.py": (
        '"qwq.ops_portal_package"',
        '"qwq.service_package"',
    ),
    "quwoquan_service/scripts/runtime/packaging/build_service_env_package.sh": (
        '"schema": "qwq.service_package"',
    ),
    "quwoquan_ops/ci/render_environment_chain_timing_diagnostics.py": (
        '"ci-timing-summary"',
        'summary.get("criticalPath")',
        'summary.get("budget")',
        'phase.get("name", "")',
        'phase.get("durationSeconds")',
        '"historical_incomplete"',
    ),
    "quwoquan_ops/ci/verify_release_governance.py": (
        "validate_manifest",
        'manifest.get("artifactDigest")',
    ),
    "quwoquan_ops/ci/render_beta_device_evidence.py": (
        '"schema": "release-device-matrix-evidence"',
        '"candidateId": candidate',
        '"sourceGitSha": git_sha',
        '"sourceTreeDigest": tree_digest',
        '"artifactDigest": artifact_digest',
        '"platformEvidence": platform_evidence',
        'if "schema" in payload',
        "_validate_exact_ref",
        'artifact_digests != {expected_artifact_digest}',
        'evidence.get("runtimeMode") != "immutable-oci"',
        'evidence.get("destructiveActions") != []',
        'raise ValueError("Beta Android/iOS executions did not overlap")',
    ),
    "quwoquan_ops/ci/device_runner_lease.py": (
        'expected_label = f"mobile-{platform}"',
        'raise ValueError("platform runner is not the Beta stack host")',
        'raise ValueError(f"{platform} device already has an active lease")',
    ),
    "quwoquan_ops/ci/render_environment_release_receipt.py": (
        '"candidateId": candidate',
        '"sourceGitSha": source["gitSha"]',
        '"sourceTreeDigest": source["treeDigest"]',
        'manifest["artifactDigest"]',
        'if "package" not in evidence',
        'label in {"package", "devices"}',
        'set(platforms) != {"android", "ios"}',
        '"candidate-bound-environment-evidence"',
    ),
    "quwoquan_ops/ci/render_release_lifecycle_receipts.py": (
        'schema="release-rollback-receipt"',
        'schema="release-environment-receipt"',
        'schema="release-rollout-receipt"',
        'status="ready"',
        '"not_triggered"',
        '"rolled_back"',
        '"rollback_failed"',
        "_validate_ledger_readback",
        "_validate_receipt_readback",
    ),
    "quwoquan_ops/ci/render_hosted_release_stage_report.py": (
        "validate_rollback_evidence",
        'projectionPurpose": "terminal-sealing-only',
        'sourceAuthority": HOSTED_AUTHORITY',
        'rollback_evidence["durationMs"] <= ROLLBACK_BUDGET_MS',
    ),
    "quwoquan_ops/cli/prod/hosted_release_ledger.py": (
        '"rollbackEvidence"',
        "validate_rollback_evidence",
        "successful rollbackEvidence requires non-empty passed post-checks",
    ),
    "quwoquan_ops/cli/prod/resolve_prod_release_state.py": (
        'decision == "rolled_back"',
        'decision == "rollback_failed"',
        '"resumeStage": "complete"',
        "hosted release ledger records rollback_failed",
    ),
    "quwoquan_ops/ci/render_provider_conformance_source.py": (
        'SCHEMA = "provider-conformance-source"',
        'report.get("schema") != "provider-conformance-readiness"',
        "expected_required_cell_count_from_readiness(readiness)",
        "expected_required_cell_keys(",
        "exact_required_cell_issues",
        "validate_source(payload)",
    ),
    "quwoquan_ops/ci/render_provider_release_evidence.py": (
        "validate_source(conformance)",
        '"schema": "provider-conformance-readiness"',
    ),
    "quwoquan_ops/ci/verify_workflow_release_candidate.py": (
        '"--require-deployable"',
        'manifest.get("candidateId")',
        'manifest.get("artifactDigest")',
        'manifest.get("environmentReceipts")',
    ),
    "quwoquan_ops/cli/prod/fetch_mainline_release_artifact.py": (
        "validate_manifest",
        'manifest["candidateId"]',
        'manifest["artifactDigest"]',
    ),
}
FORBIDDEN_FLAT_TIMING_FIELDS = (
    "criticalPathSeconds",
    "budgetStatus",
    "phaseBudgetsSeconds",
    "criticalPathDefinition",
)
FORBIDDEN_GITHUB_TIMING_INFERENCE = (
    "dependency_completions",
    'result["approval_requested_at"]',
    'result["approval_approved_at"]',
    'result["approval_wait_seconds"]',
    'result["human_decision_wait_seconds"]',
)
FORBIDDEN_LITERAL_FIELDS = (
    "schemaVersion",
    "contractVersion",
    "registryRevision",
    "manifestDigest",
)
PROVIDER_ONLINE_FILES = frozenset(
    {
        "quwoquan_ops/ci/provider_conformance/run_prod_remote_uat.py",
        "quwoquan_ops/ci/provider_conformance/native_case_result.py",
        "quwoquan_ops/ci/provider_conformance/run_prod_remote_patrol_uat.py",
        "quwoquan_ops/ci/render_provider_conformance_source.py",
        "quwoquan_ops/ci/render_provider_release_evidence.py",
        "quwoquan_ops/ci/provider_release_evidence.py",
        "quwoquan_ops/cli/lib/provider_conformance.py",
        "quwoquan_ops/cli/provider_conformance_runner.py",
        "quwoquan_ops/environments/provider_conformance_evidence.schema.json",
    }
)
PROVIDER_FIXED_COUNT_WORKFLOWS = frozenset(
    {
        ".github/workflows/delivery-gate.yml",
        ".github/workflows/provider-release-evidence.yml",
    }
)
PROVIDER_FIXED_COUNT = re.compile(
    r"(?:\b(?:14|42|126|140)\b[^\n]*(?:Provider|cells?|evidenceCount)|"
    r"(?:Provider|cells?|evidenceCount)[^\n]*\b(?:14|42|126|140)\b)",
    re.IGNORECASE,
)
SERIALIZED_VERSION_FIELD = re.compile(r"[\"']version[\"']\s*:")
VERSIONED_IDENTITY = re.compile(
    r"\b(?:ci-timing-summary|release-evidence-manifest|ai-ci-advisory|"
    r"CiTimingSummary|ReleaseEvidenceManifest|AiCiAdvisory)"
    r"(?:\s*[._/-]?\s*(?:(?:v|version)\s*)?[0-9]+)\b",
    re.IGNORECASE,
)
VERSIONED_SCHEMA_IDENTITY = re.compile(
    r"[A-Za-z][A-Za-z0-9_.-]*[._-](?:(?:v|version))?[0-9]+",
    re.IGNORECASE,
)
SCHEMA_IDENTITY_DECLARATION = re.compile(
    r"(?:[\"']schema[\"']\s*:\s*|^\s*schema\s*:\s*|"
    r"(?:\.get\(\s*[\"']schema[\"']\s*\)|"
    r"\[\s*[\"']schema[\"']\s*\])\s*(?:==|!=)\s*|"
    r"\b[A-Z][A-Z0-9_]*SCHEMA\s*=\s*)"
    r"[\"']?(?P<identity>[A-Za-z][A-Za-z0-9_.-]*)",
    re.IGNORECASE,
)
VERSIONS_ENVELOPE = re.compile(
    r"(?:[\"']versions[\"']\s*:|\.get\(\s*[\"']versions[\"']|"
    r"\[\s*[\"']versions[\"']\s*\]|^\s*versions\s*:)",
    re.MULTILINE,
)
COMPAT_ESCAPE = re.compile(
    r"(?:--warn-only\b|mode\s*=\s*compat\b|"
    r"compat(?:ibility)?[_ -]?(?:shim|alias|mode)\b|"
    r"dual[_ -]?(?:read|write)\b|legacy[_ -]?(?:alias|fallback)\b)",
    re.IGNORECASE,
)
NEGATIVE_LANGUAGE = re.compile(
    r"(?:禁止|不得|不存在|拒绝|阻断|移除|退役|forbid|reject|must not|not contain|"
    r"no compat|no warn|legacy.*(?:forbid|reject))",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    detail: str


def _relative(path: Path, root: Path = ROOT) -> str:
    return path.relative_to(root).as_posix()


def _constant_value(path: Path, constant_name: str) -> object:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(
            isinstance(target, ast.Name) and target.id == constant_name
            for target in targets
        ):
            continue
        value = node.value
        if value is None:
            return None
        try:
            return ast.literal_eval(value)
        except (ValueError, TypeError):
            return None
    return None


def _allowed_validator_lines(path: Path, relative_path: str) -> set[int]:
    names = VALIDATOR_FIELD_CONSTANTS.get(relative_path)
    if not names:
        return set()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    allowed: set[int] = set()
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(
            isinstance(target, ast.Name) and target.id in names for target in targets
        ):
            continue
        allowed.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
    return allowed


def _negative_use(relative_path: str, line: str) -> bool:
    if relative_path in EXPLICIT_NEGATIVE_TESTS:
        return True
    return NEGATIVE_LANGUAGE.search(line) is not None


def scan_text(
    relative_path: str,
    text: str,
    *,
    allowed_validator_lines: Iterable[int] = (),
    line_offset: int = 0,
) -> list[Finding]:
    findings: list[Finding] = []
    allowed_lines = set(allowed_validator_lines)
    for local_line_number, line in enumerate(text.splitlines(), start=1):
        line_number = local_line_number + line_offset
        negative = _negative_use(relative_path, line)
        validator_declaration = line_number in allowed_lines
        for token in FORBIDDEN_LITERAL_FIELDS:
            if token in line and not (negative or validator_declaration):
                findings.append(
                    Finding(
                        relative_path,
                        line_number,
                        f"legacy field is forbidden: {token}",
                    )
                )
        if "mainline-release-artifact" in line and not negative:
            findings.append(
                Finding(
                    relative_path,
                    line_number,
                    "legacy release schema identity is forbidden",
                )
            )
        if VERSIONS_ENVELOPE.search(line) and not (negative or validator_declaration):
            findings.append(
                Finding(relative_path, line_number, "versions envelope is forbidden")
            )
        match = VERSIONED_IDENTITY.search(line)
        if match and not negative:
            findings.append(
                Finding(
                    relative_path,
                    line_number,
                    f"versioned evidence identity is forbidden: {match.group(0)}",
                )
            )
        for declaration in SCHEMA_IDENTITY_DECLARATION.finditer(line):
            identity = declaration.group("identity")
            if VERSIONED_SCHEMA_IDENTITY.fullmatch(identity) and not (
                negative or validator_declaration
            ):
                findings.append(
                    Finding(
                        relative_path,
                        line_number,
                        f"versioned schema identity is forbidden: {identity}",
                    )
                )
        match = COMPAT_ESCAPE.search(line)
        if match and not (negative or validator_declaration):
            findings.append(
                Finding(
                    relative_path,
                    line_number,
                    f"compatibility escape is forbidden: {match.group(0)}",
                )
            )
    return findings


def _scoped_source_findings(
    path: Path,
    relative_path: str,
    function_names: frozenset[str],
) -> list[Finding]:
    """Scan only the release-evidence functions in a shared orchestration module."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    tree = ast.parse(text, filename=str(path))
    nodes = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in function_names
    }
    findings: list[Finding] = []
    for function_name in sorted(function_names):
        node = nodes.get(function_name)
        if node is None:
            findings.append(
                Finding(
                    relative_path,
                    0,
                    f"release evidence function is missing: {function_name}",
                )
            )
            continue
        end_line = node.end_lineno or node.lineno
        source = "\n".join(lines[node.lineno - 1 : end_line])
        findings.extend(
            scan_text(
                relative_path,
                source,
                line_offset=node.lineno - 1,
            )
        )
        for token in SCOPED_REQUIRED_TOKENS.get(relative_path, {}).get(
            function_name,
            (),
        ):
            if token not in source:
                findings.append(
                    Finding(
                        relative_path,
                        node.lineno,
                        f"canonical scoped producer token is missing: {token}",
                    )
                )
    return findings


def top_level_envelope_findings(relative_path: str, text: str) -> list[Finding]:
    pattern = FORBIDDEN_TOP_LEVEL_ENVELOPES.get(relative_path)
    if pattern is None:
        return []
    match = pattern.search(text)
    if match is None:
        return []
    line = text.count("\n", 0, match.start()) + 1
    return [
        Finding(
            relative_path,
            line,
            "top-level contract version envelope is forbidden",
        )
    ]


def evidence_contract_findings(root: Path = ROOT) -> list[Finding]:
    findings: list[Finding] = []
    for relative_path, (constant_name, expected) in SCHEMA_SOURCES.items():
        path = root / relative_path
        if not path.is_file():
            findings.append(
                Finding(relative_path, 0, "canonical schema producer is missing")
            )
            continue
        actual = _constant_value(path, constant_name)
        if actual != expected or actual not in CANONICAL_SCHEMAS:
            findings.append(
                Finding(
                    relative_path,
                    0,
                    f"{constant_name} must equal the canonical identity {expected!r}",
                )
            )

    for relative_path, (constant_name, expected) in SCHEMA_REGISTRIES.items():
        path = root / relative_path
        if not path.is_file():
            findings.append(
                Finding(relative_path, 0, "canonical schema registry is missing")
            )
            continue
        actual = _constant_value(path, constant_name)
        if actual != expected:
            findings.append(
                Finding(
                    relative_path,
                    0,
                    f"{constant_name} must contain only canonical schema identities",
                )
            )

    scan_paths = [*CHAIN_FILES, *sorted(EXPLICIT_NEGATIVE_TESTS)]
    managed_paths = {*scan_paths, *SCOPED_FUNCTIONS}
    for relative_path in sorted(managed_paths):
        match = VERSIONED_IDENTITY.search(relative_path)
        if match:
            findings.append(
                Finding(
                    relative_path,
                    0,
                    f"versioned evidence path is forbidden: {match.group(0)}",
                )
            )
    for relative_path in scan_paths:
        path = root / relative_path
        if not path.is_file():
            findings.append(Finding(relative_path, 0, "evidence chain file is missing"))
            continue
        text = path.read_text(encoding="utf-8")
        findings.extend(
            scan_text(
                relative_path,
                text,
                allowed_validator_lines=_allowed_validator_lines(
                    path,
                    relative_path,
                ),
            )
        )
        findings.extend(top_level_envelope_findings(relative_path, text))
        if relative_path in PROVIDER_ONLINE_FILES:
            for match in SERIALIZED_VERSION_FIELD.finditer(text):
                findings.append(
                    Finding(
                        relative_path,
                        text.count("\n", 0, match.start()) + 1,
                        "Provider online contract version field is forbidden",
                    )
                )
        if relative_path in PROVIDER_FIXED_COUNT_WORKFLOWS:
            for match in PROVIDER_FIXED_COUNT.finditer(text):
                findings.append(
                    Finding(
                        relative_path,
                        text.count("\n", 0, match.start()) + 1,
                        "Provider workflow must delegate exact cell count to canonical Python",
                    )
                )
        for token in REQUIRED_SOURCE_TOKENS.get(relative_path, ()):
            if token not in text:
                findings.append(
                    Finding(
                        relative_path,
                        0,
                        f"canonical consumer token is missing: {token}",
                    )
                )

    for relative_path, function_names in SCOPED_FUNCTIONS.items():
        path = root / relative_path
        if not path.is_file():
            findings.append(Finding(relative_path, 0, "evidence chain file is missing"))
            continue
        findings.extend(_scoped_source_findings(path, relative_path, function_names))

    diagnostics_path = "quwoquan_ops/ci/render_environment_chain_timing_diagnostics.py"
    diagnostics_text = (root / diagnostics_path).read_text(encoding="utf-8")
    for token in FORBIDDEN_FLAT_TIMING_FIELDS:
        if token in diagnostics_text:
            findings.append(
                Finding(
                    diagnostics_path,
                    0,
                    f"timing diagnostics still reads a retired flat field: {token}",
                )
            )
    github_timing_path = "quwoquan_ops/ci/github_actions_timing.py"
    github_timing_text = (root / github_timing_path).read_text(encoding="utf-8")
    for token in FORBIDDEN_GITHUB_TIMING_INFERENCE:
        if token in github_timing_text:
            findings.append(
                Finding(
                    github_timing_path,
                    0,
                    f"GitHub Jobs timing must not infer approval evidence: {token}",
                )
            )
    return sorted(findings, key=lambda item: (item.path, item.line, item.detail))


def main() -> int:
    findings = evidence_contract_findings()
    if findings:
        print("[verify_ci_cd_evidence_contracts] FAIL")
        for finding in findings:
            location = (
                f"{finding.path}:{finding.line}" if finding.line else finding.path
            )
            print(f"  - {location}: {finding.detail}")
        return 1
    print(
        "[verify_ci_cd_evidence_contracts] OK: canonical CI timing, release evidence, "
        "and AI advisory contracts are single-track"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
