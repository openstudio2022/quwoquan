"""Canonical one-unit stable-production-proof fixture for local contracts."""
from __future__ import annotations

import hashlib
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
from content.execution import stage_authority, stage_semantic_recorder
from content.execution.operational_fingerprint import operational_fingerprint
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
from content.release.canonical.content_pool_record import pool_payload_digest
from content.release.canonical.object_source_identity import source_identity_digest, source_identity_set
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
from core import paths
from core.tree_integrity import tree_integrity_stats
from core.stage_artifact_contract import required_stage_artifacts
from quwoquan_ops.cli.lib.environment_acceptance_fact import (
    build_environment_acceptance_fact,
    required_raw_slot_id,
)

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
        "sourceDigest": source, "executionBundle": bundle,
        "operationalFingerprint": FINGERPRINT, "hostRuntime": "external_host_agent",
        "carrierDemand": {"ref": demand_ref["ref"], "digest": demand_ref["exactByteDigest"], "workRequestRef": work_request_ref, "workRequestDigest": work_request_digest},
        "requestRef": "0.plan/request.json", "targetSetRef": "0.plan/target_set.json",
        "targetSetDigest": hashlib.sha256(
            json.dumps(
                target_set, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest(),
        "retryOf": retry_of,
    }
    manifest_ref = write_exact(root, f"{base}/execution_manifest.json", manifest)
    return {"carrierDemand": demand_ref, "candidateBindings": candidate_ref, "taskInitRequest": request_ref, "executionManifest": manifest_ref, "targetSet": target_ref}


def _source_attribution() -> dict[str, object]:
    return {
        "isOriginal": False,
        "originalCreatorName": "fixture source author",
        "platform": "fixture-source",
        "sourcePostUrl": "https://fixture.example/post",
        "originalAssetUrl": "https://fixture.example/asset",
        "attributionText": "fixture source author / fixture-source",
        "rightsBasis": "public research reference",
        "commercialAuthorizationStatus": "unverified",
        "publicationAdmission": "research_release",
        "watermarkStatus": "absent",
        "audioRightsStatus": "no_audio",
        "modelReleaseStatus": "not_required",
        "propertyReleaseStatus": "not_required",
        "collectedAt": "2026-08-29T07:00:00Z",
        "takedownPolicy": "remove on substantiated request",
        "derivedModifications": [],
    }


def _carrier_execution(root: Path, *, unit: int, carrier: str) -> dict[str, object]:
    execution_id = f"20260829--travel-{carrier}-stable-unit{unit}--cn--full-001"
    documents = _task_documents(root, execution_id, carrier, None)
    published_target = f"travel/place/unit-{unit}-homepage" if carrier == "homepage" else f"{carrier}/unit-{unit}-{carrier}/1"
    canonical_ref = f"entities/{published_target}" if carrier == "homepage" else f"posts/{published_target}"
    publish = {"schema": "quwoquan_data.execution_publish_ref", "executionId": execution_id, "canonicalPublishRoot": "canonical-publish", "publishedRefs": {"entities": [published_target] if carrier == "homepage" else [], "posts": [] if carrier == "homepage" else [published_target]}}
    publish_ref = write_exact(root, f"data/tasks/{execution_id}/publish_ref.json", publish)
    result_kind = "replayed" if carrier == "video" else "appended"
    transaction_id = f"transaction-{execution_id}"
    closure_digest = canonical_sha256({"closure": published_target})
    object_kind = "entities" if carrier == "homepage" else "posts"
    object_schema = "quwoquan_data.entity_object" if carrier == "homepage" else "quwoquan_data.post_object"
    package = {
        "schema": "quwoquan_data.object_transaction_package",
        "transactionId": transaction_id,
        "executionId": execution_id,
        "publishMediaMode": "not_applicable" if carrier == "homepage" else "text_only",
        "sourcePolicyRevision": "encyclopedia-primary" if carrier == "homepage" else "rights-cleared-content",
        "target": {"layoutSchema": "quwoquan_data.canonical_publish", "objectKind": object_kind, "objectRef": published_target, "objectSchema": object_schema, "packageObjectRef": "object"},
        "closure": {"creatorRefs": [], "tagRefs": [], "sourceCatalogRef": "source_catalog.json", "rightsRef": "rights.json", "casRefs": ([{"sourceRef": "cas/a.bin", "objectKey": "media/objects/sha256/aa/aa/" + "a" * 64 + ".bin", "sha256": "sha256:" + "a" * 64, "bytes": 1}] if carrier == "homepage" else [])},
        "review": {"attestationRef": "attestation.json", "evidenceIndexRef": "evidence_index.json"},
        "objectClosureDigest": closure_digest,
    }
    package_ref = write_exact(root, f"data/tasks/{execution_id}/evidence/object-transactions/{transaction_id}/object_transaction_package.json", package)
    apply_ref_name = f"data/local/workspace/object-transactions/{transaction_id}/apply_report.json"
    apply_report = {
        "schema": "quwoquan_data.object_transaction_apply", "transactionId": transaction_id,
        "executionId": execution_id, "status": "applied", "objectKind": object_kind,
        "objectRef": published_target, "objectClosureDigest": closure_digest,
    }
    apply_ref = write_exact(root, apply_ref_name, apply_report)
    object_root = root / "canonical-publish" / canonical_ref
    object_root.mkdir(parents=True, exist_ok=True)
    evidence = {"schema": "quwoquan_data.review_attestation", "decision": "approved"}
    evidence_ref = write_exact(root, f"canonical-publish/{canonical_ref}/attestation.json", evidence)
    identity: dict[str, object] = {
        "executionId": execution_id, "sourceRevision": SOURCE_REVISION,
        "sourceDigest": SOURCE_DIGEST, "entityCatalogDigest": ENTITY_CATALOG_DIGEST,
    }
    identity["identityDigest"] = source_identity_digest(identity)
    manifest = {
        "schema": object_schema,
        ("entityId" if carrier == "homepage" else "contentId"): f"proof-{carrier}-{unit}",
        "version": 1, "executionId": execution_id,
        "sourceDigest": SourceDefinitionSnapshot(SOURCE_DIGEST).to_document(),
        "sourceIdentity": identity, "sourceAttribution": _source_attribution(),
        "status": "active", "admission": {"processResult": "completed", "qualityResult": "passed", "usageScope": "research", "evidenceRef": "attestation.json", "evidenceDigest": evidence_ref["exactByteDigest"]},
    }
    write_exact(root, f"canonical-publish/{canonical_ref}/manifest.json", manifest)
    write_exact(root, f"canonical-publish/{canonical_ref}/content.json", {"carrier": carrier, "unit": unit})
    payload_digest = pool_payload_digest(object_root)
    pool_record = {
        "schema": "quwoquan_data.pool_object_record", "objectType": "homepage" if carrier == "homepage" else "content",
        "objectId": f"proof-{carrier}-{unit}", "objectRef": published_target,
        "recordSequence": 1, "contentVersion": 1, "status": "active",
        "processResult": "completed", "qualityResult": "passed", "eligibilityResult": "passed",
        "usageScope": "research", "evidenceRef": "attestation.json", "evidenceDigest": evidence_ref["exactByteDigest"],
        "payloadDigest": payload_digest, "canonicalObjectDigest": payload_digest,
        "sourceIdentity": identity, "sourceAttribution": _source_attribution(),
    }
    pool_ref_name = f"canonical-publish/{canonical_ref}/_pool/versions/1.json"
    pool_ref = write_exact(root, pool_ref_name, pool_record)
    canonical_object = {
        "transactionId": transaction_id, "applyReportRef": apply_ref_name,
        "canonicalObjectRef": canonical_ref,
        "canonicalObjectSha256": tree_integrity_stats(object_root)["merkleRoot"],
        "objectClosureDigest": closure_digest, "admissionResult": result_kind,
        "poolRecord": {"recordRef": f"{canonical_ref}/_pool/versions/1.json", "recordSha256": pool_ref["exactByteDigest"], "contentVersion": 1, "recordSequence": 1, "payloadDigest": payload_digest},
    }
    object_result = build_pool_delivery_object_result(execution_id=execution_id, object_ref=published_target, intent_id=canonical_sha256({"intent": published_target}), result=result_kind, canonical_object=canonical_object)
    delivery = build_pool_delivery_drain_result(execution_id=execution_id, recovery_mode="host_publish", object_results=[object_result])
    delivery_ref = write_exact(root, f"data/tasks/{execution_id}/pool_delivery_result.json", delivery)
    return {
        "executionId": execution_id, **documents, "stageReceipts": [],
        "executionState": {}, "canonicalPublish": publish_ref,
        "poolDeliveryResult": delivery_ref, "objectTransactionPackage": package_ref,
        "applyReport": apply_ref, "poolRecord": pool_ref,
    }


def _release(root: Path, *, unit: int, carriers: Mapping[str, Mapping[str, object]]) -> tuple[dict[str, dict[str, str]], str, dict[str, Any]]:
    release_id = f"stable-proof-baseline-{unit}"
    release_root = root / f"data/releases/{release_id}/payload"
    objects_root = release_root / "objects"
    homepage_id = f"travel/place/unit-{unit}-homepage"
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
    desired = release_desired_state_document(release_id=release_id, desired={"entities": [homepage_id], "posts": [str(row["postRef"]) for row in contents], "creators": [], "tags": []})
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


def _ready(
    root: Path, ref: str, *, environment: str, target: str, release_id: str,
    release_digest: str, import_run_id: str, verify_run_id: str, status: str,
) -> dict[str, str]:
    return write_exact(root, ref, {
        "environment": environment, "target": target, "deploymentTarget": target,
        "releaseId": release_id, "releaseDigest": release_digest,
        "importRunId": import_run_id, "verifyRunId": verify_run_id, "status": status,
    })


def _m1_api_acceptance(
    root: Path, *, unit: int, release: Mapping[str, str],
    release_digest: str, plan: Mapping[str, Any],
) -> dict[str, str]:
    environment = "alpha"
    target = "alpha-local"
    release_id = str(plan["releaseId"])
    import_run_id = f"m1-import-run-{unit}"
    verify_run_id = f"m1-verify-run-{unit}"
    sample_by_carrier = {str(row["carrier"]): row for row in plan["samples"]}
    raw_results: list[dict[str, str]] = []
    for cell in plan["entryCarrierCells"]:
        entry = str(cell["entry"])
        carrier = str(cell["carrier"])
        sample = sample_by_carrier[carrier]
        raw = {
            "environment": environment, "target": target, "deploymentTarget": target,
            "releaseId": release_id, "releaseDigest": release_digest,
            "importRunId": import_run_id, "verifyRunId": verify_run_id,
            "producer": "service", "layer": "api_integration", "status": "passed",
            "entrySurface": entry, "carrier": carrier,
            "specRef": cell["specRef"], "runnerIdentity": cell["runnerClass"],
            "objectId": sample["objectId"],
        }
        raw_ref = write_exact(root, f"env/{unit}/m1-api-{entry}-{carrier}.json", raw)
        raw_results.append({
            "ref": raw_ref["ref"], "digest": raw_ref["exactByteDigest"],
            "slotId": required_raw_slot_id(
                sample_id=str(sample["sampleId"]), entry_surface=entry,
                carrier=carrier, spec_ref=str(cell["specRef"]),
                runner_identity=str(cell["runnerClass"]),
            ),
            "status": "passed",
        })
    def ready(name: str, status: str) -> dict[str, str]:
        return _ready(
            root, f"env/{unit}/m1-{name}.json", environment=environment,
            target=target, release_id=release_id, release_digest=release_digest,
            import_run_id=import_run_id, verify_run_id=verify_run_id, status=status,
        )
    active = ready("active", "active")
    readback = ready("readback", "passed")
    import_report = ready("import", "imported")
    data_readiness = write_exact(root, f"env/{unit}/m1-data-readiness.json", {
        "environment": environment, "target": target, "deploymentTarget": target,
        "releaseId": release_id, "releaseDigest": release_digest,
        "importRunId": import_run_id, "verifyRunId": verify_run_id,
        "status": "passed", "activationEnvelope": {
            "importReportRef": import_report["ref"],
            "importReportDigest": import_report["exactByteDigest"],
        },
    })
    lifecycle = ready("lifecycle", "Exit")
    provider = ready("provider-readiness", "ready")
    observability = ready("observability-readiness", "ready")
    rollback = ready("rollback-readiness", "ready")
    lease = ready("lease-revocation", "revoked")
    lock = ready("lock-release", "released")
    gc = ready("gc-protection", "protected")
    fact = build_environment_acceptance_fact(
        evidence_root=root, acceptance_profile="m1_api_consumer",
        environment=environment, target=target, release_id=release_id,
        release_digest=release_digest, import_run_id=import_run_id,
        verify_run_id=verify_run_id, sample_plan_ref=str(release["ref"]),
        sample_plan_digest=str(release["exactByteDigest"]), target_binding_refs=[],
        required_raw_results=raw_results, required_target_profiles=[],
        data_readiness={"ref": data_readiness["ref"], "digest": data_readiness["exactByteDigest"]},
        active_cas={
            "ref": active["ref"], "digest": active["exactByteDigest"],
            "readbackRef": readback["ref"], "readbackDigest": readback["exactByteDigest"],
            "releaseId": release_id, "releaseDigest": release_digest,
        },
        lifecycle_exit={"ref": lifecycle["ref"], "digest": lifecycle["exactByteDigest"]},
        provider_readiness={"ref": provider["ref"], "digest": provider["exactByteDigest"]},
        observability_readiness={"ref": observability["ref"], "digest": observability["exactByteDigest"]},
        rollback_readiness={"ref": rollback["ref"], "digest": rollback["exactByteDigest"]},
        predecessor_acceptance=None,
        resource_finalization={
            "leaseRevocationRefs": [{"ref": lease["ref"], "digest": lease["exactByteDigest"]}],
            "lockReleaseRefs": [{"ref": lock["ref"], "digest": lock["exactByteDigest"]}],
            "gcProtectionRefs": [{"ref": gc["ref"], "digest": gc["exactByteDigest"]}],
        },
        prod_release_facts=None, created_at="2026-08-29T09:35:00Z",
        source_fingerprint=FINGERPRINT,
    )
    return write_exact(root, f"env/{unit}/m1-environment-acceptance.json", fact)


def _write_stage_semantic_outputs(root: Path, execution_id: str, carrier: str, stage: str) -> list[str]:
    execution_root = root / f"data/tasks/{execution_id}"
    object_root = execution_root / f"posts/{carrier}/proof/proof/1"
    if carrier == "homepage":
        object_root = execution_root / "entities/travel/place/proof/1"
    if stage == "sources":
        unit = execution_root / "sources/source-001"
        values: dict[str, object] = {
            "meta.json": {
                "schema": "quwoquan_data.source_unit", "stage": "1.download",
                "executionId": execution_id, "executionBinding": "frozen",
                "sourceUnitId": "source-001", "entityName": "proof", "title": "proof",
                "sourceKind": "wikipedia", "extractor": "wikipedia_api",
                "canonicalUrl": "https://zh.wikipedia.org/wiki/proof",
                "finalUrl": "https://zh.wikipedia.org/wiki/proof",
                "fetchedAt": "2026-08-29T07:00:00Z",
                "rawSha256": canonical_sha256({"raw": execution_id}),
                "cleanSha256": canonical_sha256({"clean": execution_id}),
                "policyRevision": "encyclopedia-primary",
                "sourceUseMode": "factual_reference_only",
                "rightsMode": "factual_reference_only",
            },
            "source.md": "source\n", "source.clean.md": "source\n",
            "source.layout.json": {}, "source.quality.json": {}, "assets/index.json": {},
        }
        refs: list[str] = []
        for name, value in values.items():
            path = unit / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                (json.dumps(value, ensure_ascii=False) + "\n") if isinstance(value, dict) else str(value),
                encoding="utf-8",
            )
            refs.append(path.relative_to(execution_root).as_posix())
        return sorted(refs)
    if stage == "2.quality":
        value = {
            "schema": "quwoquan_data.quality_analysis", "stage": stage,
            "executionId": execution_id, "executionBinding": "frozen",
            "sourcePolicyRevision": "encyclopedia-primary",
            "sourceRevision": canonical_sha256({"source": execution_id}),
            "recommendation": "proceed", "sourcePaths": ["sources/source-001/source.clean.md"],
            "sourceAdmissions": [{"sourceRef": "sources/source-001", "decision": "selected", "evidenceHash": canonical_sha256({"evidence": execution_id})}],
            "rejectionReasons": [], "evidenceHashes": [canonical_sha256({"evidence": execution_id})],
        }
        path = object_root / "2.quality/quality_analysis.json"
    elif stage == "3.compose":
        if carrier == "homepage":
            value = {
                "schema": "quwoquan_data.stage_envelope", "stage": stage,
                "executionId": execution_id, "executionBinding": "frozen",
                "sourcePolicyRevision": "encyclopedia-primary",
                "sourceRevision": canonical_sha256({"source": execution_id}),
                "promptBundleRevision": canonical_sha256({"prompt": execution_id}),
                "step": "entity_page", "ref": "proof-homepage",
                "selectedSourceUrls": ["https://zh.wikipedia.org/wiki/proof"],
                "payload": {"name": "proof", "entityRef": "travel/place/proof", "baseDraft": {}, "draftPage": "4.draft/page.md", "minChars": 1, "minSectionChars": 1},
            }
            path = object_root / "3.compose/entity_page_input.json"
        else:
            value = {
                "schema": "quwoquan_data.writing_pack", "stage": stage,
                "executionId": execution_id, "executionBinding": "frozen",
                "sourcePolicyRevision": "encyclopedia-primary",
                "sourceRevision": canonical_sha256({"source": execution_id}),
                "promptBundleRevision": canonical_sha256({"prompt": execution_id}),
                "selectedSourceUrls": ["https://zh.wikipedia.org/wiki/proof"],
                "ref": f"proof-{carrier}", "kind": carrier, "title": "proof", "carrier": carrier,
            }
            path = object_root / "3.compose/writing_pack.json"
    elif stage == "4.draft":
        draft_dir = object_root / "4.draft"
        draft_dir.mkdir(parents=True, exist_ok=True)
        authored_name = "page.md" if carrier == "homepage" else ("draft.article.md" if carrier == "article" else "draft_meta.json")
        authored = draft_dir / authored_name
        if not authored.exists():
            authored.write_text("proof draft\n" if authored.suffix == ".md" else "{}\n", encoding="utf-8")
        value = {
            "schema": "quwoquan.agent_result_envelope", "executionId": execution_id,
            "jobId": "stable-proof-author", "ref": f"proof-{carrier}", "stage": stage,
            "agent": {"provider": "cursor", "model": "gpt", "runId": f"{execution_id}-4.draft-run", "promptSha256": canonical_sha256({"prompt": execution_id})},
            "files": [{"path": authored.name, "sha256": proof.exact_byte_digest(authored)}],
            "gates": [{"schema": "quwoquan.gate_verdict", "gateId": "draft", "decision": "passed", "final": True, "inputHash": canonical_sha256({"input": execution_id}), "outputHash": proof.exact_byte_digest(authored)}],
        }
        path = draft_dir / "agent_result_envelope.json"
    else:
        review_dir = object_root / "5.review"
        review_dir.mkdir(parents=True, exist_ok=True)
        reviewer = {
            "schema": "quwoquan_data.reviewer_result", "stage": stage,
            "executionId": execution_id, "executionBinding": "frozen", "objectRef": f"proof-{carrier}",
            "provider": "cursor", "model": "claude", "modelFamily": "claude",
            "runId": f"{execution_id}-5.review-run", "verdict": "passed", "issues": [],
            "resultHash": canonical_sha256({"review": execution_id}),
        }
        rubric = {
            "schema": "quwoquan_data.rubric_review", "ref": f"proof-{carrier}",
            "generationModelFamily": "gpt",
            "judges": [{"modelId": "claude", "modelFamily": "claude", "promptHash": canonical_sha256({"rubric": execution_id}), "temperature": 0}],
            "biasControls": {"positionSwapApplied": True, "lengthControlApplied": True},
            "dimensions": [{"name": "professionalism", "scores": [9, 9], "verdict": "pass", "rationale": "pass"}],
            "decision": "approved",
        }
        refs = []
        for name, value in (("reviewer_result.json", reviewer), ("rubric_review.json", rubric)):
            target = review_dir / name
            target.write_text(json.dumps(value, ensure_ascii=False) + "\n", encoding="utf-8")
            refs.append(target.relative_to(execution_root).as_posix())
        return sorted(refs)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False) + "\n", encoding="utf-8")
    return [path.relative_to(execution_root).as_posix()]


