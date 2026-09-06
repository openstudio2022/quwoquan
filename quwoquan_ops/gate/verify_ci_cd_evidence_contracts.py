#!/usr/bin/env python3
"""Verify the atomic-cutover CI/CD evidence and release-governance chain."""

from __future__ import annotations

import ast
import json
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate.ci_cd_evidence_contracts import (  # noqa: E402
    constant_resolution,
)

ENVIRONMENT_ACCEPTANCE_V2 = "quwoquan_ops.environment_acceptance_fact.v2"
CANONICAL_EVIDENCE_IDENTITIES = frozenset(
    {
        ENVIRONMENT_ACCEPTANCE_V2,
        "quwoquan_ops.environment_execution_request.v1",
        "quwoquan_ops.integration_qualification_fact.v1",
        "quwoquan_ops.promotion_admission_receipt.v1",
        "quwoquan_ops.main_source_seal.v1",
        "quwoquan_ops.release_candidate_tag_admission_fact.v1",
        "quwoquan_ops.release_tag_admission_fact.v1",
        "quwoquan_ops.prod_activation_admission_fact.v1",
        "quwoquan_ops.qualification_fact.v1",
    }
)
CANONICAL_CONSTANTS: dict[str, dict[str, object]] = {
    "quwoquan_ops/cli/lib/environment_acceptance_fact_contract.py": {
        "SCHEMA": ENVIRONMENT_ACCEPTANCE_V2,
        "DSSE_PAYLOAD_TYPE": (
            "application/vnd.quwoquan.environment-acceptance-fact.v2+json"
        ),
    },
    "quwoquan_ops/ci/environment_scheduler.py": {
        "REQUEST_SCHEMA": "quwoquan_ops.environment_execution_request.v1",
    },
    "quwoquan_ops/ci/scoped_candidate/core.py": {
        "_SCHEMA": "quwoquan_ops.exact_integration_candidate.v1",
        "_ADMISSION_SCHEMA": "quwoquan_ops.integration_publish_admission.v1",
        "_PUBLISH_RESULT_SCHEMA": "quwoquan_ops.integration_publish_result.v1",
    },
    "quwoquan_ops/ci/integration_qualification.py": {
        "SCHEMA": "quwoquan_ops.integration_qualification_fact.v1",
    },
    "quwoquan_ops/ci/promotion_evidence.py": {
        "ADMISSION_SCHEMA": "quwoquan_ops.promotion_admission_receipt.v1",
        "SEAL_SCHEMA": "quwoquan_ops.main_source_seal.v1",
        "HANDOFF_SCHEMA": "quwoquan_ops.promotion_admission_handoff.v1",
        "HANDOFF_CONTEXT": "quwoquan/promotion-admission-handoff/v1",
    },
    "quwoquan_ops/ci/release_tag_admission.py": {
        "RC_SCHEMA": "quwoquan_ops.release_candidate_tag_admission_fact.v1",
        "STABLE_SCHEMA": "quwoquan_ops.release_tag_admission_fact.v1",
    },
    "quwoquan_ops/ci/promotion_timing_ratchet.py": {
        "CLASSIFICATIONS": (
            "success",
            "failure",
            "infra",
            "superseded",
            "unclassified",
            "incomplete",
        ),
    },
}
SCHEMA_DOCUMENT_IDENTITIES: dict[str, frozenset[str]] = {
    "quwoquan_ops/environments/evidence/environment_acceptance_fact.schema.json": frozenset(
        {ENVIRONMENT_ACCEPTANCE_V2}
    ),
    "quwoquan_ops/environments/evidence/environment_execution_request.schema.json": frozenset(
        {"quwoquan_ops.environment_execution_request.v1"}
    ),
    "quwoquan_ops/environments/evidence/integration_qualification_fact.schema.json": frozenset(
        {"quwoquan_ops.integration_qualification_fact.v1"}
    ),
    "quwoquan_ops/environments/evidence/release_tag_admission_fact.schema.json": frozenset(
        {
            "quwoquan_ops.release_candidate_tag_admission_fact.v1",
            "quwoquan_ops.release_tag_admission_fact.v1",
        }
    ),
    "quwoquan_ops/environments/evidence/prod_activation_admission_fact.schema.json": frozenset(
        {"quwoquan_ops.prod_activation_admission_fact.v1"}
    ),
}

REQUIRED_RELEASE_WORKFLOWS = (
    ".github/workflows/release-qualification.yml",
    ".github/workflows/release-tag-selection.yml",
    ".github/workflows/deploy-prod-auto.yml",
)
PROMOTION_WORKFLOW = ".github/workflows/delivery-gate.yml"
FACTORY_WORKFLOW_CONTRACTS: dict[str, tuple[str, frozenset[str]]] = {
    ".github/workflows/app_pipeline.yml": (
        "quwoquan_ops.app_factory_material",
        frozenset(
            {
                "source_git_sha",
                "qualification_request_ref",
                "qualification_request_digest",
                "rc_tag_admission_ref",
                "artifact_build_number",
                "artifact_build_number_allocation_ref",
                "artifact_build_number_allocation_digest",
            }
        ),
    ),
    ".github/workflows/service_pipeline.yml": (
        "quwoquan_ops.service_factory_material",
        frozenset(
            {
                "source_sha",
                "rc_tag_admission_ref",
                "qualification_request_ref",
                "qualification_request_digest",
                "artifact_build_number",
                "artifact_build_number_allocation_ref",
                "artifact_build_number_allocation_digest",
            }
        ),
    ),
}
RETIRED_WORKFLOWS = frozenset(
    {
        ".github/workflows/pre-release-gate.yml",
        ".github/workflows/app-env-device-matrix-self-hosted.yml",
        ".github/workflows/beta-device-platform.yml",
        ".github/workflows/provider-release-evidence.yml",
    }
)
RETIRED_CANONICAL_IMPLEMENTATIONS = frozenset(
    {
        "quwoquan_ops/ci/render_environment_release_receipt.py",
        "quwoquan_ops/ci/render_release_lifecycle_receipts.py",
        "quwoquan_ops/ci/release_lifecycle_receipts",
        "quwoquan_ops/cli/prod/generate_mainline_release_artifact.py",
        "quwoquan_ops/cli/prod/finalize_mainline_release_artifact.py",
        "quwoquan_ops/cli/prod/finalize_mainline_release_artifact_lib",
        "quwoquan_ops/ci/verify_release_governance.py",
    }
)
RETIRED_EVIDENCE_IDENTITIES = frozenset(
    {
        "quwoquan_ops.environment_acceptance_fact.v1",
        "release-environment-receipt",
        "release-rollback-receipt",
        "release-rollout-receipt",
        "alpha-beta-gamma-green-matrix",
        "green-matrix",
    }
)

