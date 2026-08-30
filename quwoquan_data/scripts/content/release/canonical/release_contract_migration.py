"""Fail-closed migration of pre-contract immutable releases to fresh identities.

The source release remains byte-for-byte immutable.  This module validates its
canonical payload and copies that exact object/media closure into a new release,
then regenerates only release-identity documents owned by the current contract.
"""
from __future__ import annotations

import json
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.release.canonical.aggregate_release_closure import (
    OBJECT_KINDS,
    existing_refs,
)
from content.release.canonical.aggregate_release_documents import (
    assert_holdings_reachable,
    release_attestation_document,
    release_desired_state_document,
    release_header_document,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _now,
    _read_json,
    _safe_id,
    _write_json,
    assert_environment_neutral,
)
from content.release.canonical.release_attestation import ReleaseAttestation
from content.release.canonical.release_header import validate_release_header
from content.release.canonical.release_identity_incident import (
    canonical_release_identity_guard,
    release_output_root,
)
from content.release.canonical.release_uat_sample_plan import (
    PLAN_REF as UAT_SAMPLE_PLAN_REF,
)
from content.release.canonical.release_uat_sample_plan import (
    build_release_uat_sample_plan,
    exact_document_sha256,
    validate_release_uat_sample_plan,
)
from content.release.environment.consistency import scan_release_contract
from core.release_layout import (
    attestation_root,
    objects_merkle,
    payload_digest,
    payload_file,
    payload_root,
)
from core.schema import assert_valid

_SCHEMA = "quwoquan_data.release_contract_migration"
_SAMPLE_FIELDS = frozenset(
    {"sampleId", "carrier", "objectId", "objectRef", "objectDigest"}
)

class ReleaseContractMigrationError(ObjectTransactionError):
    """The source release cannot be safely projected onto the current contract."""


def _source_path(release_root: Path, release_id: str) -> Path:
    source = (release_root / _safe_id(release_id, label="sourceReleaseId")).resolve(
        strict=True
    )
    expected_parent = release_root.resolve(strict=True)
    if source.parent != expected_parent or source.is_symlink() or not source.is_dir():
        raise ReleaseContractMigrationError(
            "DATA.RELEASE.CONTRACT_MIGRATION_SOURCE_INVALID"
        )
    return source


