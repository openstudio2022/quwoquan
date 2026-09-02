"""Read-only evaluator for the OPEN-006 one-unit pre-delete proof."""
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
from content.execution.runtime_contract import canonical_sha256
from content.release.canonical.content_pool_record import pool_payload_digest
from content.release.canonical.object_transaction_contract import ObjectTransactionError
from content.release.canonical.pool_record_history import _validated_pool_record
from content.release.canonical.release_header import ReleaseHeaderError, validate_release_header
from content.release.canonical.release_uat_sample_plan import (
    CARRIERS,
    ENTRIES,
    ReleaseUatSamplePlanError,
    exact_document_sha256,
    validate_release_uat_sample_plan,
)
from core.schema import assert_valid
from core.tree_integrity import tree_integrity_stats

SCHEMA = "quwoquan_data.stable_production_proof_set"
SPEC_REF = "specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-034"
OPEN_ITEM_REF = "specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#open-006"
STAGES = ("0.plan", "sources", "1.download", "2.quality", "3.compose", "4.draft", "5.review", "publish", "release", "ship")
ENVIRONMENTS = ("alpha", "beta", "gamma")
BASELINE_COUNTS = {carrier: 1 for carrier in CARRIERS}
_DIGEST_RE = re.compile(r"sha256:[a-f0-9]{64}")
_EXACT_REF_KEYS = frozenset({"ref", "exactByteDigest"})
_CARRIER_KEYS = frozenset(CARRIERS)
_UNIT_KEYS = frozenset({"unitId", "fingerprint", "evidenceAuthority", "carrierExecutions", "release", "environment", "environmentAcceptanceFact"})
_EXECUTION_KEYS = frozenset({"executionId", "carrierDemand", "candidateBindings", "taskInitRequest", "executionManifest", "targetSet", "stageReceipts", "executionState", "canonicalPublish", "poolDeliveryResult", "objectTransactionPackage", "applyReport", "poolRecord"})
_RELEASE_KEYS = frozenset({"header", "attestation", "desiredState", "samplePlan"})
_FORBIDDEN_LIVE_PREFIXES = ("content.execution.agent", "content.execution.queue", "content.execution.controller", "content.execution.recovery", "content.execution.campaign")


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
    if label == "stableProductionProof" and document.get("evidenceAuthority") != "canonical_runtime":
        raise StableProductionProofError(
            "stableProductionProof must carry canonical_runtime evidence authority"
        )
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
    original_tasks_root: Path | None = None
    original_output_root: Path | None = None
    original_release_root: Path | None = None
    original_authority_fingerprint = None
    original_semantic_fingerprint = None
    try:
        from content.execution import stage_authority, stage_semantic_recorder

        first_receipt, _ = _load_exact_json(root, refs[0], "stageReceipts[0]")
        authority = first_receipt.get("authority")
        workflow = authority.get("workflowContract") if isinstance(authority, Mapping) else None
        frozen_workflow_digest = _digest(
            workflow.get("digest") if isinstance(workflow, Mapping) else None,
            "stageReceipts[0].authority.workflowContract.digest",
        )
        original_authority_fingerprint = stage_authority.operational_fingerprint
        original_semantic_fingerprint = stage_semantic_recorder.operational_fingerprint
        stage_authority.operational_fingerprint = lambda **_kwargs: frozen_workflow_digest
        stage_semantic_recorder.operational_fingerprint = lambda **_kwargs: frozen_workflow_digest
        actual_execution_root = _contained_path(root, _exact_ref(refs[0], "stageReceipts[0]")["ref"]).parents[2]
        original_tasks_root = stage_authority.paths.DATA_EXECUTIONS_ROOT
        original_output_root = stage_authority.paths.OUTPUT_ROOT
        original_release_root = stage_authority.paths.RELEASE_ROOT
        stage_authority.paths.DATA_EXECUTIONS_ROOT = actual_execution_root.parent
        stage_authority.paths.OUTPUT_ROOT = root
        stage_authority.paths.RELEASE_ROOT = root / "data/releases"
        for index, expected_stage in enumerate(STAGES):
            receipt, binding = _load_exact_json(root, refs[index], f"stageReceipts[{index}]")
            try:
                receipt = stage_authority.validate_stage_receipt_authority(
                    execution_id, _contained_path(root, binding["ref"]),
                    verify_current_workflow=False,
                )
            except (ValueError, OSError) as exc:
                raise StableProductionProofError(
                    f"stage receipt authority rejected at {expected_stage}: {exc}"
                ) from exc
            if receipt.get("executionId") != execution_id or receipt.get("sequence") != index + 1 or receipt.get("stage") != expected_stage or receipt.get("verdict") != "pass":
                raise StableProductionProofError(f"stage receipt sequence/verdict drifted at {expected_stage}")
            expected_next = STAGES[index + 1] if index + 1 < len(STAGES) else "END"
            if receipt.get("next") != expected_next:
                raise StableProductionProofError(f"stage {expected_stage} next must be {expected_next}")
            projected.append(binding)
            if expected_stage == "ship":
                ship = receipt
    finally:
        if original_tasks_root is not None:
            stage_authority.paths.DATA_EXECUTIONS_ROOT = original_tasks_root
            stage_authority.paths.OUTPUT_ROOT = original_output_root
            stage_authority.paths.RELEASE_ROOT = original_release_root
        if original_authority_fingerprint is not None:
            stage_authority.operational_fingerprint = original_authority_fingerprint
        if original_semantic_fingerprint is not None:
            stage_semantic_recorder.operational_fingerprint = original_semantic_fingerprint
    assert ship is not None
    return projected, ship