CHAIN_FILES = (
    "quwoquan_ops/cli/lib/environment_acceptance_fact_contract.py",
    "quwoquan_ops/cli/lib/environment_acceptance_fact_validator.py",
    "quwoquan_ops/environments/evidence/environment_acceptance_fact.schema.json",
    "quwoquan_ops/environments/evidence/environment_execution_request.schema.json",
    "quwoquan_ops/environments/evidence/integration_qualification_fact.schema.json",
    "quwoquan_ops/environments/evidence/release_tag_admission_fact.schema.json",
    "quwoquan_ops/environments/evidence/prod_activation_admission_fact.schema.json",
    "quwoquan_ops/ci/environment_scheduler.py",
    "quwoquan_ops/ci/scoped_candidate/__init__.py",
    "quwoquan_ops/ci/scoped_candidate/core.py",
    "quwoquan_ops/ci/integration_qualification.py",
    "quwoquan_ops/ci/promotion_evidence.py",
    "quwoquan_ops/ci/promotion_timing_ratchet.py",
    "quwoquan_ops/ci/release_control.py",
    "quwoquan_ops/ci/release_qualification.py",
    "quwoquan_ops/ci/release_tag_admission.py",
    "quwoquan_ops/ci/qualified_prod.py",
    "quwoquan_ops/policies/promotion_timing_ratchet.yaml",
    "quwoquan_ops/policies/release_selection_policy.yaml",
    PROMOTION_WORKFLOW,
    *REQUIRED_RELEASE_WORKFLOWS,
)

REQUIRED_SOURCE_TOKENS: dict[str, tuple[str, ...]] = {
    "quwoquan_ops/cli/lib/environment_acceptance_fact_contract.py": (
        f'SCHEMA = "{ENVIRONMENT_ACCEPTANCE_V2}"',
        "_FACT_KEYS_BY_STATUS",
        "leaseClosureEvidence",
    ),
    "quwoquan_ops/cli/lib/environment_acceptance_fact_validator.py": (
        "validate_environment_acceptance_fact",
        "DSSE_PAYLOAD_TYPE",
        "factId",
    ),
    "quwoquan_ops/ci/environment_scheduler.py": (
        "SCHEMA as ACCEPTANCE_SCHEMA",
        "validate_canonical_environment_acceptance_fact",
        '"hermetic_detached_exact_candidate"',
        '"safe_teardown_required"',
        '"acceptance_issued"',
    ),
    "quwoquan_ops/ci/scoped_candidate/core.py": (
        'private_env = {"GIT_INDEX_FILE": private_index}',
        '"expectedRemoteOid"',
        '"targetRef": "refs/heads/dev1.0"',
        "hosted_broker_cas_publish",
    ),
    "quwoquan_ops/ci/integration_qualification.py": (
        'dev_ref: str = "refs/heads/dev1.0"',
        "validate_environment_acceptance_fact",
        '"environmentChain"',
        "Alpha/Beta/Gamma predecessor chain drifted",
    ),
    "quwoquan_ops/ci/promotion_evidence.py": (
        '"syntheticMergeTree"',
        '"sourceStatus": "source-admitted"',
        '"releaseStatus": "not_selected"',
        '"promotionReadyAt"',
        '"mainReadbackAt"',
        '"promotionAdmissionOciRef"',
        '"hostedPromotionHandoff"',
        "validate_hosted_promotion_handoff",
    ),
    "quwoquan_ops/ci/promotion_timing_ratchet.py": (
        "CLASSIFICATION_SET = frozenset(CLASSIFICATIONS)",
        'policy["targetP95Seconds"] != 300',
        "nearest_rank_p95",
        "verify_monotonic",
    ),
    "quwoquan_ops/ci/release_control.py": (
        "create_promotion_admission",
        "create_main_source_seal",
        "create_qualification_request",
        "create_qualification_fact",
        "create_release_candidate_tag_intent",
        "create_release_tag_intent",
        "record_tag_mutation_outcome",
        "finalize_release_candidate_tag_admission",
        "finalize_release_tag_admission",
        "create_prod_activation_admission",
    ),
    "quwoquan_ops/ci/release_qualification.py": (
        '"buildPolicy": "build_sign_attest_once"',
        '"physicalDevicePlatforms"',
        ') != ["android", "ios"]',
        '"artifactBuildNumber"',
        '"candidateMaterialManifest"',
    ),
    "quwoquan_ops/ci/release_tag_admission.py": (
        "_require_main_reachable",
        'policy.get("production", {}).get("selector")',
        '== "ReleaseTagAdmissionFact"',
        'policy.get("stableSelection", {}).get("rebuild") == "denied"',
        '"candidateMaterialManifest"',
    ),
    "quwoquan_ops/ci/qualified_prod.py": (
        '"quwoquan_ops.release_tag_admission_fact.v1"',
        '_STAGES = ("canary", "5", "20", "50", "100")',
        '"previousActiveReleasedLedger"',
        '"rollbackReadiness"',
        '"ociDigests"',
    ),
    "quwoquan_ops/policies/promotion_timing_ratchet.yaml": (
        "targetP95Seconds: 300",
        "requiredTimingCompleteness: 1.0",
        "allowedMissingEvidence: 0",
        "expires_when: never",
    ),
    "quwoquan_ops/policies/release_selection_policy.yaml": (
        "selector: ReleaseTagAdmissionFact",
        "mainHeadDenied: true",
        "mutablePointerDenied: true",
        "rebuild: denied",
        "bypassActors: []",
    ),
    PROMOTION_WORKFLOW: (
        "name: 03. Delivery Gate",
        "pull_request:",
        "push:",
        "promotion_verify:",
        "main_source_seal:",
        "system_backsync:",
        "uses: ./.github/workflows/system-backsync.yml",
        "timeout-minutes: 5",
        '"quwoquan_ops/ci/release_control.py",',
        '"promotion-admit"',
        "promotion_evidence.py main-seal",
        "promotion_evidence.py materialize-oci",
        "actions/create-github-app-token@",
        "promotion-admission-handoff/v1",
        "validate-hosted-handoff",
        "sync_hosted_ci_timing_ledger.py append-sample",
    ),
    ".github/workflows/release-qualification.yml": (
        "name: 06. RC Qualification Factory",
        "rc_tag_admission_ref:",
        "artifact_build_number:",
        "release_qualification.py",
        "Build, sign and attest once",
    ),
    ".github/workflows/release-tag-selection.yml": (
        "name: 07. Release Tag Selection",
        "selection_fact_ref:",
        "git tag -a",
        "release_tag_admission.py",
        "release-controller",
    ),
    ".github/workflows/deploy-prod-auto.yml": (
        "name: 07. Deploy Qualified Stable Tag",
        "release_tag_admission_ref:",
        "ProdActivationAdmissionFact",
        "qualified_prod.py",
        "stackctl.py deploy --target prod-hosted",
        "canary 5 20 50 100",
    ),
}

