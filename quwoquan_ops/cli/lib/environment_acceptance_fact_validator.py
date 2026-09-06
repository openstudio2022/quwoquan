"""Strict validation for canonical EnvironmentAcceptanceFact v2."""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from quwoquan_ops.cli.lib.environment_acceptance_fact_contract import (
    _CANDIDATE_KEYS,
    _DIGEST_RE,
    _EVIDENCE_REF_FIELDS,
    _EVIDENCE_ROLE_CONTRACT,
    _EXACT_REF_KEYS,
    _FACT_KEYS_BY_STATUS,
    _GIT_OID_RE,
    _IDENTITY_RE,
    _SIGNER_KEYS,
    ACCEPTANCE_PROFILES,
    DSSE_PAYLOAD_TYPE,
    ENVIRONMENTS,
    NO_LIVE_ENVIRONMENT_REQUIRED,
    PREDECESSOR,
    SCHEMA,
)
from quwoquan_ops.cli.lib.readiness_case_result import (
    ReadinessCaseResultError,
    validate_readiness_case_result,
)


def _fail(error_type: type[ValueError], code: str, detail: str) -> None:
    try:
        raise error_type(code, detail)
    except TypeError:
        raise error_type(f"{code}: {detail}")


def _canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("value is not canonical JSON") from exc


def _text(value: object, field: str, *, error_type: type[ValueError], code: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(character in value for character in ("\x00", "\n", "\r"))
    ):
        _fail(error_type, code, f"{field} must be non-empty canonical text")
    return value


def _identity(value: object, field: str, *, error_type: type[ValueError], code: str) -> str:
    text = _text(value, field, error_type=error_type, code=code)
    if _IDENTITY_RE.fullmatch(text) is None:
        _fail(error_type, code, f"{field} has invalid identity format")
    return text


def _digest(value: object, field: str, *, error_type: type[ValueError], code: str) -> str:
    text = _text(value, field, error_type=error_type, code=code)
    if _DIGEST_RE.fullmatch(text) is None:
        _fail(error_type, code, f"{field} must be sha256:<64 lowercase hex>")
    return text


def _git_oid(value: object, field: str, *, error_type: type[ValueError], code: str) -> str:
    text = _text(value, field, error_type=error_type, code=code)
    if _GIT_OID_RE.fullmatch(text) is None:
        _fail(error_type, code, f"{field} must be an exact Git object id")
    return text


def _timestamp(value: object, field: str, *, error_type: type[ValueError], code: str) -> tuple[str, datetime]:
    text = _text(value, field, error_type=error_type, code=code)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        _fail(error_type, code, f"{field} must be ISO-8601")
    if parsed.tzinfo is None:
        _fail(error_type, code, f"{field} must include timezone")
    return text, parsed


def _relative_ref(value: object, field: str, *, error_type: type[ValueError], code: str) -> str:
    text = _text(value, field, error_type=error_type, code=code)
    path = PurePosixPath(text)
    if (
        path.is_absolute()
        or path.as_posix() != text
        or any(part in {"", ".", ".."} for part in path.parts)
        or "\\" in text
        or text.endswith("/latest")
        or "/latest/" in text
        or path.name.startswith("latest.")
    ):
        _fail(error_type, code, f"{field} must be an immutable relative ref")
    return text


