"""schema 常量、字段闭集、正则与基础校验原语（stdlib-only）。"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from typing import Any, Mapping

AUTHORITY = "prod-hosted-service-plane"
REQUEST_SCHEMA = "prod-hosted-release-transition-request"
RECEIPT_SCHEMA = "prod-hosted-release-receipt"
READBACK_SCHEMA = "prod-hosted-release-readback"
RECEIPT_READBACK_SCHEMA = "prod-hosted-release-receipt-readback"
STATE_SCHEMA = "prod-release-ledger"
SOAK_REQUEST_SCHEMA = "prod-hosted-soak-request"
SOAK_RECEIPT_SCHEMA = "prod-hosted-soak-receipt"
SOAK_RECEIPT_READBACK_SCHEMA = "prod-hosted-soak-receipt-readback"
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
OCI_REF_RE = re.compile(r"^ghcr\.io/[a-z0-9._/-]+@sha256:[0-9a-f]{64}$")
SERVICE_RE = re.compile(r"^[a-z][a-z0-9-]{1,62}$")
SAFE_VALUE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/+\-]{0,255}$")
STAGES = {"canary", "5", "20", "50", "100"}
STAGE_STEPS = {"canary": "0", "5": "5", "20": "20", "50": "50", "100": "100"}
DECISIONS = {"continue", "pause", "rolled_back", "rollback_failed"}
ROLLBACK_OUTCOMES = {"not_triggered", "rolled_back", "rollback_failed"}
RECEIPT_ID_RE = re.compile(r"^[0-9a-f]{64}$")
POSITIVE_INTEGER_RE = re.compile(r"^[1-9][0-9]*$")
STAGE_RECEIPT_ID_FIELDS = {
    "canary": "canary_receipt_id",
    "5": "percent_5_receipt_id",
    "20": "percent_20_receipt_id",
    "50": "percent_50_receipt_id",
    "100": "percent_100_receipt_id",
}
PROMOTION_EVIDENCE_FIELDS = frozenset(
    {
        "schema",
        "authority",
        "candidateId",
        "candidateMaterialId",
        "campaignId",
        "routingPolicyDigest",
        "stage",
        "observedFrom",
        "observedUntil",
        "durationSeconds",
        "syntheticRequestCount",
        "candidateRequestCount",
        "uniqueCandidateInstallations",
        "platforms",
        "audiences",
        "supportedAppCoverage",
        "source",
        "evidenceDigest",
    }
)
PROMOTION_THRESHOLDS = {
    "canary": (0, 0, 6, 2, 120),
    "5": (30 * 60, 1000, 50, 10, 0),
    "20": (2 * 60 * 60, 5000, 200, 30, 0),
    "50": (24 * 60 * 60, 20000, 1000, 100, 0),
    "100": (0, 0, 3, 1, 0),
}
REQUEST_FIELDS = frozenset(
    {
        "schema",
        "service",
        "fromCandidateDigest",
        "toCandidateDigest",
        "step",
        "stage",
        "triggerStage",
        "fromServiceFactoryOciDigest",
        "toServiceFactoryOciDigest",
        "fromAppFactoryOciDigest",
        "toAppFactoryOciDigest",
        "decision",
        "rollbackOutcome",
        "rollbackEvidence",
        "candidateMaterialId",
        "prodActivationAdmissionRef",
        "prodActivationAdmissionOciDigest",
        "prodActivationAdmissionPayloadDigest",
        "prodActivationAdmissionId",
        "candidateMaterialManifestRef",
        "candidateMaterialManifestOciDigest",
        "candidateMaterialManifestPayloadDigest",
        "previousReleasedRef",
        "previousReleasedOciDigest",
        "previousReleasedPayloadDigest",
        "previousReleasedId",
        "imageDigest",
        "configDigest",
        "contractGraphDigest",
        "adapterDigest",
        "expectedGeneration",
        "sloReadback",
        "postChecks",
        "lastGoodCandidateDigest",
        "verifiedAt",
    }
)
STATE_FIELDS = frozenset(
    {
        "schema",
        "authority",
        "service",
        "from_candidate_digest",
        "to_candidate_digest",
        "step",
        "stage",
        "trigger_stage",
        "from_service_factory_oci_digest",
        "to_service_factory_oci_digest",
        "from_app_factory_oci_digest",
        "to_app_factory_oci_digest",
        "decision",
        "rollback_outcome",
        "candidate_material_id",
        "prod_activation_admission_ref",
        "prod_activation_admission_oci_digest",
        "prod_activation_admission_payload_digest",
        "prod_activation_admission_id",
        "candidate_material_manifest_ref",
        "candidate_material_manifest_oci_digest",
        "candidate_material_manifest_payload_digest",
        "previous_released_ref",
        "previous_released_oci_digest",
        "previous_released_payload_digest",
        "previous_released_id",
        "image_digest",
        "config_digest",
        "contract_graph_digest",
        "adapter_digest",
        "last_good_candidate_digest",
        "canary_receipt_id",
        "percent_5_receipt_id",
        "percent_20_receipt_id",
        "percent_50_receipt_id",
        "percent_100_receipt_id",
        "generation",
        "receipt_id",
        "updated_at",
    }
)
RECEIPT_FIELDS = frozenset(
    {
        "schema",
        "authority",
        "service",
        "fromCandidateDigest",
        "toCandidateDigest",
        "step",
        "stage",
        "triggerStage",
        "fromServiceFactoryOciDigest",
        "toServiceFactoryOciDigest",
        "fromAppFactoryOciDigest",
        "toAppFactoryOciDigest",
        "decision",
        "rollbackOutcome",
        "rollbackEvidence",
        "candidateMaterialId",
        "prodActivationAdmissionRef",
        "prodActivationAdmissionOciDigest",
        "prodActivationAdmissionPayloadDigest",
        "prodActivationAdmissionId",
        "candidateMaterialManifestRef",
        "candidateMaterialManifestOciDigest",
        "candidateMaterialManifestPayloadDigest",
        "previousReleasedRef",
        "previousReleasedOciDigest",
        "previousReleasedPayloadDigest",
        "previousReleasedId",
        "imageDigest",
        "configDigest",
        "contractGraphDigest",
        "adapterDigest",
        "expectedGeneration",
        "committedGeneration",
        "sloReadback",
        "postChecks",
        "lastGoodCandidateDigest",
        "verifiedAt",
        "receiptId",
    }
)
SOAK_REQUEST_FIELDS = frozenset(
    {
        "schema",
        "service",
        "environment",
        "target",
        "fullRolloutReceiptId",
        "candidateId",
        "candidateMaterialId",
        "prodActivationAdmissionRef",
        "prodActivationAdmissionOciDigest",
        "prodActivationAdmissionPayloadDigest",
        "prodActivationAdmissionId",
        "candidateMaterialManifestRef",
        "candidateMaterialManifestOciDigest",
        "candidateMaterialManifestPayloadDigest",
        "serviceFactoryOciDigest",
        "appFactoryOciDigest",
        "releasedRef",
        "releasedOciDigest",
        "releasedPayloadDigest",
        "releasedId",
        "sourceGitSha",
        "sourceTreeDigest",
        "rolloutConfigDigest",
        "configGraphDigest",
        "contractGraphDigest",
        "requiredSoakSeconds",
        "soakPolicyDigest",
        "credentialPolicyDigest",
        "slo",
        "alerts",
        "health",
        "credentials",
        "approval",
    }
)
SOAK_RECEIPT_FIELDS = frozenset(
    (SOAK_REQUEST_FIELDS - {"schema"})
    | {
        "schema",
        "authority",
        "soakStartedAt",
        "soakEndedAt",
        "soakDurationSeconds",
        "verifiedAt",
        "receiptId",
    }
)
SOAK_EVIDENCE_FIELDS = {
    "slo": frozenset(
        {
            "source",
            "observedAt",
            "windowSeconds",
            "minimumSamples",
            "sampleCount",
            "status",
            "decision",
            "values",
            "receiptDigest",
        }
    ),
    "alerts": frozenset(
        {
            "source",
            "observedAt",
            "status",
            "activeFiring",
            "receiptDigest",
        }
    ),
    "health": frozenset(
        {
            "source",
            "observedAt",
            "target",
            "scope",
            "status",
            "receiptDigest",
        }
    ),
}
SOAK_CREDENTIAL_FIELDS = frozenset(
    {
        "plane",
        "account",
        "reference",
        "publicDigest",
        "issuer",
        "expiresAt",
        "verifiedAt",
    }
)
SOAK_APPROVAL_FIELDS = frozenset(
    {
        "kind",
        "repository",
        "sourceGitSha",
        "candidateMaterialId",
        "prodActivationAdmissionId",
        "environment",
        "workflowRunId",
        "workflowRunAttempt",
        "actor",
        "receiptDigest",
        "verifiedAt",
    }
)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _receipt_id(receipt: Mapping[str, Any]) -> str:
    unsigned = dict(receipt)
    unsigned.pop("receiptId", None)
    return hashlib.sha256(_canonical_bytes(unsigned)).hexdigest()


def _require_safe_string(value: object, *, field: str) -> str:
    text = str(value or "").strip()
    if SAFE_VALUE_RE.fullmatch(text) is None:
        raise ValueError(f"{field} is missing or unsafe")
    return text


def _require_timestamp(value: object, *, field: str) -> dt.datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a timestamp")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field} must be a timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed


def _require_non_negative_integer(value: object, *, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value