NEGATIVE_LANGUAGE = re.compile(
    r"(?:禁止|不得|不存在|拒绝|阻断|移除|退役|forbidden|reject|must not|"
    r"never|non[-_ ]promotable|no compat|no fallback|without rebuilding)",
    re.IGNORECASE,
)
MUTABLE_AUTHORITY = re.compile(
    r"(?:RELEASED_RELEASE_EVIDENCE_REF|latestQualified|latest[_-]qualified)",
    re.IGNORECASE,
)
BARE_SOURCE_PROMOTABLE = re.compile(
    r"(?:\b(?:source(?:[_-]?(?:git|commit))?[_-]?(?:sha|oid)?|git[_-]?sha|"
    r"commit|main(?:[_ -]?head)?)\b[^\n]{0,96}(?<!non[-_ ])\b"
    r"(?:promotable|promotion[_-]?eligible|production[_-]?eligible)\b|"
    r"(?<!non[-_ ])\b(?:promotable|promotion[_-]?eligible|production[_-]?eligible)\b"
    r"[^\n]{0,96}\b(?:source(?:[_-]?(?:git|commit))?[_-]?(?:sha|oid)?|"
    r"git[_-]?sha|commit|main(?:[_ -]?head)?)\b)",
    re.IGNORECASE,
)
PROMOTION_FORBIDDEN_EXECUTION = re.compile(
    r"(?:actions/setup-(?:go|node|java)|subosito/flutter-action|\bflutter\s+test\b|"
    r"\bgo\s+test\b|\bnpm\s|\bstackctl\.py\s+(?:package|up|health|verify|deploy)\b|"
    r"\b(?:build|package|ABG|device)\b|\bprovider(?:[-_ ]conformance)?\s+live\b|"
    r"\b(?:alpha|beta|gamma)[-_ ](?:environment|matrix|execution)\b)",
    re.IGNORECASE,
)
PROD_MARKER = re.compile(
    r"(?:prod-hosted|environment\s*:\s*production|prod[_-]activation|"
    r"stackctl\.py\s+deploy|deploy[-_]prod)",
    re.IGNORECASE,
)
FACTORY_SCHEMA_IDENTITY = re.compile(
    r"[\"']schema[\"']\s*:\s*[\"']"
    r"(?P<identity>quwoquan_ops\.(?:app|service)_factory_material"
    r"(?:[._-](?:(?:v|version)?[0-9]+))?)[\"']",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    detail: str


def _constant_value(
    path: Path, constant_name: str, root: Path = ROOT, depth: int = 0
) -> object:
    return constant_resolution.constant_value(path, constant_name, root, depth)


def _negative_line(line: str) -> bool:
    """Ignore comments and explicit diagnostic assertions, not executable suffixes."""

    stripped = line.strip()
    return (
        not stripped
        or stripped.startswith("#")
        or ("echo" in stripped and NEGATIVE_LANGUAGE.search(stripped) is not None)
    )


def _retired_invocation(line: str) -> str | None:
    if _negative_line(line):
        return None
    normalized = line.replace("\\", "/")
    for retired in sorted(RETIRED_CANONICAL_IMPLEMENTATIONS):
        if retired in normalized or Path(retired).name in normalized:
            return retired
    return None


def scan_canonical_source(relative_path: str, text: str) -> list[Finding]:
    """Reject retired identities/imports only on canonical production sources."""

    findings: list[Finding] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if _negative_line(line):
            continue
        retired = _retired_invocation(line)
        if retired is not None:
            findings.append(
                Finding(relative_path, number, f"canonical source calls retired implementation: {retired}")
            )
        for identity in RETIRED_EVIDENCE_IDENTITIES:
            if identity in line:
                findings.append(
                    Finding(relative_path, number, f"retired evidence identity is forbidden: {identity}")
                )
    return findings


def _schema_identities(value: object) -> set[str]:
    identities: set[str] = set()
    if isinstance(value, Mapping):
        schema = value.get("schema")
        if isinstance(schema, Mapping) and isinstance(schema.get("const"), str):
            identities.add(schema["const"])
        for child in value.values():
            identities.update(_schema_identities(child))
    elif isinstance(value, list):
        for child in value:
            identities.update(_schema_identities(child))
    return identities


def _workflow_on(workflow: Mapping[object, object]) -> object:
    return workflow.get("on", workflow.get(True))


def _event_configuration(workflow: Mapping[object, object], event: str) -> tuple[bool, object]:
    triggers = _workflow_on(workflow)
    if isinstance(triggers, str):
        return triggers == event, None
    if isinstance(triggers, list):
        return event in triggers, None
    if isinstance(triggers, Mapping):
        return event in triggers, triggers.get(event)
    return False, None


def _push_targets_main(configuration: object) -> bool:
    if configuration is None:
        return True
    if not isinstance(configuration, Mapping):
        return True
    branches = configuration.get("branches")
    if branches is None:
        ignored = configuration.get("branches-ignore", ())
        if isinstance(ignored, str):
            ignored = [ignored]
        return "main" not in ignored
    if isinstance(branches, str):
        branches = [branches]
    return any(branch == "main" or branch == "**" for branch in branches)


def active_workflow_findings(
    relative_path: str, text: str, workflow: Mapping[object, object]
) -> list[Finding]:
    findings: list[Finding] = []
    has_push, push_configuration = _event_configuration(workflow, "push")
    if has_push and _push_targets_main(push_configuration) and (
        "prod" in Path(relative_path).stem.lower() or PROD_MARKER.search(text)
    ):
        findings.append(
            Finding(relative_path, 0, "main push must not trigger Prod behavior")
        )
    for number, line in enumerate(text.splitlines(), start=1):
        if _negative_line(line):
            continue
        mutable = MUTABLE_AUTHORITY.search(line)
        if mutable is not None:
            findings.append(
                Finding(relative_path, number, f"mutable release authority is forbidden: {mutable.group(0)}")
            )
        fallback = BARE_SOURCE_PROMOTABLE.search(line)
        if fallback is not None:
            findings.append(
                Finding(relative_path, number, "bare source promotable fallback is forbidden")
            )
        retired = _retired_invocation(line)
        if retired is not None:
            findings.append(
                Finding(relative_path, number, f"active workflow calls retired implementation: {retired}")
            )
        for identity in RETIRED_EVIDENCE_IDENTITIES:
            if identity in line:
                findings.append(
                    Finding(relative_path, number, f"active workflow requires retired evidence: {identity}")
                )
    return findings


def factory_workflow_findings(
    relative_path: str,
    text: str,
    workflow: Mapping[object, object],
    *,
    expected_schema: str,
    expected_inputs: frozenset[str],
) -> list[Finding]:
    """Require one immutable RC-qualified component-factory contract."""

    findings: list[Finding] = []
    triggers = _workflow_on(workflow)
    if not isinstance(triggers, Mapping) or set(triggers) != {"workflow_call"}:
        findings.append(
            Finding(
                relative_path,
                0,
                "factory must be reusable-only and must not react to main push",
            )
        )
        call: object = None
    else:
        call = triggers.get("workflow_call")
    inputs = call.get("inputs") if isinstance(call, Mapping) else None
    if not isinstance(inputs, Mapping) or set(inputs) != set(expected_inputs):
        findings.append(
            Finding(
                relative_path,
                0,
                "factory inputs must be exactly the explicit RC qualification inputs",
            )
        )
    elif any(
        not isinstance(configuration, Mapping)
        or configuration.get("required") not in {True, "true"}
        for configuration in inputs.values()
    ):
        findings.append(
            Finding(relative_path, 0, "every factory input must be required")
        )

    actual_schemas = {
        match.group("identity") for match in FACTORY_SCHEMA_IDENTITY.finditer(text)
    }
    if actual_schemas != {expected_schema}:
        findings.append(
            Finding(
                relative_path,
                0,
                f"factory material schema must be exactly {expected_schema!r}",
            )
        )
    for token in (
        "QUALIFICATION_REQUEST_REF",
        "QUALIFICATION_REQUEST_DIGEST",
        "RC_TAG_ADMISSION_REF",
        "materialize_evidence_oci.py",
    ):
        if token not in text:
            findings.append(
                Finding(
                    relative_path,
                    0,
                    f"factory immutable qualification check is missing: {token}",
                )
            )
    return findings


def _job_commands(job: object) -> str:
    if not isinstance(job, Mapping):
        return ""
    steps = job.get("steps")
    if not isinstance(steps, list):
        return ""
    return "\n".join(
        str(step.get("run") or "")
        for step in steps
        if isinstance(step, Mapping)
    )


def _job_checkout_ref(job: object) -> object:
    if not isinstance(job, Mapping):
        return None
    steps = job.get("steps")
    if not isinstance(steps, list):
        return None
    for step in steps:
        if isinstance(step, Mapping) and isinstance(step.get("uses"), str):
            configuration = step.get("with")
            return configuration.get("ref") if isinstance(configuration, Mapping) else None
    return None


def promotion_workflow_findings(
    relative_path: str,
    text: str,
    workflow: Mapping[object, object] | None = None,
) -> list[Finding]:
    findings: list[Finding] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if _negative_line(line):
            continue
        match = PROMOTION_FORBIDDEN_EXECUTION.search(line)
        if match is not None:
            findings.append(
                Finding(
                    relative_path,
                    number,
                    f"03 Delivery Gate contains forbidden execution: {match.group(0)}",
                )
            )

    if workflow is None:
        return findings

    triggers = _workflow_on(workflow)
    expected_triggers = {
        "pull_request": {"branches": ["main"]},
        "push": {"branches": ["main"]},
    }
    if triggers != expected_triggers:
        findings.append(
            Finding(
                relative_path,
                0,
                "promotion workflow must use only pull_request and trusted post-merge main push",
            )
        )

    if workflow.get("permissions") != {"contents": "read"}:
        findings.append(
            Finding(relative_path, 0, "promotion workflow top-level permissions must be contents: read")
        )

    jobs = workflow.get("jobs")
    expected_jobs = ["promotion_verify", "main_source_seal", "system_backsync"]
    if not isinstance(jobs, Mapping) or list(jobs) != expected_jobs:
        findings.append(
            Finding(
                relative_path,
                0,
                "promotion workflow must separate pre-merge verification and MainSourceSeal, then expose exactly one system backsync caller",
            )
        )
        return findings

    premerge = jobs["promotion_verify"]
    postmerge = jobs["main_source_seal"]
    backsync = jobs["system_backsync"]
    pre_commands = _job_commands(premerge)
    post_commands = _job_commands(postmerge)
    expected_permissions = {
        "promotion_verify": {"contents": "read", "packages": "write"},
        "main_source_seal": {
            "contents": "read", "packages": "write",
            "checks": "read", "pull-requests": "read",
        },
    }
    for job_name, job in (("promotion_verify", premerge), ("main_source_seal", postmerge)):
        if not isinstance(job, Mapping) or job.get("permissions") != expected_permissions[job_name]:
            findings.append(
                Finding(relative_path, 0, f"{job_name} permissions drifted from least privilege")
            )
        if not isinstance(job, Mapping) or job.get("runs-on") != "ubuntu-latest":
            findings.append(Finding(relative_path, 0, f"{job_name} must use a GitHub-hosted portable runner"))
        if not isinstance(job, Mapping) or job.get("timeout-minutes") != 5:
            findings.append(Finding(relative_path, 0, f"{job_name} must retain the five-minute job boundary"))

    pre_condition = str(premerge.get("if") or "") if isinstance(premerge, Mapping) else ""
    if pre_condition != "${{ github.event_name == 'pull_request' }}":
        findings.append(
            Finding(
                relative_path,
                0,
                "pre-merge job must run for every pull request targeting main and fail closed inside the job",
            )
        )
    for token in (
        'values["HEAD_REF"] != "dev1.0"',
        'values["BASE_REF"] != "main"',
        'os.environ["PR_HEAD_REPOSITORY"] != os.environ["REPOSITORY"]',
    ):
        if token not in _job_commands(premerge):
            findings.append(
                Finding(relative_path, 0, f"pre-merge qualification validation is missing: {token}")
            )
    for token in (
        "actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1",
        "permission-checks: write",
        "promotion_evidence.py create-handoff",
        "/check-runs",
    ):
        if token not in text:
            findings.append(Finding(relative_path, 0, f"trusted hosted handoff producer is missing: {token}"))
    if '"promotion_admission_ref"' in pre_commands:
        findings.append(Finding(relative_path, 0, "PR body must not self-assert final exact admission ref"))

    expected_push_condition = (
        "${{ github.event_name == 'push' && github.ref == 'refs/heads/main' }}"
    )
    if not isinstance(postmerge, Mapping) or postmerge.get("if") != expected_push_condition:
        findings.append(
            Finding(relative_path, 0, "MainSourceSeal must run only for the trusted main push event")
        )

    expected_seal_outputs = {
        "source_sha": "${{ steps.readback.outputs.source_sha }}",
        "main_source_seal_ref": "${{ steps.seal.outputs.main_source_seal_ref }}",
        "main_source_seal_digest": "${{ steps.seal.outputs.main_source_seal_digest }}",
    }
    if not isinstance(postmerge, Mapping) or postmerge.get("outputs") != expected_seal_outputs:
        findings.append(
            Finding(
                relative_path,
                0,
                "MainSourceSeal job outputs must expose the exact readback source and seal ref/digest",
            )
        )

    expected_backsync_permissions = {
        "actions": "read",
        "checks": "read",
        "contents": "read",
        "packages": "read",
    }
    expected_backsync_inputs = {
        "expected_dev_before": "${{ needs.main_source_seal.outputs.source_sha }}",
        "source_sha": "${{ needs.main_source_seal.outputs.source_sha }}",
        "main_source_seal_ref": "${{ needs.main_source_seal.outputs.main_source_seal_ref }}",
        "main_source_seal_digest": "${{ needs.main_source_seal.outputs.main_source_seal_digest }}",
    }
    allowed_backsync_keys = {"name", "needs", "if", "permissions", "uses", "with"}
    if not isinstance(backsync, Mapping):
        findings.append(Finding(relative_path, 0, "system backsync caller must be a reusable workflow job"))
    else:
        if set(backsync) != allowed_backsync_keys:
            findings.append(
                Finding(
                    relative_path,
                    0,
                    "system backsync caller must contain no direct steps, environment, runner, secrets, or fallback",
                )
            )
        if backsync.get("needs") != "main_source_seal":
            findings.append(Finding(relative_path, 0, "system backsync caller must need MainSourceSeal"))
        if backsync.get("if") != expected_push_condition:
            findings.append(Finding(relative_path, 0, "system backsync caller must run only for the trusted main push event"))
        if backsync.get("uses") != "./.github/workflows/system-backsync.yml":
            findings.append(Finding(relative_path, 0, "system backsync caller must use the same-commit canonical reusable workflow"))
        if backsync.get("permissions") != expected_backsync_permissions:
            findings.append(Finding(relative_path, 0, "system backsync caller permissions drifted from read-only least privilege"))
        if backsync.get("with") != expected_backsync_inputs:
            findings.append(Finding(relative_path, 0, "system backsync caller must consume only exact sealed outputs"))

    if _job_checkout_ref(premerge) != "${{ github.event.pull_request.head.sha }}":
        findings.append(Finding(relative_path, 0, "pre-merge checkout must bind the exact PR head SHA"))
    if _job_checkout_ref(postmerge) != "${{ github.event.after }}":
        findings.append(Finding(relative_path, 0, "post-merge checkout must bind the exact main push after SHA"))
    if "github.sha" in text:
        findings.append(Finding(relative_path, 0, "github.sha fallback is forbidden in source promotion"))

    for token in (
        "main-seal",
        "main-source-seal",
        "promotion_timing_ratchet.py sample",
        "sync_hosted_ci_timing_ledger.py append-sample",
    ):
        if token in pre_commands:
            findings.append(
                Finding(relative_path, 0, f"pre-merge qualification must not issue post-merge evidence: {token}")
            )
    if "promotion-admit" not in pre_commands:
        findings.append(Finding(relative_path, 0, "pre-merge qualification must issue PromotionAdmissionReceipt"))
    if "promotion-admit" in post_commands:
        findings.append(
            Finding(relative_path, 0, "post-merge sealing must consume rather than recreate PromotionAdmissionReceipt")
        )

    required_postmerge_tokens = (
        ("refs/remotes/origin/main", "hosted main HEAD readback"),
        ("PUSH_BEFORE_SHA", "main push before identity"),
        ("PUSH_AFTER_SHA", "main push after identity"),
        ("/commits/${SOURCE_SHA}/check-runs", "exact hosted handoff lookup"),
        ("HANDOFF_COUNT", "create-once hosted handoff cardinality"),
        ("validate-hosted-handoff", "hosted App/workflow identity verification"),
        ("--ref \"$PROMOTION_ADMISSION_REF\"", "exact PromotionAdmissionReceipt materialization"),
        ("git merge-base --is-ancestor", "post-merge source reachability"),
        ("promotion_evidence.py main-seal", "MainSourceSeal exact predecessor issuance"),
        ("--admission-oci-ref \"$PROMOTION_ADMISSION_REF\"", "MainSourceSeal exact OCI binding"),
        ("--hosted-handoff", "MainSourceSeal hosted record binding"),
        ("main-source-seal-oci.json", "MainSourceSeal OCI publication"),
        ("--ref \"$MAIN_SOURCE_SEAL_REF\"", "hosted MainSourceSeal readback"),
        ("cmp \"$CONTROL_ROOT/$SEAL_PATH\" \"$RUNNER_TEMP/main-source-seal-readback.json\"", "exact MainSourceSeal byte readback"),
        ("promotion_timing_ratchet.py sample", "post-readback promotion timing sample"),
        ("sync_hosted_ci_timing_ledger.py append-sample", "hosted timing sample readback"),
    )
    for token, description in required_postmerge_tokens:
        if token not in post_commands:
            findings.append(Finding(relative_path, 0, f"post-merge path is missing {description}"))

    order_tokens = (
        "refs/remotes/origin/main",
        "/commits/${SOURCE_SHA}/check-runs",
        "validate-hosted-handoff",
        "promotion_evidence.py materialize-oci",
        "git merge-base --is-ancestor",
        "promotion_evidence.py main-seal",
        "main-source-seal-readback.json",
        'cmp "$CONTROL_ROOT/$SEAL_PATH" "$RUNNER_TEMP/main-source-seal-readback.json"',
        'MAIN_SOURCE_SEAL_DIGEST="${MAIN_SOURCE_SEAL_REF##*@}"',
        'echo "main_source_seal_digest=$MAIN_SOURCE_SEAL_DIGEST"',
        "promotion_timing_ratchet.py sample",
        "sync_hosted_ci_timing_ledger.py append-sample",
    )
    positions = [post_commands.find(token) for token in order_tokens]
    if any(position < 0 for position in positions) or positions != sorted(positions):
        findings.append(
            Finding(
                relative_path,
                0,
                "post-merge order must preserve MainSourceSeal post-readback ref/digest outputs before timing and backsync",
            )
        )

    forbidden_authority = (
        "oras resolve", '"promotion_admission_ref"', "latest",
        "promotion-handoff-status", "$STORE/promotion-handoff",
    )
    for token in forbidden_authority:
        if token in post_commands:
            findings.append(
                Finding(relative_path, 0, f"post-merge mutable or local handoff authority is forbidden: {token}")
            )
    for fake in (
        "$STORE/main-source-seal.json",
        'cp "$SEAL_PATH" "$RUNNER_TEMP/main-source-seal-readback.json"',
        'cp "$CONTROL_ROOT/$SEAL_PATH" "$RUNNER_TEMP/main-source-seal-readback.json"',
    ):
        if fake in post_commands:
            findings.append(
                Finding(relative_path, 0, "local store must not masquerade as hosted MainSourceSeal readback")
            )
    return findings


def _active_workflow_paths(root: Path) -> list[Path]:
    directory = root / ".github/workflows"
    return sorted({*directory.glob("*.yml"), *directory.glob("*.yaml")})



def _retired_modules() -> dict[str, str]:
    return {
        relative.removesuffix(".py").replace("/", "."): relative
        for relative in RETIRED_CANONICAL_IMPLEMENTATIONS
    }


HISTORICAL_READER_MODULE = "quwoquan_ops.ci.release_evidence_reader"
HISTORICAL_READER_PATH = "quwoquan_ops/ci/release_evidence_reader.py"
ALLOWED_HISTORICAL_READERS = frozenset(
    {
        "validate_frozen_diagnostic_snapshot",
        "validate_historical_release_snapshot",
    }
)
GENERIC_HISTORICAL_VALIDATORS = frozenset(
    {"validate", "validate_manifest", "validate_manifest_files"}
)
RETIRED_PUBLIC_SYMBOLS = frozenset(
    {
        "_command_package_release_manifest",
        "finalize_mainline_release_artifact",
        "generate_mainline_release_artifact",
    }
)
_UNRESOLVED = object()
_PACKAGE_RELEASE_MANIFEST = "release-manifest"
_FORMAL_RELEASE_MANIFEST_OPTION = "--release-manifest"
_PACKAGE_COMMAND_PATTERN = re.compile(
    r"(?:^|\s)package\s+--kind(?:=|\s+)release-manifest(?:$|\s)"
)


def _inside_retired_implementation(relative_path: str) -> bool:
    return any(
        relative_path == retired
        or relative_path.startswith(retired.rstrip("/") + "/")
        for retired in RETIRED_CANONICAL_IMPLEMENTATIONS
    )


def historical_implementation_paths(root: Path = ROOT) -> list[str]:
    """List frozen retired implementation bytes that must be deleted."""

    return sorted(
        relative
        for relative in RETIRED_CANONICAL_IMPLEMENTATIONS
        if (root / relative).is_file()
        or (
            (root / relative).is_dir()
            and any((root / relative).rglob("*"))
        )
    )


def retired_implementation_findings(root: Path = ROOT) -> list[Finding]:
    """Fail closed while any frozen writer/finalizer implementation remains."""

    return [
        Finding(path, 0, "retired writer/finalizer implementation must be deleted")
        for path in historical_implementation_paths(root)
    ]


def _static_value(node: ast.AST, constants: Mapping[str, object]) -> object:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id, _UNRESOLVED)
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        values = [_static_value(item, constants) for item in node.elts]
        if any(value is _UNRESOLVED for value in values):
            return _UNRESOLVED
        return tuple(values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _static_value(node.left, constants)
        right = _static_value(node.right, constants)
        if isinstance(left, str) and isinstance(right, str):
            return left + right
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            elif isinstance(value, ast.FormattedValue):
                resolved = _static_value(value.value, constants)
                if resolved is _UNRESOLVED:
                    return _UNRESOLVED
                parts.append(str(resolved))
            else:
                return _UNRESOLVED
        return "".join(parts)
    return _UNRESOLVED


def _constant_bindings(tree: ast.AST) -> dict[str, object]:
    constants: dict[str, object] = {}
    assignments = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Assign, ast.AnnAssign))
    ]
    for _ in range(len(assignments) + 1):
        changed = False
        for assignment in assignments:
            if assignment.value is None:
                continue
            value = _static_value(assignment.value, constants)
            if value is _UNRESOLVED:
                continue
            targets = (
                assignment.targets
                if isinstance(assignment, ast.Assign)
                else [assignment.target]
            )
            for target in targets:
                if (
                    isinstance(target, ast.Name)
                    and constants.get(target.id, _UNRESOLVED) != value
                ):
                    constants[target.id] = value
                    changed = True
        if not changed:
            break
    return constants


