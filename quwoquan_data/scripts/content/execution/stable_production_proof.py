"""Read-only evaluator for the OPEN-006 three-unit pre-delete proof."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from content.execution.identity import parse_execution_id
from content.execution.stage_receipt import receipt_state_status
from content.release.canonical.release_header import ReleaseHeaderError, validate_release_header
from content.release.canonical.release_uat_sample_plan import (
    CARRIERS,
    ENTRIES,
    ReleaseUatSamplePlanError,
    exact_document_sha256,
    validate_release_uat_sample_plan,
)
from core.schema import assert_valid

SCHEMA = "quwoquan_data.stable_production_proof_set"
SPEC_REF = "specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-034"
OPEN_ITEM_REF = "specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#open-006"
STAGES = ("0.plan", "sources", "1.download", "2.quality", "3.compose", "4.draft", "5.review", "publish", "release", "ship")
ENVIRONMENTS = ("alpha", "beta", "gamma")
BASELINE_COUNTS = {carrier: 1 for carrier in CARRIERS}
_DIGEST_RE = re.compile(r"sha256:[a-f0-9]{64}")
_EXACT_REF_KEYS = frozenset({"ref", "exactByteDigest"})
_CARRIER_KEYS = frozenset(CARRIERS)
_UNIT_KEYS = frozenset({"unitId", "fingerprint", "carrierExecutions", "release", "environment", "environmentAcceptanceFact"})
_EXECUTION_KEYS = frozenset({"executionId", "carrierDemand", "candidateBindings", "taskInitRequest", "executionManifest", "targetSet", "stageReceipts", "executionState", "canonicalPublish", "poolDeliveryResult", "retryRecovery"})
_RELEASE_KEYS = frozenset({"header", "attestation", "desiredState", "samplePlan"})


class StableProductionProofError(ValueError):
    """Selected evidence is incomplete, drifted, or cannot count for OPEN-006."""


def exact_byte_digest(raw: bytes | Path) -> str:
    payload = raw if isinstance(raw, bytes) else _read_regular_nofollow(Path(raw))
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise StableProductionProofError(f"{label} must be a non-empty canonical string")
    return value


def _digest(value: object, label: str) -> str:
    digest = _text(value, label)
    if _DIGEST_RE.fullmatch(digest) is None:
        raise StableProductionProofError(f"{label} must be a sha256 digest")
    return digest


def _safe_root(root: Path) -> Path:
    candidate = Path(root).expanduser()
    try:
        if candidate.is_symlink():
            raise OSError("symbolic roots are not accepted")
        resolved = candidate.resolve(strict=True)
        metadata = resolved.stat()
    except OSError as exc:
        raise StableProductionProofError(f"artifact root is unavailable: {exc}") from exc
    if not stat.S_ISDIR(metadata.st_mode):
        raise StableProductionProofError("artifact root must be a directory")
    return resolved


def _contained_path(root: Path, ref: str) -> Path:
    relative = Path(_text(ref, "ref"))
    if relative.is_absolute() or ".." in relative.parts:
        raise StableProductionProofError(f"ref must be relative and contained: {ref}")
    current = root
    try:
        for part in relative.parts:
            current /= part
            if current.is_symlink():
                raise OSError(f"symbolic link is not accepted: {current}")
        resolved = current.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise StableProductionProofError(f"ref is unavailable or escapes containment: {ref}: {exc}") from exc
    return resolved


def _read_regular_nofollow(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        before = path.lstat()
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise StableProductionProofError(f"ref cannot be opened safely: {path}: {exc}") from exc
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or not stat.S_ISREG(opened.st_mode):
            raise StableProductionProofError(f"ref must be a regular file: {path}")
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise StableProductionProofError(f"ref changed while opening: {path}")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise StableProductionProofError(f"ref changed while reading: {path}")
    return b"".join(chunks)


def _exact_ref(value: object, label: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _EXACT_REF_KEYS:
        raise StableProductionProofError(f"{label} must contain ref and exactByteDigest only")
    return {"ref": _text(value.get("ref"), f"{label}.ref"), "exactByteDigest": _digest(value.get("exactByteDigest"), f"{label}.exactByteDigest")}


def _load_exact_json(root: Path, value: object, label: str) -> tuple[dict[str, Any], dict[str, str]]:
    binding = _exact_ref(value, label)
    raw = _read_regular_nofollow(_contained_path(root, binding["ref"]))
    actual = exact_byte_digest(raw)
    if actual != binding["exactByteDigest"]:
        raise StableProductionProofError(f"{label} exact-byte digest drifted: expected {binding['exactByteDigest']}, got {actual}")
    try:
        document = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise StableProductionProofError(f"{label} must reference typed JSON") from exc
    if not isinstance(document, dict):
        raise StableProductionProofError(f"{label} JSON root must be an object")
    return document, binding


def _assert_schema(document: Mapping[str, Any], group: str, name: str, label: str) -> None:
    try:
        assert_valid(document, group, name, label=label)
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise StableProductionProofError(f"{label} canonical schema invalid: {exc}") from exc


def _validate_receipts(root: Path, refs: object, execution_id: str) -> tuple[list[dict[str, str]], dict[str, Any]]:
    if not isinstance(refs, Sequence) or isinstance(refs, (str, bytes)) or len(refs) != len(STAGES):
        raise StableProductionProofError("each carrier execution requires exactly ten stage receipts")
    projected: list[dict[str, str]] = []
    ship: dict[str, Any] | None = None
    for index, expected_stage in enumerate(STAGES):
        receipt, binding = _load_exact_json(root, refs[index], f"stageReceipts[{index}]")
        _assert_schema(receipt, "execution", "stage_receipt", f"stageReceipts[{index}]")
        if receipt.get("executionId") != execution_id or receipt.get("sequence") != index + 1 or receipt.get("stage") != expected_stage or receipt.get("verdict") != "pass":
            raise StableProductionProofError(f"stage receipt sequence/verdict drifted at {expected_stage}")
        expected_next = STAGES[index + 1] if index + 1 < len(STAGES) else "END"
        if receipt.get("next") != expected_next:
            raise StableProductionProofError(f"stage {expected_stage} next must be {expected_next}")
        projected.append(binding)
        if expected_stage == "ship":
            ship = receipt
    assert ship is not None
    return projected, ship


def _validate_retry(root: Path, execution_id: str, retry_of: object, value: object) -> dict[str, Any] | None:
    if retry_of is None:
        if value is not None:
            raise StableProductionProofError("non-retry execution must not claim retryRecovery")
        return None
    predecessor = _text(retry_of, "executionManifest.retryOf")
    if predecessor == execution_id or not isinstance(value, Mapping) or set(value) != {"retryOf", "executionManifest", "executionState"} or value.get("retryOf") != predecessor:
        raise StableProductionProofError("retryRecovery identity or fields drifted")
    previous_manifest, manifest_ref = _load_exact_json(root, value.get("executionManifest"), "retry predecessor manifest")
    previous_state, state_ref = _load_exact_json(root, value.get("executionState"), "retry predecessor state")
    if previous_manifest.get("executionId") != predecessor or previous_state.get("executionId") != predecessor:
        raise StableProductionProofError("retry predecessor exact identity drifted")
    current_identity = parse_execution_id(execution_id)
    previous_identity = parse_execution_id(predecessor)
    if (current_identity.run_date, current_identity.vertical, current_identity.content_type, current_identity.intent, current_identity.scope, current_identity.phase) != (previous_identity.run_date, previous_identity.vertical, previous_identity.content_type, previous_identity.intent, previous_identity.scope, previous_identity.phase) or previous_identity.sequence >= current_identity.sequence:
        raise StableProductionProofError("retryOf must be an earlier sequence of the same execution scope")
    if previous_state.get("status") != "manual_required":
        raise StableProductionProofError(
            "retryOf must bind the canonical failed terminal predecessor state"
        )
    latest_ref = str(previous_state.get("latestReceiptRef") or "")
    if not latest_ref:
        raise StableProductionProofError("retry predecessor lacks latest blocked receipt")
    predecessor_receipt, _receipt_ref = _load_exact_json(
        root,
        {
            "ref": f"{Path(manifest_ref['ref']).parent.as_posix()}/{latest_ref}",
            "exactByteDigest": previous_state.get("latestReceiptDigest"),
        },
        "retry predecessor latest receipt",
    )
    _assert_schema(
        predecessor_receipt,
        "execution",
        "stage_receipt",
        "retry predecessor latest receipt",
    )
    if (
        predecessor_receipt.get("executionId") != predecessor
        or predecessor_receipt.get("verdict") != "blocked"
        or receipt_state_status(predecessor_receipt).value != "manual_required"
        or previous_state.get("latestStage") != predecessor_receipt.get("stage")
    ):
        raise StableProductionProofError(
            "retry predecessor is not a receipt-derived failed terminal"
        )
    return {"retryOf": predecessor, "executionManifest": manifest_ref, "executionState": state_ref}


def _published_target(document: Mapping[str, Any], execution_id: str, carrier: str) -> str:
    _assert_schema(document, "execution", "publish_ref", "canonicalPublish")
    if document.get("executionId") != execution_id or document.get("canonicalPublishRoot") != "canonical-publish":
        raise StableProductionProofError("canonical publish identity drifted")
    published = document.get("publishedRefs")
    if not isinstance(published, Mapping):
        raise StableProductionProofError("canonical publish refs are invalid")
    entities = published.get("entities")
    posts = published.get("posts")
    if not isinstance(entities, list) or not isinstance(posts, list):
        raise StableProductionProofError("canonical publish refs are invalid")
    refs = [str(value) for value in entities + posts]
    if len(refs) != 1:
        raise StableProductionProofError("each carrier publish must contain exactly one target")
    target = refs[0]
    if carrier == "homepage" and target not in entities:
        raise StableProductionProofError("homepage must publish exactly one entity")
    if carrier != "homepage" and (target not in posts or not target.startswith(f"{carrier}/")):
        raise StableProductionProofError(f"{carrier} must publish exactly one carrier-bound post")
    return target


def _validate_delivery(document: Mapping[str, Any], execution_id: str, published_target: str) -> None:
    _assert_schema(document, "execution", "pool_delivery_drain_result", "poolDeliveryResult")
    if document.get("executionId") != execution_id or document.get("status") != "completed" or document.get("attemptedCount") != 1 or document.get("completedCount") != 1 or document.get("total") != 1 or document.get("qualifiedCount") != 1 or document.get("discardedCount") != 0 or document.get("pendingCount") != 0 or document.get("excludedCount") != 0 or document.get("blockedCount") != 0:
        raise StableProductionProofError("pool delivery must be one completed qualified target")
    appended = document.get("appendedCount")
    replayed = document.get("replayedCount")
    delta = document.get("poolDelta")
    if (appended, replayed, delta) not in {(1, 0, 1), (0, 1, 0)}:
        raise StableProductionProofError("pool delivery requires appended=>delta1 or replayed=>delta0")
    results = document.get("objectResults")
    if not isinstance(results, list) or len(results) != 1 or results[0].get("objectRef") != published_target or results[0].get("result") != ("appended" if appended == 1 else "replayed"):
        raise StableProductionProofError("pool delivery object result drifted from publish")


def _validate_carrier_execution(root: Path, source: Mapping[str, Any], carrier: str, fingerprint: str) -> tuple[dict[str, Any], str, str | None]:
    if set(source) != _EXECUTION_KEYS:
        raise StableProductionProofError(f"{carrier} carrier execution fields mismatch")
    execution_id = _text(source.get("executionId"), f"{carrier}.executionId")
    try:
        identity = parse_execution_id(execution_id)
    except ValueError as exc:
        raise StableProductionProofError(str(exc)) from exc
    if identity.content_type.value != carrier:
        raise StableProductionProofError(f"carrier key {carrier} differs from execution identity")
    demand, demand_ref = _load_exact_json(root, source.get("carrierDemand"), f"{carrier}.carrierDemand")
    candidates, candidate_ref = _load_exact_json(root, source.get("candidateBindings"), f"{carrier}.candidateBindings")
    request, request_ref = _load_exact_json(root, source.get("taskInitRequest"), f"{carrier}.taskInitRequest")
    manifest, manifest_ref = _load_exact_json(root, source.get("executionManifest"), f"{carrier}.executionManifest")
    target_set, target_ref = _load_exact_json(root, source.get("targetSet"), f"{carrier}.targetSet")
    for document, schema_name, label in ((demand, "carrier_demand", "carrierDemand"), (candidates, "immutable_candidate_bindings", "candidateBindings"), (request, "task_init_request", "taskInitRequest"), (manifest, "content_execution_manifest", "executionManifest"), (target_set, "target_set", "targetSet")):
        _assert_schema(document, "execution", schema_name, f"{carrier}.{label}")
    if any(document.get("executionId") != execution_id for document in (demand, candidates, request, manifest, target_set)):
        raise StableProductionProofError(f"{carrier} task init identity drifted")
    if demand.get("carrier") != carrier or candidates.get("carrier") != carrier or request.get("carrier") != carrier:
        raise StableProductionProofError(f"{carrier} task init carrier drifted")
    bundle = manifest.get("executionBundle")
    if not isinstance(bundle, Mapping) or bundle.get("digest") != fingerprint:
        raise StableProductionProofError(f"{carrier} execution fingerprint drifted")
    candidate_binding = target_set.get("candidateBinding")
    if demand.get("quota") != 1 or candidates.get("candidateCount") != 1 or request.get("quota") != 1 or request.get("workUnitCount") != 1 or target_set.get("targetCount") != 1 or not isinstance(candidate_binding, Mapping) or candidate_binding.get("candidateCount") != 1:
        raise StableProductionProofError(f"{carrier} task init requires quota/candidate/workUnit/target all equal 1")
    if request.get("retryOf") != manifest.get("retryOf"):
        raise StableProductionProofError(f"{carrier} retryOf drifted between task init and manifest")
    receipts, ship = _validate_receipts(root, source.get("stageReceipts"), execution_id)
    state, state_ref = _load_exact_json(root, source.get("executionState"), f"{carrier}.executionState")
    _assert_schema(state, "execution", "execution_state", f"{carrier}.executionState")
    if state.get("executionId") != execution_id or state.get("status") != "succeeded" or receipt_state_status(ship).value != "succeeded":
        raise StableProductionProofError(f"{carrier} succeeded must derive only from ship pass")
    publish, publish_ref = _load_exact_json(root, source.get("canonicalPublish"), f"{carrier}.canonicalPublish")
    target = _published_target(publish, execution_id, carrier)
    delivery, delivery_ref = _load_exact_json(root, source.get("poolDeliveryResult"), f"{carrier}.poolDeliveryResult")
    _validate_delivery(delivery, execution_id, target)
    retry_of = manifest.get("retryOf")
    recovery = _validate_retry(root, execution_id, retry_of, source.get("retryRecovery"))
    return ({"executionId": execution_id, "carrier": carrier, "retryOf": retry_of, "retryRecovery": recovery, "carrierDemand": demand_ref, "candidateBindings": candidate_ref, "taskInitRequest": request_ref, "executionManifest": manifest_ref, "targetSet": target_ref, "stageReceipts": receipts, "executionState": state_ref, "canonicalPublish": publish_ref, "poolDeliveryResult": delivery_ref}, execution_id, execution_id if retry_of is not None else None)


def _validate_release(root: Path, source: Mapping[str, Any], execution_ids: set[str]) -> tuple[dict[str, Any], str, str, dict[str, Any]]:
    if set(source) != _RELEASE_KEYS:
        raise StableProductionProofError("release evidence fields mismatch")
    header, header_ref = _load_exact_json(root, source.get("header"), "release.header")
    attestation, attestation_ref = _load_exact_json(root, source.get("attestation"), "release.attestation")
    desired, desired_ref = _load_exact_json(root, source.get("desiredState"), "release.desiredState")
    plan, plan_ref = _load_exact_json(root, source.get("samplePlan"), "release.samplePlan")
    try:
        validate_release_header(header, label="stable proof release header")
    except ReleaseHeaderError as exc:
        raise StableProductionProofError(str(exc)) from exc
    _assert_schema(attestation, "release", "release_attestation", "release.attestation")
    _assert_schema(desired, "release", "release_desired_state", "release.desiredState")
    try:
        validate_release_uat_sample_plan(plan)
    except ReleaseUatSamplePlanError as exc:
        raise StableProductionProofError(str(exc)) from exc
    release_id = _text(header.get("releaseId"), "releaseId")
    if header.get("releaseKind") != "content" or header.get("releaseClass") != "research" or header.get("productLifecycleState") != "research" or header.get("releaseMode") != "research" or header.get("milestone") is not None:
        raise StableProductionProofError("proof release must be non-milestone Research content release")
    if set(header.get("executionIds", [])) != execution_ids or len(header.get("executionIds", [])) != 4:
        raise StableProductionProofError("proof release must bind exactly the unit's four executions")
    if header.get("samplePlanRef") != "uat/sample_plan.json" or header.get("samplePlanDigest") != plan_ref["exactByteDigest"] or exact_document_sha256(plan) != plan_ref["exactByteDigest"]:
        raise StableProductionProofError("release header sample plan exact refs drifted")
    if attestation.get("releaseId") != release_id or set(attestation.get("executionIds", [])) != execution_ids or attestation.get("canonicalMerkle") != header.get("canonicalMerkle"):
        raise StableProductionProofError("release attestation identity drifted")
    if desired.get("releaseId") != release_id or plan.get("releaseId") != release_id or plan.get("milestone") is not None:
        raise StableProductionProofError("release canonical document identities drifted")
    desired_refs = desired.get("desiredRefs")
    counts = plan.get("exactCohortCounts")
    distribution = (plan.get("sampleStrategy") or {}).get("sampleDistribution") if isinstance(plan.get("sampleStrategy"), Mapping) else None
    cells = plan.get("entryCarrierCells")
    if not isinstance(desired_refs, Mapping) or len(desired_refs.get("entities", [])) != 1 or len(desired_refs.get("posts", [])) != 3 or dict(counts or {}) != BASELINE_COUNTS or dict(distribution or {}) != BASELINE_COUNTS or plan.get("sampleCount") != 4 or not isinstance(cells, list) or len(cells) != 16 or any(cell.get("applicability") != "required" for cell in cells if isinstance(cell, Mapping)):
        raise StableProductionProofError("baseline release must carry exact cohort/sample 1/1/1/1 and 16 required cells")
    release_digest = _digest(plan.get("releaseDigest"), "releaseDigest")
    return ({"releaseId": release_id, "releaseDigest": release_digest, "header": header_ref, "attestation": attestation_ref, "desiredState": desired_ref, "samplePlan": plan_ref}, release_id, release_digest, plan)


def _validate_acceptance(root: Path, value: object, *, release_id: str, release_digest: str, sample_plan_ref: Mapping[str, str], expected_fingerprint: str, environment: str) -> tuple[dict[str, str], dict[str, Any], str]:
    from quwoquan_ops.cli.lib.environment_acceptance_fact import EnvironmentAcceptanceFactError, validate_environment_acceptance_fact
    acceptance, acceptance_ref = _load_exact_json(root, value, "environmentAcceptanceFact")
    refs = acceptance.get("targetBindingRefs")
    profiles = [{"platform": item.get("platform"), "deviceProfile": item.get("deviceProfile")} for item in refs if isinstance(item, Mapping)] if isinstance(refs, list) else []
    try:
        validated = validate_environment_acceptance_fact(acceptance, evidence_root=root, required_target_profiles=profiles, verify_references=True)
    except EnvironmentAcceptanceFactError as exc:
        raise StableProductionProofError(f"canonical EnvironmentAcceptanceFact rejected: {exc}") from exc
    if validated.get("environment") != environment or environment not in ENVIRONMENTS or validated.get("releaseId") != release_id or validated.get("releaseDigest") != release_digest or validated.get("sourceFingerprint") != expected_fingerprint or validated.get("samplePlanRef") != sample_plan_ref["ref"] or validated.get("samplePlanDigest") != sample_plan_ref["exactByteDigest"]:
        raise StableProductionProofError("EnvironmentAcceptanceFact release/environment/fingerprint drifted")
    if len(profiles) != 1 or profiles[0]["deviceProfile"] != "promotable":
        raise StableProductionProofError("proof unit requires one promotable target binding")
    target_binding_ref = validated["targetBindingRefs"][0]
    binding, _ = _load_exact_json(root, {"ref": target_binding_ref["ref"], "exactByteDigest": target_binding_ref["digest"]}, "TargetUatBinding")
    provider = binding.get("provider")
    device = binding.get("device")
    runner = binding.get("runner")
    if binding.get("profile") != "promotable" or binding.get("nonPromotable") is not False or not isinstance(provider, Mapping) or provider.get("registered") is not True or not isinstance(device, Mapping) or device.get("class") != "physical" or device.get("registered") is not True or not isinstance(runner, Mapping) or runner.get("registered") is not True:
        raise StableProductionProofError("proof unit requires registered physical-device promotable UAT")
    raw_refs = validated.get("requiredRawResults")
    if not isinstance(raw_refs, list) or len(raw_refs) != 16:
        raise StableProductionProofError("proof unit requires exactly 16 raw App UAT cells")
    projected_raw: list[dict[str, str]] = []
    cells: set[tuple[str, str]] = set()
    for index, raw_ref in enumerate(raw_refs):
        raw, binding_ref = _load_exact_json(root, {"ref": raw_ref.get("ref"), "exactByteDigest": raw_ref.get("digest")}, f"requiredRawResults[{index}]")
        entry = _text(raw.get("entrySurface"), f"requiredRawResults[{index}].entrySurface")
        carrier = _text(raw.get("carrier"), f"requiredRawResults[{index}].carrier")
        cells.add((entry, carrier))
        projected_raw.append({**binding_ref, "entrySurface": entry, "carrier": carrier, "specRef": _text(raw.get("specRef"), f"requiredRawResults[{index}].specRef")})
    if cells != {(entry, carrier) for entry in ENTRIES for carrier in CARRIERS}:
        raise StableProductionProofError("raw App UAT matrix lacks one or more canonical cells")
    def fact_ref(value: object, label: str) -> dict[str, str]:
        if not isinstance(value, Mapping):
            raise StableProductionProofError(f"{label} exact ref missing")
        return _exact_ref({"ref": value.get("ref"), "exactByteDigest": value.get("digest")}, label)
    active = validated.get("activeCas")
    data = validated.get("dataReadiness")
    if not isinstance(active, Mapping) or not isinstance(data, Mapping):
        raise StableProductionProofError("acceptance lifecycle refs missing")
    data_payload, _ = _load_exact_json(root, {"ref": data.get("ref"), "exactByteDigest": data.get("digest")}, "dataReadiness")
    envelope = data_payload.get("activationEnvelope")
    if not isinstance(envelope, Mapping):
        raise StableProductionProofError("dataReadiness lacks import envelope")
    evidence = {"activation": fact_ref({"ref": active.get("ref"), "digest": active.get("digest")}, "activation"), "import": _exact_ref({"ref": envelope.get("importReportRef"), "exactByteDigest": envelope.get("importReportDigest")}, "import"), "readback": fact_ref({"ref": active.get("readbackRef"), "digest": active.get("readbackDigest")}, "readback"), "lifecycle": fact_ref(validated.get("lifecycleExit"), "lifecycle"), "rollback": fact_ref(validated.get("rollbackReadiness"), "rollback"), "appConsumerRawResults": sorted(projected_raw, key=lambda row: (row["entrySurface"], row["carrier"]))}
    return acceptance_ref, evidence, _digest(validated.get("factId"), "EnvironmentAcceptanceFact.factId")


def evaluate_stable_production_proof(*, artifact_root: Path, expected_fingerprint: str, proof_units: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Evaluate explicit evidence only; never discover latest, run commands, or write."""
    root = _safe_root(artifact_root)
    fingerprint = _digest(expected_fingerprint, "expectedFingerprint")
    if not isinstance(proof_units, Sequence) or isinstance(proof_units, (str, bytes)) or len(proof_units) != 3:
        raise StableProductionProofError("exactly three proofUnits are required")
    projected: list[dict[str, Any]] = []
    unit_ids: set[str] = set()
    release_ids: set[str] = set()
    execution_ids: set[str] = set()
    acceptance_ids: set[str] = set()
    retry_ids: set[str] = set()
    for index, source in enumerate(proof_units):
        if not isinstance(source, Mapping) or set(source) != _UNIT_KEYS:
            raise StableProductionProofError(f"proofUnits[{index}] fields mismatch")
        unit_id = _text(source.get("unitId"), f"proofUnits[{index}].unitId")
        if unit_id in unit_ids:
            raise StableProductionProofError("proof unit IDs must be independent")
        unit_ids.add(unit_id)
        if _digest(source.get("fingerprint"), f"proofUnits[{index}].fingerprint") != fingerprint:
            raise StableProductionProofError("all proof units must bind the current fingerprint")
        carriers = source.get("carrierExecutions")
        if not isinstance(carriers, Mapping) or set(carriers) != _CARRIER_KEYS:
            raise StableProductionProofError("carrierExecutions must contain exactly homepage/article/image/video")
        carrier_projection: dict[str, Any] = {}
        unit_execution_ids: set[str] = set()
        for carrier in CARRIERS:
            raw = carriers[carrier]
            if not isinstance(raw, Mapping):
                raise StableProductionProofError(f"carrierExecutions.{carrier} must be an object")
            execution, execution_id, retry_id = _validate_carrier_execution(root, raw, carrier, fingerprint)
            if execution_id in execution_ids or execution_id in unit_execution_ids:
                raise StableProductionProofError("all twelve executionIds must be independent")
            unit_execution_ids.add(execution_id)
            execution_ids.add(execution_id)
            if retry_id is not None:
                retry_ids.add(retry_id)
            carrier_projection[carrier] = execution
        release_source = source.get("release")
        if not isinstance(release_source, Mapping):
            raise StableProductionProofError("release must be an object")
        release, release_id, release_digest, _plan = _validate_release(root, release_source, unit_execution_ids)
        if release_id in release_ids:
            raise StableProductionProofError("three proof units must use independent releases")
        release_ids.add(release_id)
        environment = _text(source.get("environment"), f"proofUnits[{index}].environment")
        acceptance_ref, evidence, acceptance_id = _validate_acceptance(root, source.get("environmentAcceptanceFact"), release_id=release_id, release_digest=release_digest, sample_plan_ref=release["samplePlan"], expected_fingerprint=fingerprint, environment=environment)
        if acceptance_id in acceptance_ids:
            raise StableProductionProofError("three proof units must use independent acceptance facts")
        acceptance_ids.add(acceptance_id)
        projected.append({"unitId": unit_id, "fingerprint": fingerprint, "carrierCounts": dict(BASELINE_COUNTS), "carrierExecutions": carrier_projection, "release": release, "environment": environment, "environmentAcceptanceFact": acceptance_ref, "environmentEvidence": evidence})
    if len(execution_ids) != 12 or len(release_ids) != 3 or len(acceptance_ids) != 3:
        raise StableProductionProofError("proof set independence closure drifted")
    if not retry_ids:
        raise StableProductionProofError("three proof units require at least one valid terminal retryOf recovery")
    result = {"schema": SCHEMA, "specRef": SPEC_REF, "openItemRef": OPEN_ITEM_REF, "expectedFingerprint": fingerprint, "proofUnitCount": 3, "unitIds": sorted(unit_ids), "releaseIds": sorted(release_ids), "executionIds": sorted(execution_ids), "executionCount": 12, "retryRecoveryExecutionIds": sorted(retry_ids), "carrierCountsPerUnit": dict(BASELINE_COUNTS), "proofUnits": sorted(projected, key=lambda row: row["unitId"]), "verdict": "pass"}
    assert_valid(result, "execution", "stable_production_proof_set", label="stable-production-proof")
    return result


__all__ = ["BASELINE_COUNTS", "CARRIERS", "ENVIRONMENTS", "OPEN_ITEM_REF", "SCHEMA", "SPEC_REF", "STAGES", "StableProductionProofError", "evaluate_stable_production_proof", "exact_byte_digest"]
