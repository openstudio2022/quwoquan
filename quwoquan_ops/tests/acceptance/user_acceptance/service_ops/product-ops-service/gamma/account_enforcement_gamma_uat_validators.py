# spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/account-moderation-and-appeal-enforcement/spec.md#gwt-001
"""account-enforcement Gamma UAT 证据校验器
（自 account_enforcement_gamma_uat.py 拆分）。
"""


import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping


from account_enforcement_gamma_uat_shared import (  # noqa: E402
    CASE_RESULT_SCHEMA,
    COMMIT_RE,
    EVIDENCE_SCHEMA,
    EXPECTED_ARTIFACT_KINDS,
    EXPECTED_ASSERTIONS,
    EXPECTED_DEVICE_TARGETS,
    EXPECTED_OPERATION_SCOPES,
    EXPECTED_SPEC_REFS,
    EvidenceError,
    JOURNEY_FIELDS,
    JOURNEY_SCHEMA,
    SHA256_RE,
    _evidence_path,
    _exact_fields,
    _integer,
    _json_object,
    _manifest_digest,
    _non_empty_string,
    _require,
    _same_string_set,
    _scan_sensitive,
    _utc_timestamp,
    load_manifest,
    utc_now,
)

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