def _qualified_name(node: ast.AST, bindings: Mapping[str, str]) -> str | None:
    if isinstance(node, ast.Name):
        return bindings.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        parent = _qualified_name(node.value, bindings)
        return f"{parent}.{node.attr}" if parent else None
    return None


def _callable_name(
    node: ast.AST,
    bindings: Mapping[str, str],
    constants: Mapping[str, object],
) -> str | None:
    qualified = _qualified_name(node, bindings)
    if qualified is not None:
        return qualified
    if not isinstance(node, ast.Call) or len(node.args) < 2:
        return None
    getter = _qualified_name(node.func, bindings)
    if getter not in {"getattr", "builtins.getattr"}:
        return None
    target = _qualified_name(node.args[0], bindings)
    attribute = _static_value(node.args[1], constants)
    if target is None or not isinstance(attribute, str):
        return None
    return f"{target}.{attribute}"


def _resolve_relative_module(name: str, package: str) -> str | None:
    if not name.startswith("."):
        return name
    level = len(name) - len(name.lstrip("."))
    package_parts = package.split(".")
    if level > len(package_parts):
        return None
    base = package_parts[: len(package_parts) - level + 1]
    child = name[level:]
    return ".".join([*base, *([child] if child else [])])


def _dynamic_import_target(
    node: ast.AST,
    bindings: Mapping[str, str],
    constants: Mapping[str, object],
) -> str | None:
    if not isinstance(node, ast.Call) or not node.args:
        return None
    function = _callable_name(node.func, bindings, constants)
    if function not in {
        "importlib.import_module",
        "__import__",
        "builtins.__import__",
    }:
        return None
    value = _static_value(node.args[0], constants)
    if not isinstance(value, str):
        return None
    if function == "importlib.import_module" and value.startswith("."):
        package = (
            _static_value(node.args[1], constants)
            if len(node.args) > 1
            else _UNRESOLVED
        )
        if not isinstance(package, str):
            return None
        return _resolve_relative_module(value, package)
    return value


