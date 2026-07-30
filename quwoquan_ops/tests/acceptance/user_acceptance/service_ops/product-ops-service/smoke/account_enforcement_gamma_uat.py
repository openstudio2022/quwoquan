"""Fail-closed Gamma account-enforcement UAT evidence aggregation.

The live journey crosses operator OIDC, Product Ops PostgreSQL/outbox,
UserAccount, two physical App platforms, fault injection, readiness and
observability.  This module deliberately does not invent a test-only service
or a second environment entry.  It accepts only immutable artifacts below
``QWQ_OUTPUT_ROOT`` and emits a passed CaseResult after every required fact is
present, internally consistent and bound to one candidate digest.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping


def _find_repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "quwoquan_app").is_dir() and (
            candidate / "quwoquan_service"
        ).is_dir():
            return candidate
    raise RuntimeError("cannot locate quwoquan repository root")


REPO_ROOT = _find_repo_root()
DEFAULT_MANIFEST = (
    REPO_ROOT
    / "quwoquan_ops"
    / "tests"
    / "acceptance"
    / "user_acceptance"
    / "service_ops"
    / "product-ops-service"
    / "smoke"
    / "account_enforcement_gamma_uat_manifest.json"
)
MANIFEST_SCHEMA = "qwq.account-enforcement-gamma-uat-manifest"
EVIDENCE_SCHEMA = "qwq.account-enforcement-gamma-evidence"
JOURNEY_SCHEMA = "qwq.account-enforcement-gamma-journey-receipt"
CASE_RESULT_SCHEMA = "qwq.account-enforcement-gamma-case-result"
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$")
JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")

EXPECTED_SPEC_REFS = (
    "specs/feature-tree/product-ops-growth/product-control-plane-foundation/"
    "account-moderation-and-appeal-enforcement/spec.md#gwt-003",
    "specs/feature-tree/user-identity-profile-relationship/"
    "settings-and-device-token/account-suspension-and-appeal-lifecycle/"
    "spec.md#gwt-003",
)
EXPECTED_OPERATION_SCOPES = {
    "ops.account_enforcement_case.GetAccountEnforcementCase": (
        "ops.account.enforcement.read"
    ),
    "ops.account_enforcement_case.OpenAccountAppealCase": (
        "ops.account.appeal.write"
    ),
    "ops.account_enforcement_case.OpenAccountModerationCase": (
        "ops.account.moderation.write"
    ),
    "ops.account_enforcement_case.RetryAccountEnforcementDelivery": (
        "ops.account.enforcement.recover"
    ),
    "ops.account_enforcement_case.ReviewAccountEnforcementCase": (
        "ops.account.enforcement.review"
    ),
}
EXPECTED_PHASE_ORDER = (
    "authorization_preflight",
    "moderation_dual_approval",
    "suspend_delivery",
    "suspended_android_ios",
    "appeal_dual_approval",
    "restore_delivery",
    "restored_android_ios",
    "recoverable_delivery_failure",
    "terminal_dead_letter",
    "same_decision_recovery",
    "observability_readback",
    "cleanup",
)
EXPECTED_ASSERTIONS = (
    "operator_oidc_and_scope_fail_closed",
    "distinct_dual_approval_issues_one_suspend",
    "postgres_transaction_and_outbox_are_atomic",
    "service_identity_delivers_to_user_account",
    "old_credentials_are_rejected",
    "android_and_ios_show_suspended_recovery",
    "appeal_restores_and_new_session_logs_in",
    "android_and_ios_restore_remote_session",
    "recoverable_delivery_failure_is_bounded",
    "terminal_dlq_blocks_readiness_without_pii",
    "same_decision_recovery_clears_readiness",
    "trace_metrics_alerts_and_cleanup_align",
)
EXPECTED_ARTIFACT_KINDS = (
    "authorization",
    "storage",
    "user-account-suspend",
    "user-account-restore",
    "moderation",
    "appeal",
    "fault-injection",
    "readiness",
    "metric-delivery",
    "metric-dlq",
    "metric-readiness",
    "log-readback",
    "alert-readback",
    "dlq-readback",
    "cleanup",
)
EXPECTED_DEVICE_TARGETS = {
    "suspended": (
        "test/user_acceptance/patrol/user/"
        "account_enforcement_suspended__user_acceptance_test.dart"
    ),
    "restored": (
        "test/user_acceptance/patrol/user/"
        "account_enforcement_restored__user_acceptance_test.dart"
    ),
}
MANIFEST_FIELDS = {
    "schema",
    "environment",
    "target",
    "composition",
    "specRefs",
    "publicBaseRoles",
    "operationScopes",
    "phaseOrder",
    "deviceReports",
    "receiptSchemas",
    "artifactKinds",
    "assertionIds",
}
JOURNEY_FIELDS = {
    "schema",
    "status",
    "environment",
    "target",
    "composition",
    "runId",
    "candidateDigest",
    "commitSha",
    "capturedAt",
    "specRefs",
    "authorization",
    "storage",
    "userAccount",
    "moderation",
    "appeal",
    "faultInjection",
    "readiness",
    "observability",
    "cleanup",
    "artifactRefs",
}
SENSITIVE_KEYS = {
    "accountid",
    "reviewerid",
    "operatorid",
    "intakeref",
    "rawpayload",
    "requestbody",
    "authorizationheader",
    "accesstoken",
    "refreshtoken",
    "credential",
    "credentials",
    "endpoint",
    "url",
}


class EvidenceError(ValueError):
    """The supplied artifacts cannot support a passed UAT CaseResult."""


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def output_root() -> Path:
    configured = os.environ.get("QWQ_OUTPUT_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (REPO_ROOT / ".qwq_output").resolve()


def _json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"{label} is unreadable: {path}") from exc
    if not isinstance(value, dict):
        raise EvidenceError(f"{label} must be a JSON object: {path}")
    return value


def _exact_fields(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    observed = set(value)
    if observed != expected:
        missing = sorted(expected - observed)
        unknown = sorted(observed - expected)
        raise EvidenceError(
            f"{label} field set drift: missing={missing}, unknown={unknown}"
        )


def _non_empty_string(value: object, label: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise EvidenceError(f"{label} must be a non-empty string")
    return normalized


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise EvidenceError(f"{label} must be an integer >= {minimum}")
    return value


def _utc_timestamp(value: object, label: str) -> str:
    normalized = _non_empty_string(value, label)
    if not normalized.endswith("Z"):
        raise EvidenceError(f"{label} must be UTC")
    try:
        parsed = dt.datetime.fromisoformat(normalized[:-1] + "+00:00")
    except ValueError as exc:
        raise EvidenceError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.utcoffset() != dt.timedelta(0):
        raise EvidenceError(f"{label} must use the UTC offset")
    return normalized


def _require(value: bool, message: str) -> None:
    if not value:
        raise EvidenceError(message)


def _same_string_set(value: object, expected: Iterable[str], label: str) -> None:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise EvidenceError(f"{label} must be a string array")
    observed = [item.strip() for item in value]
    if any(not item for item in observed) or len(observed) != len(set(observed)):
        raise EvidenceError(f"{label} must contain unique non-empty strings")
    if set(observed) != set(expected):
        raise EvidenceError(f"{label} does not match its canonical set")


def _same_string_sequence(value: object, expected: Iterable[str], label: str) -> None:
    if not isinstance(value, list) or tuple(value) != tuple(expected):
        raise EvidenceError(f"{label} does not match its canonical order")


def _manifest_digest(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    manifest = _json_object(path, "account-enforcement Gamma UAT manifest")
    _exact_fields(manifest, MANIFEST_FIELDS, "UAT manifest")
    _require(manifest.get("schema") == MANIFEST_SCHEMA, "UAT manifest schema drift")
    _require(manifest.get("environment") == "gamma", "UAT manifest must own gamma")
    _require(manifest.get("target") == "gamma-local", "UAT manifest target drift")
    _require(
        manifest.get("composition") == "production_remote",
        "UAT manifest must require production_remote",
    )
    _same_string_set(manifest.get("specRefs"), EXPECTED_SPEC_REFS, "manifest specRefs")
    _same_string_set(
        manifest.get("publicBaseRoles"), ("api", "productOps"), "publicBaseRoles"
    )
    _require(
        manifest.get("operationScopes") == EXPECTED_OPERATION_SCOPES,
        "manifest operationScopes drift from ContractGraph operations",
    )
    _same_string_sequence(manifest.get("phaseOrder"), EXPECTED_PHASE_ORDER, "phaseOrder")
    _same_string_sequence(
        manifest.get("assertionIds"), EXPECTED_ASSERTIONS, "assertionIds"
    )
    reports = manifest.get("deviceReports")
    _require(isinstance(reports, dict), "manifest deviceReports must be an object")
    _exact_fields(
        reports,
        {"suspended", "restored", "physicalPlatforms"},
        "manifest deviceReports",
    )
    _require(
        reports.get("suspended") == EXPECTED_DEVICE_TARGETS["suspended"]
        and reports.get("restored") == EXPECTED_DEVICE_TARGETS["restored"],
        "manifest Patrol target drift",
    )
    _same_string_set(
        reports.get("physicalPlatforms"), ("android", "ios"), "physicalPlatforms"
    )
    schemas = manifest.get("receiptSchemas")
    _require(
        schemas
        == {
            "evidence": EVIDENCE_SCHEMA,
            "journey": JOURNEY_SCHEMA,
            "caseResult": CASE_RESULT_SCHEMA,
        },
        "manifest receipt schema drift",
    )
    _same_string_sequence(
        manifest.get("artifactKinds"),
        EXPECTED_ARTIFACT_KINDS,
        "artifactKinds",
    )
    return manifest


def _evidence_path(raw: object, label: str) -> tuple[Path, str]:
    ref = _non_empty_string(raw, label)
    root = output_root()
    candidate = Path(ref).expanduser()
    if not candidate.is_absolute():
        if candidate.parts and candidate.parts[0] == ".qwq_output":
            candidate = REPO_ROOT / candidate
        else:
            candidate = root / candidate
    candidate = candidate.resolve()
    try:
        relative = candidate.relative_to(root).as_posix()
    except ValueError as exc:
        raise EvidenceError(f"{label} must stay below QWQ_OUTPUT_ROOT") from exc
    if not candidate.is_file():
        raise EvidenceError(f"{label} is missing: {relative}")
    return candidate, relative


def _scan_sensitive(value: object, path: str = "receipt") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).replace("_", "").replace("-", "").lower()
            if normalized in SENSITIVE_KEYS:
                raise EvidenceError(f"{path} contains forbidden sensitive field {key}")
            _scan_sensitive(child, f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _scan_sensitive(child, f"{path}[{index}]")
        return
    if isinstance(value, str):
        if "Bearer " in value or JWT_RE.search(value):
            raise EvidenceError(f"{path} contains credential material")


def _validate_artifact_refs(receipt: Mapping[str, Any]) -> dict[str, str]:
    raw_refs = receipt.get("artifactRefs")
    if not isinstance(raw_refs, list) or len(raw_refs) != len(EXPECTED_ARTIFACT_KINDS):
        raise EvidenceError(
            "journey artifactRefs must contain the complete canonical artifact set"
        )
    refs: list[str] = []
    kinds: list[str] = []
    normalized: list[str] = []
    for index, descriptor in enumerate(raw_refs):
        if not isinstance(descriptor, dict):
            raise EvidenceError(f"journey artifactRefs[{index}] must be an object")
        _exact_fields(
            descriptor,
            {"kind", "path", "sha256", "mediaType"},
            f"journey artifactRefs[{index}]",
        )
        kind = _non_empty_string(descriptor.get("kind"), "journey artifact kind")
        ref = _non_empty_string(descriptor.get("path"), "journey artifact path")
        digest = _non_empty_string(
            descriptor.get("sha256"), "journey artifact sha256"
        )
        _require(
            descriptor.get("mediaType") == "application/json",
            "journey evidence artifacts must be safe JSON projections",
        )
        _path, relative = _evidence_path(ref, "journey artifactRef")
        try:
            raw_artifact = _path.read_bytes()
        except OSError as exc:
            raise EvidenceError(f"journey artifact is unreadable: {relative}") from exc
        _require(
            len(raw_artifact) <= 1024 * 1024,
            f"journey artifact exceeds the 1 MiB safe-projection limit: {relative}",
        )
        observed_digest = f"sha256:{hashlib.sha256(raw_artifact).hexdigest()}"
        _require(
            SHA256_RE.fullmatch(digest) is not None and digest == observed_digest,
            f"journey artifact digest mismatch: {relative}",
        )
        artifact = _json_object(_path, f"journey artifact {kind}")
        _exact_fields(
            artifact,
            {
                "schema",
                "kind",
                "status",
                "runId",
                "candidateDigest",
                "capturedAt",
                "facts",
            },
            f"journey artifact {kind}",
        )
        _scan_sensitive(artifact, f"journey artifact {kind}")
        _require(
            artifact.get("schema") == EVIDENCE_SCHEMA
            and artifact.get("kind") == kind
            and artifact.get("status") == "captured"
            and artifact.get("runId") == receipt.get("runId")
            and artifact.get("candidateDigest") == receipt.get("candidateDigest")
            and bool(_utc_timestamp(artifact.get("capturedAt"), "artifact capturedAt"))
            and isinstance(artifact.get("facts"), dict)
            and bool(artifact.get("facts")),
            f"journey artifact envelope is not candidate-bound: {relative}",
        )
        refs.append(ref)
        kinds.append(kind)
        normalized.append(relative)
    if len(refs) != len(set(refs)) or len(kinds) != len(set(kinds)):
        raise EvidenceError("journey artifact paths and kinds must be unique")
    _same_string_set(kinds, EXPECTED_ARTIFACT_KINDS, "journey artifact kinds")

    declared_refs: list[str] = []

    def collect(value: object, key: str = "") -> None:
        if isinstance(value, dict):
            for child_key, child in value.items():
                if child_key in {"artifactRefs", "specRefs"}:
                    continue
                if child_key.endswith("Ref") and isinstance(child, str):
                    declared_refs.append(child.strip())
                elif child_key.endswith("Refs") and isinstance(child, list):
                    declared_refs.extend(
                        str(item).strip() for item in child if isinstance(item, str)
                    )
                collect(child, child_key)
        elif isinstance(value, list):
            for child in value:
                collect(child, key)

    collect(receipt)
    missing = sorted({ref for ref in declared_refs if ref and ref not in refs})
    if missing:
        raise EvidenceError(
            "journey named evidence refs are absent from artifactRefs: "
            + ", ".join(missing)
        )
    return dict(zip(kinds, normalized, strict=True))


def validate_journey_receipt(
    receipt: Mapping[str, Any],
    *,
    manifest: Mapping[str, Any],
    run_id: str,
    candidate_digest: str,
) -> dict[str, str]:
    _exact_fields(receipt, JOURNEY_FIELDS, "journey receipt")
    _scan_sensitive(receipt)
    _require(receipt.get("schema") == JOURNEY_SCHEMA, "journey receipt schema drift")
    _require(receipt.get("status") == "passed", "journey receipt is not passed")
    _require(receipt.get("environment") == "gamma", "journey environment drift")
    _require(receipt.get("target") == "gamma-local", "journey target drift")
    _require(
        receipt.get("composition") == "production_remote",
        "journey must use production_remote composition",
    )
    _require(receipt.get("runId") == run_id, "journey runId drift")
    _require(
        receipt.get("candidateDigest") == candidate_digest,
        "journey candidate digest drift",
    )
    _require(
        COMMIT_RE.fullmatch(str(receipt.get("commitSha") or "")) is not None,
        "journey commitSha is not canonical",
    )
    _utc_timestamp(receipt.get("capturedAt"), "journey capturedAt")
    _same_string_set(receipt.get("specRefs"), EXPECTED_SPEC_REFS, "journey specRefs")

    authorization = receipt.get("authorization")
    _require(isinstance(authorization, dict), "authorization evidence is missing")
    _exact_fields(
        authorization,
        {
            "oidcVerified",
            "missingCredentialStatus",
            "invalidCredentialStatus",
            "insufficientScopeStatus",
            "distinctOperatorCount",
            "operationScopes",
            "receiptRef",
        },
        "authorization",
    )
    _require(authorization.get("oidcVerified") is True, "operator OIDC was not verified")
    _require(
        authorization.get("missingCredentialStatus") == 401
        and authorization.get("invalidCredentialStatus") == 401
        and authorization.get("insufficientScopeStatus") == 403,
        "operator authentication/scope negative cases did not fail closed",
    )
    _integer(authorization.get("distinctOperatorCount"), "distinctOperatorCount", minimum=2)
    _require(
        authorization.get("operationScopes") == EXPECTED_OPERATION_SCOPES,
        "journey operation scope readback drift",
    )

    storage = receipt.get("storage")
    _require(isinstance(storage, dict), "storage evidence is missing")
    _exact_fields(
        storage,
        {"backend", "transactionAtomic", "outboxAtomic", "receiptRef"},
        "storage",
    )
    _require(storage.get("backend") == "postgresql", "journey did not use PostgreSQL")
    _require(
        storage.get("transactionAtomic") is True and storage.get("outboxAtomic") is True,
        "case/decision/receipt/outbox transaction is not proven atomic",
    )

    user_account = receipt.get("userAccount")
    _require(isinstance(user_account, dict), "UserAccount evidence is missing")
    _exact_fields(
        user_account,
        {
            "remoteComposition",
            "controlledSubjectDigest",
            "servicePrincipal",
            "serviceScope",
            "suspendReceiptRef",
            "restoreReceiptRef",
            "oldCredentialStatus",
            "oldCredentialErrorCode",
            "newSessionStatus",
        },
        "userAccount",
    )
    _require(
        user_account.get("remoteComposition") is True
        and SHA256_RE.fullmatch(
            str(user_account.get("controlledSubjectDigest") or "")
        )
        is not None
        and user_account.get("servicePrincipal") == "product-ops-service"
        and user_account.get("serviceScope") == "user.account.enforcement.write",
        "Product Ops to UserAccount service identity is not proven",
    )
    _require(
        user_account.get("oldCredentialStatus") in {401, 403}
        and user_account.get("oldCredentialErrorCode")
        in {"USER.AUTH.account_suspended", "USER.AUTH.token_stale"},
        "old credential was not rejected by canonical UserAccount semantics",
    )
    _require(
        user_account.get("newSessionStatus") == "passed",
        "restored account did not obtain a new session",
    )

    moderation = _validate_approved_case(receipt.get("moderation"), "moderation")
    appeal = _validate_approved_case(receipt.get("appeal"), "appeal")
    _require(
        moderation["caseId"] != appeal["caseId"]
        and moderation["decisionId"] != appeal["decisionId"],
        "moderation and appeal must use distinct immutable facts",
    )

    fault = receipt.get("faultInjection")
    _require(isinstance(fault, dict), "fault-injection evidence is missing")
    _exact_fields(
        fault,
        {
            "recoverableFailureObserved",
            "recoverableAttemptCount",
            "terminalCaseId",
            "terminalDecisionId",
            "terminalDeliveryStatus",
            "deadLetterContainsPII",
            "sameDecisionRecovery",
            "recoveredDecisionId",
            "retryGenerationBefore",
            "retryGenerationAfter",
            "finalDeliveryStatus",
            "receiptRef",
        },
        "faultInjection",
    )
    _require(
        fault.get("recoverableFailureObserved") is True,
        "recoverable delivery failure was not observed",
    )
    _integer(fault.get("recoverableAttemptCount"), "recoverableAttemptCount", minimum=2)
    terminal_decision = _non_empty_string(
        fault.get("terminalDecisionId"), "terminalDecisionId"
    )
    _non_empty_string(fault.get("terminalCaseId"), "terminalCaseId")
    _require(
        terminal_decision not in {moderation["decisionId"], appeal["decisionId"]}
        and fault.get("terminalCaseId")
        not in {moderation["caseId"], appeal["caseId"]},
        "fault-injection case and decision must be distinct immutable facts",
    )
    _require(
        fault.get("terminalDeliveryStatus") == "dead_letter"
        and fault.get("deadLetterContainsPII") is False,
        "terminal DLQ state or PII boundary is not proven",
    )
    before = _integer(fault.get("retryGenerationBefore"), "retryGenerationBefore")
    after = _integer(fault.get("retryGenerationAfter"), "retryGenerationAfter")
    _require(
        fault.get("sameDecisionRecovery") is True
        and fault.get("recoveredDecisionId") == terminal_decision
        and after == before + 1
        and fault.get("finalDeliveryStatus") == "delivered",
        "terminal recovery did not replay the same decision exactly once",
    )

    readiness = receipt.get("readiness")
    _require(isinstance(readiness, dict), "readiness evidence is missing")
    _exact_fields(
        readiness,
        {"terminalStatus", "recoveredStatus", "pendingAgeWithinSlo", "receiptRef"},
        "readiness",
    )
    _require(
        readiness.get("terminalStatus") == "gate_block"
        and readiness.get("recoveredStatus") == "healthy"
        and readiness.get("pendingAgeWithinSlo") is True,
        "DLQ/readiness transition is not fail-closed and recoverable",
    )

    observability = receipt.get("observability")
    _require(isinstance(observability, dict), "observability evidence is missing")
    _exact_fields(
        observability,
        {
            "traceAligned",
            "decisionTraceAligned",
            "metricRefs",
            "logRef",
            "alertRef",
            "dlqReadbackRef",
            "crossDomainLagMilliseconds",
        },
        "observability",
    )
    _require(
        observability.get("traceAligned") is True
        and observability.get("decisionTraceAligned") is True,
        "cross-domain trace/decision alignment is not proven",
    )
    metric_refs = observability.get("metricRefs")
    _require(
        isinstance(metric_refs, list)
        and len(metric_refs) >= 3
        and all(isinstance(item, str) and item.strip() for item in metric_refs),
        "observability requires at least three typed metric readbacks",
    )
    _integer(
        observability.get("crossDomainLagMilliseconds"),
        "crossDomainLagMilliseconds",
    )

    cleanup = receipt.get("cleanup")
    _require(isinstance(cleanup, dict), "cleanup evidence is missing")
    _exact_fields(
        cleanup,
        {
            "accountState",
            "newSessionStatus",
            "unresolvedDeadLetterCount",
            "appRestrictionCleared",
            "receiptRef",
        },
        "cleanup",
    )
    _require(
        cleanup.get("accountState") == "active"
        and cleanup.get("newSessionStatus") == "passed"
        and cleanup.get("unresolvedDeadLetterCount") == 0
        and cleanup.get("appRestrictionCleared") is True,
        "controlled account or DLQ was not restored to a clean terminal state",
    )
    return _validate_artifact_refs(receipt)


def _validate_approved_case(value: object, label: str) -> dict[str, Any]:
    _require(isinstance(value, dict), f"{label} evidence is missing")
    assert isinstance(value, dict)
    _exact_fields(
        value,
        {
            "caseId",
            "status",
            "approvalCount",
            "decisionId",
            "deliveryStatus",
            "receiptRef",
        },
        label,
    )
    _non_empty_string(value.get("caseId"), f"{label}.caseId")
    _non_empty_string(value.get("decisionId"), f"{label}.decisionId")
    _require(
        value.get("status") == "approved"
        and value.get("approvalCount") == 2
        and value.get("deliveryStatus") == "delivered",
        f"{label} did not reach two-signature delivered state",
    )
    return value


def validate_device_report(
    report: Mapping[str, Any],
    *,
    phase: str,
    candidate_digest: str,
    controlled_subject_digest: str,
) -> None:
    _scan_sensitive(report, f"{phase} device report")
    expected_target = EXPECTED_DEVICE_TARGETS[phase]
    _require(report.get("status") == "passed", f"{phase} device report is not passed")
    _require(
        report.get("runtimeEnv") == "gamma"
        and report.get("apiContractEnv") == "gamma"
        and report.get("composition") == "production_remote",
        f"{phase} device report is not Gamma production Remote",
    )
    _require(report.get("target") == expected_target, f"{phase} Patrol target drift")
    _require(
        report.get("candidateDigest") == candidate_digest,
        f"{phase} device report candidate digest drift",
    )
    _require(
        report.get("controlledSubjectDigest") == controlled_subject_digest,
        f"{phase} device report controlled subject drift",
    )
    _require(report.get("sessionSource") != "dry_run", f"{phase} cannot use dry-run")

    devices = report.get("devices")
    _require(isinstance(devices, list) and devices, f"{phase} devices are missing")
    physical_android = any(
        isinstance(device, dict)
        and str(device.get("targetPlatform") or "").lower().startswith("android")
        and device.get("emulator") is False
        for device in devices
    )
    physical_ios = any(
        isinstance(device, dict)
        and str(device.get("targetPlatform") or "").lower() == "ios"
        and device.get("emulator") is False
        for device in devices
    )
    _require(
        physical_android and physical_ios,
        f"{phase} requires one physical Android and one physical iPhone",
    )

    runs = report.get("runs")
    cases = report.get("caseResults")
    _require(
        isinstance(runs, list)
        and isinstance(cases, list)
        and len(runs) == len(devices)
        and len(cases) == len(devices),
        f"{phase} device run/CaseResult cardinality drift",
    )
    expected_marker = (
        {
            "phase": "suspended",
            "candidateDigest": candidate_digest,
            "remoteCode": "USER.AUTH.account_suspended",
            "sessionCredentialsCleared": True,
            "restrictionSurfaceVisible": True,
        }
        if phase == "suspended"
        else {
            "phase": "restored",
            "candidateDigest": candidate_digest,
            "remoteProfileRead": True,
            "sessionAuthenticated": True,
            "safeHomeVisible": True,
        }
    )
    for index, run in enumerate(runs):
        _require(isinstance(run, dict), f"{phase} runs[{index}] must be an object")
        _require(
            run.get("exitCode") == 0 and run.get("timedOut") is False,
            f"{phase} runs[{index}] did not complete successfully",
        )
        evidence = run.get("evidence")
        _require(
            isinstance(evidence, dict)
            and evidence.get("accountEnforcement") == expected_marker,
            f"{phase} runs[{index}] lacks the exact account-enforcement marker",
        )
    for index, case in enumerate(cases):
        _require(isinstance(case, dict), f"{phase} caseResults[{index}] is invalid")
        execution = case.get("testExecution")
        evidence = case.get("evidence")
        _require(
            case.get("status") == "passed"
            and isinstance(execution, dict)
            and isinstance(execution.get("executed"), int)
            and execution.get("executed") >= 1
            and execution.get("failed") == 0
            and isinstance(evidence, dict)
            and evidence.get("accountEnforcement") == expected_marker,
            f"{phase} caseResults[{index}] is not a real passed execution",
        )


def aggregate_case_result(
    *,
    manifest_path: Path,
    run_id: str,
    candidate_digest: str,
    journey_path: Path,
    journey_ref: str,
    suspended_path: Path,
    suspended_ref: str,
    restored_path: Path,
    restored_ref: str,
) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    journey = _json_object(journey_path, "Gamma account-enforcement journey receipt")
    journey_artifacts = validate_journey_receipt(
        journey,
        manifest=manifest,
        run_id=run_id,
        candidate_digest=candidate_digest,
    )
    suspended = _json_object(suspended_path, "suspended device report")
    restored = _json_object(restored_path, "restored device report")
    controlled_subject_digest = str(
        journey["userAccount"]["controlledSubjectDigest"]
    )
    validate_device_report(
        suspended,
        phase="suspended",
        candidate_digest=candidate_digest,
        controlled_subject_digest=controlled_subject_digest,
    )
    validate_device_report(
        restored,
        phase="restored",
        candidate_digest=candidate_digest,
        controlled_subject_digest=controlled_subject_digest,
    )

    evidence_by_assertion = {
        "operator_oidc_and_scope_fail_closed": [
            journey_ref,
            journey_artifacts["authorization"],
        ],
        "distinct_dual_approval_issues_one_suspend": [
            journey_ref,
            journey_artifacts["moderation"],
            journey_artifacts["user-account-suspend"],
        ],
        "postgres_transaction_and_outbox_are_atomic": [
            journey_ref,
            journey_artifacts["storage"],
        ],
        "service_identity_delivers_to_user_account": [
            journey_ref,
            journey_artifacts["user-account-suspend"],
            journey_artifacts["user-account-restore"],
        ],
        "old_credentials_are_rejected": [
            journey_ref,
            journey_artifacts["user-account-suspend"],
            suspended_ref,
        ],
        "android_and_ios_show_suspended_recovery": [journey_ref, suspended_ref],
        "appeal_restores_and_new_session_logs_in": [
            journey_ref,
            journey_artifacts["appeal"],
            journey_artifacts["user-account-restore"],
            restored_ref,
        ],
        "android_and_ios_restore_remote_session": [journey_ref, restored_ref],
        "recoverable_delivery_failure_is_bounded": [
            journey_ref,
            journey_artifacts["fault-injection"],
        ],
        "terminal_dlq_blocks_readiness_without_pii": [
            journey_ref,
            journey_artifacts["fault-injection"],
            journey_artifacts["dlq-readback"],
            journey_artifacts["readiness"],
            journey_artifacts["metric-dlq"],
            journey_artifacts["alert-readback"],
        ],
        "same_decision_recovery_clears_readiness": [
            journey_ref,
            journey_artifacts["fault-injection"],
            journey_artifacts["readiness"],
        ],
        "trace_metrics_alerts_and_cleanup_align": [
            journey_ref,
            journey_artifacts["metric-delivery"],
            journey_artifacts["metric-dlq"],
            journey_artifacts["metric-readiness"],
            journey_artifacts["log-readback"],
            journey_artifacts["alert-readback"],
            journey_artifacts["cleanup"],
        ],
    }
    return {
        "schema": CASE_RESULT_SCHEMA,
        "status": "passed",
        "capturedAt": utc_now(),
        "environment": "gamma",
        "target": "gamma-local",
        "composition": "production_remote",
        "runId": run_id,
        "candidateDigest": candidate_digest,
        "controlledSubjectDigest": controlled_subject_digest,
        "commitSha": journey["commitSha"],
        "manifestDigest": _manifest_digest(manifest_path),
        "specRefs": list(EXPECTED_SPEC_REFS),
        "assertionIds": list(EXPECTED_ASSERTIONS),
        "caseResults": [
            {
                "assertionId": assertion_id,
                "status": "passed",
                "evidenceRefs": sorted(
                    set(evidence_by_assertion[assertion_id])
                ),
            }
            for assertion_id in EXPECTED_ASSERTIONS
        ],
        "journeyReceiptRef": journey_ref,
        "journeyReceiptDigest": _manifest_digest(journey_path),
        "deviceReportRefs": {
            "suspended": suspended_ref,
            "restored": restored_ref,
        },
        "deviceReportDigests": {
            "suspended": _manifest_digest(suspended_path),
            "restored": _manifest_digest(restored_path),
        },
    }


def _report_path(raw: str, run_id: str) -> Path:
    if raw.strip():
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = REPO_ROOT / candidate
    else:
        candidate = (
            output_root()
            / "env"
            / "gamma"
            / "runs"
            / "account-enforcement-gamma-uat"
            / (run_id or "preflight")
            / "case-result.json"
        )
    candidate = candidate.resolve()
    try:
        candidate.relative_to(output_root())
    except ValueError as exc:
        raise EvidenceError("CaseResult report must stay below QWQ_OUTPUT_ROOT") from exc
    return candidate


def _write_once(path: Path, payload: Mapping[str, Any]) -> None:
    if path.exists():
        raise EvidenceError(f"CaseResult artifact already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument(
        "--run-id",
        default=os.environ.get("QWQ_ACCOUNT_ENFORCEMENT_GAMMA_RUN_ID", ""),
    )
    parser.add_argument(
        "--candidate-digest",
        default=os.environ.get(
            "QWQ_ACCOUNT_ENFORCEMENT_GAMMA_CANDIDATE_DIGEST", ""
        ),
    )
    parser.add_argument(
        "--journey-receipt",
        default=os.environ.get(
            "QWQ_ACCOUNT_ENFORCEMENT_GAMMA_JOURNEY_RECEIPT", ""
        ),
    )
    parser.add_argument(
        "--suspended-device-report",
        default=os.environ.get(
            "QWQ_ACCOUNT_ENFORCEMENT_GAMMA_SUSPENDED_DEVICE_REPORT", ""
        ),
    )
    parser.add_argument(
        "--restored-device-report",
        default=os.environ.get(
            "QWQ_ACCOUNT_ENFORCEMENT_GAMMA_RESTORED_DEVICE_REPORT", ""
        ),
    )
    parser.add_argument("--report", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_id = str(args.run_id or "").strip()
    candidate_digest = str(args.candidate_digest or "").strip()
    try:
        report_path = _report_path(args.report, run_id)
        if RUN_ID_RE.fullmatch(run_id) is None:
            raise EvidenceError("runId must be a unique 8-128 character execution id")
        if SHA256_RE.fullmatch(candidate_digest) is None:
            raise EvidenceError("candidateDigest must be canonical sha256")
        journey_path, journey_ref = _evidence_path(
            args.journey_receipt, "journey receipt"
        )
        suspended_path, suspended_ref = _evidence_path(
            args.suspended_device_report, "suspended device report"
        )
        restored_path, restored_ref = _evidence_path(
            args.restored_device_report, "restored device report"
        )
        payload = aggregate_case_result(
            manifest_path=Path(args.manifest).expanduser().resolve(),
            run_id=run_id,
            candidate_digest=candidate_digest,
            journey_path=journey_path,
            journey_ref=journey_ref,
            suspended_path=suspended_path,
            suspended_ref=suspended_ref,
            restored_path=restored_path,
            restored_ref=restored_ref,
        )
        _write_once(report_path, payload)
    except EvidenceError as exc:
        issue = str(exc)
        try:
            report_path = _report_path(args.report, run_id)
            _write_once(
                report_path,
                {
                    "schema": CASE_RESULT_SCHEMA,
                    "status": "gate_block",
                    "capturedAt": utc_now(),
                    "environment": "gamma",
                    "target": "gamma-local",
                    "runId": run_id,
                    "candidateDigest": candidate_digest,
                    "issues": [issue],
                    "caseResults": [],
                },
            )
        except EvidenceError as report_error:
            print(f"GATE_BLOCK: {issue}; report error: {report_error}", file=sys.stderr)
            return 2
        print(f"GATE_BLOCK: {issue}", file=sys.stderr)
        return 2
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