def _exact_ref(value: object, field: str, *, error_type: type[ValueError], code: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _EXACT_REF_KEYS:
        _fail(error_type, code, f"{field} must contain exactly ref and digest")
    return {
        "ref": _relative_ref(value.get("ref"), f"{field}.ref", error_type=error_type, code=code),
        "digest": _digest(value.get("digest"), f"{field}.digest", error_type=error_type, code=code),
    }


def _load_exact(
    root: Path,
    exact: Mapping[str, str],
    field: str,
    *,
    error_type: type[ValueError],
    invalid_code: str,
    evidence_code: str,
) -> dict[str, Any]:
    path = root.joinpath(*PurePosixPath(exact["ref"]).parts)
    try:
        root_resolved = root.resolve(strict=True)
        if root.is_symlink():
            raise OSError("root is a symlink")
        current = root_resolved
        for part in PurePosixPath(exact["ref"]).parts:
            current = current / part
            if current.is_symlink():
                raise OSError("reference traverses a symlink")
        resolved = path.resolve(strict=True)
        resolved.relative_to(root_resolved)
        raw = resolved.read_bytes()
    except (OSError, ValueError) as exc:
        _fail(error_type, evidence_code, f"{field} is missing, linked, or unsafe: {exc}")
    actual = "sha256:" + hashlib.sha256(raw).hexdigest()
    if actual != exact["digest"]:
        _fail(error_type, evidence_code, f"{field} exact bytes drifted")
    try:
        decoded = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        _fail(error_type, evidence_code, f"{field} is not readable JSON: {exc}")
    if not isinstance(decoded, dict):
        _fail(error_type, invalid_code, f"{field} must identify a JSON object")
    return decoded


def validate_environment_acceptance_fact(
    payload: Mapping[str, Any],
    *,
    store_root: Path | None = None,
    verify_references: bool = True,
    accepted_at: datetime | None = None,
    error_type: type[ValueError] = ValueError,
    invalid_code: str = "OPS.ENVIRONMENT_ACCEPTANCE_FACT.invalid",
    evidence_code: str = "OPS.ENVIRONMENT_ACCEPTANCE_FACT.evidence_blocked",
    signature_verifier: Callable[[str, bytes, str], bool] | None = None,
) -> dict[str, Any]:
    """Validate one exact, signed v2 fact and all required evidence roles."""

    if not isinstance(payload, Mapping):
        _fail(error_type, invalid_code, "environment acceptance fact must be an object")
    fact = dict(payload)
    if fact.get("schema") != SCHEMA:
        _fail(error_type, invalid_code, "schema is not EnvironmentAcceptanceFact v2")
    status = _text(fact.get("status"), "status", error_type=error_type, code=invalid_code)
    expected_keys = _FACT_KEYS_BY_STATUS.get(status)
    if expected_keys is None or set(fact) != expected_keys:
        _fail(error_type, invalid_code, "environment acceptance fact fields are invalid")

    environment = _text(fact.get("environment"), "environment", error_type=error_type, code=invalid_code)
    if environment not in ENVIRONMENTS:
        _fail(error_type, invalid_code, "environment is unknown")
    profile = _text(fact.get("profile"), "profile", error_type=error_type, code=invalid_code)
    if profile not in ACCEPTANCE_PROFILES:
        _fail(error_type, invalid_code, "profile is unknown")
    if status == "not_required" and (
        environment != "beta" or fact.get("reasonCode") != NO_LIVE_ENVIRONMENT_REQUIRED
    ):
        _fail(error_type, invalid_code, "only typed Beta no-live may be not_required")

    candidate = fact.get("candidate")
    if not isinstance(candidate, Mapping) or set(candidate) != _CANDIDATE_KEYS:
        _fail(error_type, invalid_code, "candidate binding is invalid")
    normalized_candidate = {
        "candidateId": _digest(candidate.get("candidateId"), "candidate.candidateId", error_type=error_type, code=invalid_code),
        "commit": _git_oid(candidate.get("commit"), "candidate.commit", error_type=error_type, code=invalid_code),
        "tree": _git_oid(candidate.get("tree"), "candidate.tree", error_type=error_type, code=invalid_code),
    }
    _digest(fact.get("impactPlanDigest"), "impactPlanDigest", error_type=error_type, code=invalid_code)
    if type(fact.get("nonPromotable")) is not bool:
        _fail(error_type, invalid_code, "nonPromotable must be boolean")
    _, issued = _timestamp(fact.get("issuedAt"), "issuedAt", error_type=error_type, code=invalid_code)
    _, expires = _timestamp(fact.get("expiresAt"), "expiresAt", error_type=error_type, code=invalid_code)
    if expires <= issued or (accepted_at is not None and expires <= accepted_at):
        _fail(error_type, invalid_code, "acceptance fact is expired")

    raw_case_refs = fact.get("caseResultRefs")
    if not isinstance(raw_case_refs, list) or not raw_case_refs:
        _fail(error_type, invalid_code, "caseResultRefs must be a non-empty array")
    case_refs = [
        _exact_ref(item, f"caseResultRefs[{index}]", error_type=error_type, code=invalid_code)
        for index, item in enumerate(raw_case_refs)
    ]
    if len({(item["ref"], item["digest"]) for item in case_refs}) != len(case_refs):
        _fail(error_type, invalid_code, "caseResultRefs must be duplicate-free")

    evidence_refs = {
        field: _exact_ref(fact.get(field), field, error_type=error_type, code=invalid_code)
        for field in _EVIDENCE_REF_FIELDS
    }
    all_evidence = [*case_refs, *evidence_refs.values()]
    if len({(item["ref"], item["digest"]) for item in all_evidence}) != len(all_evidence):
        _fail(error_type, invalid_code, "evidence roles must bind distinct exact refs")

    predecessor_value = fact.get("predecessor")
    expected_predecessor = PREDECESSOR[environment]
    predecessor = None
    if expected_predecessor is None:
        if predecessor_value is not None:
            _fail(error_type, invalid_code, "alpha predecessor must be null")
    else:
        predecessor = _exact_ref(predecessor_value, "predecessor", error_type=error_type, code=invalid_code)

    signer = fact.get("signer")
    if not isinstance(signer, Mapping) or set(signer) != _SIGNER_KEYS:
        _fail(error_type, invalid_code, "signer envelope is invalid")
    signer_identity = _identity(signer.get("identity"), "signer.identity", error_type=error_type, code=invalid_code)
    signature = _text(signer.get("signature"), "signer.signature", error_type=error_type, code=invalid_code)
    if signer.get("payloadType") != DSSE_PAYLOAD_TYPE:
        _fail(error_type, invalid_code, "DSSE payload type drifted")
    try:
        signed_payload = base64.b64decode(str(signer.get("payload")), validate=True)
    except (TypeError, ValueError) as exc:
        _fail(error_type, invalid_code, f"DSSE payload is invalid: {exc}")
    unsigned = dict(fact)
    unsigned.pop("factId", None)
    unsigned.pop("signer", None)
    if signed_payload != _canonical_json_bytes(unsigned):
        _fail(error_type, invalid_code, "DSSE payload does not bind exact fact")
    if signature_verifier is not None and not signature_verifier(signer_identity, signed_payload, signature):
        _fail(error_type, invalid_code, "DSSE signature verification failed")

    fact_id_material = dict(fact)
    fact_id = fact_id_material.pop("factId", None)
    expected_fact_id = "sha256:" + hashlib.sha256(_canonical_json_bytes(fact_id_material)).hexdigest()
    if _digest(fact_id, "factId", error_type=error_type, code=invalid_code) != expected_fact_id:
        _fail(error_type, invalid_code, "factId does not bind signed fact")

    root = store_root
    if verify_references:
        if root is None:
            _fail(error_type, invalid_code, "evidence root is required for reference verification")
        resolved_root = Path(root)
        expected_target = f"{environment}-local"
        for index, exact in enumerate(case_refs):
            result = _load_exact(
                resolved_root,
                exact,
                f"caseResultRefs[{index}]",
                error_type=error_type,
                invalid_code=invalid_code,
                evidence_code=evidence_code,
            )
            try:
                result = validate_readiness_case_result(result, generated_at=str(result.get("completedAt") or ""))
            except ReadinessCaseResultError as exc:
                _fail(error_type, evidence_code, f"caseResultRefs[{index}] is not a canonical ReadinessCaseResult: {exc}")
            if result.get("status") != "passed":
                _fail(error_type, evidence_code, f"caseResultRefs[{index}] status must be passed")
            if result.get("environment") != environment or result.get("deploymentTarget") != expected_target:
                _fail(error_type, evidence_code, f"caseResultRefs[{index}] environment/target drifted")
            if result.get("commitSha") != normalized_candidate["commit"]:
                _fail(error_type, evidence_code, f"caseResultRefs[{index}] candidate commit drifted")
            candidate_digest = result.get("candidateDigest")
            if candidate_digest != normalized_candidate["candidateId"]:
                _fail(error_type, evidence_code, f"caseResultRefs[{index}] candidate identity drifted")
            if profile == "release" and (
                result.get("producer") != "app"
                or result.get("layer") != "user_acceptance"
            ):
                _fail(error_type, evidence_code, f"caseResultRefs[{index}] is not release App UAT")
        for field, exact in evidence_refs.items():
            evidence = _load_exact(
                resolved_root,
                exact,
                field,
                error_type=error_type,
                invalid_code=invalid_code,
                evidence_code=evidence_code,
            )
            expected_role, allowed_statuses = _EVIDENCE_ROLE_CONTRACT[field]
            if (
                evidence.get("role") != expected_role
                or evidence.get("status") not in allowed_statuses
            ):
                _fail(error_type, evidence_code, f"{field} does not prove closure")
            for key, expected in (
                ("environment", environment),
                ("profile", profile),
                ("candidateId", normalized_candidate["candidateId"]),
                ("commit", normalized_candidate["commit"]),
                ("tree", normalized_candidate["tree"]),
                ("impactPlanDigest", fact["impactPlanDigest"]),
            ):
                if evidence.get(key) != expected:
                    _fail(error_type, evidence_code, f"{field} {key} drifted")
        if predecessor is not None:
            previous = _load_exact(
                resolved_root,
                predecessor,
                "predecessor",
                error_type=error_type,
                invalid_code=invalid_code,
                evidence_code=evidence_code,
            )
            previous = validate_environment_acceptance_fact(
                previous,
                store_root=resolved_root,
                verify_references=True,
                accepted_at=issued,
                error_type=error_type,
                invalid_code=invalid_code,
                evidence_code=evidence_code,
                signature_verifier=signature_verifier,
            )
            if (
                previous.get("environment") != expected_predecessor
                or previous.get("profile") != profile
                or previous.get("candidate") != normalized_candidate
                or previous.get("impactPlanDigest") != fact["impactPlanDigest"]
                or previous.get("status") not in {"passed", "not_required"}
                or previous.get("nonPromotable") != fact["nonPromotable"]
            ):
                _fail(error_type, evidence_code, "predecessor fact identity drifted")

    fact["candidate"] = normalized_candidate
    fact["caseResultRefs"] = case_refs
    fact.update(evidence_refs)
    fact["predecessor"] = predecessor
    return fact


__all__ = ["validate_environment_acceptance_fact"]
