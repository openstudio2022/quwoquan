"""Deterministic read-only governance pipeline admission evaluator."""
from __future__ import annotations

import hashlib
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from ..evidence_fingerprint import canonical_digest, canonical_json_bytes
from ..objective_execution import inspect_admission
from ..objective_execution.contract import (
    blocked_admission_fallback,
    emergency_blocked_admission_fallback,
    validate_admission_readback,
)
from .contract import ContractError, load_contract, validate_exact_fields

ActivationVerifier = Callable[[Mapping[str, Any]], Mapping[str, Any]]


class _Issues:
    def __init__(self, priorities: Sequence[str]) -> None:
        self._priorities = {code: index for index, code in enumerate(priorities)}
        self._values: set[str] = set()

    def add(self, code: str) -> None:
        self._values.add(code)

    def values(self) -> list[str]:
        return sorted(self._values, key=lambda code: (self._priorities.get(code, len(self._priorities)), code))


def _mapping(value: object, schema: str, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{label} must be an object")
    validate_exact_fields(value, schema)
    return value


def _optional_mapping(value: object, schema: str, label: str) -> Mapping[str, Any] | None:
    if value is None:
        return None
    return _mapping(value, schema, label)


def _text(value: object, label: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not value:
        raise ContractError(f"{label} must be a non-empty string")
    return unicodedata.normalize("NFC", value)


def _bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ContractError(f"{label} must be boolean")
    return value


def _enum(value: object, values: Sequence[str], label: str) -> str:
    if not isinstance(value, str) or value not in values:
        raise ContractError(f"{label} must be one of {list(values)}")
    return value


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        raise ContractError(f"{label} must be sha256:<64-lowercase-hex>")
    digest = value[7:]
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ContractError(f"{label} must be sha256:<64-lowercase-hex>")
    return value


def _subject(value: object) -> dict[str, str]:
    item = _mapping(value, "subject", "subject")
    return {
        "subject_id": str(_text(item["subject_id"], "subject.subject_id")),
        "scope_id": str(_text(item["scope_id"], "subject.scope_id")),
        "candidate_id": str(_text(item["candidate_id"], "subject.candidate_id")),
        "evidence_fingerprint": _sha256(item["evidence_fingerprint"], "subject.evidence_fingerprint"),
    }


def _readback(value: object, label: str, contract: Mapping[str, Any]) -> dict[str, Any]:
    item = _mapping(value, "evidence_readback", label)
    closed = contract["closed_sets"]
    status = _enum(item["status"], closed["evidence_status"], f"{label}.status")
    return {
        "status": status,
        "schema_valid": _bool(item["schema_valid"], f"{label}.schema_valid"),
        "fresh": _bool(item["fresh"], f"{label}.fresh"),
        "fingerprint_match": _bool(item["fingerprint_match"], f"{label}.fingerprint_match"),
        "result": _enum(item["result"], closed["evidence_result"], f"{label}.result"),
        "provider_kind": _enum(item["provider_kind"], closed["provider_kind"], f"{label}.provider_kind"),
        "release_evidence_eligible": _bool(item["release_evidence_eligible"], f"{label}.release_evidence_eligible"),
        "detail": _text(item["detail"], f"{label}.detail", nullable=True),
        "receipt_ref": _text(item["receipt_ref"], f"{label}.receipt_ref", nullable=True),
        "receipt_bytes_sha256": _sha256(item["receipt_bytes_sha256"], f"{label}.receipt_bytes_sha256") if item["receipt_bytes_sha256"] is not None else None,
        "verified_at": _text(item["verified_at"], f"{label}.verified_at", nullable=True),
        "provider_timestamp": _text(item["provider_timestamp"], f"{label}.provider_timestamp", nullable=True),
        "candidate_id": _text(item["candidate_id"], f"{label}.candidate_id", nullable=True),
        "scope_id": _text(item["scope_id"], f"{label}.scope_id", nullable=True),
        "verifier_id": _text(item["verifier_id"], f"{label}.verifier_id", nullable=True),
    }


def _evidence(value: object, contract: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    if not isinstance(value, Mapping):
        raise ContractError("evidence must be an object")
    expected = set(contract["evidence_layers"])
    actual = set(value)
    if actual != expected:
        raise ContractError(f"evidence layers drifted: missing={sorted(expected-actual)}, extra={sorted(actual-expected)}")
    return {name: _readback(value[name], f"evidence.{name}", contract) for name in sorted(expected)}


def _human_readback(value: object, contract: Mapping[str, Any]) -> dict[str, Any] | None:
    if value is None:
        return None
    try:
        from ..human_agent_delivery import validate_calibration_readback
        return validate_calibration_readback(value)
    except Exception as error:
        raise ContractError(f"human_calibration_readback incompatible: {error}") from error


def _activation_receipt(value: object, contract: Mapping[str, Any]) -> dict[str, Any] | None:
    item = _optional_mapping(value, "activation_receipt", "activation_receipt")
    if item is None:
        return None
    return {
        "status": _enum(item["status"], contract["closed_sets"]["evidence_status"], "activation_receipt.status"),
        "receipt_id": _text(item["receipt_id"], "activation_receipt.receipt_id", nullable=True),
        "evaluation_digest": _sha256(item["evaluation_digest"], "activation_receipt.evaluation_digest") if item["evaluation_digest"] is not None else None,
        "evaluation_bytes_sha256": _sha256(item["evaluation_bytes_sha256"], "activation_receipt.evaluation_bytes_sha256") if item["evaluation_bytes_sha256"] is not None else None,
    }


def _normalize(payload: object, contract: Mapping[str, Any]) -> dict[str, Any]:
    root = _mapping(payload, "inspection_input", "inspection_input")
    return {
        "subject": _subject(root["subject"]),
        "evidence": _evidence(root["evidence"], contract),
        "human_calibration_readback": _human_readback(root["human_calibration_readback"], contract),
        "activation_receipt": _activation_receipt(root["activation_receipt"], contract),
    }


def _objective_s4_once() -> tuple[dict[str, Any], str | None]:
    try:
        return validate_admission_readback(inspect_admission()), None
    except Exception as error:
        try:
            fallback = blocked_admission_fallback()
        except Exception:
            fallback = emergency_blocked_admission_fallback()
        return dict(fallback), (str(error) or type(error).__name__)


def _calibration_complete(normalized: Mapping[str, Any], issues: _Issues, contract: Mapping[str, Any]) -> bool:
    evidence = normalized["evidence"]["human_calibration"]
    readback = normalized["human_calibration_readback"]
    policy = contract["human_calibration_policy"]
    if evidence["status"] != "present" or readback is None:
        return False
    if evidence["result"] != policy["required_status"]:
        if readback["status"] == "insufficient":
            issues.add("HUMAN_CALIBRATION_INSUFFICIENT")
        return False
    if readback["status"] != policy["required_status"]:
        issues.add("HUMAN_CALIBRATION_INSUFFICIENT")
        return False
    return True


def _provider_is_qualified(layer: str, readback: Mapping[str, Any], contract: Mapping[str, Any]) -> bool:
    policy = contract["layer_admission"][layer]
    return (
        readback["provider_kind"] in policy["provider_kinds"]
        and readback["release_evidence_eligible"] is policy["release_evidence_eligible"]
        and readback["verifier_id"] == policy["verifier_id"]
    )


def _evaluate_layers(normalized: Mapping[str, Any], issues: _Issues, contract: Mapping[str, Any]) -> bool:
    all_qualified = True
    subject = normalized["subject"]
    for name, descriptor in contract["evidence_layers"].items():
        readback = normalized["evidence"][name]
        # Structural identity has precedence regardless of present/failed status.
        if not readback["schema_valid"]:
            issues.add("EVIDENCE_SCHEMA_INVALID")
            all_qualified = False
        if not readback["fresh"]:
            issues.add("EVIDENCE_STALE")
            all_qualified = False
        if not readback["fingerprint_match"]:
            issues.add("EVIDENCE_FINGERPRINT_MISMATCH")
            all_qualified = False
        if name == "hosted_authority_code" and readback["result"] == "code_absent":
            issues.add("REQUIRED_CODE_EVIDENCE_ABSENT")
            all_qualified = False
        if readback["status"] != "present":
            issues.add(descriptor["missing_blocker"] if readback["status"] == "absent" else descriptor["failed_blocker"])
            all_qualified = False
            continue
        if readback["candidate_id"] != subject["candidate_id"] or readback["scope_id"] != subject["scope_id"]:
            issues.add("EVIDENCE_FINGERPRINT_MISMATCH")
            all_qualified = False
        if name == "effect_readback" and readback["result"] == "unknown":
            issues.add("EFFECT_OUTCOME_UNKNOWN")
            all_qualified = False
            continue
        if readback["result"] != descriptor["qualifying_result"] or not _provider_is_qualified(name, readback, contract):
            issues.add(descriptor["unqualified_blocker"])
            all_qualified = False
    return all_qualified


def _structural_blocker(blockers: Sequence[str], contract: Mapping[str, Any]) -> bool:
    return any(code in set(contract["precedence"]["blocked_before_admission"]) for code in blockers)


def _activation_verification(
    verifier: ActivationVerifier,
    receipt: Mapping[str, Any],
    *,
    evaluation_digest: str,
    evaluation_bytes_sha256: str,
    contract: Mapping[str, Any],
) -> tuple[bool, str | None, str | None]:
    try:
        raw = verifier({
            "receipt": dict(receipt),
            "evaluation_digest": evaluation_digest,
            "evaluation_bytes_sha256": evaluation_bytes_sha256,
        })
        item = _mapping(raw, "activation_verification", "activation_verification")
        status = _enum(item["status"], contract["closed_sets"]["activation_verification_status"], "activation_verification.status")
        provider = _enum(item["provider_kind"], contract["closed_sets"]["provider_kind"], "activation_verification.provider_kind")
        authenticated = _bool(item["authenticated"], "activation_verification.authenticated")
        exact = _bool(item["exact_bytes_verified"], "activation_verification.exact_bytes_verified")
        eligible = _bool(item["release_evidence_eligible"], "activation_verification.release_evidence_eligible")
        receipt_id = _text(item["receipt_id"], "activation_verification.receipt_id", nullable=True)
        digest = _sha256(item["evaluation_digest"], "activation_verification.evaluation_digest") if item["evaluation_digest"] is not None else None
        bytes_digest = _sha256(item["evaluation_bytes_sha256"], "activation_verification.evaluation_bytes_sha256") if item["evaluation_bytes_sha256"] is not None else None
    except Exception:
        return False, "ACTIVATION_READBACK_FAILED", None
    if status != "present":
        return False, "ACTIVATION_READBACK_FAILED", receipt_id
    if provider != "authenticated_external" or not authenticated or not exact or not eligible or not receipt_id:
        return False, "ACTIVATION_RECEIPT_INVALID", receipt_id
    if (
        receipt.get("receipt_id") != receipt_id
        or receipt.get("evaluation_digest") != evaluation_digest
        or receipt.get("evaluation_bytes_sha256") != evaluation_bytes_sha256
        or digest != evaluation_digest
        or bytes_digest != evaluation_bytes_sha256
        or digest != receipt.get("evaluation_digest")
        or bytes_digest != receipt.get("evaluation_bytes_sha256")
    ):
        return False, "ACTIVATION_RECEIPT_MISMATCH", receipt_id
    return True, None, receipt_id


def _result(
    *, contract: Mapping[str, Any], subject: Mapping[str, Any] | None, status: str,
    blockers: list[str], s4: Mapping[str, Any], evidence_summary: Mapping[str, Any],
    evaluation_digest: str | None, evaluation_bytes_sha256: str | None,
    detail: str = "", error_code: str | None = None, activation_receipt_ref: str | None = None,
) -> dict[str, Any]:
    output = {
        "schema_id": "governance-pipeline-admission-inspection",
        "schema_version": 2,
        "result": "typed_blocker" if status == "blocked" else "inspection",
        "error_code": error_code,
        "detail": detail,
        "subject": dict(subject) if subject is not None else None,
        "status": status,
        "allowed_mode": "observe_only" if status in {"eligible_observe_only", "observe_only"} else "manual",
        "production_ready": False,
        "commercial_ready": False,
        "hotl_admitted": False,
        "mutation_allowed": False,
        "prod_mutation_allowed": False,
        "hotl_mutation_allowed": False,
        "max_write_concurrency": min(1, max(0, int(s4.get("write_concurrency", 0)))),
        "activation_required": status != "observe_only",
        "activation_receipt_ref": activation_receipt_ref,
        "evaluation_digest": evaluation_digest,
        "evaluation_bytes_sha256": evaluation_bytes_sha256,
        "blockers": blockers,
        "evidence_summary": dict(evidence_summary),
        "objective_s4_readback": dict(s4),
        "external_effect_policy": dict(contract["admission_policy"]["external_effects"]),
        "observation_metrics": list(contract["observation_metrics"]["definitions"]),
        "external_open": list(contract["admission_policy"]["external_open"]),
    }
    validate_exact_fields(output, "inspection_result")
    return output


def invalid_inspection(detail: str, *, contract: Mapping[str, Any] | None = None) -> dict[str, Any]:
    active = dict(contract or load_contract())
    s4, _ = _objective_s4_once()
    return _result(
        contract=active, subject=None, status="blocked", blockers=["INPUT_CONTRACT_INVALID"],
        s4=s4, evidence_summary={}, evaluation_digest=None, evaluation_bytes_sha256=None,
        detail=detail, error_code="GPA.INPUT_CONTRACT_INVALID",
    )


def inspect(payload: object, *, activation_verifier: ActivationVerifier | None = None) -> dict[str, Any]:
    """Inspect admission without collecting metrics, mutating state, or creating authority."""
    contract = load_contract()
    try:
        normalized = _normalize(payload, contract)
    except ContractError as error:
        if "human_calibration_readback incompatible" in str(error):
            try:
                fallback = dict(payload) if isinstance(payload, Mapping) else {}
                fallback["human_calibration_readback"] = None
                normalized = _normalize(fallback, contract)
            except Exception:
                return invalid_inspection(str(error), contract=contract)
            issues = _Issues(contract["blocker_priority"])
            issues.add(contract["human_calibration_policy"]["incompatibility_blocker"])
        else:
            return invalid_inspection(str(error), contract=contract)
    else:
        issues = _Issues(contract["blocker_priority"])
    layers_qualified = _evaluate_layers(normalized, issues, contract)
    calibration_qualified = _calibration_complete(normalized, issues, contract)
    s4, s4_error = _objective_s4_once()
    if s4_error is not None or s4["status"] == "blocked":
        issues.add("OBJECTIVE_ADMISSION_BLOCKED")
    evidence_summary = {
        name: {
            "status": readback["status"], "result": readback["result"],
            "provider_kind": readback["provider_kind"],
        }
        for name, readback in normalized["evidence"].items()
    }
    identity_payload = {
        "schema_id": "governance-pipeline-admission-evaluation",
        "schema_version": 2,
        "subject": normalized["subject"],
        "evidence": normalized["evidence"],
        "human_calibration_readback": normalized["human_calibration_readback"],
        "objective_s4_readback": s4,
    }
    try:
        exact_bytes = canonical_json_bytes(identity_payload)
        evaluation_digest = canonical_digest(identity_payload)
        evaluation_bytes_sha256 = "sha256:" + hashlib.sha256(exact_bytes).hexdigest()
    except Exception as error:
        return _result(
            contract=contract, subject=normalized["subject"], status="blocked",
            blockers=["EVALUATION_IDENTITY_FAILED"], s4=s4,
            evidence_summary=evidence_summary, evaluation_digest=None,
            evaluation_bytes_sha256=None, detail=str(error) or type(error).__name__,
            error_code="GPA.EVALUATION_IDENTITY_FAILED",
        )
    blockers = issues.values()
    if _structural_blocker(blockers, contract):
        code = "GPA.OBJECTIVE_ADMISSION_BLOCKED" if "OBJECTIVE_ADMISSION_BLOCKED" in blockers else "GPA.EVIDENCE_IDENTITY_BLOCKED"
        return _result(
            contract=contract, subject=normalized["subject"], status="blocked", blockers=blockers,
            s4=s4, evidence_summary=evidence_summary, evaluation_digest=evaluation_digest,
            evaluation_bytes_sha256=evaluation_bytes_sha256, detail=s4_error or "required code evidence is invalid",
            error_code=code,
        )
    all_facts = layers_qualified and calibration_qualified and not blockers
    if not all_facts:
        if activation_verifier is None:
            issues.add("ACTIVATION_PROVIDER_UNAVAILABLE")
            blockers = issues.values()
        return _result(
            contract=contract, subject=normalized["subject"], status="not_admitted", blockers=blockers,
            s4=s4, evidence_summary=evidence_summary, evaluation_digest=evaluation_digest,
            evaluation_bytes_sha256=evaluation_bytes_sha256, error_code="GPA.NOT_ADMITTED",
        )
    receipt = normalized["activation_receipt"]
    if activation_verifier is None:
        return _result(
            contract=contract, subject=normalized["subject"], status="eligible_observe_only",
            blockers=["ACTIVATION_PROVIDER_UNAVAILABLE"], s4=s4,
            evidence_summary=evidence_summary, evaluation_digest=evaluation_digest,
            evaluation_bytes_sha256=evaluation_bytes_sha256,
            error_code="GPA.ACTIVATION_PROVIDER_UNAVAILABLE",
        )
    if receipt is None or receipt["status"] != "present":
        return _result(
            contract=contract, subject=normalized["subject"], status="not_admitted",
            blockers=["ACTIVATION_RECEIPT_INVALID"], s4=s4,
            evidence_summary=evidence_summary, evaluation_digest=evaluation_digest,
            evaluation_bytes_sha256=evaluation_bytes_sha256, error_code="GPA.NOT_ADMITTED",
        )
    activated, blocker, receipt_ref = _activation_verification(
        activation_verifier, receipt, evaluation_digest=evaluation_digest,
        evaluation_bytes_sha256=evaluation_bytes_sha256, contract=contract,
    )
    if not activated:
        return _result(
            contract=contract, subject=normalized["subject"], status="not_admitted",
            blockers=[str(blocker)], s4=s4, evidence_summary=evidence_summary,
            evaluation_digest=evaluation_digest, evaluation_bytes_sha256=evaluation_bytes_sha256,
            error_code="GPA.NOT_ADMITTED", activation_receipt_ref=receipt_ref,
        )
    return _result(
        contract=contract, subject=normalized["subject"], status="observe_only", blockers=[],
        s4=s4, evidence_summary=evidence_summary, evaluation_digest=evaluation_digest,
        evaluation_bytes_sha256=evaluation_bytes_sha256, activation_receipt_ref=receipt_ref,
    )