def _ensure_stage_artifacts(root: Path, execution_id: str, carrier: str, stage: str) -> list[dict[str, str]]:
    execution_root = root / f"data/tasks/{execution_id}"
    object_root = execution_root / ("entities/travel/place/proof/1" if carrier == "homepage" else f"posts/{carrier}/proof/proof/1")
    refs: list[dict[str, str]] = []
    for name in required_stage_artifacts(carrier).get(stage, ()):
        path = object_root / stage / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text("proof\n" if path.suffix == ".md" else "{}\n", encoding="utf-8")
        refs.append({"scope": "execution", "ref": path.relative_to(execution_root).as_posix()})
    return refs


def _complete_authority(
    root: Path, execution: dict[str, object], *, carrier: str,
    release_id: str, release_digest: str, acceptance: Mapping[str, str],
) -> None:
    execution_id = str(execution["executionId"])
    acceptance_document = json.loads(
        (root / str(acceptance["ref"])).read_text(encoding="utf-8")
    )
    receipts: list[dict[str, str]] = []
    for stage in proof.STAGES:
        stage_authority.open_stage(execution_id, stage)
        context: dict[str, object] = {"artifactRefs": []}
        actor_family = "gpt"
        if stage in stage_semantic_recorder.SEMANTIC_STAGES:
            if stage == "4.draft":
                draft_dir = root / f"data/tasks/{execution_id}" / ("entities/travel/place/proof/1/4.draft" if carrier == "homepage" else f"posts/{carrier}/proof/proof/1/4.draft")
                draft_dir.mkdir(parents=True, exist_ok=True)
                for name in ("prompt.md", "prompt_snapshot.json", "author_job_packet.json"):
                    path = draft_dir / name
                    if not path.exists():
                        path.write_text("prompt\n" if path.suffix == ".md" else "{}\n", encoding="utf-8")
            if stage in {"2.quality", "3.compose", "4.draft", "5.review"}:
                previous = "1.download" if stage == "2.quality" else None
                if previous:
                    _ensure_stage_artifacts(root, execution_id, carrier, previous)
            refs = _write_stage_semantic_outputs(root, execution_id, carrier, stage)
            request_path = stage_semantic_recorder.prepare_stage_semantic_request(execution_id, stage)
            request = json.loads(request_path.read_text(encoding="utf-8"))
            actor_family = "claude" if stage == "5.review" else "gpt"
            result = stage_semantic_recorder.record_stage_semantic_result(execution_id, stage, {
                "schema": "quwoquan_data.stage_semantic_result_input",
                "requestRef": request_path.relative_to(root / f"data/tasks/{execution_id}").as_posix(),
                "requestDigest": request["requestDigest"],
                "actor": {
                    "host": "cursor", "modelFamily": actor_family,
                    "sessionId": f"{execution_id}-{stage}-session",
                    "invocation": {"provider": "cursor", "model": actor_family, "runId": f"{execution_id}-{stage}-run"},
                },
                "resultRefs": refs,
            })
            context.update({
                "semanticResultRef": result.relative_to(root / f"data/tasks/{execution_id}").as_posix(),
                "semanticResultDigest": proof.exact_byte_digest(result),
            })
        if stage in {"1.download", "2.quality", "3.compose", "4.draft", "5.review"}:
            context["artifactRefs"] = _ensure_stage_artifacts(root, execution_id, carrier, stage)
        elif stage == "publish":
            context["artifactRefs"] = [{"scope": "execution", "ref": "publish_ref.json"}]
        elif stage == "release":
            context.update({
                "releaseId": release_id, "releaseDigest": release_digest,
                "releaseClass": "research",
                "artifactRefs": [{"scope": "output", "ref": f"data/releases/{release_id}/payload/release.json"}],
            })
        elif stage == "ship":
            context.update({
                "releaseId": release_id, "releaseDigest": release_digest,
                "environment": "alpha",
                "importRunId": acceptance_document["importRunId"],
                "verifyRunId": acceptance_document["verifyRunId"],
                "readinessPhase": "research", "target": "alpha-local",
                "acceptanceProfile": "m1_api_consumer",
                "requiredTargetProfiles": [],
                "environmentAcceptanceFactRef": acceptance["ref"],
                "environmentAcceptanceFactDigest": acceptance["exactByteDigest"],
                "artifactRefs": [{"scope": "output", "ref": acceptance["ref"]}],
            })
        gate = stage_authority.run_stage_gate(
            execution_id, stage, close_context=context,
            runner=lambda _argv: type("Result", (), {"returncode": 0, "stdout": "fixture pass", "stderr": ""})(),
        )
        receipt = stage_authority.close_stage(execution_id, stage)
        receipts.append({
            "ref": receipt.relative_to(root).as_posix(),
            "exactByteDigest": proof.exact_byte_digest(receipt),
        })
    execution["stageReceipts"] = receipts
    state = root / f"data/tasks/{execution_id}/_shared/execution_state.json"
    execution["executionState"] = {
        "ref": state.relative_to(root).as_posix(),
        "exactByteDigest": proof.exact_byte_digest(state),
    }


