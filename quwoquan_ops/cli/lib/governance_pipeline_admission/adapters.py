"""Provider-specific read-only adapters for governance admission evidence."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any

from .. import feature_context_fingerprint
from ..agent_governance_contract import validate_feature_context_manifest
from ..evidence_fingerprint import (
    canonical_json_bytes,
    validate_digest,
    validate_evidence_fingerprint,
)
from ..feature_context_fingerprint import (
    build_feature_context_fingerprint,
    validate_current_feature_context_fingerprint,
)
from ..human_agent_delivery import CalibrationError, verify_calibration_readback
from ..objective_execution import inspect_admission
from ..objective_execution.contract import validate_admission_readback
from .contract import REPO_ROOT, ContractError, EvidenceAdapterError
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
    verification_time: datetime | None = None,
) -> dict[str, Any]:
    current = verification_time or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ContractError("verification time must be timezone-aware")
    verified_at = current.astimezone(timezone.utc).isoformat(timespec="seconds")
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
        "verified_at": verified_at,
        "provider_timestamp": _timestamp(provider_timestamp, "provider timestamp"),
        "candidate_id": candidate_id,
        "scope_id": scope_id,
        "verifier_id": verifier_id,
    }


def verify_owner_manifest(
    *, raw: bytes, receipt_ref: str, candidate_id: str, scope_id: str,
    verification_time: datetime, contract: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        manifest = _json(raw, "owner manifest")
        validate_feature_context_manifest(manifest)
        feature_context_fingerprint.validate_content_addressed_ref(
            receipt_ref, raw_bytes=raw, repo_root=REPO_ROOT,
        )
    except Exception as error:
        raise EvidenceAdapterError.schema(str(error) or type(error).__name__) from error
    source = contract["current_repository_evidence"]
    target = str(source["owner_manifest_target"])
    if manifest.get("target") != target or manifest.get("resolved_owner") != target:
        raise EvidenceAdapterError.identity("owner manifest target/owner mismatch")
    try:
        from ..feature_tree.commands import _context_manifest
        from ..feature_tree.nodes import discover_nodes
        from ..feature_tree.ownership import resolve_target_details

        nodes = discover_nodes()
        canonical = _context_manifest(target, resolve_target_details(target, nodes), nodes)
    except Exception as error:
        raise EvidenceAdapterError.schema(
            f"canonical owner manifest could not be resolved: {error}"
        ) from error
    for field in (
        "target",
        "resolved_owner",
        "owner_chain",
        "canonical_contexts",
        "applicable_agents",
        "open_items",
    ):
        if manifest[field] != canonical[field]:
            raise EvidenceAdapterError.identity(
                f"owner manifest {field} differs from canonical feature-tree producer"
            )
    chain = manifest["owner_chain"]
    if not chain or chain[-1].get("path") != manifest["resolved_owner"]:
        raise EvidenceAdapterError.identity(
            "owner manifest owner_chain must be non-empty and end at resolved_owner"
        )
    try:
        fingerprint = validate_current_feature_context_fingerprint(
            manifest, repo_root=REPO_ROOT,
        )
    except Exception as error:
        identity = {key: value for key, value in manifest.items() if key != "evidence_fingerprint"}
        try:
            expected = build_feature_context_fingerprint(identity, repo_root=REPO_ROOT)
            actual = feature_context_fingerprint.resolve_fingerprint_binding(
                manifest.get("evidence_fingerprint"), repo_root=REPO_ROOT,
            )
        except Exception as identity_error:
            raise EvidenceAdapterError.identity(
                str(identity_error) or type(identity_error).__name__
            ) from identity_error
        if actual.get("digest_payload") != expected.get("digest_payload"):
            raise EvidenceAdapterError.stale(str(error) or type(error).__name__) from error
        raise EvidenceAdapterError.identity(str(error) or type(error).__name__) from error
    readback = _readback(
        result="pass", provider_kind="local_runtime", release=False,
        receipt_ref=receipt_ref, raw=raw, provider_timestamp=verification_time.astimezone(timezone.utc).isoformat(timespec="seconds"),
        candidate_id=candidate_id, scope_id=scope_id,
        verifier_id=contract["layer_admission"]["owner_manifest"]["verifier_id"],
        verification_time=verification_time,
    )
    return readback, fingerprint


def verify_local_readiness(*, level: str, raw: bytes, receipt_ref: str, owner_manifest_ref: str, candidate_evidence_ref: str | None = None, candidate_id: str, scope_id: str, verification_time: datetime, contract: Mapping[str, Any]) -> dict[str, Any]:
    source = contract["current_repository_evidence"]
    receipt = verify_explicit_receipt_read_only(
        level=level, receipt_path=REPO_ROOT / receipt_ref, exact_bytes=raw,
        paths=list(source["local_readiness_paths"]), mode=str(source["local_readiness_mode"]),
        owner_manifest_path=REPO_ROOT / owner_manifest_ref,
        candidate_evidence_path=REPO_ROOT / candidate_evidence_ref if candidate_evidence_ref else None,
    )
    return _readback(
        result="scope_ready" if level == "scope" else "release_ready",
        provider_kind="local_runtime", release=False, receipt_ref=receipt_ref, raw=raw,
        provider_timestamp=str(receipt["finished_at"]), candidate_id=candidate_id, scope_id=scope_id,
        verifier_id=contract["layer_admission"][f"local_{level}_ready"]["verifier_id"],
        verification_time=verification_time,
    )


def verify_review(*, plan_raw: bytes, plan_ref: str, evidence_raw: bytes, evidence_ref: str, reviewer_result_pairs: list[tuple[str, bytes]], consolidation_raw: bytes, consolidation_ref: str, candidate_id: str, scope_id: str, verification_time: datetime, contract: Mapping[str, Any]) -> dict[str, Any]:
    plan = _json(plan_raw, "Review plan")
    evidence = _json(evidence_raw, "Review named evidence")
    consolidation = _json(consolidation_raw, "Review consolidation")
    try:
        import handoff_consumer
        import review_consolidator

        if (
            evidence.get("evidence_class") != "reusable"
            or evidence.get("admission_eligible") is not True
        ):
            raise EvidenceAdapterError.ineligible(
                "REVIEW.EVIDENCE_FEEDBACK_ONLY: governance review requires "
                "admission-eligible named evidence"
            )
        evidence_identity = handoff_consumer.named_evidence_identity_from_raw(
            evidence_ref, evidence_raw, evidence
        )
        reviewer_pairs: list[tuple[str, dict[str, Any]]] = []
        exact_bytes_by_ref = {evidence_ref: evidence_raw}
        for result_ref, result_raw in reviewer_result_pairs:
            exact_result = _json(result_raw, f"Review result {result_ref}")
            reviewer_pairs.append((result_ref, exact_result))
            exact_bytes_by_ref[result_ref] = result_raw
        review_consolidator.validate_exact_consolidation(
            consolidation,
            plan=dict(plan),
            evidence_pairs=[(evidence_ref, dict(evidence))],
            reviewer_pairs=reviewer_pairs,
            registry=review_consolidator._registry(),
            exact_bytes_by_ref=exact_bytes_by_ref,
        )
    except ContractError:
        raise
    except Exception as error:
        raise ContractError(f"Review consolidation exact validation failed: {error}") from error
    return _readback(
        result="pass", provider_kind="local_runtime", release=False,
        receipt_ref=consolidation_ref, raw=consolidation_raw,
        provider_timestamp=str(evidence.get("finished_at")), candidate_id=candidate_id,
        scope_id=scope_id, verifier_id=contract["layer_admission"]["review_terminal"]["verifier_id"],
        detail=f"plan={plan_ref}; named_evidence={evidence_ref}", verification_time=verification_time,
    )


def verify_handoff(*, raw: bytes, receipt_ref: str, candidate_id: str, scope_id: str, verification_time: datetime, contract: Mapping[str, Any], validate_current: bool = False) -> dict[str, Any]:
    import handoff_consumer
    verified = handoff_consumer.validate_published_bytes(
        receipt_ref, raw, validate_current=validate_current
    )
    fingerprint = validate_evidence_fingerprint(verified.get("fingerprint_receipt"))
    return _readback(
        result="pass", provider_kind="local_runtime", release=False,
        receipt_ref=receipt_ref, raw=raw, provider_timestamp=verification_time.astimezone(timezone.utc).isoformat(timespec="seconds"),
        candidate_id=candidate_id, scope_id=scope_id,
        verifier_id=contract["layer_admission"]["handoff_freshness"]["verifier_id"],
        verification_time=verification_time,
    )


def verify_human_readback(
    *, raw: bytes, receipt_ref: str, candidate_id: str, scope_id: str,
    evidence_fingerprint: str, session_bytes_by_ref: Mapping[str, bytes],
    provider_timestamp: str, verification_time: datetime,
    verifier: ExternalVerifier | None, contract: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Consume only Human-owned exact v2 readback; never recompute a shadow role model."""
    value = _json(raw, "Human calibration readback")
    try:
        readback = verify_calibration_readback(
            value, session_bytes_by_ref=session_bytes_by_ref, now=verification_time,
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
            verification_time=verification_time,
        ),
        readback,
    )

