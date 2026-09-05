"""Canonical single-object publish transaction."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from content.release.canonical.application import apply_object_transaction
from content.release.canonical.canonical_inventory import load_or_bootstrap_inventory
from content.release.canonical.object_transaction import build_entity_object_transaction_package
from content.release.canonical.object_transaction_audit import audit_object_transaction
from content.release.canonical.object_transaction_contract import ObjectTransactionError
from content.release.canonical.object_transaction_lock import canonical_publish_lock
from content.release.canonical.post_promotion import promote_post_object
from core.io import read_json
from core.paths import OUTPUT_ROOT, PUBLISH_ROOT, execution_root
from core.schema import assert_valid
from core.tree_integrity import tree_integrity_stats


def _target_object(execution_id: str, target_ref: str) -> tuple[str, str, Path]:
    root = execution_root(execution_id)
    target_set = read_json(root / "0.plan/target_set.json")
    assert_valid(target_set, "execution", "target_set", label="publish-object target_set")
    refs = [str(value).strip() for value in target_set.get("targetRefs") or []]
    if int(target_set.get("targetCount") or 0) != len(refs) or not refs:
        raise ObjectTransactionError("target_set targetCount/targetRefs closure is invalid")
    normalized = str(target_ref or "").strip()
    if normalized not in refs:
        raise ObjectTransactionError("target-ref is not declared by target_set.targetRefs")
    carrier = str(target_set.get("carrier") or "").strip()
    ref = normalized.strip("/")
    if carrier == "homepage":
        canonical_ref = ref.removeprefix("entities/").removeprefix("entity/")
        path = root / "entities" / canonical_ref
        kind = "entity"
    else:
        canonical_ref = ref.removeprefix("posts/")
        path = root / "posts" / canonical_ref
        kind = "post"
    if not path.is_dir():
        raise ObjectTransactionError(f"declared target object directory missing: {normalized}")
    return kind, canonical_ref, path


def _review_approved(object_dir: Path, *, expected_object_ref: str | None = None) -> None:
    documents: dict[str, dict[str, Any]] = {}
    for name, schema_name in (
        ("rubric_review.json", "rubric_review"),
        ("reviewer_result.json", "reviewer_result"),
        ("media_ref_review.json", "media_ref_review"),
        ("attestation.json", "review_attestation"),
    ):
        path = object_dir / "5.review" / name
        document = read_json(path)
        assert_valid(document, "content", schema_name, label=path.as_posix())
        documents[name] = document
    attestation = documents["attestation.json"]
    manifest = read_json(object_dir / "manifest.json")
    from content.release.canonical.review_rights_binding import validate_review_authority

    object_kind = "entity" if (object_dir / "_entity.json").is_file() else "posts"
    if not manifest.get("assets"):
        source_assets = {}
    elif object_kind == "entity":
        from content.release.canonical.entity_transaction_sources import source_assets_by_ref

        source_assets = source_assets_by_ref(object_dir.parents[3])
    else:
        from content.release.canonical.post_transaction_assets import source_assets as load_source_assets

        source_assets = load_source_assets(object_dir.parents[4])
    validate_review_authority(
        review_root=object_dir / "5.review",
        manifest=manifest,
        object_kind=object_kind,
        execution_id=str(attestation.get("executionId") or ""),
        object_ref=str(attestation.get("objectRef") or expected_object_ref or ""),
        attestation=attestation,
        source_assets=source_assets,
    )
    expected_ref = (
        str(expected_object_ref).strip("/")
        if expected_object_ref is not None
        else str(attestation.get("objectRef") or "").strip("/")
    )
    attested_ref = str(attestation.get("objectRef") or "").strip("/")
    manifest_topic_ref = str(manifest.get("topicId") or "").strip("/")
    valid_refs = {expected_ref}
    if object_kind == "posts" and manifest_topic_ref:
        valid_refs.add(manifest_topic_ref)
    if attested_ref not in valid_refs:
        raise ObjectTransactionError("target review attestation object binding drift")
    if attestation.get("independentReviewer", {}).get("actor") != documents["reviewer_result.json"].get("actor"):
        raise ObjectTransactionError("target review attestation reviewer binding drift")
    if attestation.get("decision") != "approved":
        raise ObjectTransactionError("target review attestation is not approved")
    for field in ("deterministicGate", "independentReviewer", "mediaRefReview"):
        if (attestation.get(field) or {}).get("status") != "passed":
            raise ObjectTransactionError(f"target review attestation {field} is not passed")
    if documents["rubric_review.json"].get("decision") != "approved":
        raise ObjectTransactionError("target rubric review is not approved")
    if documents["reviewer_result.json"].get("verdict") != "passed":
        raise ObjectTransactionError("target independent reviewer result is not passed")
    if documents["media_ref_review.json"].get("passed") is not True:
        raise ObjectTransactionError("target media and rights review is not passed")


def publish_object(execution_id: str, target_ref: str, *, apply: bool = False) -> dict[str, Any]:
    kind, canonical_ref, object_dir = _target_object(execution_id, target_ref)
    _review_approved(object_dir, expected_object_ref=target_ref)
    if not apply:
        return {
            "schema": "quwoquan_data.publish_object_result",
            "executionId": execution_id,
            "targetRef": target_ref,
            "mode": "plan",
            "status": "ready",
        }
    if kind == "post":
        result = promote_post_object(execution_id, canonical_ref)
    else:
        transaction_id = (
            f"{execution_id}--entity-"
            f"{hashlib.sha256(canonical_ref.encode('utf-8')).hexdigest()[:12]}"
        )
        root = execution_root(execution_id)
        package_root = root / "evidence/object-transactions" / transaction_id
        with canonical_publish_lock(PUBLISH_ROOT):
            build_entity_object_transaction_package(
                execution_root=root,
                object_ref=f"/entity/{canonical_ref}",
                transaction_id=transaction_id,
                package_root=package_root,
            )
            canonical_object = PUBLISH_ROOT / "entities" / canonical_ref
            if canonical_object.is_dir():
                if tree_integrity_stats(canonical_object)["merkleRoot"] != tree_integrity_stats(package_root / "object")["merkleRoot"]:
                    raise ObjectTransactionError("completed transaction canonical object drift")
                applied = {"objectClosureDigest": ""}
                admission = "replayed"
            else:
                before = load_or_bootstrap_inventory(PUBLISH_ROOT)["stats"]["merkleRoot"]
                audit = audit_object_transaction(
                    publish_root=PUBLISH_ROOT,
                    output_root=OUTPUT_ROOT,
                    package_root=package_root,
                    transaction_id=transaction_id,
                    expected_canonical_merkle=before,
                )
                applied = apply_object_transaction(
                    publish_root=PUBLISH_ROOT,
                    output_root=OUTPUT_ROOT,
                    package_root=package_root,
                    transaction_id=transaction_id,
                    dry_run_attestation_sha256=str(audit["dryRunAttestationSha256"]),
                )
                admission = "appended"
        result = {
            "transactionId": transaction_id,
            "canonicalObjectRef": f"entities/{canonical_ref}",
            "canonicalObjectSha256": str(tree_integrity_stats(canonical_object)["merkleRoot"]),
            "objectClosureDigest": str(applied.get("objectClosureDigest") or ""),
            "admissionResult": admission,
        }
    canonical_object_ref = str(result["canonicalObjectRef"])
    canonical_object = PUBLISH_ROOT / canonical_object_ref
    from content.release.canonical.content_pool_record import latest_pool_record
    pool_type = "homepage" if kind == "entity" else "content"
    record = latest_pool_record(canonical_object, pool_type)
    if not isinstance(record, dict):
        raise ObjectTransactionError("published object lacks canonical pool record")
    pool_record_ref = (
        f"{canonical_object_ref}/_pool/versions/{int(record['recordSequence'])}.json"
    )
    result.update(
        packageRef=f"evidence/object-transactions/{result['transactionId']}/package.json",
        attestationRef=f"{target_ref.strip('/')}/5.review/attestation.json",
        poolRecordRef=pool_record_ref,
    )
    return {
        "schema": "quwoquan_data.publish_object_result",
        "executionId": execution_id,
        "targetRef": target_ref,
        "mode": "apply",
        "status": "published",
        **result,
    }


def handle_publish_object(args: object) -> None:
    try:
        report = publish_object(
            str(getattr(args, "execution_id")),
            str(getattr(args, "target_ref")),
            apply=bool(getattr(args, "apply", False)),
        )
    except (FileNotFoundError, OSError, TypeError, ValueError, ObjectTransactionError) as exc:
        raise SystemExit(f"[release publish-object] GATE_BLOCK {exc}") from exc
    print(json.dumps(report, ensure_ascii=False, indent=2))


__all__ = ["handle_publish_object", "publish_object"]