def _module_bindings(
    tree: ast.AST, constants: Mapping[str, object]
) -> dict[str, str]:
    bindings: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bound = alias.asname or alias.name.split(".", 1)[0]
                bindings[bound] = alias.name if alias.asname else bound
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                if alias.name != "*":
                    bindings[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    assignments = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Assign, ast.AnnAssign))
    ]
    for _ in range(len(assignments) + 1):
        changed = False
        for assignment in assignments:
            if assignment.value is None:
                continue
            module = _dynamic_import_target(
                assignment.value, bindings, constants
            )
            if module is None and isinstance(assignment.value, ast.Call):
                call = assignment.value
                getter = _qualified_name(call.func, bindings)
                if getter in {"getattr", "builtins.getattr"} and len(call.args) >= 2:
                    target = _qualified_name(call.args[0], bindings)
                    attribute = _static_value(call.args[1], constants)
                    if target is not None and isinstance(attribute, str):
                        module = f"{target}.{attribute}"
            if module is None:
                continue
            targets = (
                assignment.targets
                if isinstance(assignment, ast.Assign)
                else [assignment.target]
            )
            for target in targets:
                if isinstance(target, ast.Name) and bindings.get(target.id) != module:
                    bindings[target.id] = module
                    changed = True
        if not changed:
            break
    return bindings