def _normalized_object_ref(value: object, carrier: str, label: str) -> str:
    reference = _text(value, label).strip("/")
    if carrier == "homepage":
        reference = reference.removeprefix("entity/").removeprefix("entities/")
    else:
        reference = reference.removeprefix("posts/")
    candidate = Path(reference)
    if not reference or candidate.is_absolute() or ".." in candidate.parts:
        raise StableProductionProofError(f"{label} is unsafe")
    return reference


def _published_target(document: Mapping[str, Any], execution_id: str, carrier: str) -> tuple[str, str]:
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
    if carrier == "homepage":
        if target not in entities:
            raise StableProductionProofError("homepage must publish exactly one entity")
        normalized = _normalized_object_ref(target, carrier, "canonicalPublish.homepage")
        canonical_ref = f"entities/{normalized}"
    else:
        if target not in posts or not target.startswith(f"{carrier}/"):
            raise StableProductionProofError(f"{carrier} must publish exactly one carrier-bound post")
        normalized = _normalized_object_ref(target, carrier, f"canonicalPublish.{carrier}")
        canonical_ref = f"posts/{normalized}"
    return normalized, canonical_ref


def _validate_delivery(
    document: Mapping[str, Any], execution_id: str, published_target: str, carrier: str,
) -> dict[str, Any]:
    _assert_schema(document, "execution", "pool_delivery_drain_result", "poolDeliveryResult")
    if document.get("executionId") != execution_id or document.get("status") != "completed" or document.get("attemptedCount") != 1 or document.get("completedCount") != 1 or document.get("total") != 1 or document.get("qualifiedCount") != 1 or document.get("discardedCount") != 0 or document.get("pendingCount") != 0 or document.get("excludedCount") != 0 or document.get("blockedCount") != 0:
        raise StableProductionProofError("pool delivery must be one completed qualified target")
    appended = document.get("appendedCount")
    replayed = document.get("replayedCount")
    delta = document.get("poolDelta")
    if (appended, replayed, delta) not in {(1, 0, 1), (0, 1, 0)}:
        raise StableProductionProofError("pool delivery requires appended=>delta1 or replayed=>delta0")
    results = document.get("objectResults")
    canonical_objects = document.get("canonicalObjects")
    if not isinstance(results, list) or len(results) != 1 or not isinstance(results[0], Mapping) or results[0].get("result") != ("appended" if appended == 1 else "replayed"):
        raise StableProductionProofError("pool delivery object result drifted from publish")
    if _normalized_object_ref(results[0].get("objectRef"), carrier, "poolDeliveryResult.objectResults[0].objectRef") != published_target:
        raise StableProductionProofError("pool delivery object result drifted from publish")
    if not isinstance(canonical_objects, list) or len(canonical_objects) != 1 or not isinstance(canonical_objects[0], Mapping):
        raise StableProductionProofError("pool delivery requires exactly one canonicalObject")
    canonical_object = dict(canonical_objects[0])
    if results[0].get("canonicalObject") != canonical_object:
        raise StableProductionProofError("pool delivery canonicalObject projections differ")
    pool_record = canonical_object.get("poolRecord")
    if not isinstance(pool_record, Mapping) or document.get("recordSetDigest") != canonical_sha256([dict(pool_record)]):
        raise StableProductionProofError("pool delivery recordSetDigest drifted")
    if results[0].get("transactionInputDigest") != canonical_object.get("objectClosureDigest"):
        raise StableProductionProofError("transactionInputDigest differs from objectClosureDigest")
    return canonical_object


