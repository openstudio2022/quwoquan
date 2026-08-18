"""Typed campaign boundary for a reviewed-closure adoption operation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.schema import assert_valid
from core.source_digest import (
    SourceDefinitionSnapshot,
    SourceDigestError,
    content_source_revision,
)

from content.execution.identity import parse_execution_id
from content.execution.campaign.lane import normalize_active_carriers
from content.execution.closure.adoption_contract import (
    ReviewedClosureAdoptionError,
    canonical_digest,
    file_digest,
    validate_reviewed_closure_adoption_receipt,
    validate_reviewed_closure_adoption_ref,
)
from content.execution.closure.adoption_identity import (
    ReleaseIdentityTuple,
    ReviewedClosureAdoptionReceipt,
    ReviewedClosureAdoptionRef,
    _read_object,
    _resolve_path,
    _typed,
)

CAMPAIGN_ADOPTION_FIELD = "reviewedClosureAdoption"
ADOPTION_OPERATIONS = {
    "homepage": "homepage.adoptReviewedClosure",
    "article": "article.adoptReviewedClosure",
    "image": "image.adoptReviewedClosure",
    "video": "video.adoptReviewedClosure",
}


@dataclass(frozen=True, slots=True)
class ReviewedClosureCampaignBinding:
    adoption_id: str
    source_release_identity: ReleaseIdentityTuple
    adoption_ref: ReviewedClosureAdoptionRef
    adoption_receipt: ReviewedClosureAdoptionReceipt
    ref_path: Path
    receipt_path: Path


def validate_campaign_adoption_binding(
    value: object,
    *,
    output_root: Path,
) -> ReviewedClosureCampaignBinding:
    try:
        assert_valid(
            value,
            "execution",
            "reviewed_closure_adoption_campaign_binding",
            label="reviewed closure campaign binding",
        )
    except ValueError as exc:
        raise _typed("CAMPAIGN_BINDING_INVALID", str(exc)) from exc
    if not isinstance(value, Mapping):
        raise _typed("CAMPAIGN_BINDING_INVALID", "binding must be an object")
    document = dict(value)
    ref_binding = document.get("adoptionRef")
    receipt_binding = document.get("adoptionReceipt")
    if not isinstance(ref_binding, Mapping) or not isinstance(receipt_binding, Mapping):
        raise _typed("CAMPAIGN_BINDING_INVALID", "file bindings are invalid")
    ref_path = _resolve_path(
        ref_binding.get("ref"),
        output_root=output_root,
        label="reviewedClosureAdoption.adoptionRef.ref",
        kind="file",
    )
    receipt_path = _resolve_path(
        receipt_binding.get("ref"),
        output_root=output_root,
        label="reviewedClosureAdoption.adoptionReceipt.ref",
        kind="file",
    )
    if file_digest(ref_path) != ref_binding.get("fileSha256"):
        raise _typed("DIGEST_DRIFT", "campaign adoption ref bytes drifted")
    if file_digest(receipt_path) != receipt_binding.get("fileSha256"):
        raise _typed("DIGEST_DRIFT", "campaign adoption receipt bytes drifted")
    adoption_ref = validate_reviewed_closure_adoption_ref(
        _read_object(ref_path, label="reviewed closure adoption ref"),
        output_root=output_root,
    )
    adoption_receipt = validate_reviewed_closure_adoption_receipt(
        _read_object(receipt_path, label="reviewed closure adoption receipt"),
        output_root=output_root,
    )
    identity_document = adoption_ref.source_release_identity.to_document()
    if (
        document.get("adoptionId") != adoption_ref.adoption_id
        or document.get("adoptionId") != adoption_receipt.adoption_id
        or document.get("sourceReleaseIdentity") != identity_document
        or adoption_receipt.source_release_identity
        != adoption_ref.source_release_identity
        or ref_binding.get("adoptionRefDigest") != adoption_ref.adoption_ref_digest
        or receipt_binding.get("receiptDigest") != adoption_receipt.receipt_digest
    ):
        raise _typed("CAMPAIGN_BINDING_INVALID", "adoption identity drifted")
    return ReviewedClosureCampaignBinding(
        adoption_id=adoption_ref.adoption_id,
        source_release_identity=adoption_ref.source_release_identity,
        adoption_ref=adoption_ref,
        adoption_receipt=adoption_receipt,
        ref_path=ref_path,
        receipt_path=receipt_path,
    )


def validate_adoption_target_identity(
    target: object,
    *,
    binding: ReviewedClosureCampaignBinding,
) -> SourceDefinitionSnapshot:
    if not isinstance(target, Mapping):
        raise _typed("TARGET_IDENTITY_INVALID", "target identity must be an object")
    try:
        source = SourceDefinitionSnapshot.from_document(target.get("sourceDigest"))
        expected_revision = content_source_revision(
            source_digest=source.digest,
            entity_catalog_digest=str(target.get("entityCatalogDigest") or ""),
        )
    except SourceDigestError as exc:
        raise _typed("TARGET_IDENTITY_INVALID", str(exc)) from exc
    if (
        target.get("sourceRevision") != expected_revision
        or source.digest != binding.adoption_receipt.target_source_digest
        or expected_revision != binding.adoption_receipt.target_source_revision
    ):
        raise _typed("TARGET_IDENTITY_INVALID", "target identity drifted")
    return source


def adopted_object_refs(
    receipt_document: Mapping[str, Any],
) -> dict[str, list[str]]:
    rows = receipt_document.get("laneExecutions")
    if not isinstance(rows, list):
        raise _typed("LANE_CLOSURE_DRIFT", "laneExecutions are missing")
    result: dict[str, list[str]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise _typed("LANE_CLOSURE_DRIFT", "lane execution is invalid")
        carrier = str(row.get("carrier") or "")
        refs = row.get("adoptedObjectRefs")
        if carrier in result or not isinstance(refs, list) or not refs:
            raise _typed("LANE_CLOSURE_DRIFT", "lane object closure is invalid")
        result[carrier] = list(refs)
    try:
        active = normalize_active_carriers(result)
    except ValueError as exc:
        raise _typed("LANE_CLOSURE_DRIFT", str(exc)) from exc
    if tuple(result) != active:
        raise _typed("LANE_CLOSURE_DRIFT", "active lanes are not in canonical order")
    return result


def validate_adoption_task_binding(
    value: object,
    *,
    output_root: Path,
) -> dict[str, Any]:
    try:
        assert_valid(
            value,
            "execution",
            "reviewed_closure_adoption_task_binding",
            label="reviewed closure adoption task binding",
        )
    except ValueError as exc:
        raise _typed("TASK_BINDING_INVALID", str(exc)) from exc
    if not isinstance(value, Mapping):
        raise _typed("TASK_BINDING_INVALID", "task binding must be an object")
    document = dict(value)
    stable = {key: item for key, item in document.items() if key != "bindingDigest"}
    if document.get("bindingDigest") != canonical_digest(stable):
        raise _typed("DIGEST_DRIFT", "task bindingDigest drifted")
    binding = validate_campaign_adoption_binding(
        document.get(CAMPAIGN_ADOPTION_FIELD),
        output_root=output_root,
    )
    identity = parse_execution_id(str(document.get("executionId") or ""))
    carrier = identity.content_type.value
    if (
        document.get("carrier") != carrier
        or document.get("operation") != ADOPTION_OPERATIONS.get(carrier)
        or str(document.get("rootExecutionId") or "")
        != binding.adoption_receipt.lane_execution_ids[0]
    ):
        raise _typed("TASK_BINDING_INVALID", "task/campaign identity drifted")
    receipt_document = _read_object(
        binding.receipt_path,
        label="reviewed closure adoption receipt",
    )
    lane_refs = adopted_object_refs(receipt_document)
    lane_ids = {
        str(row["carrier"]): str(row["executionId"])
        for row in receipt_document["laneExecutions"]
    }
    active_carriers = tuple(lane_ids)
    root_carrier = active_carriers[0]
    if (
        document.get("rootExecutionId") != lane_ids[root_carrier]
        or lane_ids.get(carrier) != identity.execution_id
        or document.get("adoptedObjectRefs") != lane_refs[carrier]
    ):
        raise _typed("TASK_BINDING_INVALID", "task lane closure drifted")
    validate_adoption_target_identity(
        document.get("targetSourceIdentity"),
        binding=binding,
    )
    return document


__all__ = [
    "ADOPTION_OPERATIONS",
    "CAMPAIGN_ADOPTION_FIELD",
    "ReviewedClosureAdoptionError",
    "ReviewedClosureCampaignBinding",
    "adopted_object_refs",
    "validate_adoption_target_identity",
    "validate_adoption_task_binding",
    "validate_campaign_adoption_binding",
]
