"""Build a forward-only Post successor from exact reviewed transaction evidence."""

from __future__ import annotations

import hashlib
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.execution.runtime_contract import canonical_sha256, file_sha256
from content.release.canonical.application import apply_object_transaction
from content.release.canonical.canonical_inventory import (
    assert_canonical_image_unique,
    load_or_bootstrap_inventory,
)
from content.release.canonical.content_pool_record import (
    append_pool_record,
    latest_pool_record,
    pool_payload_digest,
)
from content.release.canonical.object_transaction_contract import (
    EXPECTED_OBJECT_SCHEMAS,
    PACKAGE_SCHEMA,
    _closure_digest,
    _copy_tree,
    _document_tree_digest,
    _read_json,
    _review_binding,
    _safe_id,
    _tree_digest,
    _write_json,
    _verify_package,
)
from content.release.canonical.object_transaction_audit import audit_object_transaction
from content.release.canonical.object_transaction_delta import load_transaction_delta
from content.release.canonical.pool_record_history import POOL_RECORD_SCHEMA
from content.release.canonical.post_metadata_adoption_contract import (
    ADOPTION_SCHEMA,
    ALLOWED_CHANGES,
    ZERO_INVOCATIONS,
    PostMetadataAdoptionError,
    adoption_digest,
    validate_adoption_delta,
    validate_adoption_receipt,
)
from content.release.canonical.post_metadata_adoption_source import (
    assert_qualified_and_published as _qualified_and_published,
    assert_retry_delivery_state as _assert_retry_delivery_state,
    restore_snapshot_cas as _restore_snapshot_cas,
    semantic_attempt as _semantic_attempt,
    source_post_root as _source_post_root,
    source_provenance as _source_provenance,
    write_semantic_inventory as _semantic_inventory,
)
from core.schema import assert_valid


def _relative_output(path: Path, *, output_root: Path) -> str:
    try:
        return path.relative_to(output_root).as_posix()
    except ValueError as exc:
        raise PostMetadataAdoptionError(
            "DATA.POOL.METADATA_ADOPTION_OUTPUT_ESCAPE"
        ) from exc


