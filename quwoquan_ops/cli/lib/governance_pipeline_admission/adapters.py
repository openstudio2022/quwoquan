"""Provider-specific read-only adapters for governance admission evidence."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from ..evidence_fingerprint import canonical_json_bytes, validate_digest, validate_evidence_fingerprint
from ..feature_context_fingerprint import validate_current_feature_context_fingerprint
from ..human_agent_delivery import CalibrationError, verify_calibration_readback
from ..objective_execution import inspect_admission
from ..objective_execution.contract import validate_admission_readback
from ..workflow_resolution import verify_receipt as verify_workflow_receipt
from .contract import ContractError, REPO_ROOT
from .read_only_local_readiness import verify_explicit_receipt_read_only

ExternalVerifier = Callable[[Mapping[str, Any]], Mapping[str, Any]]


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _json(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ContractError(f"{label} JSON invalid: {error}") from error
    if not isinstance(value, dict):
        raise ContractError(f"{label} must be a JSON object")
    return value


def _timestamp(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ContractError(f"{label} must be a non-empty timezone-aware timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ContractError(f"{label} timestamp invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContractError(f"{label} must be timezone-aware")
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")


def _readback(
    *,
    result: str,
    provider_kind: str,
    release: bool,
    receipt_ref: str,
    raw: bytes,
    provider_timestamp: str,
    candidate_id: str,
    scope_id: str,
    verifier_id: str,
    detail: str | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return {
        "status": "present",
        "schema_valid": True,
        "fresh": True,
        "fingerprint_match": True,
        "result": result,
        "provider_kind": provider_kind,
        "release_evidence_eligible": release,
        "detail": detail,
        "receipt_ref": receipt_ref,
        "receipt_bytes_sha256": _sha256(raw),
        "verified_at": now,
        "provider_timestamp": _timestamp(provider_timestamp, "provider timestamp"),
        "candidate_id": candidate_id,
        "scope_id": scope_id,
        "verifier_id": verifier_id,
    }


def verify_owner_manifest(*, raw: bytes, receipt_ref: str, candidate_id: str, scope_id: str, contract: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = _json(raw, "owner manifest")
    source = contract["current_repository_evidence"]
    if manifest.get("target") != source["owner_manifest_target"] or manifest.get("resolved_owner") != source["owner_manifest_target"]:
        raise ContractError("owner manifest target/owner mismatch")
    fingerprint = validate_current_feature_context_fingerprint(manifest, repo_root=REPO_ROOT)
    path = REPO_ROOT / receipt_ref
    root = (REPO_ROOT / source["owner_manifest_root"]).resolve()
    try:
        relative = path.resolve().relative_to(root)
    except ValueError as error:
        raise ContractError("owner manifest ref must be under fingerprint-indexed root") from error
    expected_name = f"{fingerprint['digest'].removeprefix('sha256:')}.json"
    if len(relative.parts) != 1 or relative.name != expected_name:
        raise ContractError("owner manifest ref is not indexed by its canonical fingerprint")
    readback = _readback(
        result="pass", provider_kind="local_runtime", release=False,
        receipt_ref=receipt_ref, raw=raw, provider_timestamp=fingerprint["captured_at"],
        candidate_id=candidate_id, scope_id=scope_id,
        verifier_id=contract["layer_admission"]["owner_manifest"]["verifier_id"],
    )
    return readback, fingerprint


def verify_workflow(*, raw: bytes, receipt_ref: str, manifest_fingerprint: Mapping[str, Any], candidate_id: str, scope_id: str, contract: Mapping[str, Any]) -> dict[str, Any]:
    receipt = _json(raw, "workflow receipt")
    verified = verify_workflow_receipt(receipt)
    fingerprint = validate_evidence_fingerprint(receipt.get("evidence_fingerprint"))
    if fingerprint["digest"] != manifest_fingerprint["digest"]:
        raise ContractError("workflow receipt is not bound to current owner manifest")
    result = "selected" if receipt.get("result") == "selected" and receipt.get("owner_manifest_status") == "fresh" and verified.get("selected_workflow") else "absent"
    return _readback(
        result=result, provider_kind="local_runtime", release=False,
        receipt_ref=receipt_ref, raw=raw, provider_timestamp=fingerprint["captured_at"],
        candidate_id=candidate_id, scope_id=scope_id,
        verifier_id=contract["layer_admission"]["workflow_resolve"]["verifier_id"],
    )


def verify_local_readiness(*, level: str, raw: bytes, receipt_ref: str, owner_manifest_ref: str, candidate_id: str, scope_id: str, contract: Mapping[str, Any]) -> dict[str, Any]:
    source = contract["current_repository_evidence"]
    receipt = verify_explicit_receipt_read_only(
        level=level, receipt_path=REPO_ROOT / receipt_ref, exact_bytes=raw,
        paths=list(source["local_readiness_paths"]), mode=str(source["local_readiness_mode"]),
        owner_manifest_path=REPO_ROOT / owner_manifest_ref,
    )
    return _readback(
        result="scope_ready" if level == "scope" else "release_ready",
        provider_kind="local_runtime", release=False, receipt_ref=receipt_ref, raw=raw,
        provider_timestamp=str(receipt["finished_at"]), candidate_id=candidate_id, scope_id=scope_id,
        verifier_id=contract["layer_admission"][f"local_{level}_ready"]["verifier_id"],
    )


def verify_review(*, plan_raw: bytes, plan_ref: str, evidence_raw: bytes, evidence_ref: str, consolidation_raw: bytes, consolidation_ref: str, candidate_id: str, scope_id: str, contract: Mapping[str, Any]) -> dict[str, Any]:
    plan = _json(plan_raw, "Review plan")
    evidence = _json(evidence_raw, "Review named evidence")
    consolidation = _json(consolidation_raw, "Review consolidation")
    import review_consolidator
    recomputed = review_consolidator.consolidate(dict(plan), dict(evidence), list(consolidation.get("reviewer_results") or []))
    if recomputed != consolidation:
        raise ContractError("Review consolidation does not match current recomputation")
    terminal = consolidation.get("terminal")
    if terminal != {"status": "PASS", "codes": []}:
        return _readback(
            result="READY", provider_kind="local_runtime", release=False,
            receipt_ref=consolidation_ref, raw=consolidation_raw,
            provider_timestamp=str(evidence.get("finished_at")), candidate_id=candidate_id,
            scope_id=scope_id, verifier_id=contract["layer_admission"]["review_terminal"]["verifier_id"],
            detail="Review consolidation is not PASS",
        )
    if any(item.get("severity") == "GATE_BLOCK" for item in consolidation.get("findings") or []):
        raise ContractError("Review consolidation contains a GATE_BLOCK finding")
    return _readback(
        result="pass", provider_kind="local_runtime", release=False,
        receipt_ref=consolidation_ref, raw=consolidation_raw,
        provider_timestamp=str(evidence.get("finished_at")), candidate_id=candidate_id,
        scope_id=scope_id, verifier_id=contract["layer_admission"]["review_terminal"]["verifier_id"],
        detail=f"plan={plan_ref}; named_evidence={evidence_ref}",
    )


def verify_handoff(*, raw: bytes, receipt_ref: str, candidate_id: str, scope_id: str, contract: Mapping[str, Any]) -> dict[str, Any]:
    payload = _json(raw, "handoff manifest")
    import handoff_consumer
    verified = handoff_consumer.validate_handoff_payload(payload)
    fingerprint = validate_evidence_fingerprint(verified.get("fingerprint_receipt"))
    return _readback(
        result="pass", provider_kind="local_runtime", release=False,
        receipt_ref=receipt_ref, raw=raw, provider_timestamp=fingerprint["captured_at"],
        candidate_id=candidate_id, scope_id=scope_id,
        verifier_id=contract["layer_admission"]["handoff_freshness"]["verifier_id"],
    )


def verify_human_readback(
    *, raw: bytes, receipt_ref: str, candidate_id: str, scope_id: str,
    evidence_fingerprint: str, session_bytes_by_ref: Mapping[str, bytes],
    provider_timestamp: str, verifier: ExternalVerifier | None, contract: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Consume only Human-owned exact v2 readback; never recompute a shadow role model."""
    value = _json(raw, "Human calibration readback")
    verified_at = datetime.now(timezone.utc)
    try:
        readback = verify_calibration_readback(
            value, session_bytes_by_ref=session_bytes_by_ref, now=verified_at,
            expected_scope={
                "decision_unit_id": str(value.get("scope", {}).get("decision_unit_id", "")),
                "evidence_fingerprint": evidence_fingerprint,
            },
        )
    except CalibrationError as error:
        raise ContractError(f"{error.code}: {error.detail}") from error
    if readback["scope"]["evidence_fingerprint"] != evidence_fingerprint:
        raise ContractError("HAD.CALIBRATION_CONTRACT_INCOMPATIBLE: EvidenceFingerprint mismatch")
    expected_provider_time = _timestamp(provider_timestamp, "Human provider timestamp")
    if expected_provider_time != _timestamp(readback["generated_at"], "Human readback generated_at"):
        raise ContractError("HAD.CALIBRATION_CONTRACT_INCOMPATIBLE: provider timestamp/readback mismatch")
    if verifier is None:
        raise ContractError("HAD.CALIBRATION_CONTRACT_INCOMPATIBLE: authenticated Human calibration verifier unavailable")
    policy = contract["layer_admission"]["human_calibration"]
    request = {
        "provider_id": policy["provider_id"], "receipt_ref": receipt_ref,
        "receipt_bytes": raw, "receipt_bytes_sha256": _sha256(raw),
        "session_bytes_by_ref": dict(session_bytes_by_ref),
        "subject": {"candidate_id": candidate_id, "scope_id": scope_id, "evidence_fingerprint": evidence_fingerprint},
    }
    external = verifier(request)
    required = {"provider_id", "provider_kind", "authenticated", "exact_bytes_verified", "release_evidence_eligible", "candidate_id", "scope_id", "evidence_fingerprint", "result", "provider_timestamp", "receipt_bytes_sha256", "verifier_id"}
    if not isinstance(external, Mapping) or set(external) != required:
        raise ContractError("HAD.CALIBRATION_CONTRACT_INCOMPATIBLE: Human external verifier fields drifted")
    if (
        external["provider_id"] != policy["provider_id"]
        or external["provider_kind"] != "authenticated_external"
        or external["authenticated"] is not True
        or external["exact_bytes_verified"] is not True
        or external["release_evidence_eligible"] is not True
        or external["candidate_id"] != candidate_id
        or external["scope_id"] != scope_id
        or external["evidence_fingerprint"] != evidence_fingerprint
        or external["result"] != readback["status"]
        or external["provider_timestamp"] != readback["generated_at"]
        or external["receipt_bytes_sha256"] != _sha256(raw)
        or external["verifier_id"] != policy["verifier_id"]
    ):
        raise ContractError("HAD.CALIBRATION_CONTRACT_INCOMPATIBLE: Human authenticated exact readback mismatch")
    return (
        _readback(
            result=readback["status"], provider_kind="authenticated_external", release=True,
            receipt_ref=receipt_ref, raw=raw, provider_timestamp=provider_timestamp,
            candidate_id=candidate_id, scope_id=scope_id, verifier_id=policy["verifier_id"],
        ),
        readback,
    )