def _operational_receipts(root: Path) -> tuple[dict[str, str], dict[str, str]]:
    output = {"stdoutDigest": canonical_sha256({"stdout": "pass"}), "stderrDigest": canonical_sha256({"stderr": ""})}
    verify = write_exact(root, "operational/verify-all.json", {
        "schema": "quwoquan_data.verify_all_receipt", "sourceFingerprint": FINGERPRINT,
        "command": {"commandId": "data.verify.all", "entrypoint": "quwoquan_data/scripts/cli.py", "arguments": ["verify", "all"]},
        "exitCode": 0, "verdict": "pass", "capturedOutput": output,
        "closedModules": ["cli-first", "data-layout", "reusable-data-contract"],
    })
    loaded = ["cli", "governance", "governance.stable_production_proof"]
    probe_digest = canonical_sha256({"probe": "fixture-public-cli-live-import-zero"})
    loaded_modules_digest = exact_document_sha256({"loadedModules": loaded})
    receipt_id = exact_document_sha256({
        "sourceFingerprint": FINGERPRINT,
        "probeDigest": probe_digest,
        "checkedCommands": ["task", "source-pool", "filter-catalog", "release", "ship", "template", "governance", "verify"],
        "forbiddenPrefixes": list(proof._FORBIDDEN_LIVE_PREFIXES),
        "loadedModulesDigest": loaded_modules_digest,
    })
    discovered_commands = {
        "filter-catalog": ["content.filter_catalog.handler"],
        "governance": ["governance.handler"],
        "release": ["content.release.canonical.handler"],
        "ship": ["content.release.environment.cli"],
        "source-pool": ["content.source.research.handler_cli"],
        "task": ["content.execution.handler"],
        "template": ["content.templates.handler"],
        "verify": ["verify.handler"],
    }
    imported_modules = sorted({
        module for modules in discovered_commands.values() for module in modules
    })
    live = write_exact(root, "operational/public-cli-live-import-zero.json", {
        "schema": "quwoquan_data.public_cli_live_import_zero_receipt", "sourceFingerprint": FINGERPRINT,
        "command": {"commandId": "data.public_cli.live_import_zero", "entrypoint": "quwoquan_data/scripts/cli.py", "arguments": ["governance", "public-cli-live-import-zero"]},
        "exitCode": 0, "verdict": "pass", "capturedOutput": output,
        "probeDigest": probe_digest,
        "checkedCommands": ["task", "source-pool", "filter-catalog", "release", "ship", "template", "governance", "verify"],
        "discoveredCommands": discovered_commands,
        "forbiddenPrefixes": list(proof._FORBIDDEN_LIVE_PREFIXES),
        "importedModules": imported_modules,
        "loadedModules": loaded,
        "loadedModulesDigest": loaded_modules_digest,
        "receiptId": receipt_id,
        "forbiddenLoadedModules": [],
    })
    return verify, live