def objective_readback(*, raw: bytes, receipt_ref: str, candidate_id: str, scope_id: str, verification_time: datetime, contract: Mapping[str, Any]) -> dict[str, Any]:
    envelope = _json(raw, "Objective dynamic inspect")
    if set(envelope) != {"provider_timestamp", "readback"}:
        raise ContractError("Objective dynamic inspect envelope fields drifted")
    readback = validate_admission_readback(envelope["readback"])
    return _readback(
        result="present" if readback["status"] != "blocked" else "absent",
        provider_kind="local_runtime", release=False, receipt_ref=receipt_ref, raw=raw,
        provider_timestamp=str(envelope["provider_timestamp"]), candidate_id=candidate_id,
        scope_id=scope_id, verifier_id=contract["layer_admission"]["objective_readback"]["verifier_id"],
        detail=readback["reason"], verification_time=verification_time,
    )


def produce_objective_bytes() -> bytes:
    envelope = {"provider_timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"), "readback": inspect_admission()}
    return canonical_json_bytes(envelope)


def verify_hotl(*, raw: bytes, receipt_ref: str, candidate_id: str, scope_id: str, verification_time: datetime, contract: Mapping[str, Any]) -> dict[str, Any]:
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
        verification_time=verification_time,
    )


def produce_hotl_bytes(input_raw: bytes) -> bytes:
    from ..hotl_admission import inspect as inspect_hotl
    payload = _json(input_raw, "HOTL inspect input")
    envelope = {"provider_timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"), "readback": inspect_hotl(payload)}
    return canonical_json_bytes(envelope)


