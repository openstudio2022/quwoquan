"""Canonical three-unit stable-production-proof fixture for local contracts."""
from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

DATA_ROOT = Path(__file__).resolve().parents[2]
ROOT = DATA_ROOT.parent
SCRIPTS = DATA_ROOT / "scripts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from content.execution import stable_production_proof as proof
from content.execution.closure.pool_delivery_result import (
    build_pool_delivery_drain_result,
    build_pool_delivery_object_result,
)
from content.execution.runtime_contract import canonical_sha256
from content.release.canonical.aggregate_release_documents import (
    release_attestation_document,
    release_desired_state_document,
    release_header_document,
)
from content.release.canonical.object_source_identity import source_identity_set
from content.release.canonical.release_uat_sample_plan import (
    PLAN_REF,
    build_release_uat_sample_plan,
    exact_document_bytes,
    exact_document_sha256,
)
from core.source_digest import (
    ExecutionBundleIdentity,
    SourceDefinitionSnapshot,
    content_source_revision,
)
from quwoquan_ops.cli.lib.environment_acceptance_fact import (
    build_environment_acceptance_fact,
    required_raw_slot_id,
)
from quwoquan_ops.cli.lib.target_uat_binding import build_target_uat_binding

FINGERPRINT = "sha256:" + "f" * 64
SOURCE_DIGEST = "sha256:" + "a" * 64
ENTITY_CATALOG_DIGEST = "sha256:" + "b" * 64
SOURCE_REVISION = content_source_revision(
    source_digest=SOURCE_DIGEST,
    entity_catalog_digest=ENTITY_CATALOG_DIGEST,
)
SPEC_REF = "specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#req-006"
ENTRIES = ("feed", "search", "recommendation", "direct_or_object_route")