def _retired_module_path(module: str) -> str | None:
    for retired_module, retired_path in _retired_modules().items():
        if module == retired_module or module.startswith(retired_module + "."):
            return retired_path
    return None


def _historical_symbol_is_forbidden(symbol: str) -> bool:
    if symbol in ALLOWED_HISTORICAL_READERS:
        return False
    lowered = symbol.lower()
    return symbol in GENERIC_HISTORICAL_VALIDATORS or any(
        token in lowered
        for token in (
            "writer",
            "write",
            "finaliz",
            "seal",
            "verdict",
            "admission",
            "admit",
            "publish",
            "persist",
        )
    )


def _finding(relative_path: str, node: ast.AST, detail: str) -> Finding:
    return Finding(relative_path, getattr(node, "lineno", 0), detail)


def _import_findings(
    relative_path: str, tree: ast.AST
) -> list[Finding]:
    findings: list[Finding] = []
    modules = _retired_modules()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports = [(alias.name, alias.name.rsplit(".", 1)[-1]) for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports = [(node.module, alias.name) for alias in node.names]
        else:
            continue
        for module, symbol in imports:
            candidates = (module, f"{module}.{symbol}")
            retired = next(
                (
                    retired_path
                    for candidate in candidates
                    for retired_module, retired_path in modules.items()
                    if candidate == retired_module
                    or candidate.startswith(retired_module + ".")
                ),
                None,
            )
            if retired is not None:
                findings.append(
                    _finding(
                        relative_path,
                        node,
                        f"production import calls retired implementation: {retired}",
                    )
                )
            if (
                isinstance(node, ast.ImportFrom)
                and node.module == HISTORICAL_READER_MODULE
                and (symbol == "*" or _historical_symbol_is_forbidden(symbol))
            ):
                findings.append(
                    _finding(
                        relative_path,
                        node,
                        f"historical reader import exposes forbidden surface: {symbol}",
                    )
                )
            if isinstance(node, ast.ImportFrom) and symbol in RETIRED_PUBLIC_SYMBOLS:
                findings.append(
                    _finding(relative_path, node, f"retired public surface is forbidden: {symbol}")
                )
    return findings


def _dynamic_surface_findings(
    relative_path: str,
    tree: ast.AST,
    constants: Mapping[str, object],
    bindings: Mapping[str, str],
) -> list[Finding]:
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            module = _dynamic_import_target(node, bindings, constants)
            if module is not None:
                candidates = [module]
                function = _callable_name(node.func, bindings, constants)
                if function in {"__import__", "builtins.__import__"}:
                    fromlist = next(
                        (
                            keyword.value
                            for keyword in node.keywords
                            if keyword.arg == "fromlist"
                        ),
                        node.args[3] if len(node.args) > 3 else None,
                    )
                    children = _static_value(fromlist, constants) if fromlist else ()
                    if isinstance(children, tuple):
                        candidates.extend(
                            f"{module}.{child}" for child in children if isinstance(child, str)
                        )
                retired = next(
                    (_retired_module_path(candidate) for candidate in candidates if _retired_module_path(candidate)),
                    None,
                )
                if retired is not None:
                    findings.append(
                        _finding(relative_path, node, f"dynamic import reaches retired implementation: {retired}")
                    )
                elif module == HISTORICAL_READER_MODULE:
                    findings.append(
                        _finding(relative_path, node, "historical reader must not be loaded through a dynamic import surface")
                    )
            function = _callable_name(node.func, bindings, constants)
            if function in {
                "getattr",
                "builtins.getattr",
                "setattr",
                "builtins.setattr",
            } and len(node.args) >= 2:
                attribute = _static_value(node.args[1], constants)
                target = _qualified_name(node.args[0], bindings) or _dynamic_import_target(
                    node.args[0], bindings, constants
                )
                if isinstance(attribute, str):
                    candidate = f"{target}.{attribute}" if target else attribute
                    retired = _retired_module_path(candidate)
                    forbidden_historical = (
                        target == HISTORICAL_READER_MODULE
                        and _historical_symbol_is_forbidden(attribute)
                    )
                    if retired is not None or attribute in RETIRED_PUBLIC_SYMBOLS or forbidden_historical:
                        findings.append(
                            _finding(relative_path, node, f"dynamic attribute reaches retired surface: {candidate}")
                        )
        elif isinstance(node, ast.Attribute):
            qualified = _qualified_name(node, bindings)
            if qualified is None:
                continue
            retired = _retired_module_path(qualified)
            historical_prefix = HISTORICAL_READER_MODULE + "."
            if retired is not None or (
                qualified.startswith(historical_prefix)
                and _historical_symbol_is_forbidden(qualified.removeprefix(historical_prefix).split(".", 1)[0])
            ):
                findings.append(
                    _finding(relative_path, node, f"attribute reaches retired surface: {qualified}")
                )
    return findings


def _node_is_under_assert(node: ast.AST, parents: Mapping[ast.AST, ast.AST]) -> bool:
    parent = parents.get(node)
    while parent is not None:
        if isinstance(parent, ast.Assert):
            return True
        parent = parents.get(parent)
    return False


def _old_package_command(value: object) -> bool:
    if isinstance(value, str):
        return _PACKAGE_COMMAND_PATTERN.search(value) is not None
    if isinstance(value, tuple) and all(isinstance(item, str) for item in value):
        return _PACKAGE_COMMAND_PATTERN.search(" ".join(value)) is not None
    return False


def _cli_surface_findings(
    relative_path: str,
    tree: ast.AST,
    constants: Mapping[str, object],
    bindings: Mapping[str, str],
) -> list[Finding]:
    findings: list[Finding] = []
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    for node in ast.walk(tree):
        if _node_is_under_assert(node, parents):
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_command_package_release_manifest":
            findings.append(_finding(relative_path, node, "public release-manifest package writer is forbidden"))
        if isinstance(node, ast.Call):
            function = _callable_name(node.func, bindings, constants) or ""
            positional = [_static_value(argument, constants) for argument in node.args]
            if function.endswith(".add_argument"):
                options = {value for value in positional if isinstance(value, str)}
                if _FORMAL_RELEASE_MANIFEST_OPTION in options:
                    findings.append(
                        _finding(
                            relative_path,
                            node,
                            "formal --release-manifest argparse option is forbidden",
                        )
                    )
                if "--kind" in options:
                    choices_node = next(
                        (keyword.value for keyword in node.keywords if keyword.arg == "choices"),
                        None,
                    )
                    choices = _static_value(choices_node, constants) if choices_node else ()
                    if isinstance(choices, tuple) and _PACKAGE_RELEASE_MANIFEST in choices:
                        findings.append(_finding(relative_path, node, "public package --kind release-manifest choice is forbidden"))
            if function.rsplit(".", 1)[-1] in {"run", "Popen", "call", "check_call", "check_output"} and any(
                _old_package_command(value) for value in positional
            ):
                findings.append(_finding(relative_path, node, "public package --kind release-manifest invocation is forbidden"))
        elif isinstance(node, ast.Compare):
            values = [
                _static_value(node.left, constants),
                *(
                    _static_value(item, constants)
                    for item in node.comparators
                ),
            ]
            contains_retired_kind = any(
                value == _PACKAGE_RELEASE_MANIFEST
                or (
                    isinstance(value, tuple)
                    and _PACKAGE_RELEASE_MANIFEST in value
                )
                for value in values
            )
            names = {
                item.id.lower()
                for item in ast.walk(node)
                if isinstance(item, ast.Name)
            }
            positive = any(
                isinstance(operator, (ast.Eq, ast.Is, ast.In))
                for operator in node.ops
            )
            if contains_retired_kind and positive and any(
                any(token in name for token in ("kind", "package", "command", "dispatch"))
                for name in names
            ):
                findings.append(_finding(relative_path, node, "public package --kind release-manifest dispatch is forbidden"))
        elif isinstance(node, ast.Dict):
            keys = [_static_value(key, constants) for key in node.keys if key is not None]
            if _PACKAGE_RELEASE_MANIFEST in keys:
                findings.append(
                    _finding(
                        relative_path,
                        node,
                        "public package --kind release-manifest dispatch mapping is forbidden",
                    )
                )
        elif (
            isinstance(node, ast.MatchValue)
            and _static_value(node.value, constants) == _PACKAGE_RELEASE_MANIFEST
        ):
            findings.append(
                _finding(
                    relative_path,
                    node,
                    "public package --kind release-manifest match dispatch is forbidden",
                )
            )
    return findings


def _historical_reader_definition_findings(
    relative_path: str, tree: ast.AST, constants: Mapping[str, object]
) -> list[Finding]:
    if relative_path != HISTORICAL_READER_PATH:
        return []
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
            node.name == "__getattr__" or _historical_symbol_is_forbidden(node.name)
        ):
            findings.append(_finding(relative_path, node, f"historical reader defines forbidden surface: {node.name}"))
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and (
                    target.id == "__getattr__" or _historical_symbol_is_forbidden(target.id)
                ):
                    findings.append(_finding(relative_path, node, f"historical reader aliases forbidden surface: {target.id}"))
            if any(isinstance(target, ast.Name) and target.id == "__all__" for target in targets):
                exports = _static_value(node.value, constants)
                if isinstance(exports, tuple):
                    for export in exports:
                        if isinstance(export, str) and _historical_symbol_is_forbidden(export):
                            findings.append(_finding(relative_path, node, f"historical reader exports forbidden surface: {export}"))
    return findings