def _validate_source_release(
    *, release_root: Path, source_release_id: str
) -> tuple[Path, dict[str, Any], ReleaseAttestation, dict[str, list[str]]]:
    source = _source_path(release_root, source_release_id)
    header = validate_release_header(
        _read_json(payload_file(source, "release.json")),
        label=f"release_contract_migration_source:{source_release_id}",
    )
    if header.get("releaseId") != source_release_id:
        raise ReleaseContractMigrationError(
            "DATA.RELEASE.CONTRACT_MIGRATION_SOURCE_ID_DRIFT"
        )
    try:
        attestation = ReleaseAttestation.from_document(
            _read_json(attestation_root(source) / "release.json")
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise ReleaseContractMigrationError(
            "DATA.RELEASE.CONTRACT_MIGRATION_ATTESTATION_INVALID"
        ) from exc
    if (
        attestation.release_id != source_release_id
        or attestation.payload_sha256 != payload_digest(source)
        or attestation.canonical_merkle != objects_merkle(source)
        or attestation.release_class.value != header.get("releaseClass")
        or attestation.product_lifecycle_state.value
        != header.get("productLifecycleState")
    ):
        raise ReleaseContractMigrationError(
            "DATA.RELEASE.CONTRACT_MIGRATION_ATTESTATION_DRIFT"
        )
    desired = existing_refs(source)
    if (
        sorted(attestation.execution_ids)
        != sorted(str(item) for item in header.get("executionIds") or [])
        or attestation.entity_count != len(desired["entities"])
        or attestation.post_count != len(desired["posts"])
        or attestation.creator_count != len(desired["creators"])
        or attestation.tag_count != len(desired["tags"])
    ):
        raise ReleaseContractMigrationError(
            "DATA.RELEASE.CONTRACT_MIGRATION_CLOSURE_DRIFT"
        )
    try:
        admission = _read_json(payload_file(source, "asset_admission.json"))
        assert_valid(
            admission,
            "release",
            "release_asset_admission",
            label=f"release_contract_migration_admission:{source_release_id}",
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise ReleaseContractMigrationError(
            "DATA.RELEASE.CONTRACT_MIGRATION_ADMISSION_INVALID"
        ) from exc
    admission_binding = {
        "releaseId": source_release_id,
        "releaseClass": header.get("releaseClass"),
        "productLifecycleState": header.get("productLifecycleState"),
        "containsUnverifiedAssets": header.get("containsUnverifiedAssets"),
        "rightsStatusCounts": header.get("rightsStatusCounts"),
        "authorizationRequiredAssetIds": header.get(
            "authorizationRequiredAssetIds"
        ),
        "researchAcceptedCount": header.get("researchAcceptedCount"),
        "commercialAcceptedCount": header.get("commercialAcceptedCount"),
    }
    if any(admission.get(field) != value for field, value in admission_binding.items()):
        raise ReleaseContractMigrationError(
            "DATA.RELEASE.CONTRACT_MIGRATION_ADMISSION_DRIFT"
        )
    consistency = scan_release_contract(
        release_desired_state_document(
            release_id=source_release_id,
            desired=desired,
        ),
        release_root=source,
        phase="preflight",
    )
    if consistency.get("status") != "passed":
        raise ReleaseContractMigrationError(
            "DATA.RELEASE.CONTRACT_MIGRATION_CONSISTENCY_INVALID"
        )
    assert_holdings_reachable(source, source_release_id)
    assert_environment_neutral(source)
    return source, header, attestation, desired


def _sample_contract_state(source: Path, header: Mapping[str, Any]) -> str:
    ref = str(header.get("samplePlanRef") or "")
    digest = str(header.get("samplePlanDigest") or "")
    if ref != UAT_SAMPLE_PLAN_REF or not digest:
        return "missing_current_binding"
    path = payload_file(source, ref)
    if not path.is_file() or path.is_symlink():
        return "missing_current_binding"
    document = _read_json(path)
    samples = document.get("samples")
    if not isinstance(samples, list) or not samples:
        return "invalid_current_contract"
    if any(not isinstance(sample, Mapping) for sample in samples):
        return "invalid_current_contract"
    field_sets = {frozenset(sample) for sample in samples}
    if field_sets == {_SAMPLE_FIELDS}:
        try:
            validate_release_uat_sample_plan(document)
        except (ObjectTransactionError, TypeError, ValueError):
            return "invalid_current_contract"
        return "current"
    if all(
        fields == {"sampleId", "carrier", "objectId", "carrierRef"}
        for fields in field_sets
    ):
        return "retired_sample_fields"
    return "invalid_current_contract"


def _eligible_counts(
    *,
    source: Path,
    header: Mapping[str, Any],
    desired: Mapping[str, list[str]],
) -> dict[str, int]:
    counts = {
        "homepage": len(desired["entities"]),
        "article": 0,
        "image": 0,
        "video": 0,
    }
    contents = header.get("contents")
    if not isinstance(contents, list):
        raise ReleaseContractMigrationError(
            "DATA.RELEASE.CONTRACT_MIGRATION_CONTENTS_MISSING"
        )
    for row in contents:
        if not isinstance(row, Mapping):
            raise ReleaseContractMigrationError(
                "DATA.RELEASE.CONTRACT_MIGRATION_CONTENTS_INVALID"
            )
        carrier = str(row.get("postRef") or "").partition("/")[0]
        if carrier not in {"article", "image", "video"}:
            raise ReleaseContractMigrationError(
                "DATA.RELEASE.CONTRACT_MIGRATION_CONTENTS_INVALID"
            )
        counts[carrier] += 1
    sample_plan = _read_json(payload_file(source, UAT_SAMPLE_PLAN_REF))
    raw = sample_plan.get("eligiblePopulationCounts")
    if not isinstance(raw, Mapping):
        return counts
    return {
        carrier: max(counts[carrier], int(raw.get(carrier) or 0))
        for carrier in counts
    }


def release_contract_migration_precheck(
    *, release_root: Path, source_release_id: str, new_release_id: str
) -> dict[str, Any]:
    source_release_id = _safe_id(source_release_id, label="sourceReleaseId")
    new_release_id = _safe_id(new_release_id, label="newReleaseId")
    if source_release_id == new_release_id:
        raise ReleaseContractMigrationError(
            "DATA.RELEASE.CONTRACT_MIGRATION_REQUIRES_FRESH_RELEASE_ID"
        )
    source, header, attestation, _desired = _validate_source_release(
        release_root=release_root,
        source_release_id=source_release_id,
    )
    if header.get("selectionScope") not in {
        "target_environment",
        "all_publishable",
    } or header.get("milestone") is not None:
        raise ReleaseContractMigrationError(
            "DATA.RELEASE.CONTRACT_MIGRATION_SCOPE_UNSUPPORTED"
        )
    state = _sample_contract_state(source, header)
    if state == "current":
        raise ReleaseContractMigrationError(
            "DATA.RELEASE.CONTRACT_MIGRATION_NOT_REQUIRED"
        )
    if state != "retired_sample_fields":
        raise ReleaseContractMigrationError(
            f"DATA.RELEASE.CONTRACT_MIGRATION_SOURCE_UNSUPPORTED: {state}"
        )
    target = release_root.resolve() / new_release_id
    if target.exists():
        raise ReleaseContractMigrationError(
            "DATA.RELEASE.CONTRACT_MIGRATION_TARGET_EXISTS"
        )
    return {
        "schema": _SCHEMA,
        "status": "ready",
        "sourceReleaseId": source_release_id,
        "sourcePayloadSha256": attestation.payload_sha256,
        "sourceCanonicalMerkle": attestation.canonical_merkle,
        "sourceSamplePlanDigest": str(header["samplePlanDigest"]),
        "sourceSampleContractState": state,
        "newReleaseId": new_release_id,
        "releaseClass": str(header["releaseClass"]),
        "selectionScope": str(header["selectionScope"]),
        "targetEnvironment": header.get("targetEnvironment"),
        "applyCommand": (
            "python3 quwoquan_data/scripts/cli.py release contract-migrate "
            f"--source-release-id {source_release_id} "
            f"--new-release-id {new_release_id} --apply"
        ),
    }


def _target_header(
    *,
    source: Path,
    source_header: Mapping[str, Any],
    new_release_id: str,
    desired: Mapping[str, list[str]],
    sample_plan_digest: str,
) -> dict[str, Any]:
    document = release_header_document(
        release_id=new_release_id,
        execution_ids=list(source_header["executionIds"]),
        source_revision=None,
        source_digest=None,
        entity_catalog_digest=None,
        source_digest_documents=list(source_header["sourceDigests"]),
        asset_admission=_read_json(payload_file(source, "asset_admission.json")),
        canonical_merkle=objects_merkle(source),
        release_class=str(source_header["releaseClass"]),
        product_lifecycle_state=str(source_header["productLifecycleState"]),
        reviewed_closure_adoption=None,
        selection_scope=str(source_header["selectionScope"]),
        target_environment=(
            str(source_header["targetEnvironment"])
            if source_header.get("targetEnvironment") is not None
            else None
        ),
        release_mode=str(source_header["releaseMode"]),
        pool_digest=str(source_header["poolDigest"]),
        counts=dict(source_header["counts"]),
        contents=list(source_header["contents"]),
        authors=list(source_header["authors"]),
        milestone=None,
        milestone_targets=None,
        sample_plan_ref=UAT_SAMPLE_PLAN_REF,
        sample_plan_digest=sample_plan_digest,
        source_identities=list(source_header["sourceIdentities"]),
        source_identity_set_digest=str(source_header["sourceIdentitySetDigest"]),
    )
    document["contractMigration"] = {
        "sourceReleaseId": str(source_header["releaseId"]),
        "sourcePayloadSha256": payload_digest(source),
        "sourceCanonicalMerkle": objects_merkle(source),
        "sourceSamplePlanRef": UAT_SAMPLE_PLAN_REF,
        "sourceSamplePlanDigest": str(source_header["samplePlanDigest"]),
        "reasonCode": "RELEASE_UAT_SAMPLE_PLAN_CONTRACT_CUTOVER",
    }
    return validate_release_header(
        document, label=f"release_contract_migration_target:{new_release_id}"
    )


def migrate_release_contract(
    *, release_root: Path, source_release_id: str, new_release_id: str
) -> dict[str, Any]:
    precheck = release_contract_migration_precheck(
        release_root=release_root,
        source_release_id=source_release_id,
        new_release_id=new_release_id,
    )
    source, source_header, source_attestation, desired = _validate_source_release(
        release_root=release_root,
        source_release_id=source_release_id,
    )
    target = release_root.resolve() / new_release_id
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{new_release_id}.", dir=target.parent))
    try:
        source_payload = payload_root(source)
        target_payload = payload_root(staging)
        for relative in ("objects", "media"):
            source_path = source_payload / relative
            if source_path.is_dir():
                shutil.copytree(source_path, target_payload / relative)
        for relative in ("index/objects.json", "sample_bundle.json", "media_manifest.json"):
            source_path = source_payload / relative
            target_path = target_payload / relative
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target_path)

        desired_document = release_desired_state_document(
            release_id=new_release_id,
            desired=desired,
        )
        _write_json(target_payload / "desired_state.json", desired_document)
        asset_admission = _read_json(payload_file(source, "asset_admission.json"))
        asset_admission["releaseId"] = new_release_id
        assert_valid(
            asset_admission,
            "release",
            "release_asset_admission",
            label=f"release_contract_migration_admission:{new_release_id}",
        )
        _write_json(target_payload / "asset_admission.json", asset_admission)

        current_merkle = objects_merkle(staging)
        if current_merkle != source_attestation.canonical_merkle:
            raise ReleaseContractMigrationError(
                "DATA.RELEASE.CONTRACT_MIGRATION_OBJECT_BYTES_DRIFT"
            )
        eligible_counts = _eligible_counts(
            source=source,
            header=source_header,
            desired=desired,
        )
        sample_plan = build_release_uat_sample_plan(
            release_id=new_release_id,
            milestone=None,
            pool_digest=str(source_header["poolDigest"]),
            source_identity_set_digest=str(source_header["sourceIdentitySetDigest"]),
            canonical_merkle=current_merkle,
            release_contents=list(source_header["contents"]),
            entity_refs=desired["entities"],
            release_objects_root=target_payload / "objects",
            eligible_population_counts=eligible_counts,
        )
        sample_path = target_payload / UAT_SAMPLE_PLAN_REF
        _write_json(sample_path, sample_plan)
        sample_digest = exact_document_sha256(sample_plan)
        header = _target_header(
            source=source,
            source_header=source_header,
            new_release_id=new_release_id,
            desired=desired,
            sample_plan_digest=sample_digest,
        )
        _write_json(target_payload / "release.json", header)

        media_manifest = _read_json(target_payload / "media_manifest.json")
        media_manifest["releaseId"] = new_release_id
        assert_valid(
            media_manifest,
            "release",
            "media_manifest",
            label=f"release_media_manifest:{new_release_id}",
        )
        _write_json(target_payload / "media_manifest.json", media_manifest)
        index = _read_json(target_payload / "index/objects.json")
        sample_bundle = _read_json(target_payload / "sample_bundle.json")
        if index != {"schema": "quwoquan_data.release_object_index", **desired}:
            raise ReleaseContractMigrationError(
                "DATA.RELEASE.CONTRACT_MIGRATION_INDEX_DRIFT"
            )
        if sample_bundle != {"schema": "quwoquan_data.release_sample_bundle", **desired}:
            raise ReleaseContractMigrationError(
                "DATA.RELEASE.CONTRACT_MIGRATION_SAMPLE_BUNDLE_DRIFT"
            )
        consistency = scan_release_contract(
            desired_document,
            release_root=staging,
            phase="preflight",
        )
        if consistency.get("status") != "passed":
            raise ReleaseContractMigrationError(
                "DATA.RELEASE.CONTRACT_MIGRATION_CONSISTENCY_INVALID"
            )
        attestation = release_attestation_document(
            release_id=new_release_id,
            execution_ids=list(source_attestation.execution_ids),
            source_revision=None,
            source_digest=None,
            entity_catalog_digest=None,
            source_digests=source_attestation.source_digests,
            asset_admission=asset_admission,
            canonical_merkle=current_merkle,
            entity_count=len(desired["entities"]),
            post_count=len(desired["posts"]),
            creator_count=len(desired["creators"]),
            tag_count=len(desired["tags"]),
            payload_sha256=payload_digest(staging),
            recorded_at=_now(),
            release_class=str(source_header["releaseClass"]),
            source_identities=source_attestation.source_identities,
            source_identity_set_digest=source_attestation.source_identity_set_digest,
        )
        _write_json(attestation_root(staging) / "release.json", attestation)
        validate_release_uat_sample_plan(
            sample_plan,
            release_contents=list(source_header["contents"]),
            entity_refs=desired["entities"],
            release_objects_root=target_payload / "objects",
            expected_release_id=new_release_id,
            expected_milestone=None,
            expected_selection_evidence=sample_plan["selectionEvidence"],
        )
        assert_holdings_reachable(staging, new_release_id)
        assert_environment_neutral(staging)
        if payload_digest(staging) != attestation["payloadSha256"]:
            raise ReleaseContractMigrationError(
                "DATA.RELEASE.CONTRACT_MIGRATION_PAYLOAD_DRIFT"
            )
        if (
            payload_digest(source) != source_attestation.payload_sha256
            or objects_merkle(source) != source_attestation.canonical_merkle
            or source_attestation.payload_sha256 != precheck["sourcePayloadSha256"]
        ):
            raise ReleaseContractMigrationError(
                "DATA.RELEASE.CONTRACT_MIGRATION_SOURCE_CHANGED"
            )
        with canonical_release_identity_guard(
            output_root=release_output_root(release_root),
            release_id=new_release_id,
        ):
            if target.exists():
                raise ReleaseContractMigrationError(
                    "DATA.RELEASE.CONTRACT_MIGRATION_TARGET_EXISTS"
                )
            staging.replace(target)
        return {
            **precheck,
            "status": "migrated",
            "newPayloadSha256": payload_digest(target),
            "newCanonicalMerkle": objects_merkle(target),
            "newSamplePlanRef": UAT_SAMPLE_PLAN_REF,
            "newSamplePlanDigest": sample_digest,
            "newAttestationRef": (
                Path(new_release_id) / "attestations/release.json"
            ).as_posix(),
        }
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


__all__ = [
    "ReleaseContractMigrationError",
    "migrate_release_contract",
    "release_contract_migration_precheck",
]