def objective_readback(*, raw: bytes, receipt_ref: str, candidate_id: str, scope_id: str, contract: Mapping[str, Any]) -> dict[str, Any]:
    envelope = _json(raw, "Objective dynamic inspect")
    if set(envelope) != {"provider_timestamp", "readback"}:
        raise ContractError("Objective dynamic inspect envelope fields drifted")
    readback = validate_admission_readback(envelope["readback"])
    return _readback(
        result="present" if readback["status"] != "blocked" else "absent",
        provider_kind="local_runtime", release=False, receipt_ref=receipt_ref, raw=raw,
        provider_timestamp=str(envelope["provider_timestamp"]), candidate_id=candidate_id,
        scope_id=scope_id, verifier_id=contract["layer_admission"]["objective_readback"]["verifier_id"],
        detail=readback["reason"],
    )


def produce_objective_bytes() -> bytes:
    envelope = {"provider_timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"), "readback": inspect_admission()}
    return canonical_json_bytes(envelope)


def verify_hotl(*, raw: bytes, receipt_ref: str, candidate_id: str, scope_id: str, contract: Mapping[str, Any]) -> dict[str, Any]:
    envelope = _json(raw, "HOTL dynamic inspect")
    if set(envelope) != {"provider_timestamp", "readback"} or not isinstance(envelope["readback"], Mapping):
        raise ContractError("HOTL dynamic inspect envelope fields drifted")
    result = envelope["readback"]
    safe = result.get("allowed_mode") == "manual" and result.get("mutation_allowed") is False and result.get("grant_executable") is False and int(result.get("max_write_concurrency", 2)) <= 1
    return _readback(
        result="manual_safe" if safe else "absent", provider_kind="local_runtime", release=False,
        receipt_ref=receipt_ref, raw=raw, provider_timestamp=str(envelope["provider_timestamp"]),
        candidate_id=candidate_id, scope_id=scope_id,
        verifier_id=contract["layer_admission"]["hotl_inspect"]["verifier_id"],
    )