def retired_import_findings(root: Path = ROOT) -> list[Finding]:
    """Reject static/dynamic production reachability to every retired surface."""

    findings: list[Finding] = []
    candidates: set[Path] = set()
    for source_root in (root / "quwoquan_ops/ci", root / "quwoquan_ops/cli"):
        if source_root.is_dir():
            candidates.update(source_root.rglob("*.py"))
    for path in sorted(candidates):
        relative_path = path.relative_to(root).as_posix()
        if _inside_retired_implementation(relative_path):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, UnicodeError, SyntaxError) as exc:
            findings.append(Finding(relative_path, 0, f"cannot inspect production retired surfaces: {exc}"))
            continue
        constants = _constant_bindings(tree)
        bindings = _module_bindings(tree, constants)
        findings.extend(_import_findings(relative_path, tree))
        findings.extend(_dynamic_surface_findings(relative_path, tree, constants, bindings))
        findings.extend(_cli_surface_findings(relative_path, tree, constants, bindings))
        findings.extend(_historical_reader_definition_findings(relative_path, tree, constants))
    return sorted(set(findings), key=lambda item: (item.path, item.line, item.detail))

def release_control_tag_api_findings(relative_path: str, text: str) -> list[Finding]:
    """Require every canonical tag phase as executable release-control calls."""

    release_control = "quwoquan_ops/ci/release_control.py"
    if relative_path != release_control:
        return []
    try:
        tree = ast.parse(text, filename=relative_path)
    except SyntaxError as exc:
        return [Finding(relative_path, 0, f"cannot inspect release tag API calls: {exc}")]
    called = {
        node.func.id for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    canonical = REQUIRED_SOURCE_TOKENS[release_control][4:-1]
    return [
        Finding(relative_path, 0, f"canonical release tag API call is missing: {api}")
        for api in canonical if api not in called
    ]


def _configuration_findings() -> list[Finding]:
    findings: list[Finding] = []
    chain = set(CHAIN_FILES)
    retired_overlap = chain & RETIRED_CANONICAL_IMPLEMENTATIONS
    for path in sorted(retired_overlap):
        findings.append(Finding(path, 0, "retired implementation remains canonical in CHAIN_FILES"))
    for path in sorted(set(REQUIRED_SOURCE_TOKENS) & RETIRED_CANONICAL_IMPLEMENTATIONS):
        findings.append(Finding(path, 0, "retired implementation remains canonical in REQUIRED_SOURCE_TOKENS"))
    missing_workflows = set(REQUIRED_RELEASE_WORKFLOWS) - chain
    for path in sorted(missing_workflows):
        findings.append(Finding(path, 0, "permanent release workflow is absent from CHAIN_FILES"))
    if PROMOTION_WORKFLOW not in chain:
        findings.append(Finding(PROMOTION_WORKFLOW, 0, "03 Delivery Gate is absent from CHAIN_FILES"))
    return findings


def evidence_contract_findings(root: Path = ROOT) -> list[Finding]:
    findings = _configuration_findings()

    for relative_path in sorted(RETIRED_WORKFLOWS):
        if (root / relative_path).exists():
            findings.append(Finding(relative_path, 0, "retired workflow must not exist after atomic cutover"))

    for relative_path in CHAIN_FILES:
        path = root / relative_path
        if not path.is_file():
            findings.append(Finding(relative_path, 0, "canonical atomic-cutover chain file is missing"))
            continue
        text = path.read_text(encoding="utf-8")
        for token in REQUIRED_SOURCE_TOKENS.get(relative_path, ()):
            if token not in text:
                findings.append(
                    Finding(relative_path, 0, f"canonical source token is missing: {token}")
                )
        findings.extend(release_control_tag_api_findings(relative_path, text))
        if relative_path not in {PROMOTION_WORKFLOW, *REQUIRED_RELEASE_WORKFLOWS}:
            findings.extend(scan_canonical_source(relative_path, text))

    for relative_path, constants in CANONICAL_CONSTANTS.items():
        path = root / relative_path
        if not path.is_file():
            continue
        for name, expected in constants.items():
            try:
                actual = _constant_value(path, name, root)
            except (SyntaxError, ValueError) as exc:
                findings.append(Finding(relative_path, 0, f"cannot resolve {name}: {exc}"))
                continue
            if actual != expected:
                findings.append(
                    Finding(relative_path, 0, f"{name} must equal {expected!r}, got {actual!r}")
                )

    for relative_path, expected in SCHEMA_DOCUMENT_IDENTITIES.items():
        path = root / relative_path
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            findings.append(Finding(relative_path, 0, f"canonical schema document is invalid: {exc}"))
            continue
        actual = _schema_identities(payload)
        if actual != set(expected):
            findings.append(
                Finding(relative_path, 0, f"schema document identities must be exactly {sorted(expected)!r}")
            )

    for path in _active_workflow_paths(root):
        relative_path = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        try:
            workflow = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            findings.append(Finding(relative_path, 0, f"active workflow YAML is invalid: {exc}"))
            continue
        if not isinstance(workflow, Mapping):
            findings.append(Finding(relative_path, 0, "active workflow must be a YAML object"))
            continue
        findings.extend(active_workflow_findings(relative_path, text, workflow))
        factory_contract = FACTORY_WORKFLOW_CONTRACTS.get(relative_path)
        if factory_contract is not None:
            expected_schema, expected_inputs = factory_contract
            findings.extend(
                factory_workflow_findings(
                    relative_path,
                    text,
                    workflow,
                    expected_schema=expected_schema,
                    expected_inputs=expected_inputs,
                )
            )
        if relative_path == PROMOTION_WORKFLOW:
            findings.extend(promotion_workflow_findings(relative_path, text, workflow))

    findings.extend(retired_implementation_findings(root))
    findings.extend(retired_import_findings(root))
    return sorted(set(findings), key=lambda item: (item.path, item.line, item.detail))


def main() -> int:
    findings = evidence_contract_findings()
    if findings:
        print("[verify_ci_cd_evidence_contracts] FAIL")
        for finding in findings:
            location = f"{finding.path}:{finding.line}" if finding.line else finding.path
            print(f"  - {location}: {finding.detail}")
        return 1
    print(
        "[verify_ci_cd_evidence_contracts] OK: EnvironmentAcceptanceFact v2, "
        "scoped integration, evidence-only promotion, RC qualification, stable-tag "
        "admission and qualified Prod are single-track"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
