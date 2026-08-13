# spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/account-moderation-and-appeal-enforcement/spec.md#gwt-001
"""account-enforcement Gamma UAT 共享常量、schema 与 manifest 加载
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
    / "gamma"
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
        "test/user_acceptance/journeys/account_enforcement/"
        "account_enforcement_suspended__user_acceptance_test.dart"
    ),
    "restored": (
        "test/user_acceptance/journeys/account_enforcement/"
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