def produce_hotl_bytes(input_raw: bytes) -> bytes:
    from ..hotl_admission import inspect as inspect_hotl
    payload = _json(input_raw, "HOTL inspect input")
    envelope = {"provider_timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"), "readback": inspect_hotl(payload)}
    return canonical_json_bytes(envelope)


def produce_hosted_source_bytes(contract: Mapping[str, Any]) -> bytes:
    hosted = contract["hosted_authority_source"]
    refs: list[str] = []
    for key in ("service_contract_refs", "adapter_implementation_refs", "service_implementation_refs", "portal_implementation_refs"):
        refs.extend(hosted[key])
    snapshots = []
    for ref in sorted(refs):
        path = REPO_ROOT / ref
        if not path.is_file():
            snapshots.append({"path": ref, "state": "missing", "sha256": None})
        else:
            snapshots.append({"path": ref, "state": "present", "sha256": _sha256(path.read_bytes())})
    return canonical_json_bytes({"provider_timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"), "snapshots": snapshots})


def verify_hosted_source(*, raw: bytes, receipt_ref: str, candidate_id: str, scope_id: str, contract: Mapping[str, Any]) -> dict[str, Any]:
    expected = produce_hosted_source_bytes(contract)
    actual = _json(raw, "hosted authority source inspect")
    current = _json(expected, "current hosted authority source inspect")
    if actual.get("snapshots") != current.get("snapshots"):
        raise ContractError("hosted authority source bytes drifted")
    missing = [item["path"] for item in actual["snapshots"] if item.get("state") != "present"]
    return _readback(
        result="code_absent" if missing else "code_pass", provider_kind="hosted_code", release=False,
        receipt_ref=receipt_ref, raw=raw, provider_timestamp=str(actual["provider_timestamp"]),
        candidate_id=candidate_id, scope_id=scope_id,
        verifier_id=contract["layer_admission"]["hosted_authority_code"]["verifier_id"],
        detail=("missing required source: " + ",".join(missing)) if missing else None,
    )