def _hosted_source_snapshots(contract: Mapping[str, Any]) -> list[dict[str, Any]]:
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
    return snapshots


def produce_hosted_source_bytes(contract: Mapping[str, Any]) -> bytes:
    return canonical_json_bytes({
        "provider_timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "snapshots": _hosted_source_snapshots(contract),
    })


def verify_hosted_source(*, raw: bytes, receipt_ref: str, candidate_id: str, scope_id: str, verification_time: datetime, contract: Mapping[str, Any]) -> dict[str, Any]:
    actual = _json(raw, "hosted authority source inspect")
    if actual.get("snapshots") != _hosted_source_snapshots(contract):
        raise ContractError("hosted authority source bytes drifted")
    missing = [item["path"] for item in actual["snapshots"] if item.get("state") != "present"]
    return _readback(
        result="code_absent" if missing else "code_pass", provider_kind="hosted_code", release=False,
        receipt_ref=receipt_ref, raw=raw, provider_timestamp=str(actual["provider_timestamp"]),
        candidate_id=candidate_id, scope_id=scope_id,
        verifier_id=contract["layer_admission"]["hosted_authority_code"]["verifier_id"],
        detail=("missing required source: " + ",".join(missing)) if missing else None,
        verification_time=verification_time,
    )


def verify_external(*, layer: str, raw: bytes, receipt_ref: str, verifier: ExternalVerifier | None, subject: Mapping[str, Any], verification_time: datetime, contract: Mapping[str, Any]) -> dict[str, Any]:
    policy = contract["layer_admission"][layer]
    if policy["interface"] != "external":
        raise ContractError(f"{layer} does not accept an external provider interface")
    if verifier is None:
        raise EvidenceAdapterError.identity(
            f"external verifier unavailable for {policy['provider_id']}"
        )
    request = {
        "provider_id": policy["provider_id"], "receipt_ref": receipt_ref,
        "receipt_bytes": raw, "receipt_bytes_sha256": _sha256(raw), "subject": dict(subject),
    }
    verified = verifier(request)
    required = {"provider_id", "provider_kind", "authenticated", "exact_bytes_verified", "release_evidence_eligible", "candidate_id", "scope_id", "evidence_fingerprint", "result", "provider_timestamp", "receipt_bytes_sha256", "verifier_id"}
    if not isinstance(verified, Mapping) or set(verified) != required:
        raise EvidenceAdapterError.schema("external verifier readback fields drifted")
    if verified["provider_id"] != policy["provider_id"] or verified["provider_kind"] not in policy["provider_kinds"]:
        raise EvidenceAdapterError.identity(
            "external verifier provider identity is not allowed for layer"
        )
    if verified["authenticated"] is not True or verified["exact_bytes_verified"] is not True:
        raise EvidenceAdapterError.identity(
            "external provider receipt is not authenticated exact-byte readback"
        )
    if verified["receipt_bytes_sha256"] != _sha256(raw) or verified["evidence_fingerprint"] != subject["evidence_fingerprint"]:
        raise EvidenceAdapterError.identity(
            "external provider receipt bytes/fingerprint mismatch"
        )
    if verified["candidate_id"] != subject["candidate_id"] or verified["scope_id"] != subject["scope_id"]:
        raise EvidenceAdapterError.identity(
            "external provider candidate/scope mismatch"
        )
    if verified["verifier_id"] != policy["verifier_id"]:
        raise EvidenceAdapterError.identity("external verifier identity mismatch")
    try:
        validate_digest(verified["receipt_bytes_sha256"])
    except Exception as error:
        raise EvidenceAdapterError.identity(
            str(error) or type(error).__name__
        ) from error
    return _readback(
        result=str(verified["result"]), provider_kind=str(verified["provider_kind"]),
        release=bool(verified["release_evidence_eligible"]), receipt_ref=receipt_ref, raw=raw,
        provider_timestamp=str(verified["provider_timestamp"]), candidate_id=str(verified["candidate_id"]),
        scope_id=str(verified["scope_id"]), verifier_id=str(verified["verifier_id"]),
        verification_time=verification_time,
    )