def write_exact(root: Path, ref: str, value: object, *, canonical: bool = False) -> dict[str, str]:
    path = root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (
        exact_document_bytes(value)
        if canonical and isinstance(value, Mapping)
        else (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    )
    path.write_bytes(raw)
    return {"ref": ref, "exactByteDigest": proof.exact_byte_digest(raw)}


def _receipt(execution_id: str, stage: str, sequence: int, verdict: str = "pass") -> dict[str, object]:
    return {
        "schema": "quwoquan_data.stage_receipt",
        "executionId": execution_id,
        "stage": stage,
        "sequence": sequence,
        "verdict": verdict,
        "actor": {"host": "test-host", "modelFamily": "fixture", "sessionId": "stable-proof"},
        "artifacts": [f"artifact/{stage}.json"],
        "openItems": ([] if verdict == "pass" else [{"item": "terminal fixture", "disposition": "gate_block"}]),
        "next": (proof.STAGES[sequence] if verdict == "pass" and sequence < len(proof.STAGES) else "END"),
        "evidence": {"commands": [{"command": f"fixture {stage}", "exitCode": 0 if verdict == "pass" else 1}], "issueCount": 0 if verdict == "pass" else 1, "repairRounds": 0},
        "recordedAt": f"2026-08-29T07:{sequence:02d}:00Z",
    }


def _execution_state(execution_id: str, receipt_ref: dict[str, str], *, status: str, completed: list[str], stage: str, next_stage: str) -> dict[str, object]:
    return {
        "schema": "quwoquan.content.execution_state_projection",
        "executionId": execution_id,
        "completed": completed,
        "status": status,
        "latestStage": stage,
        "next": next_stage,
        "latestReceiptRef": str(receipt_ref["ref"]).split(f"data/tasks/{execution_id}/", 1)[1],
        "latestReceiptDigest": receipt_ref["exactByteDigest"],
        "updatedAt": "2026-08-29T07:10:00Z",
    }


def _task_documents(root: Path, execution_id: str, carrier: str, retry_of: str | None) -> dict[str, dict[str, str]]:
    base = f"data/tasks/{execution_id}"
    family_ref = f"quwoquan_data/verticals/travel/{carrier}/family.yaml"
    source = SourceDefinitionSnapshot(SOURCE_DIGEST).to_document()
    bundle = ExecutionBundleIdentity(FINGERPRINT).to_document()
    work_request_ref = f"requests/{execution_id}.json"
    work_request_digest = canonical_sha256({"executionId": execution_id})
    demand = {
        "schema": "quwoquan_data.carrier_demand", "status": "confirmed",
        "executionId": execution_id, "carrier": carrier, "familyRef": family_ref,
        "quota": 1, "workRequestRef": work_request_ref,
        "workRequestDigest": work_request_digest, "sourceDigest": source,
        "executionBundle": bundle, "entityCatalogDigest": ENTITY_CATALOG_DIGEST,
        "retryOf": retry_of,
    }
    demand_ref = write_exact(root, f"{base}/inputs/carrier_demand.json", demand)
    target = {"name": f"proof-{carrier}", "entityType": "travel/place"}
    candidates = {
        "schema": "quwoquan_data.immutable_candidate_bindings", "executionId": execution_id,
        "carrier": carrier, "sourceRef": "inputs/work_request.json",
        "entityCatalogDigest": ENTITY_CATALOG_DIGEST, "candidateCount": 1, "targets": [target],
    }
    candidate_ref = write_exact(root, f"{base}/inputs/candidate_bindings.json", candidates)
    request = {
        "schema": "quwoquan_data.task_init_request", "executionId": execution_id,
        "familyRef": family_ref, "carrier": carrier, "quota": 1, "workUnitCount": 1,
        "carrierDemand": {"ref": demand_ref["ref"], "digest": demand_ref["exactByteDigest"], "workRequestRef": work_request_ref, "workRequestDigest": work_request_digest},
        "candidateBinding": {"ref": candidate_ref["ref"], "digest": candidate_ref["exactByteDigest"]},
        "retryOf": retry_of,
    }
    request_ref = write_exact(root, f"{base}/0.plan/request.json", request)
    target_set = {
        "executionId": execution_id, "selectionPolicy": "frozen", "sourceRef": "inputs/work_request.json",
        "candidateBinding": {"ref": candidate_ref["ref"], "digest": candidate_ref["exactByteDigest"], "candidateCount": 1},
        "entityCatalogDigest": ENTITY_CATALOG_DIGEST, "targetCount": 1,
        "targetRefs": [f"travel/place/proof-{carrier}"], "targets": [target],
    }
    target_ref = write_exact(root, f"{base}/0.plan/target_set.json", target_set)
    manifest = {
        "executionId": execution_id,
        "familyRef": {"ref": family_ref, "sha256": "c" * 64},
        "sourceDigest": source, "executionBundle": bundle, "hostRuntime": "external_host_agent",
        "carrierDemand": {"ref": demand_ref["ref"], "digest": demand_ref["exactByteDigest"], "workRequestRef": work_request_ref, "workRequestDigest": work_request_digest},
        "requestRef": "0.plan/request.json", "targetSetRef": "0.plan/target_set.json",
        "targetSetDigest": proof.exact_byte_digest(root / target_ref["ref"]).removeprefix("sha256:"),
        "retryOf": retry_of,
    }
    manifest_ref = write_exact(root, f"{base}/execution_manifest.json", manifest)
    return {"carrierDemand": demand_ref, "candidateBindings": candidate_ref, "taskInitRequest": request_ref, "executionManifest": manifest_ref, "targetSet": target_ref}


def _retry_recovery(root: Path, predecessor_id: str) -> dict[str, object]:
    base = f"data/tasks/{predecessor_id}"
    terminal = _receipt(predecessor_id, "ship", 10, "blocked")
    terminal_ref = write_exact(root, f"{base}/_shared/receipts/010-ship.json", terminal)
    manifest = _task_documents(root, predecessor_id, "video", None)["executionManifest"]
    state = _execution_state(predecessor_id, terminal_ref, status="manual_required", completed=list(proof.STAGES[:-1]), stage="ship", next_stage="END")
    state_ref = write_exact(root, f"{base}/_shared/execution_state.json", state)
    return {"retryOf": predecessor_id, "executionManifest": manifest, "executionState": state_ref}


def _carrier_execution(root: Path, *, unit: int, carrier: str, retry: bool) -> dict[str, object]:
    sequence = 2 if retry else 1
    execution_id = f"20260829--travel-{carrier}-stable-unit{unit}--cn--full-{sequence:03d}"
    predecessor_id = f"20260829--travel-{carrier}-stable-unit{unit}--cn--full-001" if retry else None
    documents = _task_documents(root, execution_id, carrier, predecessor_id)
    receipts = [write_exact(root, f"data/tasks/{execution_id}/_shared/receipts/{index:03d}-{stage}.json", _receipt(execution_id, stage, index)) for index, stage in enumerate(proof.STAGES, 1)]
    state = _execution_state(execution_id, receipts[-1], status="succeeded", completed=list(proof.STAGES), stage="ship", next_stage="END")
    state_ref = write_exact(root, f"data/tasks/{execution_id}/_shared/execution_state.json", state)
    object_ref = f"travel/place/proof-unit-{unit}" if carrier == "homepage" else f"{carrier}/proof-unit-{unit}/1"
    publish = {"schema": "quwoquan_data.execution_publish_ref", "executionId": execution_id, "canonicalPublishRoot": "canonical-publish", "publishedRefs": {"entities": [object_ref] if carrier == "homepage" else [], "posts": [] if carrier == "homepage" else [object_ref]}}
    publish_ref = write_exact(root, f"data/tasks/{execution_id}/publish_ref.json", publish)
    result_kind = "replayed" if carrier == "video" and unit == 3 else "appended"
    canonical_object = {
        "transactionId": f"transaction-{execution_id}", "applyReportRef": f"apply/{execution_id}.json",
        "canonicalObjectRef": f"entities/proof-unit-{unit}" if carrier == "homepage" else f"posts/{object_ref}",
        "canonicalObjectSha256": canonical_sha256({"objectRef": object_ref}),
        "objectClosureDigest": canonical_sha256({"closure": object_ref}),
        "admissionResult": result_kind,
        "poolRecord": {"recordRef": f"pool/{object_ref}.json", "recordSha256": canonical_sha256({"record": object_ref}), "contentVersion": 1, "recordSequence": 1, "payloadDigest": canonical_sha256({"payload": object_ref})},
    }
    object_result = build_pool_delivery_object_result(execution_id=execution_id, object_ref=object_ref, intent_id=canonical_sha256({"intent": object_ref}), result=result_kind, canonical_object=canonical_object)
    delivery = build_pool_delivery_drain_result(execution_id=execution_id, recovery_mode="host_publish", object_results=[object_result])
    delivery_ref = write_exact(root, f"data/tasks/{execution_id}/pool_delivery_result.json", delivery)
    return {
        "executionId": execution_id, **documents, "stageReceipts": receipts,
        "executionState": state_ref, "canonicalPublish": publish_ref,
        "poolDeliveryResult": delivery_ref,
        "retryRecovery": _retry_recovery(root, predecessor_id) if predecessor_id else None,
    }


def _release(root: Path, *, unit: int, carriers: Mapping[str, Mapping[str, object]]) -> tuple[dict[str, dict[str, str]], str, dict[str, Any]]:
    release_id = f"stable-proof-baseline-{unit}"
    release_root = root / f"data/releases/{release_id}/payload"
    objects_root = release_root / "objects"
    homepage_id = f"unit-{unit}-homepage"
    (objects_root / "entities" / homepage_id).mkdir(parents=True, exist_ok=True)
    (objects_root / "entities" / homepage_id / "entity.json").write_text(json.dumps({"id": homepage_id}), encoding="utf-8")
    contents: list[dict[str, object]] = []
    for carrier in ("article", "image", "video"):
        post_ref = f"{carrier}/unit-{unit}-{carrier}/1"
        path = objects_root / "posts" / post_ref
        path.mkdir(parents=True, exist_ok=True)
        (path / "post.json").write_text(json.dumps({"id": post_ref}), encoding="utf-8")
        contents.append({
            "contentId": f"unit-{unit}-{carrier}", "version": 1, "postRef": post_ref,
            "selectionIdentityDigest": canonical_sha256({"selection": post_ref}),
            "canonicalObjectDigest": canonical_sha256({"canonical": post_ref}),
            "contentLibraryBindingDigest": canonical_sha256({"library": post_ref}),
        })
    execution_ids = [str(carriers[carrier]["executionId"]) for carrier in proof.CARRIERS]
    identities, identity_set_digest = source_identity_set([
        {"executionId": execution_id, "sourceRevision": SOURCE_REVISION, "sourceDigest": SOURCE_DIGEST, "entityCatalogDigest": ENTITY_CATALOG_DIGEST}
        for execution_id in execution_ids
    ])
    canonical_merkle = canonical_sha256({"unit": unit, "kind": "release"})
    plan = build_release_uat_sample_plan(
        release_id=release_id, milestone=None, pool_digest=canonical_sha256({"pool": unit}),
        source_identity_set_digest=identity_set_digest, canonical_merkle=canonical_merkle,
        release_contents=contents, entity_refs=[f"/entity/{homepage_id}"],
        release_objects_root=objects_root, eligible_population_counts=proof.BASELINE_COUNTS,
    )
    plan_ref = write_exact(root, f"data/releases/{release_id}/payload/{PLAN_REF}", plan, canonical=True)
    asset_admission = {"containsUnverifiedAssets": False, "rightsStatusCounts": {"verified": 4, "unverified": 0, "restricted": 0, "unknown": 0}, "authorizationRequiredAssetIds": [], "researchAcceptedCount": 4, "commercialAcceptedCount": 0}
    source_documents = [SourceDefinitionSnapshot(SOURCE_DIGEST).to_document()]
    header = release_header_document(
        release_id=release_id, execution_ids=execution_ids, source_revision=None,
        source_digest=None, entity_catalog_digest=None, source_digest_documents=source_documents,
        asset_admission=asset_admission, canonical_merkle=canonical_merkle,
        release_class="research", product_lifecycle_state="research", reviewed_closure_adoption=None,
        selection_scope="all_publishable", release_mode="research", pool_digest=canonical_sha256({"pool": unit}),
        counts={"article": 1, "image": 1, "video": 1, "total": 3}, contents=contents, authors=[],
        milestone=None, sample_plan_ref=PLAN_REF, sample_plan_digest=exact_document_sha256(plan),
        source_identities=identities, source_identity_set_digest=identity_set_digest,
    )
    desired = release_desired_state_document(release_id=release_id, desired={"entities": [f"entity/{homepage_id}"], "posts": [str(row["postRef"]) for row in contents], "creators": [], "tags": []})
    attestation = release_attestation_document(
        release_id=release_id, execution_ids=execution_ids, source_revision=None,
        source_digest=None, entity_catalog_digest=None, source_digests=(SourceDefinitionSnapshot(SOURCE_DIGEST),),
        asset_admission=asset_admission, canonical_merkle=canonical_merkle,
        entity_count=1, post_count=3, creator_count=0, tag_count=0,
        payload_sha256=canonical_sha256({"payload": release_id}), recorded_at="2026-08-29T08:00:00Z",
        release_class="research", source_identities=tuple(identities), source_identity_set_digest=identity_set_digest,
    )
    return ({
        "header": write_exact(root, f"data/releases/{release_id}/payload/release.json", header),
        "attestation": write_exact(root, f"data/releases/{release_id}/attestations/release.json", attestation),
        "desiredState": write_exact(root, f"data/releases/{release_id}/payload/desired_state.json", desired),
        "samplePlan": plan_ref,
    }, str(plan["releaseDigest"]), plan)


def _ready(root: Path, ref: str, *, environment: str, target: str, release_id: str, release_digest: str, status: str) -> dict[str, str]:
    return write_exact(root, ref, {"environment": environment, "target": target, "deploymentTarget": target, "releaseId": release_id, "releaseDigest": release_digest, "status": status})


def _acceptance(root: Path, *, unit: int, environment: str, release: Mapping[str, str], release_digest: str, plan: Mapping[str, Any]) -> dict[str, str]:
    release_id = str(plan["releaseId"])
    target = f"{environment}-proof-{unit}"
    plan_ref = str(release["ref"])
    plan_digest = str(release["exactByteDigest"])
    runner_identity = str(plan["entryCarrierCells"][0]["runnerClass"])
    binding = build_target_uat_binding(
        runtime_binding={"environment": environment, "target": target, "releaseId": release_id, "manifestDigest": release_digest, "candidateDigest": canonical_sha256({"candidate": unit}), "packageDigest": canonical_sha256({"package": unit}), "runtimeConfigDigest": canonical_sha256({"runtime": unit}), "environmentRuntimeDigest": canonical_sha256({"environment": unit}), "startupIdentity": {"configurationDigest": canonical_sha256({"config": unit})}},
        launch_binding={"environment": environment, "target": target, "platform": "android", "deviceId": f"physical-{unit}", "artifactDigest": canonical_sha256({"artifact": unit}), "applicationId": "com.quwoquan.proof"},
        sample_plan_binding={"releaseId": release_id, "releaseUatSamplePlanRef": plan_ref, "releaseUatSamplePlanDigest": plan_digest},
        active_cas={"ref": f"env/{unit}/active.json", "digest": canonical_sha256({"active": unit})},
        readback={"ref": f"env/{unit}/readback.json", "digest": canonical_sha256({"readback": unit})},
        artifact_class="production_behavior", build_mode="release", build_profile="nonprod",
        provider={"identity": "first-party-https", "class": "first_party", "type": "https", "registered": True, "conformanceEvidence": {"ref": f"env/{unit}/provider.json", "digest": canonical_sha256({"provider": unit})}},
        device={"identity": f"physical-{unit}", "class": "physical", "registered": True},
        runner={"identity": runner_identity, "sourcePath": "quwoquan_app/test/user_acceptance/stable_production_uat.dart", "digest": canonical_sha256({"runner": unit}), "registered": True},
        profile="promotable", non_promotable=False, created_at="2026-08-29T09:00:00Z",
    )
    binding_ref = write_exact(root, f"env/{unit}/target-binding.json", binding)
    raw_results: list[dict[str, str]] = []
    sample_by_carrier = {str(row["carrier"]): row for row in plan["samples"]}
    for entry in ENTRIES:
        for carrier in proof.CARRIERS:
            sample = sample_by_carrier[carrier]
            cell = next(row for row in plan["entryCarrierCells"] if row["entry"] == entry and row["carrier"] == carrier)
            raw = {
                "environment": environment, "target": target, "deploymentTarget": target,
                "releaseId": release_id, "releaseDigest": release_digest,
                "producer": "app", "layer": "user_acceptance", "status": "passed",
                "caseId": sample["sampleId"], "objectId": sample["objectId"],
                "targetUatBindingDigest": binding_ref["exactByteDigest"],
                "entrySurface": entry, "carrier": carrier, "specRef": cell["specRef"],
                "runnerIdentity": cell["runnerClass"], "platform": "android",
                "provider": binding["provider"]["identity"], "uatProfile": "promotable",
            }
            raw_ref = write_exact(root, f"env/{unit}/raw-{entry}-{carrier}.json", raw)
            raw_results.append({"ref": raw_ref["ref"], "digest": raw_ref["exactByteDigest"], "slotId": required_raw_slot_id(target_uat_binding_digest=binding_ref["exactByteDigest"], sample_id=str(sample["sampleId"]), entry_surface=entry, carrier=carrier, spec_ref=str(cell["specRef"]), runner_identity=str(cell["runnerClass"])), "status": "passed"})
    active = _ready(root, f"env/{unit}/active.json", environment=environment, target=target, release_id=release_id, release_digest=release_digest, status="active")
    readback = _ready(root, f"env/{unit}/readback.json", environment=environment, target=target, release_id=release_id, release_digest=release_digest, status="passed")
    import_report = _ready(root, f"env/{unit}/import.json", environment=environment, target=target, release_id=release_id, release_digest=release_digest, status="imported")
    data_readiness = write_exact(root, f"env/{unit}/data-readiness.json", {"environment": environment, "target": target, "deploymentTarget": target, "releaseId": release_id, "releaseDigest": release_digest, "status": "passed", "activationEnvelope": {"importReportRef": import_report["ref"], "importReportDigest": import_report["exactByteDigest"]}})
    def evidence(name: str, status: str) -> dict[str, str]:
        return _ready(root, f"env/{unit}/{name}.json", environment=environment, target=target, release_id=release_id, release_digest=release_digest, status=status)
    lifecycle = evidence("lifecycle", "Exit")
    provider_readiness = evidence("provider-readiness", "ready")
    observability_readiness = evidence("observability-readiness", "ready")
    rollback_readiness = evidence("rollback-readiness", "ready")
    lease_revocation = evidence("lease-revocation", "revoked")
    lock_release = evidence("lock-release", "released")
    gc_protection = evidence("gc-protection", "protected")
    fact = build_environment_acceptance_fact(
        evidence_root=root, environment=environment, target=target, release_id=release_id,
        release_digest=release_digest, sample_plan_ref=plan_ref, sample_plan_digest=plan_digest,
        target_binding_refs=[{"ref": binding_ref["ref"], "digest": binding_ref["exactByteDigest"], "platform": "android", "deviceProfile": "promotable"}],
        required_raw_results=raw_results, required_target_profiles=[{"platform": "android", "deviceProfile": "promotable"}],
        data_readiness={"ref": data_readiness["ref"], "digest": data_readiness["exactByteDigest"]},
        active_cas={"ref": active["ref"], "digest": active["exactByteDigest"], "readbackRef": readback["ref"], "readbackDigest": readback["exactByteDigest"], "releaseId": release_id, "releaseDigest": release_digest},
        lifecycle_exit={"ref": lifecycle["ref"], "digest": lifecycle["exactByteDigest"]},
        provider_readiness={"ref": provider_readiness["ref"], "digest": provider_readiness["exactByteDigest"]},
        observability_readiness={"ref": observability_readiness["ref"], "digest": observability_readiness["exactByteDigest"]},
        rollback_readiness={"ref": rollback_readiness["ref"], "digest": rollback_readiness["exactByteDigest"]},
        predecessor_acceptance=None,
        resource_finalization={"leaseRevocationRefs": [{"ref": lease_revocation["ref"], "digest": lease_revocation["exactByteDigest"]}], "lockReleaseRefs": [{"ref": lock_release["ref"], "digest": lock_release["exactByteDigest"]}], "gcProtectionRefs": [{"ref": gc_protection["ref"], "digest": gc_protection["exactByteDigest"]}]},
        prod_release_facts=None, created_at="2026-08-29T09:30:00Z", source_fingerprint=FINGERPRINT,
    )
    return write_exact(root, f"env/{unit}/environment-acceptance.json", fact)


def build_proof_fixture(root: Path) -> dict[str, object]:
    units: list[dict[str, object]] = []
    for unit in range(1, 4):
        carriers = {carrier: _carrier_execution(root, unit=unit, carrier=carrier, retry=(unit == 3 and carrier == "video")) for carrier in proof.CARRIERS}
        release, release_digest, plan = _release(root, unit=unit, carriers=carriers)
        environment = "alpha"
        acceptance = _acceptance(root, unit=unit, environment=environment, release=release["samplePlan"], release_digest=release_digest, plan=plan)
        units.append({"unitId": f"proof-unit-{unit}", "fingerprint": FINGERPRINT, "carrierExecutions": carriers, "release": release, "environment": environment, "environmentAcceptanceFact": acceptance})
    return {"schema": "quwoquan_data.stable_production_proof_request", "artifactRoot": str(root), "fingerprint": FINGERPRINT, "proofUnits": units}


def clone_request(value: Mapping[str, object]) -> dict[str, object]:
    return deepcopy(dict(value))