def _without_manifest_changes(document: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(document)
    result.pop("generator", None)
    result.pop("version", None)
    return result


def _without_provenance_change(document: Mapping[str, Any]) -> dict[str, Any]:
    result = {**document, "final": dict(document.get("final") or {})}
    result["final"].pop("generator", None)
    return result


def _result(
    *,
    final_root: Path,
    source_object_ref: str,
    target_object_ref: str,
    transaction_id: str,
    idempotent: bool,
) -> dict[str, Any]:
    return {
        "schema": "quwoquan_data.post_metadata_adoption_result",
        "packageRoot": str(final_root / "package"),
        "sourceObjectRef": source_object_ref,
        "targetObjectRef": target_object_ref,
        "transactionId": transaction_id,
        "idempotent": idempotent,
    }


def apply_post_metadata_adoption(
    *,
    source_execution_root: Path,
    source_package_root: Path,
    adoption_id: str,
    output_root: Path,
    publish_root: Path,
) -> dict[str, Any]:
    prepared = build_post_metadata_adoption_package(
        source_execution_root=source_execution_root,
        source_package_root=source_package_root,
        adoption_id=adoption_id,
        output_root=output_root,
        publish_root=publish_root,
    )
    package_root = Path(str(prepared["packageRoot"]))
    transaction_id = str(prepared["transactionId"])
    source_object_ref = str(prepared["sourceObjectRef"])
    source_canonical = publish_root / "posts" / source_object_ref
    if source_canonical.exists() and (
        not source_canonical.is_dir()
        or pool_payload_digest(source_canonical)
        != pool_payload_digest(
            package_root.parent / "source-package/object"
        )
    ):
        raise PostMetadataAdoptionError(
            "DATA.POOL.METADATA_ADOPTION_CANONICAL_PREDECESSOR_DRIFT"
        )
    run_root = (
        output_root
        / "data/local/workspace/object-transactions"
        / transaction_id
    )
    audit_path = run_root / "audit_report.json"
    apply_path = run_root / "apply_report.json"
    if not apply_path.is_file():
        assert_canonical_image_unique(
            publish_root=publish_root,
            manifest=_read_json(package_root / "object/manifest.json"),
            excluded_manifest_path=f"posts/{source_object_ref}/manifest.json",
        )
    if apply_path.is_file() and audit_path.is_file():
        audit = _read_json(audit_path)
    else:
        audit = audit_object_transaction(
            publish_root=publish_root,
            output_root=output_root,
            package_root=package_root,
            transaction_id=transaction_id,
            expected_canonical_merkle=load_or_bootstrap_inventory(publish_root)[
                "stats"
            ]["merkleRoot"],
        )
    delta = load_transaction_delta(
        run_root=run_root,
        expected_digest=str(audit["deltaManifestDigest"]),
    )
    validate_adoption_delta(
        delta,
        source_object_ref=str(prepared["sourceObjectRef"]),
        target_object_ref=str(prepared["targetObjectRef"]),
    )
    applied = apply_object_transaction(
        publish_root=publish_root,
        output_root=output_root,
        package_root=package_root,
        transaction_id=transaction_id,
        dry_run_attestation_sha256=str(audit["dryRunAttestationSha256"]),
    )
    target_root = publish_root / "posts" / str(prepared["targetObjectRef"])
    if _document_tree_digest(target_root) != _document_tree_digest(
        package_root / "object"
    ):
        raise PostMetadataAdoptionError(
            "DATA.POOL.METADATA_ADOPTION_READBACK_DRIFT"
        )
    return {
        **prepared,
        "status": str(applied["status"]),
        "auditReportRef": str(run_root / "audit_report.json"),
        "applyReportRef": str(run_root / "apply_report.json"),
        "canonicalObjectSha256": _tree_digest(target_root),
        "idempotent": bool(prepared["idempotent"] or applied["idempotent"]),
    }


def build_post_metadata_adoption_package(
    *,
    source_execution_root: Path,
    source_package_root: Path,
    adoption_id: str,
    output_root: Path,
    publish_root: Path,
) -> dict[str, Any]:
    normalized_adoption = _safe_id(adoption_id, label="adoptionId")
    source_execution = source_execution_root.resolve(strict=True)
    source_package = source_package_root.resolve(strict=True)
    output = output_root.resolve()
    publish = publish_root.resolve()
    if source_execution_root.is_symlink() or source_package_root.is_symlink():
        raise PostMetadataAdoptionError(
            "DATA.POOL.METADATA_ADOPTION_SOURCE_SYMLINK"
        )
    source_tree_before = _tree_digest(source_package)
    semantic_root = source_execution / "_shared/semantic_tasks"
    semantic_before = _tree_digest(semantic_root)
    source_document = _read_json(source_package / "object_transaction_package.json")
    source_object_ref = str((source_document.get("target") or {}).get("objectRef") or "")
    source_object = source_package / "object"
    source_manifest = _read_json(source_object / "manifest.json")
    source_version = source_manifest.get("version")
    content_id = str(source_manifest.get("contentId") or "").strip()
    topic_id = str(source_manifest.get("topicId") or "").strip()
    if (
        source_document.get("executionId") != source_execution.name
        or source_document.get("schema") != PACKAGE_SCHEMA
        or (source_document.get("target") or {}).get("objectKind") != "posts"
        or source_manifest.get("contentType") != "image"
        or source_manifest.get("generator") != "image_evidence_pack"
        or not isinstance(source_version, int)
        or isinstance(source_version, bool)
        or source_version < 1
        or not content_id
        or not topic_id
        or source_object_ref.rsplit("/", 1)[-1] != str(source_version)
    ):
        raise PostMetadataAdoptionError(
            "DATA.POOL.METADATA_ADOPTION_SOURCE_IDENTITY_INVALID"
        )
    _assert_retry_delivery_state(source_execution)
    _qualified_and_published(
        source_execution,
        object_ref=source_object_ref,
        topic_id=topic_id,
    )
    source_post = _source_post_root(source_execution, source_object_ref)
    if (
        file_sha256(source_post / "5.review/attestation.json")
        != file_sha256(source_object / "attestation.json")
    ):
        raise PostMetadataAdoptionError(
            "DATA.POOL.METADATA_ADOPTION_ATTESTATION_DRIFT"
        )
    source_provenance, source_provenance_path = _source_provenance(
        source_post=source_post,
        source_package_object=source_object,
    )
    author_run_id = str((source_provenance.get("final") or {}).get("agentRunId") or "")
    attestation = _read_json(source_object / "attestation.json")
    reviewer_run_id = str(
        (attestation.get("independentReviewer") or {}).get("runId") or ""
    )
    if not author_run_id or not reviewer_run_id:
        raise PostMetadataAdoptionError(
            "DATA.POOL.METADATA_ADOPTION_RUN_ID_MISSING"
        )
    _semantic_attempt(semantic_root, run_id=author_run_id, label="author")
    _semantic_attempt(semantic_root, run_id=reviewer_run_id, label="reviewer")

    target_version = source_version + 1
    target_object_ref = source_object_ref.rsplit("/", 1)[0] + f"/{target_version}"
    transaction_hash = hashlib.sha256(
        f"{normalized_adoption}|{target_object_ref}".encode("utf-8")
    ).hexdigest()
    transaction_id = f"post-metadata-adoption-{transaction_hash}"
    final_root = (
        output
        / "data/local/workspace/post-metadata-adoptions"
        / normalized_adoption
    )
    if final_root.is_dir():
        package_root = final_root / "package"
        receipt = validate_adoption_receipt(
            _read_json(package_root / "object/metadata_adoption.json"),
            object_root=package_root / "object",
        )
        source_snapshot = final_root / "source-package"
        provenance_snapshot = final_root / "source-evidence/provenance.json"
        semantic_inventory_path = (
            final_root / "source-evidence/semantic-inventory.json"
        )
        semantic_inventory = _read_json(semantic_inventory_path)
        if (
            receipt["source"]["packageTreeDigest"] != source_tree_before
            or receipt["source"]["verifiedPackageTreeDigest"]
            != _tree_digest(source_snapshot)
            or receipt["source"]["provenanceFileSha256"]
            != file_sha256(provenance_snapshot)
            or receipt["source"]["provenanceCanonicalSha256"]
            != canonical_sha256(_read_json(provenance_snapshot))
            or receipt["source"]["semanticInventoryDigest"] != semantic_before
            or semantic_inventory.get("treeDigest") != semantic_before
            or receipt["target"]["objectRef"] != target_object_ref
        ):
            raise PostMetadataAdoptionError(
                "DATA.POOL.METADATA_ADOPTION_CREATE_ONCE_CONFLICT"
            )
        _verify_package(
            package_root,
            canonical_root=publish,
            require_target_absent=False,
        )
        return _result(
            final_root=final_root,
            source_object_ref=source_object_ref,
            target_object_ref=target_object_ref,
            transaction_id=transaction_id,
            idempotent=True,
        )
    if final_root.exists():
        raise PostMetadataAdoptionError(
            "DATA.POOL.METADATA_ADOPTION_INCOMPLETE_OUTPUT"
        )

    final_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{normalized_adoption}.", dir=final_root.parent)
    )
    try:
        source_snapshot = staging / "source-package"
        _copy_tree(source_package, source_snapshot)
        _restore_snapshot_cas(
            snapshot=source_snapshot,
            source_execution_root=source_execution,
        )
        verified_source = _verify_package(
            source_snapshot,
            canonical_root=publish,
            require_target_absent=False,
        )
        package_root = staging / "package"
        _copy_tree(source_snapshot, package_root)
        target_object = package_root / "object"
        shutil.rmtree(target_object / "_pool", ignore_errors=True)

        target_manifest = {**source_manifest, "generator": "agent", "version": target_version}
        assert_valid(
            target_manifest,
            "content",
            "post_manifest",
            label="post metadata adoption target manifest",
        )
        if _without_manifest_changes(target_manifest) != _without_manifest_changes(
            source_manifest
        ):
            raise PostMetadataAdoptionError(
                "DATA.POOL.METADATA_ADOPTION_MANIFEST_DRIFT"
            )
        _write_json(target_object / "manifest.json", target_manifest)

        target_provenance = {
            **source_provenance,
            "final": {**dict(source_provenance.get("final") or {}), "generator": "agent"},
        }
        if _without_provenance_change(target_provenance) != _without_provenance_change(
            source_provenance
        ):
            raise PostMetadataAdoptionError(
                "DATA.POOL.METADATA_ADOPTION_PROVENANCE_DRIFT"
            )
        _write_json(target_object / "provenance.json", target_provenance)

        source_evidence = staging / "source-evidence"
        source_evidence.mkdir(parents=True)
        shutil.copy2(source_provenance_path, source_evidence / "provenance.json")
        semantic_digest = _semantic_inventory(
            semantic_root,
            destination=source_evidence / "semantic-inventory.json",
        )
        expected_final_root = final_root
        receipt: dict[str, Any] = {
            "schema": ADOPTION_SCHEMA,
            "adoptionId": normalized_adoption,
            "source": {
                "executionId": source_execution.name,
                "transactionId": str(source_document["transactionId"]),
                "packageRef": _relative_output(
                    expected_final_root / "source-package", output_root=output
                ),
                "packageTreeDigest": source_tree_before,
                "verifiedPackageTreeDigest": _tree_digest(source_snapshot),
                "packageSha256": str(verified_source["packageSha256"]),
                "objectRef": source_object_ref,
                "contentId": content_id,
                "contentVersion": source_version,
                "manifestSha256": file_sha256(source_object / "manifest.json"),
                "provenanceRef": _relative_output(
                    expected_final_root / "source-evidence/provenance.json",
                    output_root=output,
                ),
                "provenanceCanonicalSha256": canonical_sha256(source_provenance),
                "provenanceFileSha256": file_sha256(source_provenance_path),
                "semanticInventoryRef": _relative_output(
                    expected_final_root / "source-evidence/semantic-inventory.json",
                    output_root=output,
                ),
                "semanticInventoryDigest": semantic_digest,
                "attestationSha256": file_sha256(source_object / "attestation.json"),
                "evidenceIndexSha256": file_sha256(
                    source_object / "evidence_index.json"
                ),
                "authorRunId": author_run_id,
                "reviewerRunId": reviewer_run_id,
            },
            "target": {
                "transactionId": transaction_id,
                "objectRef": target_object_ref,
                "contentId": content_id,
                "contentVersion": target_version,
                "manifestSha256": file_sha256(target_object / "manifest.json"),
                "provenanceCanonicalSha256": canonical_sha256(target_provenance),
                "provenanceFileSha256": file_sha256(
                    target_object / "provenance.json"
                ),
            },
            "allowedChanges": list(ALLOWED_CHANGES),
            "invocationCounts": dict(ZERO_INVOCATIONS),
        }
        receipt["receiptDigest"] = adoption_digest(receipt)
        _write_json(target_object / "metadata_adoption.json", receipt)
        validate_adoption_receipt(receipt, object_root=target_object)

        source_record = latest_pool_record(source_snapshot / "object", "content")
        if source_record is None or source_record.get("contentVersion") != source_version:
            raise PostMetadataAdoptionError(
                "DATA.POOL.METADATA_ADOPTION_SOURCE_RECORD_INVALID"
            )
        payload_digest = pool_payload_digest(target_object)
        append_pool_record(
            object_root=target_object,
            record={
                "schema": POOL_RECORD_SCHEMA,
                "objectType": "content",
                "objectId": content_id,
                "objectRef": target_object_ref,
                "recordSequence": 1,
                "contentVersion": target_version,
                "status": "active",
                "processResult": "completed",
                "qualityResult": "passed",
                "eligibilityResult": "passed",
                "usageScope": source_record.get("usageScope"),
                "evidenceRef": "metadata_adoption.json",
                "evidenceDigest": file_sha256(
                    target_object / "metadata_adoption.json"
                ),
                "payloadDigest": payload_digest,
                "canonicalObjectDigest": payload_digest,
                "sourceIdentity": source_record.get("sourceIdentity"),
                "sourceAttribution": source_record.get("sourceAttribution"),
            },
        )

        source_package_payload = verified_source["package"]
        closure = dict(source_package_payload["closure"])
        review = dict(source_package_payload["review"])
        binding = {
            "ref": "metadata_adoption.json",
            "sha256": file_sha256(target_object / "metadata_adoption.json"),
            "receiptDigest": str(receipt["receiptDigest"]),
        }
        review_binding = _review_binding(target_object, {"review": review})
        closure_digest = _closure_digest(
            object_root=target_object,
            object_kind="posts",
            object_ref=target_object_ref,
            target_schema=EXPECTED_OBJECT_SCHEMAS["posts"],
            source_policy_revision=str(
                source_package_payload["sourcePolicyRevision"]
            ),
            closure=closure,
            cas_rows=list(verified_source["casRows"]),
            review=review_binding,
            metadata_adoption=binding,
        )
        package_document = {
            **source_package_payload,
            "transactionId": transaction_id,
            "inputPayloadDigest": canonical_sha256(
                {
                    "adoptionId": normalized_adoption,
                    "sourcePackageTreeDigest": source_tree_before,
                    "targetObjectRef": target_object_ref,
                    "targetManifestSha256": receipt["target"]["manifestSha256"],
                    "targetProvenanceSha256": receipt["target"][
                        "provenanceFileSha256"
                    ],
                }
            ),
            "target": {
                **dict(source_package_payload["target"]),
                "objectRef": target_object_ref,
            },
            "metadataAdoption": binding,
            "objectClosureDigest": closure_digest,
        }
        _write_json(package_root / "object_transaction_package.json", package_document)
        _verify_package(
            package_root,
            canonical_root=publish,
            require_target_absent=True,
        )
        if (
            _tree_digest(source_package) != source_tree_before
            or _tree_digest(semantic_root) != semantic_before
        ):
            raise PostMetadataAdoptionError(
                "DATA.POOL.METADATA_ADOPTION_SOURCE_MUTATED"
            )
        staging.replace(final_root)
        return _result(
            final_root=final_root,
            source_object_ref=source_object_ref,
            target_object_ref=target_object_ref,
            transaction_id=transaction_id,
            idempotent=False,
        )
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


__all__ = [
    "PostMetadataAdoptionError",
    "apply_post_metadata_adoption",
    "build_post_metadata_adoption_package",
]