def build_proof_fixture(root: Path) -> dict[str, object]:
    global FINGERPRINT
    unit = 1
    root = root.resolve()
    FINGERPRINT = operational_fingerprint()
    carriers = {carrier: _carrier_execution(root, unit=unit, carrier=carrier) for carrier in proof.CARRIERS}
    release, release_digest, plan = _release(root, unit=unit, carriers=carriers)
    acceptance = _m1_api_acceptance(
        root, unit=unit, release=release["samplePlan"], release_digest=release_digest, plan=plan,
    )
    original = (paths.OUTPUT_ROOT, paths.DATA_EXECUTIONS_ROOT, paths.RELEASE_ROOT)
    original_artifacts = stage_authority._artifact_bindings
    original_authority_fingerprint = stage_authority.operational_fingerprint
    original_semantic_fingerprint = stage_semantic_recorder.operational_fingerprint
    try:
        paths.OUTPUT_ROOT = root
        paths.DATA_EXECUTIONS_ROOT = root / "data/tasks"
        paths.RELEASE_ROOT = root / "data/releases"
        stage_authority.operational_fingerprint = lambda **_kwargs: FINGERPRINT
        stage_semantic_recorder.operational_fingerprint = lambda **_kwargs: FINGERPRINT
        def fixture_artifacts(execution_id: str, stage: str, refs):
            if stage not in {"release", "ship"}:
                return original_artifacts(execution_id, stage, refs)
            execution_root = root / f"data/tasks/{execution_id}"
            bindings = []
            for index, item in enumerate(refs):
                source = root / str(item["ref"])
                target = execution_root / f"_shared/authority-artifacts/{stage}/{index}.json"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())
                bindings.append(
                    stage_authority._binding(
                        target, scope="execution", root=execution_root
                    )
                )
            return bindings
        stage_authority._artifact_bindings = fixture_artifacts
        for carrier in proof.CARRIERS:
            _complete_authority(
                root, carriers[carrier], carrier=carrier, release_id=str(plan["releaseId"]),
                release_digest=release_digest, acceptance=acceptance,
            )
    finally:
        stage_authority._artifact_bindings = original_artifacts
        stage_authority.operational_fingerprint = original_authority_fingerprint
        stage_semantic_recorder.operational_fingerprint = original_semantic_fingerprint
        paths.OUTPUT_ROOT, paths.DATA_EXECUTIONS_ROOT, paths.RELEASE_ROOT = original
    verify, live = _operational_receipts(root)
    unit_value = {
        "unitId": "proof-unit-1", "fingerprint": FINGERPRINT,
        "evidenceAuthority": "test_only",
        "carrierExecutions": carriers, "release": release, "environment": "alpha",
        "environmentAcceptanceFact": acceptance,
    }
    return {
        "schema": "quwoquan_data.stable_production_proof_request",
        "artifactRoot": str(root), "fingerprint": FINGERPRINT,
        "verifyAllReceipt": verify, "publicCliLiveImportZeroReceipt": live,
        "proofUnits": [unit_value],
    }

def clone_request(value: Mapping[str, object]) -> dict[str, object]:
    return deepcopy(dict(value))