def _assert_no_symlinks(root: Path, label: str) -> None:
    try:
        if root.is_symlink() or not root.is_dir() or any(path.is_symlink() for path in root.rglob("*")):
            raise OSError("directory is absent or contains a symbolic link")
    except OSError as exc:
        raise StableProductionProofError(f"{label} is not a regular symlink-free directory: {exc}") from exc


def _validate_object_evidence(
    root: Path, source: Mapping[str, Any], *, carrier: str, execution_id: str,
    published_target: str, canonical_ref: str, delivery: Mapping[str, Any],
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    transaction_id = _text(delivery.get("transactionId"), f"{carrier}.delivery.transactionId")
    closure_digest = _digest(delivery.get("objectClosureDigest"), f"{carrier}.delivery.objectClosureDigest")
    if delivery.get("canonicalObjectRef") != canonical_ref:
        raise StableProductionProofError(f"{carrier} canonical object ref drifted from publish")

    package, package_ref = _load_exact_json(root, source.get("objectTransactionPackage"), f"{carrier}.objectTransactionPackage")
    _assert_schema(package, "release", "object_transaction_package", f"{carrier}.objectTransactionPackage")
    expected_package_ref = f"data/tasks/{execution_id}/evidence/object-transactions/{transaction_id}/object_transaction_package.json"
    target = package.get("target")
    expected_kind = "entities" if carrier == "homepage" else "posts"
    if package_ref["ref"] != expected_package_ref or package.get("schema") != "quwoquan_data.object_transaction_package" or package.get("executionId") != execution_id or package.get("transactionId") != transaction_id or not isinstance(target, Mapping) or target.get("objectKind") != expected_kind or _normalized_object_ref(target.get("objectRef"), carrier, f"{carrier}.objectTransactionPackage.target.objectRef") != published_target or package.get("objectClosureDigest") != closure_digest:
        raise StableProductionProofError(f"{carrier} object transaction package identity drifted")

    apply, apply_ref = _load_exact_json(root, source.get("applyReport"), f"{carrier}.applyReport")
    expected_apply_ref = f"data/local/workspace/object-transactions/{transaction_id}/apply_report.json"
    if apply_ref["ref"] != delivery.get("applyReportRef") or apply_ref["ref"] != expected_apply_ref:
        raise StableProductionProofError(f"{carrier} apply report ref drifted")
    expected_apply = {
        "schema": "quwoquan_data.object_transaction_apply",
        "executionId": execution_id,
        "transactionId": transaction_id,
        "status": "applied",
        "objectKind": expected_kind,
        "objectClosureDigest": closure_digest,
    }
    if any(apply.get(key) != value for key, value in expected_apply.items()) or _normalized_object_ref(apply.get("objectRef"), carrier, f"{carrier}.applyReport.objectRef") != published_target:
        raise StableProductionProofError(f"{carrier} apply report identity drifted")

    record, record_ref = _load_exact_json(root, source.get("poolRecord"), f"{carrier}.poolRecord")
    delivery_record = delivery.get("poolRecord")
    if not isinstance(delivery_record, Mapping):
        raise StableProductionProofError(f"{carrier} delivery poolRecord is missing")
    sequence = delivery_record.get("recordSequence")
    expected_record_ref = f"{canonical_ref}/_pool/versions/{sequence}.json"
    expected_exact_ref = f"canonical-publish/{expected_record_ref}"
    if record_ref["ref"] != expected_exact_ref or delivery_record.get("recordRef") != expected_record_ref:
        raise StableProductionProofError(f"{carrier} pool record ref escapes canonical object")
    if delivery_record.get("recordSha256") != record_ref["exactByteDigest"]:
        raise StableProductionProofError(f"{carrier} pool record exact-byte digest drifted")

    canonical_dir = _contained_path(root, f"canonical-publish/{canonical_ref}")
    _assert_no_symlinks(canonical_dir, f"{carrier}.canonicalObject")
    actual_merkle = str(tree_integrity_stats(canonical_dir)["merkleRoot"])
    if actual_merkle != delivery.get("canonicalObjectSha256"):
        raise StableProductionProofError(f"{carrier} canonical object bytes drifted")
    _assert_schema(record, "release", "pool_object_record", f"{carrier}.poolRecord")
    try:
        validated_record = _validated_pool_record(
            record, object_type="homepage" if carrier == "homepage" else "content",
        )
    except ObjectTransactionError as exc:
        raise StableProductionProofError(f"{carrier} canonical pool record rejected: {exc}") from exc
    payload_digest = pool_payload_digest(canonical_dir)
    if _normalized_object_ref(validated_record.get("objectRef"), carrier, f"{carrier}.poolRecord.objectRef") != published_target or (validated_record.get("sourceIdentity") or {}).get("executionId") != execution_id or validated_record.get("contentVersion") != delivery_record.get("contentVersion") or validated_record.get("recordSequence") != sequence or validated_record.get("payloadDigest") != delivery_record.get("payloadDigest") or validated_record.get("canonicalObjectDigest") != delivery_record.get("payloadDigest") or payload_digest != validated_record.get("payloadDigest"):
        raise StableProductionProofError(f"{carrier} canonical pool record identity or payload drifted")
    return package_ref, apply_ref, record_ref


def _validate_carrier_execution(root: Path, source: Mapping[str, Any], carrier: str, fingerprint: str) -> tuple[dict[str, Any], str]:
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
    if not isinstance(bundle, Mapping):
        raise StableProductionProofError(f"{carrier} executionBundle is missing")
    if manifest.get("operationalFingerprint") != fingerprint:
        raise StableProductionProofError(f"{carrier} operational fingerprint drifted")
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
    target, canonical_ref = _published_target(publish, execution_id, carrier)
    delivery, delivery_ref = _load_exact_json(root, source.get("poolDeliveryResult"), f"{carrier}.poolDeliveryResult")
    canonical_object = _validate_delivery(delivery, execution_id, target, carrier)
    package_ref, apply_ref, pool_record_ref = _validate_object_evidence(
        root, source, carrier=carrier, execution_id=execution_id,
        published_target=target, canonical_ref=canonical_ref, delivery=canonical_object,
    )
    return ({"executionId": execution_id, "carrier": carrier, "carrierDemand": demand_ref, "candidateBindings": candidate_ref, "taskInitRequest": request_ref, "executionManifest": manifest_ref, "targetSet": target_ref, "stageReceipts": receipts, "executionState": state_ref, "canonicalPublish": publish_ref, "poolDeliveryResult": delivery_ref, "objectTransactionPackage": package_ref, "applyReport": apply_ref, "poolRecord": pool_record_ref}, execution_id)


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
    profiles: list[dict[str, str]] = []
    try:
        validated = validate_environment_acceptance_fact(acceptance, evidence_root=root, required_target_profiles=profiles, verify_references=True)
    except EnvironmentAcceptanceFactError as exc:
        raise StableProductionProofError(f"canonical EnvironmentAcceptanceFact rejected: {exc}") from exc
    if validated.get("environment") != environment or environment not in ENVIRONMENTS or validated.get("releaseId") != release_id or validated.get("releaseDigest") != release_digest or validated.get("sourceFingerprint") != expected_fingerprint or validated.get("samplePlanRef") != sample_plan_ref["ref"] or validated.get("samplePlanDigest") != sample_plan_ref["exactByteDigest"]:
        raise StableProductionProofError("EnvironmentAcceptanceFact release/environment/fingerprint drifted")
    if validated.get("acceptanceProfile") != "m1_api_consumer":
        raise StableProductionProofError("proof unit requires m1_api_consumer acceptance profile")
    if validated.get("targetBindingRefs") != []:
        raise StableProductionProofError("m1_api_consumer proof must not bind TargetUatBinding")
    raw_refs = validated.get("requiredRawResults")
    if not isinstance(raw_refs, list) or len(raw_refs) != 16:
        raise StableProductionProofError("proof unit requires exactly 16 raw Service API cells")
    projected_raw: list[dict[str, str]] = []
    cells: set[tuple[str, str]] = set()
    for index, raw_ref in enumerate(raw_refs):
        raw, binding_ref = _load_exact_json(root, {"ref": raw_ref.get("ref"), "exactByteDigest": raw_ref.get("digest")}, f"requiredRawResults[{index}]")
        entry = _text(raw.get("entrySurface"), f"requiredRawResults[{index}].entrySurface")
        carrier = _text(raw.get("carrier"), f"requiredRawResults[{index}].carrier")
        cells.add((entry, carrier))
        projected_raw.append({**binding_ref, "entrySurface": entry, "carrier": carrier, "specRef": _text(raw.get("specRef"), f"requiredRawResults[{index}].specRef")})
    if cells != {(entry, carrier) for entry in ENTRIES for carrier in CARRIERS}:
        raise StableProductionProofError("raw Service API matrix lacks one or more canonical cells")
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
    evidence = {"activation": fact_ref({"ref": active.get("ref"), "digest": active.get("digest")}, "activation"), "import": _exact_ref({"ref": envelope.get("importReportRef"), "exactByteDigest": envelope.get("importReportDigest")}, "import"), "readback": fact_ref({"ref": active.get("readbackRef"), "digest": active.get("readbackDigest")}, "readback"), "lifecycle": fact_ref(validated.get("lifecycleExit"), "lifecycle"), "rollback": fact_ref(validated.get("rollbackReadiness"), "rollback"), "apiConsumerRawResults": sorted(projected_raw, key=lambda row: (row["entrySurface"], row["carrier"]))}
    return acceptance_ref, evidence, _digest(validated.get("factId"), "EnvironmentAcceptanceFact.factId")


def _validate_operational_receipt(
    root: Path, value: object, *, name: str, fingerprint: str,
) -> dict[str, str]:
    document, binding = _load_exact_json(root, value, name)
    _assert_schema(document, "execution", name, name)
    if document.get("sourceFingerprint") != fingerprint or document.get("exitCode") != 0 or document.get("verdict") != "pass":
        raise StableProductionProofError(f"{name} must be a current passing canonical receipt")
    command = document.get("command")
    canonical = {
        "verify_all_receipt": ("data.verify.all", "quwoquan_data/scripts/cli.py", ["verify", "all"]),
        "public_cli_live_import_zero_receipt": (
            "data.public_cli.live_import_zero",
            "quwoquan_data/scripts/cli.py",
            ["governance", "public-cli-live-import-zero"],
        ),
    }[name]
    if not isinstance(command, Mapping) or (command.get("commandId"), command.get("entrypoint"), command.get("arguments")) != canonical:
        raise StableProductionProofError(f"{name} canonical command identity drifted")
    output = document.get("capturedOutput")
    if not isinstance(output, Mapping) or any(_DIGEST_RE.fullmatch(str(output.get(field) or "")) is None for field in ("stdoutDigest", "stderrDigest")):
        raise StableProductionProofError(f"{name} captured output digests are invalid")
    if name == "verify_all_receipt":
        modules = document.get("closedModules")
        if not isinstance(modules, list) or not modules:
            raise StableProductionProofError("verify_all_receipt closed module list is empty")
    else:
        prefixes = document.get("forbiddenPrefixes")
        loaded = document.get("loadedModules")
        if tuple(prefixes or ()) != _FORBIDDEN_LIVE_PREFIXES:
            raise StableProductionProofError("public CLI receipt forbidden prefix closure drifted")
        if not isinstance(loaded, list) or not loaded or loaded != sorted(set(map(str, loaded))):
            raise StableProductionProofError("public CLI receipt loaded module list is invalid")
        expected_digest = exact_document_sha256({"loadedModules": loaded})
        if document.get("loadedModulesDigest") != expected_digest:
            raise StableProductionProofError("public CLI receipt loaded module digest drifted")
        probe_digest = _digest(document.get("probeDigest"), "public CLI receipt probeDigest")
        checked_commands = document.get("checkedCommands")
        receipt_id = exact_document_sha256({
            "sourceFingerprint": fingerprint,
            "probeDigest": probe_digest,
            "checkedCommands": checked_commands,
            "forbiddenPrefixes": list(prefixes),
            "loadedModulesDigest": expected_digest,
        })
        if document.get("receiptId") != receipt_id:
            raise StableProductionProofError("public CLI receipt identity digest drifted")
        forbidden = [module for module in loaded if any(module == prefix or module.startswith(prefix + ".") for prefix in _FORBIDDEN_LIVE_PREFIXES)]
        if forbidden or document.get("forbiddenLoadedModules") != []:
            raise StableProductionProofError(f"public CLI loaded forbidden retired modules: {forbidden}")
    return binding


def evaluate_stable_production_proof(*, artifact_root: Path, expected_fingerprint: str, verify_all_receipt: Mapping[str, Any], public_cli_live_import_zero_receipt: Mapping[str, Any], proof_units: Sequence[Mapping[str, Any]], allow_test_evidence: bool = False) -> dict[str, Any]:
    """Evaluate explicit evidence only; never discover latest, run commands, or write."""
    root = _safe_root(artifact_root)
    fingerprint = _digest(expected_fingerprint, "expectedFingerprint")
    if not isinstance(proof_units, Sequence) or isinstance(proof_units, (str, bytes)) or len(proof_units) != 1:
        raise StableProductionProofError("exactly one proofUnit is required")
    verify_all_binding = _validate_operational_receipt(
        root, verify_all_receipt, name="verify_all_receipt", fingerprint=fingerprint,
    )
    public_cli_binding = _validate_operational_receipt(
        root, public_cli_live_import_zero_receipt,
        name="public_cli_live_import_zero_receipt", fingerprint=fingerprint,
    )
    unit_sources = list(proof_units)
    authorities: set[str] = set()
    for index, source in enumerate(unit_sources):
        if not isinstance(source, Mapping) or set(source) != _UNIT_KEYS:
            raise StableProductionProofError(f"proofUnits[{index}] fields mismatch")
        authority = _text(source.get("evidenceAuthority"), f"proofUnits[{index}].evidenceAuthority")
        if authority not in {"canonical_runtime", "test_only"}:
            raise StableProductionProofError("proof unit evidenceAuthority is invalid")
        if authority == "test_only" and not allow_test_evidence:
            raise StableProductionProofError("test_only evidence is not accepted by the production evaluator")
        authorities.add(authority)
    if len(authorities) != 1:
        raise StableProductionProofError("proof units must use one evidence authority")
    evidence_authority = next(iter(authorities))
    prevalidated_acceptance: dict[str, tuple[dict[str, str], dict[str, Any], str]] = {}
    for index, source in enumerate(unit_sources):
        release_source = source.get("release")
        if not isinstance(release_source, Mapping):
            raise StableProductionProofError("release must be an object")
        header, _ = _load_exact_json(root, release_source.get("header"), "release.header")
        plan, plan_binding = _load_exact_json(root, release_source.get("samplePlan"), "release.samplePlan")
        release_id = _text(header.get("releaseId"), "releaseId")
        release_digest = _digest(plan.get("releaseDigest"), "releaseDigest")
        environment = _text(source.get("environment"), f"proofUnits[{index}].environment")
        prevalidated_acceptance[_text(source.get("unitId"), f"proofUnits[{index}].unitId")] = _validate_acceptance(
            root, source.get("environmentAcceptanceFact"), release_id=release_id,
            release_digest=release_digest, sample_plan_ref=plan_binding,
            expected_fingerprint=fingerprint, environment=environment,
        )
    projected: list[dict[str, Any]] = []
    unit_ids: set[str] = set()
    release_ids: set[str] = set()
    execution_ids: set[str] = set()
    acceptance_ids: set[str] = set()
    for index, source in enumerate(unit_sources):
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
            execution, execution_id = _validate_carrier_execution(root, raw, carrier, fingerprint)
            if execution_id in execution_ids or execution_id in unit_execution_ids:
                raise StableProductionProofError("all four executionIds must be independent")
            unit_execution_ids.add(execution_id)
            execution_ids.add(execution_id)
            carrier_projection[carrier] = execution
        release_source = source.get("release")
        if not isinstance(release_source, Mapping):
            raise StableProductionProofError("release must be an object")
        release, release_id, release_digest, _plan = _validate_release(root, release_source, unit_execution_ids)
        if release_id in release_ids:
            raise StableProductionProofError("proof unit release identity is duplicated")
        release_ids.add(release_id)
        environment = _text(source.get("environment"), f"proofUnits[{index}].environment")
        acceptance_ref, evidence, acceptance_id = prevalidated_acceptance[unit_id]
        if acceptance_id in acceptance_ids:
            raise StableProductionProofError("proof unit acceptance identity is duplicated")
        acceptance_ids.add(acceptance_id)
        projected.append({"unitId": unit_id, "fingerprint": fingerprint, "evidenceAuthority": evidence_authority, "carrierCounts": dict(BASELINE_COUNTS), "carrierExecutions": carrier_projection, "release": release, "environment": environment, "environmentAcceptanceFact": acceptance_ref, "environmentEvidence": evidence})
    if len(execution_ids) != 4 or len(release_ids) != 1 or len(acceptance_ids) != 1:
        raise StableProductionProofError("proof set one-unit closure drifted")
    result = {"schema": SCHEMA, "specRef": SPEC_REF, "openItemRef": OPEN_ITEM_REF, "expectedFingerprint": fingerprint, "evidenceAuthority": evidence_authority, "proofUnitCount": 1, "unitIds": sorted(unit_ids), "releaseIds": sorted(release_ids), "executionIds": sorted(execution_ids), "executionCount": 4, "verifyAllReceipt": verify_all_binding, "publicCliLiveImportZeroReceipt": public_cli_binding, "carrierCountsPerUnit": dict(BASELINE_COUNTS), "proofUnits": sorted(projected, key=lambda row: row["unitId"]), "verdict": "pass"}
    assert_valid(result, "execution", "stable_production_proof_set", label="stable-production-proof")
    return result


__all__ = ["BASELINE_COUNTS", "CARRIERS", "ENVIRONMENTS", "OPEN_ITEM_REF", "SCHEMA", "SPEC_REF", "STAGES", "StableProductionProofError", "evaluate_stable_production_proof", "exact_byte_digest"]
