#!/usr/bin/env python3
"""Hosted service-plane authority for immutable production release receipts.

The script is intentionally stdlib-only so ``sync_prod_plane_stack.sh`` can
pipe this exact source to ``python3 -`` over the service-plane SSH boundary.
The hosted filesystem owns the CAS generation and immutable receipt; local
``.qwq_output`` files are readback copies only.
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
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
STAGES = {"gray-initial", "carry-on", "full"}
DECISIONS = {"continue", "pause", "rolled_back", "rollback_failed"}
ROLLBACK_OUTCOMES = {"not_triggered", "rolled_back", "rollback_failed"}
RECEIPT_ID_RE = re.compile(r"^[0-9a-f]{64}$")
POSITIVE_INTEGER_RE = re.compile(r"^[1-9][0-9]*$")
STAGE_RECEIPT_ID_FIELDS = {
    "gray-initial": "gray_initial_receipt_id",
    "carry-on": "carry_on_receipt_id",
    "full": "full_receipt_id",
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
        "fromReleaseEvidenceRef",
        "toReleaseEvidenceRef",
        "fromImageTransportTag",
        "toImageTransportTag",
        "decision",
        "rollbackOutcome",
        "rollbackEvidence",
        "artifactDigest",
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
        "from_release_evidence_ref",
        "to_release_evidence_ref",
        "from_image_transport_tag",
        "to_image_transport_tag",
        "decision",
        "rollback_outcome",
        "artifact_digest",
        "image_digest",
        "config_digest",
        "contract_graph_digest",
        "adapter_digest",
        "last_good_candidate_digest",
        "gray_initial_receipt_id",
        "carry_on_receipt_id",
        "full_receipt_id",
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
        "fromReleaseEvidenceRef",
        "toReleaseEvidenceRef",
        "fromImageTransportTag",
        "toImageTransportTag",
        "decision",
        "rollbackOutcome",
        "rollbackEvidence",
        "artifactDigest",
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
        "rolloutArtifactDigest",
        "artifactDigest",
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
        "artifactDigest",
        "pullRequest",
        "approvers",
        "distinctPrincipals",
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


def _validate_check_summaries(
    value: object, *, field: str
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(
        isinstance(item, dict)
        and set(item) == {"name", "status", "receiptDigest"}
        and _require_safe_string(item.get("name"), field=f"{field}.name")
        and item.get("status") in {"passed", "failed"}
        and isinstance(item.get("receiptDigest"), str)
        and SHA256_RE.fullmatch(item["receiptDigest"]) is not None
        for item in value
    ):
        raise ValueError(f"{field} must contain canonical digest-bound checks")
    return [dict(item) for item in value]


def validate_rollback_evidence(
    value: object,
    *,
    decision: object,
    rollback_outcome: object,
    verified_at: object,
) -> dict[str, Any]:
    """Validate the exact hosted rollback fact persisted with one transition."""

    expected_decisions = {
        "not_triggered": {"continue", "pause"},
        "rolled_back": {"rolled_back"},
        "rollback_failed": {"rollback_failed"},
    }.get(rollback_outcome)
    if expected_decisions is None or decision not in expected_decisions:
        raise ValueError("rollback outcome and decision are not canonically bound")
    verified = _require_timestamp(verified_at, field="verifiedAt")
    if rollback_outcome == "not_triggered":
        if not isinstance(value, dict) or value != {"triggered": False}:
            raise ValueError(
                "non-triggered rollbackEvidence must contain only triggered=false"
            )
        return dict(value)

    expected_fields = {
        "triggered",
        "startedAt",
        "endedAt",
        "durationMs",
        "postChecks",
    }
    if (
        not isinstance(value, dict)
        or set(value) != expected_fields
        or value.get("triggered") is not True
    ):
        raise ValueError("triggered rollbackEvidence has a non-canonical shape")
    started = _require_timestamp(
        value.get("startedAt"), field="rollbackEvidence.startedAt"
    )
    ended = _require_timestamp(
        value.get("endedAt"), field="rollbackEvidence.endedAt"
    )
    duration_ms = value.get("durationMs")
    if (
        ended < started
        or ended > verified
        or not isinstance(duration_ms, int)
        or isinstance(duration_ms, bool)
        or duration_ms < 0
    ):
        raise ValueError("rollbackEvidence timing is invalid")
    checks = _validate_check_summaries(
        value.get("postChecks"), field="rollbackEvidence.postChecks"
    )
    if rollback_outcome == "rolled_back" and (
        not checks or any(item["status"] != "passed" for item in checks)
    ):
        raise ValueError(
            "successful rollbackEvidence requires non-empty passed post-checks"
        )
    return dict(value)


def _validate_request(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != REQUEST_FIELDS:
        raise ValueError("hosted release transition request has an invalid shape")
    if value.get("schema") != REQUEST_SCHEMA:
        raise ValueError("hosted release transition request schema is invalid")
    service = str(value.get("service") or "")
    if SERVICE_RE.fullmatch(service) is None:
        raise ValueError("service is invalid")
    _require_safe_string(value.get("step"), field="step")
    if value.get("stage") not in STAGES:
        raise ValueError("stage is invalid")
    if value.get("triggerStage") not in STAGES:
        raise ValueError("triggerStage is invalid")
    for field in ("fromReleaseEvidenceRef", "toReleaseEvidenceRef"):
        if not isinstance(value.get(field), str) or OCI_REF_RE.fullmatch(value[field]) is None:
            raise ValueError(f"{field} must be an exact immutable OCI ref")
    for field in ("fromImageTransportTag", "toImageTransportTag"):
        _require_safe_string(value.get(field), field=field)
    decision = value.get("decision")
    if decision not in DECISIONS:
        raise ValueError("decision is invalid")
    rollback_outcome = value.get("rollbackOutcome")
    if rollback_outcome not in ROLLBACK_OUTCOMES:
        raise ValueError("rollbackOutcome is invalid")
    for field in (
        "artifactDigest",
        "fromCandidateDigest",
        "toCandidateDigest",
        "imageDigest",
        "configDigest",
        "contractGraphDigest",
        "adapterDigest",
    ):
        if not isinstance(value.get(field), str) or SHA256_RE.fullmatch(value[field]) is None:
            raise ValueError(f"{field} must be sha256")
    generation = value.get("expectedGeneration")
    if (
        not isinstance(generation, int)
        or isinstance(generation, bool)
        or generation < 0
    ):
        raise ValueError("expectedGeneration must be a non-negative integer")
    if not isinstance(value.get("sloReadback"), dict):
        raise ValueError("sloReadback must be an object")
    _validate_check_summaries(value.get("postChecks"), field="postChecks")
    last_good = value.get("lastGoodCandidateDigest")
    if not isinstance(last_good, str) or SHA256_RE.fullmatch(last_good) is None:
        raise ValueError("lastGoodCandidateDigest must be sha256")
    validate_rollback_evidence(
        value.get("rollbackEvidence"),
        decision=decision,
        rollback_outcome=rollback_outcome,
        verified_at=value.get("verifiedAt"),
    )
    return dict(value)


def _validate_soak_request(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != SOAK_REQUEST_FIELDS:
        raise ValueError("hosted prod soak request has an invalid shape")
    if value.get("schema") != SOAK_REQUEST_SCHEMA:
        raise ValueError("hosted prod soak request schema is invalid")
    if (
        not isinstance(value.get("service"), str)
        or SERVICE_RE.fullmatch(value["service"]) is None
        or value.get("environment") != "prod"
        or value.get("target") != "prod-hosted"
    ):
        raise ValueError("hosted prod soak request target is invalid")
    if (
        not isinstance(value.get("fullRolloutReceiptId"), str)
        or RECEIPT_ID_RE.fullmatch(value["fullRolloutReceiptId"]) is None
    ):
        raise ValueError("fullRolloutReceiptId is invalid")
    for field in (
        "candidateId",
        "rolloutArtifactDigest",
        "artifactDigest",
        "rolloutConfigDigest",
        "configGraphDigest",
        "contractGraphDigest",
        "soakPolicyDigest",
        "credentialPolicyDigest",
    ):
        if (
            not isinstance(value.get(field), str)
            or SHA256_RE.fullmatch(value[field]) is None
        ):
            raise ValueError(f"{field} must be sha256")
    if (
        not isinstance(value.get("sourceGitSha"), str)
        or re.fullmatch(r"[0-9a-f]{40}", value["sourceGitSha"]) is None
    ):
        raise ValueError("sourceGitSha must be a lowercase 40-character Git SHA")
    if (
        not isinstance(value.get("sourceTreeDigest"), str)
        or re.fullmatch(
            r"(?:sha1:[0-9a-f]{40}|sha256:[0-9a-f]{64})",
            value["sourceTreeDigest"],
        )
        is None
    ):
        raise ValueError("sourceTreeDigest must be immutable")
    required_soak = value.get("requiredSoakSeconds")
    if (
        not isinstance(required_soak, int)
        or isinstance(required_soak, bool)
        or required_soak < 60
    ):
        raise ValueError("requiredSoakSeconds must be an integer >= 60")

    for name, fields in SOAK_EVIDENCE_FIELDS.items():
        evidence = value.get(name)
        if not isinstance(evidence, dict) or set(evidence) != fields:
            raise ValueError(f"{name} evidence has an invalid shape")
        _require_timestamp(evidence.get("observedAt"), field=f"{name}.observedAt")
        if (
            not isinstance(evidence.get("receiptDigest"), str)
            or SHA256_RE.fullmatch(evidence["receiptDigest"]) is None
        ):
            raise ValueError(f"{name}.receiptDigest must be sha256")
        if evidence.get("status") != "passed":
            raise ValueError(f"{name} evidence did not pass")

    slo = value["slo"]
    if slo.get("source") != "prometheus" or slo.get("decision") != "continue":
        raise ValueError("SLO evidence must be a continuing Prometheus decision")
    for field in ("windowSeconds", "minimumSamples", "sampleCount"):
        raw = slo.get(field)
        if not isinstance(raw, int) or isinstance(raw, bool) or raw < 1:
            raise ValueError(f"slo.{field} must be a positive integer")
    if slo["windowSeconds"] < required_soak:
        raise ValueError("SLO observation window is shorter than required soak")
    if slo["sampleCount"] < slo["minimumSamples"]:
        raise ValueError("SLO sample count is below the required minimum")
    values = slo.get("values")
    if not isinstance(values, dict) or set(values) != {
        "errorRate",
        "p95Ms",
        "redisErrorRate",
    }:
        raise ValueError("SLO values have an invalid shape")
    for field, raw in values.items():
        if (
            not isinstance(raw, (int, float))
            or isinstance(raw, bool)
            or float(raw) < 0
        ):
            raise ValueError(f"slo.values.{field} must be non-negative")

    alerts = value["alerts"]
    if alerts.get("source") != "alertmanager" or alerts.get("activeFiring") != 0:
        raise ValueError("alerts evidence must prove no active firing alerts")
    health = value["health"]
    if (
        health.get("source") != "stackctl"
        or health.get("target") != "prod-hosted"
        or health.get("scope") != "full"
    ):
        raise ValueError("health evidence must be full prod-hosted stackctl health")

    credentials = value.get("credentials")
    if not isinstance(credentials, list) or not credentials:
        raise ValueError("credentials evidence is missing")
    seen_credentials: set[tuple[str, str]] = set()
    for index, credential in enumerate(credentials):
        if not isinstance(credential, dict) or set(credential) != SOAK_CREDENTIAL_FIELDS:
            raise ValueError(f"credentials[{index}] has an invalid shape")
        plane = _require_safe_string(
            credential.get("plane"), field=f"credentials[{index}].plane"
        )
        account = _require_safe_string(
            credential.get("account"), field=f"credentials[{index}].account"
        )
        reference = _require_safe_string(
            credential.get("reference"), field=f"credentials[{index}].reference"
        )
        if "PRIVATE KEY" in reference or "\n" in reference:
            raise ValueError("credential reference contains secret material")
        if (
            not isinstance(credential.get("publicDigest"), str)
            or SHA256_RE.fullmatch(credential["publicDigest"]) is None
        ):
            raise ValueError("credential public digest is invalid")
        _require_safe_string(
            credential.get("issuer"), field=f"credentials[{index}].issuer"
        )
        _require_timestamp(
            credential.get("expiresAt"), field=f"credentials[{index}].expiresAt"
        )
        _require_timestamp(
            credential.get("verifiedAt"), field=f"credentials[{index}].verifiedAt"
        )
        identity = (plane, account)
        if identity in seen_credentials:
            raise ValueError(f"duplicate credential identity: {plane}/{account}")
        seen_credentials.add(identity)

    approval = value.get("approval")
    if not isinstance(approval, dict) or set(approval) != SOAK_APPROVAL_FIELDS:
        raise ValueError("approval evidence has an invalid shape")
    if approval.get("kind") != "github-reviewed-mainline":
        raise ValueError("approval must use canonical reviewed-mainline authority")
    _require_safe_string(approval.get("repository"), field="approval.repository")
    if approval.get("sourceGitSha") != value["sourceGitSha"]:
        raise ValueError("approval sourceGitSha differs from soak source")
    if approval.get("artifactDigest") != value["artifactDigest"]:
        raise ValueError("approval artifactDigest differs from soak artifact")
    if (
        not isinstance(approval.get("pullRequest"), int)
        or isinstance(approval.get("pullRequest"), bool)
        or approval["pullRequest"] < 1
    ):
        raise ValueError("approval pullRequest must be positive")
    approvers = approval.get("approvers")
    if (
        not isinstance(approvers, list)
        or not approvers
        or any(not isinstance(item, str) or not item.strip() for item in approvers)
    ):
        raise ValueError("approval approvers must be non-empty identities")
    if (
        not isinstance(approval.get("distinctPrincipals"), int)
        or isinstance(approval.get("distinctPrincipals"), bool)
        or approval["distinctPrincipals"] < 2
    ):
        raise ValueError("approval lacks author/approver separation")
    if (
        not isinstance(approval.get("receiptDigest"), str)
        or SHA256_RE.fullmatch(approval["receiptDigest"]) is None
    ):
        raise ValueError("approval receipt digest is invalid")
    _require_timestamp(approval.get("verifiedAt"), field="approval.verifiedAt")
    return dict(value)


def _load_hosted_soak_receipt(
    root: Path,
    *,
    service: str,
    receipt_id: str,
) -> dict[str, Any]:
    if RECEIPT_ID_RE.fullmatch(receipt_id) is None:
        raise RuntimeError("hosted prod soak receipt id is invalid")
    receipt_path = root / "soak-receipts" / f"{receipt_id}.json"
    if not receipt_path.is_file() or receipt_path.is_symlink():
        raise RuntimeError("hosted prod soak receipt is missing")
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("hosted prod soak receipt is not canonical JSON") from error
    if (
        not isinstance(receipt, dict)
        or set(receipt) != SOAK_RECEIPT_FIELDS
        or receipt.get("schema") != SOAK_RECEIPT_SCHEMA
        or receipt.get("authority") != AUTHORITY
        or receipt.get("service") != service
        or receipt.get("receiptId") != receipt_id
        or _receipt_id(receipt) != receipt_id
    ):
        raise RuntimeError("hosted prod soak receipt digest or ledger binding is invalid")
    request = {
        field: receipt[field] for field in SOAK_REQUEST_FIELDS if field != "schema"
    }
    request["schema"] = SOAK_REQUEST_SCHEMA
    try:
        _validate_soak_request(request)
    except ValueError as error:
        raise RuntimeError("hosted prod soak receipt payload is not canonical") from error
    started_at = _require_timestamp(receipt.get("soakStartedAt"), field="soakStartedAt")
    ended_at = _require_timestamp(receipt.get("soakEndedAt"), field="soakEndedAt")
    verified_at = _require_timestamp(receipt.get("verifiedAt"), field="verifiedAt")
    duration = receipt.get("soakDurationSeconds")
    if (
        not isinstance(duration, int)
        or isinstance(duration, bool)
        or duration != int((ended_at - started_at).total_seconds())
        or duration < receipt["requiredSoakSeconds"]
        or ended_at > verified_at
    ):
        raise RuntimeError("hosted prod soak receipt duration is invalid")
    return receipt


def _load_state(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    if not path.is_file() or path.is_symlink():
        raise RuntimeError("hosted release ledger state is not a regular file")
    payload: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if "=" not in raw:
            raise RuntimeError("hosted release ledger state is malformed")
        key, value = raw.split("=", 1)
        if key in payload:
            raise RuntimeError("hosted release ledger state has duplicate fields")
        payload[key] = value
    if set(payload) != STATE_FIELDS or payload.get("schema") != STATE_SCHEMA:
        raise RuntimeError("hosted release ledger state shape is not canonical")
    return payload


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="wb",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, path)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


@contextlib.contextmanager
def _ledger_lock(root: Path) -> Any:
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink():
        raise RuntimeError("hosted release ledger root must not be a symlink")
    lock_path = root / ".ledger.lock"
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _load_hosted_receipt(
    root: Path,
    *,
    service: str,
    receipt_id: str,
) -> dict[str, Any]:
    if RECEIPT_ID_RE.fullmatch(receipt_id) is None:
        raise RuntimeError("hosted release receipt id is invalid")
    receipt_path = root / "receipts" / f"{receipt_id}.json"
    if not receipt_path.is_file() or receipt_path.is_symlink():
        raise RuntimeError("hosted release receipt is missing")
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("hosted release receipt is not canonical JSON") from error
    if (
        not isinstance(receipt, dict)
        or set(receipt) != RECEIPT_FIELDS
        or receipt.get("schema") != RECEIPT_SCHEMA
        or receipt.get("authority") != AUTHORITY
        or receipt.get("service") != service
        or receipt.get("receiptId") != receipt_id
        or _receipt_id(receipt) != receipt_id
    ):
        raise RuntimeError("hosted release receipt digest or ledger binding is invalid")
    request = {
        field: receipt[field]
        for field in REQUEST_FIELDS
        if field != "schema"
    }
    request["schema"] = REQUEST_SCHEMA
    try:
        _validate_request(request)
    except ValueError as error:
        raise RuntimeError("hosted release receipt payload is not canonical") from error
    expected_generation = receipt.get("expectedGeneration")
    committed_generation = receipt.get("committedGeneration")
    if (
        not isinstance(committed_generation, int)
        or isinstance(committed_generation, bool)
        or committed_generation != expected_generation + 1
    ):
        raise RuntimeError("hosted release receipt generation is invalid")
    return receipt


def _history_receipt_matches_transaction(
    state: Mapping[str, str],
    receipt: Mapping[str, Any],
) -> bool:
    state_pair = (
        state.get("from_candidate_digest"),
        state.get("to_candidate_digest"),
    )
    receipt_pair = (
        receipt.get("fromCandidateDigest"),
        receipt.get("toCandidateDigest"),
    )
    if receipt_pair == state_pair:
        return True
    return (
        state.get("decision") in {"rolled_back", "rollback_failed"}
        and receipt_pair == tuple(reversed(state_pair))
    )


def _validate_stage_receipt_history(
    root: Path,
    *,
    service: str,
    state: Mapping[str, str],
) -> None:
    generation = state.get("generation", "")
    if POSITIVE_INTEGER_RE.fullmatch(generation) is None:
        raise RuntimeError("hosted release ledger generation is invalid")
    current_generation = int(generation)

    for stage, field in STAGE_RECEIPT_ID_FIELDS.items():
        receipt_id = state.get(field, "")
        if not receipt_id:
            continue
        receipt = _load_hosted_receipt(
            root,
            service=service,
            receipt_id=receipt_id,
        )
        committed_generation = receipt.get("committedGeneration")
        if (
            receipt.get("triggerStage") != stage
            or not isinstance(committed_generation, int)
            or isinstance(committed_generation, bool)
            or committed_generation <= 0
            or committed_generation > current_generation
            or not _history_receipt_matches_transaction(state, receipt)
            or receipt.get("artifactDigest") != state.get("artifact_digest")
            or receipt.get("imageDigest") != state.get("image_digest")
            or receipt.get("configDigest") != state.get("config_digest")
            or receipt.get("contractGraphDigest")
            != state.get("contract_graph_digest")
            or receipt.get("adapterDigest") != state.get("adapter_digest")
        ):
            raise RuntimeError(
                f"hosted release {stage} receipt is not candidate-transaction bound"
            )

    trigger_stage = state.get("trigger_stage", "")
    active_field = STAGE_RECEIPT_ID_FIELDS.get(trigger_stage)
    if active_field is None or state.get(active_field) != state.get("receipt_id"):
        raise RuntimeError(
            "hosted release ledger current receipt is not bound to trigger stage"
        )


def _next_stage_receipt_history(
    current: Mapping[str, str],
    payload: Mapping[str, Any],
    *,
    receipt_id: str,
) -> dict[str, str]:
    history = {field: "" for field in STAGE_RECEIPT_ID_FIELDS.values()}
    if current:
        current_pair = (
            current.get("from_candidate_digest"),
            current.get("to_candidate_digest"),
        )
        next_pair = (
            payload.get("fromCandidateDigest"),
            payload.get("toCandidateDigest"),
        )
        same_transaction = current_pair == next_pair
        rollback_transaction = (
            payload.get("decision") in {"rolled_back", "rollback_failed"}
            and current_pair == tuple(reversed(next_pair))
        )
        if same_transaction or rollback_transaction:
            for state_field, request_field in (
                ("artifact_digest", "artifactDigest"),
                ("image_digest", "imageDigest"),
                ("config_digest", "configDigest"),
                ("contract_graph_digest", "contractGraphDigest"),
                ("adapter_digest", "adapterDigest"),
            ):
                if current.get(state_field) != payload.get(request_field):
                    raise RuntimeError(
                        "hosted release candidate transaction evidence drifted"
                    )
            transport_bindings = (
                (
                    "from_release_evidence_ref",
                    "fromReleaseEvidenceRef",
                    "to_release_evidence_ref",
                    "toReleaseEvidenceRef",
                ),
                (
                    "from_image_transport_tag",
                    "fromImageTransportTag",
                    "to_image_transport_tag",
                    "toImageTransportTag",
                ),
            )
            for (
                current_from_field,
                request_from_field,
                current_to_field,
                request_to_field,
            ) in transport_bindings:
                if same_transaction:
                    transport_matches = (
                        current.get(current_from_field)
                        == payload.get(request_from_field)
                        and current.get(current_to_field)
                        == payload.get(request_to_field)
                    )
                else:
                    transport_matches = (
                        current.get(current_from_field)
                        == payload.get(request_to_field)
                        and current.get(current_to_field)
                        == payload.get(request_from_field)
                    )
                if not transport_matches:
                    raise RuntimeError(
                        "hosted release candidate transaction transport drifted"
                    )
            history = {
                field: current.get(field, "")
                for field in STAGE_RECEIPT_ID_FIELDS.values()
            }
    history[STAGE_RECEIPT_ID_FIELDS[payload["triggerStage"]]] = receipt_id
    return history


def _validated_readback(root: Path, service: str) -> dict[str, Any]:
    state = _load_state(root / f"{service}.state")
    if not state:
        return {
            "schema": READBACK_SCHEMA,
            "authority": AUTHORITY,
            "state": {},
            "receipt": {},
            "receiptRef": "",
        }
    receipt_id = state.get("receipt_id", "")
    receipt = _load_hosted_receipt(
        root,
        service=service,
        receipt_id=receipt_id,
    )
    if (
        state.get("authority") != AUTHORITY
        or state.get("service") != service
        or str(receipt.get("committedGeneration")) != state.get("generation")
        or receipt.get("artifactDigest") != state.get("artifact_digest")
        or receipt.get("fromCandidateDigest")
        != state.get("from_candidate_digest")
        or receipt.get("toCandidateDigest") != state.get("to_candidate_digest")
        or receipt.get("step") != state.get("step")
        or receipt.get("stage") != state.get("stage")
        or receipt.get("decision") != state.get("decision")
        or receipt.get("imageDigest") != state.get("image_digest")
        or receipt.get("configDigest") != state.get("config_digest")
        or receipt.get("contractGraphDigest") != state.get("contract_graph_digest")
        or receipt.get("adapterDigest") != state.get("adapter_digest")
        or receipt.get("rollbackOutcome") != state.get("rollback_outcome")
        or receipt.get("triggerStage") != state.get("trigger_stage")
        or receipt.get("fromReleaseEvidenceRef")
        != state.get("from_release_evidence_ref")
        or receipt.get("toReleaseEvidenceRef")
        != state.get("to_release_evidence_ref")
        or receipt.get("fromImageTransportTag")
        != state.get("from_image_transport_tag")
        or receipt.get("toImageTransportTag")
        != state.get("to_image_transport_tag")
        or receipt.get("lastGoodCandidateDigest")
        != state.get("last_good_candidate_digest")
        or receipt.get("verifiedAt") != state.get("updated_at")
    ):
        raise RuntimeError("hosted release receipt digest or ledger binding is invalid")
    _validate_stage_receipt_history(
        root,
        service=service,
        state=state,
    )
    return {
        "schema": READBACK_SCHEMA,
        "authority": AUTHORITY,
        "state": state,
        "receipt": receipt,
        "receiptRef": f"receipt:hosted:{receipt_id}",
    }


def commit(root: Path, request: object) -> dict[str, Any]:
    payload = _validate_request(request)
    service = payload["service"]
    with _ledger_lock(root):
        state_path = root / f"{service}.state"
        current = _validated_readback(root, service)["state"]
        current_generation = int(current.get("generation") or 0)
        if current_generation != payload["expectedGeneration"]:
            raise RuntimeError(
                "hosted release ledger CAS conflict: "
                f"expected {payload['expectedGeneration']}, found {current_generation}"
            )
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "authority": AUTHORITY,
            "service": service,
            "fromCandidateDigest": payload["fromCandidateDigest"],
            "toCandidateDigest": payload["toCandidateDigest"],
            "step": payload["step"],
            "stage": payload["stage"],
            "triggerStage": payload["triggerStage"],
            "fromReleaseEvidenceRef": payload["fromReleaseEvidenceRef"],
            "toReleaseEvidenceRef": payload["toReleaseEvidenceRef"],
            "fromImageTransportTag": payload["fromImageTransportTag"],
            "toImageTransportTag": payload["toImageTransportTag"],
            "decision": payload["decision"],
            "rollbackOutcome": payload["rollbackOutcome"],
            "rollbackEvidence": payload["rollbackEvidence"],
            "artifactDigest": payload["artifactDigest"],
            "imageDigest": payload["imageDigest"],
            "configDigest": payload["configDigest"],
            "contractGraphDigest": payload["contractGraphDigest"],
            "adapterDigest": payload["adapterDigest"],
            "expectedGeneration": payload["expectedGeneration"],
            "committedGeneration": payload["expectedGeneration"] + 1,
            "sloReadback": payload["sloReadback"],
            "postChecks": payload["postChecks"],
            "lastGoodCandidateDigest": payload["lastGoodCandidateDigest"],
            "verifiedAt": payload["verifiedAt"],
        }
        receipt_id = _receipt_id(receipt)
        receipt["receiptId"] = receipt_id
        receipt_path = root / "receipts" / f"{receipt_id}.json"
        receipt_bytes = json.dumps(
            receipt,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8") + b"\n"
        if receipt_path.exists():
            if not receipt_path.is_file() or receipt_path.is_symlink():
                raise RuntimeError("hosted release receipt path is not a regular file")
            if receipt_path.read_bytes() != receipt_bytes:
                raise RuntimeError("hosted release receipt collision")
        else:
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            with receipt_path.open("xb") as handle:
                handle.write(receipt_bytes)
                handle.flush()
                os.fsync(handle.fileno())
        stage_receipt_history = _next_stage_receipt_history(
            current,
            payload,
            receipt_id=receipt_id,
        )
        state = {
            "schema": STATE_SCHEMA,
            "authority": AUTHORITY,
            "service": service,
            "from_candidate_digest": payload["fromCandidateDigest"],
            "to_candidate_digest": payload["toCandidateDigest"],
            "step": payload["step"],
            "stage": payload["stage"],
            "trigger_stage": payload["triggerStage"],
            "from_release_evidence_ref": payload["fromReleaseEvidenceRef"],
            "to_release_evidence_ref": payload["toReleaseEvidenceRef"],
            "from_image_transport_tag": payload["fromImageTransportTag"],
            "to_image_transport_tag": payload["toImageTransportTag"],
            "decision": payload["decision"],
            "rollback_outcome": payload["rollbackOutcome"],
            "artifact_digest": payload["artifactDigest"],
            "image_digest": payload["imageDigest"],
            "config_digest": payload["configDigest"],
            "contract_graph_digest": payload["contractGraphDigest"],
            "adapter_digest": payload["adapterDigest"],
            "last_good_candidate_digest": payload["lastGoodCandidateDigest"],
            **stage_receipt_history,
            "generation": str(payload["expectedGeneration"] + 1),
            "receipt_id": receipt_id,
            "updated_at": payload["verifiedAt"],
        }
        state_bytes = (
            "\n".join(f"{key}={value}" for key, value in state.items()) + "\n"
        ).encode("utf-8")
        _atomic_write(state_path, state_bytes)
        return _validated_readback(root, service)


def fetch(root: Path, service: str) -> dict[str, Any]:
    if SERVICE_RE.fullmatch(service) is None:
        raise ValueError("service is invalid")
    with _ledger_lock(root):
        return _validated_readback(root, service)


def fetch_receipt(root: Path, service: str, receipt_id: str) -> dict[str, Any]:
    if SERVICE_RE.fullmatch(service) is None:
        raise ValueError("service is invalid")
    if RECEIPT_ID_RE.fullmatch(receipt_id) is None:
        raise ValueError("receipt id is invalid")
    with _ledger_lock(root):
        receipt = _load_hosted_receipt(
            root,
            service=service,
            receipt_id=receipt_id,
        )
        return {
            "schema": RECEIPT_READBACK_SCHEMA,
            "authority": AUTHORITY,
            "receipt": receipt,
            "receiptRef": f"receipt:hosted:{receipt_id}",
        }


def commit_soak(root: Path, request: object) -> dict[str, Any]:
    payload = _validate_soak_request(request)
    service = payload["service"]
    now = dt.datetime.now(dt.timezone.utc)
    with _ledger_lock(root):
        readback = _validated_readback(root, service)
        state = readback["state"]
        if (
            state.get("trigger_stage") != "full"
            or state.get("stage") != "full"
            or state.get("decision") != "continue"
            or state.get("rollback_outcome") != "not_triggered"
        ):
            raise RuntimeError(
                "GATE_BLOCK: prod soak requires current successful full rollout state"
            )
        full_receipt_id = state.get("full_receipt_id", "")
        if full_receipt_id != payload["fullRolloutReceiptId"]:
            raise RuntimeError("GATE_BLOCK: prod soak full rollout receipt drift")
        full_receipt = _load_hosted_receipt(
            root,
            service=service,
            receipt_id=full_receipt_id,
        )
        expected_bindings = {
            "candidateId": full_receipt["toCandidateDigest"],
            "rolloutArtifactDigest": full_receipt["artifactDigest"],
            "rolloutConfigDigest": full_receipt["configDigest"],
            "contractGraphDigest": full_receipt["contractGraphDigest"],
        }
        for field, expected in expected_bindings.items():
            if payload[field] != expected:
                raise RuntimeError(f"GATE_BLOCK: prod soak {field} drift")

        started_at = _require_timestamp(
            full_receipt["verifiedAt"], field="fullRolloutReceipt.verifiedAt"
        )
        duration = int((now - started_at).total_seconds())
        if duration < payload["requiredSoakSeconds"]:
            raise RuntimeError(
                "GATE_BLOCK: authoritative prod soak window is incomplete"
            )
        for name in ("slo", "alerts", "health"):
            observed_at = _require_timestamp(
                payload[name]["observedAt"], field=f"{name}.observedAt"
            )
            if observed_at < started_at or observed_at > now:
                raise RuntimeError(
                    f"GATE_BLOCK: {name} observation is outside authoritative soak window"
                )
        for index, credential in enumerate(payload["credentials"]):
            verified_at = _require_timestamp(
                credential["verifiedAt"], field=f"credentials[{index}].verifiedAt"
            )
            expires_at = _require_timestamp(
                credential["expiresAt"], field=f"credentials[{index}].expiresAt"
            )
            if verified_at < started_at or verified_at > now:
                raise RuntimeError(
                    "GATE_BLOCK: credential verification is outside soak window"
                )
            if expires_at <= now:
                raise RuntimeError("GATE_BLOCK: prod credential is expired")
        approval_at = _require_timestamp(
            payload["approval"]["verifiedAt"], field="approval.verifiedAt"
        )
        if approval_at > now:
            raise RuntimeError("GATE_BLOCK: prod approval verification is future-dated")

        timestamp = now.isoformat().replace("+00:00", "Z")
        receipt = {
            "schema": SOAK_RECEIPT_SCHEMA,
            "authority": AUTHORITY,
            **{field: payload[field] for field in SOAK_REQUEST_FIELDS if field != "schema"},
            "soakStartedAt": started_at.astimezone(dt.timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "soakEndedAt": timestamp,
            "soakDurationSeconds": duration,
            "verifiedAt": timestamp,
        }
        receipt_id = _receipt_id(receipt)
        receipt["receiptId"] = receipt_id
        receipt_path = root / "soak-receipts" / f"{receipt_id}.json"
        receipt_bytes = json.dumps(
            receipt,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8") + b"\n"
        if receipt_path.exists():
            if (
                not receipt_path.is_file()
                or receipt_path.is_symlink()
                or receipt_path.read_bytes() != receipt_bytes
            ):
                raise RuntimeError("hosted prod soak receipt collision")
        else:
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            with receipt_path.open("xb") as handle:
                handle.write(receipt_bytes)
                handle.flush()
                os.fsync(handle.fileno())
        verified = _load_hosted_soak_receipt(
            root,
            service=service,
            receipt_id=receipt_id,
        )
        return {
            "schema": SOAK_RECEIPT_READBACK_SCHEMA,
            "authority": AUTHORITY,
            "receipt": verified,
            "receiptRef": f"receipt:hosted-soak:{receipt_id}",
        }


def fetch_soak_receipt(
    root: Path,
    service: str,
    receipt_id: str,
) -> dict[str, Any]:
    if SERVICE_RE.fullmatch(service) is None:
        raise ValueError("service is invalid")
    if RECEIPT_ID_RE.fullmatch(receipt_id) is None:
        raise ValueError("soak receipt id is invalid")
    with _ledger_lock(root):
        receipt = _load_hosted_soak_receipt(
            root,
            service=service,
            receipt_id=receipt_id,
        )
        return {
            "schema": SOAK_RECEIPT_READBACK_SCHEMA,
            "authority": AUTHORITY,
            "receipt": receipt,
            "receiptRef": f"receipt:hosted-soak:{receipt_id}",
        }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument(
        "--action",
        choices=("fetch", "commit", "receipt", "soak-commit", "soak-receipt"),
        required=True,
    )
    parser.add_argument("--service", default="")
    parser.add_argument("--receipt-id", default="")
    parser.add_argument("--request-base64", default="")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        root = Path(args.root).expanduser()
        if not root.is_absolute():
            raise ValueError("hosted release ledger root must be absolute")
        if args.action == "fetch":
            result = fetch(root, args.service)
        elif args.action == "receipt":
            result = fetch_receipt(root, args.service, args.receipt_id)
        elif args.action == "soak-receipt":
            result = fetch_soak_receipt(root, args.service, args.receipt_id)
        else:
            raw = base64.b64decode(args.request_base64, validate=True)
            request = json.loads(raw.decode("utf-8"))
            result = (
                commit_soak(root, request)
                if args.action == "soak-commit"
                else commit(root, request)
            )
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