def verify_external(*, layer: str, raw: bytes, receipt_ref: str, verifier: ExternalVerifier | None, subject: Mapping[str, Any], contract: Mapping[str, Any]) -> dict[str, Any]:
    policy = contract["layer_admission"][layer]
    if policy["interface"] != "external":
        raise ContractError(f"{layer} does not accept an external provider interface")
    if verifier is None:
        raise ContractError(f"external verifier unavailable for {policy['provider_id']}")
    request = {
        "provider_id": policy["provider_id"], "receipt_ref": receipt_ref,
        "receipt_bytes": raw, "receipt_bytes_sha256": _sha256(raw), "subject": dict(subject),
    }
    verified = verifier(request)
    required = {"provider_id", "provider_kind", "authenticated", "exact_bytes_verified", "release_evidence_eligible", "candidate_id", "scope_id", "evidence_fingerprint", "result", "provider_timestamp", "receipt_bytes_sha256", "verifier_id"}
    if not isinstance(verified, Mapping) or set(verified) != required:
        raise ContractError("external verifier readback fields drifted")
    if verified["provider_id"] != policy["provider_id"] or verified["provider_kind"] not in policy["provider_kinds"]:
        raise ContractError("external verifier provider identity is not allowed for layer")
    if verified["authenticated"] is not True or verified["exact_bytes_verified"] is not True:
        raise ContractError("external provider receipt is not authenticated exact-byte readback")
    if verified["receipt_bytes_sha256"] != _sha256(raw) or verified["evidence_fingerprint"] != subject["evidence_fingerprint"]:
        raise ContractError("external provider receipt bytes/fingerprint mismatch")
    if verified["candidate_id"] != subject["candidate_id"] or verified["scope_id"] != subject["scope_id"]:
        raise ContractError("external provider candidate/scope mismatch")
    if verified["verifier_id"] != policy["verifier_id"]:
        raise ContractError("external verifier identity mismatch")
    validate_digest(verified["receipt_bytes_sha256"])
    return _readback(
        result=str(verified["result"]), provider_kind=str(verified["provider_kind"]),
        release=bool(verified["release_evidence_eligible"]), receipt_ref=receipt_ref, raw=raw,
        provider_timestamp=str(verified["provider_timestamp"]), candidate_id=str(verified["candidate_id"]),
        scope_id=str(verified["scope_id"]), verifier_id=str(verified["verifier_id"]),
    )
