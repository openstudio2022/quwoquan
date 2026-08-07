"""Resolve and copy an audited reviewed-closure adoption release selection."""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from content.execution.closure.adoption_campaign_contract import (
    adopted_object_refs,
    validate_adoption_target_identity,
    validate_campaign_adoption_binding,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _execution_id,
    _read_json,
    _safe_id,
    _safe_rel,
)
from core.media_asset_url import sha256_file
from core.release_layout import payload_file, payload_root
from core.source_digest import SourceDigest

OBJECT_KINDS = ("creators", "entities", "posts", "tags")


@dataclass(frozen=True, slots=True)
class ReviewedClosureSelection:
    """Validated source-release bytes selected by one adoption campaign."""

    execution_ids: tuple[str, ...]
    desired: dict[str, list[str]]
    object_root: Path
    source_release_root: Path
    media_manifest: dict[str, Any]
    source_digest: SourceDigest


def _normalized_refs(value: object, *, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ObjectTransactionError(f"{label} must be an array")
    refs = tuple(
        sorted({_safe_rel(str(item), label=label).as_posix() for item in value})
    )
    if len(refs) != len(value):
        raise ObjectTransactionError(f"{label} contains duplicate refs")
    return refs


def reviewed_closure_selection(
    *,
    release_id: str,
    execution_ids: list[str],
    source_revision: str,
    entity_catalog_digest: str,
    reviewed_closure_adoption: Mapping[str, Any],
    output_root: Path | None,
) -> ReviewedClosureSelection:
    """Resolve an adoption only through its validated immutable evidence chain."""

    release_id = _safe_id(release_id, label="releaseId")
    if output_root is None:
        raise ObjectTransactionError(
            "reviewed closure adoption requires the governed output root"
        )
    try:
        binding = validate_campaign_adoption_binding(
            reviewed_closure_adoption,
            output_root=output_root,
        )
        receipt = _read_json(binding.receipt_path)
        adoption_ref = _read_json(binding.ref_path)
        target = receipt.get("targetSourceIdentity")
        target_source = validate_adoption_target_identity(
            target,
            binding=binding,
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise ObjectTransactionError(str(exc)) from exc

    source_identity = binding.source_release_identity
    if source_identity.release_id == release_id:
        raise ObjectTransactionError(
            "reviewed closure adoption cannot reuse the collided source releaseId"
        )
    normalized_execution_ids = tuple(_execution_id(item) for item in execution_ids)
    if (
        len(normalized_execution_ids) != 4
        or len(set(normalized_execution_ids)) != 4
        or set(normalized_execution_ids)
        != set(binding.adoption_receipt.lane_execution_ids)
    ):
        raise ObjectTransactionError(
            "reviewed closure adoption execution closure drifted"
        )
    if not isinstance(target, Mapping) or (
        target.get("sourceRevision") != source_revision
        or target.get("entityCatalogDigest") != entity_catalog_digest
    ):
        raise ObjectTransactionError(
            "reviewed closure adoption target source identity drifted"
        )

    raw_desired = adoption_ref.get("desiredRefs")
    if not isinstance(raw_desired, Mapping):
        raise ObjectTransactionError(
            "reviewed closure adoption desiredRefs must be an object"
        )
    desired = {
        kind: list(_normalized_refs(raw_desired.get(kind), label=kind))
        for kind in OBJECT_KINDS
    }
    lane_refs = adopted_object_refs(receipt)
    adopted_entities = sorted(
        ref.removeprefix("entities/") for ref in lane_refs["homepage"]
    )
    adopted_posts = sorted(
        ref.removeprefix("posts/")
        for carrier in ("article", "image", "video")
        for ref in lane_refs[carrier]
    )
    if (
        adopted_entities != desired["entities"]
        or adopted_posts != desired["posts"]
    ):
        raise ObjectTransactionError(
            "reviewed closure adoption lane/object closure drifted"
        )

    source_release_root = binding.adoption_ref.source_release_root
    object_root = payload_file(source_release_root, "objects")
    media_manifest = _read_json(
        payload_file(source_release_root, "media_manifest.json")
    )
    if (
        media_manifest.get("releaseId") != source_identity.release_id
        or not isinstance(media_manifest.get("assets"), list)
    ):
        raise ObjectTransactionError(
            "reviewed closure adoption source media manifest drifted"
        )
    return ReviewedClosureSelection(
        execution_ids=tuple(sorted(normalized_execution_ids)),
        desired=desired,
        object_root=object_root,
        source_release_root=source_release_root,
        media_manifest=media_manifest,
        source_digest=target_source,
    )


def copy_reviewed_closure_media(
    *,
    source_release_root: Path,
    target_release_root: Path,
    media_manifest: Mapping[str, Any],
) -> None:
    """Copy only validated public media slices from an immutable source release."""

    assets = media_manifest.get("assets")
    if not isinstance(assets, list):
        raise ObjectTransactionError(
            "reviewed closure adoption media assets must be an array"
        )
    expected_slices: set[str] = set()
    for index, row in enumerate(assets):
        if not isinstance(row, Mapping):
            raise ObjectTransactionError(
                f"reviewed closure adoption media asset {index} is invalid"
            )
        public_slice = _safe_rel(
            str(row.get("publicSliceKey") or ""),
            label=f"mediaAssets[{index}].publicSliceKey",
        ).as_posix()
        if public_slice in expected_slices:
            raise ObjectTransactionError(
                f"reviewed closure adoption media slice duplicated: {public_slice}"
            )
        expected_slices.add(public_slice)
        expected = str(row.get("sha256") or "")
        source = payload_file(source_release_root, public_slice)
        if (
            source.is_symlink()
            or not source.is_file()
            or sha256_file(source) != expected
        ):
            raise ObjectTransactionError(
                f"reviewed closure adoption media bytes drifted: {public_slice}"
            )
        target = payload_file(target_release_root, public_slice)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if sha256_file(target) != expected:
            raise ObjectTransactionError(
                f"reviewed closure adoption media copy drifted: {public_slice}"
            )
    source_payload = payload_root(source_release_root)
    source_media_root = source_payload / "media"
    actual_source_slices = {
        path.relative_to(source_payload).as_posix()
        for path in sorted(source_media_root.rglob("*"))
        if path.is_file() or path.is_symlink()
    }
    if actual_source_slices != expected_slices:
        raise ObjectTransactionError(
            "reviewed closure adoption source media file set drifted"
        )
    target_payload = payload_root(target_release_root)
    actual_target_slices = {
        path.relative_to(target_payload).as_posix()
        for path in sorted((target_payload / "media").rglob("*"))
        if path.is_file() or path.is_symlink()
    }
    if actual_target_slices != expected_slices:
        raise ObjectTransactionError(
            "reviewed closure adoption target media file set drifted"
        )


def revalidate_reviewed_closure_selection(
    *,
    reviewed_closure_adoption: Mapping[str, Any],
    output_root: Path | None,
    selection: ReviewedClosureSelection,
) -> None:
    """Close the source-release TOCTOU window before the atomic target rename."""

    if output_root is None:
        raise ObjectTransactionError(
            "reviewed closure adoption requires the governed output root"
        )
    try:
        binding = validate_campaign_adoption_binding(
            reviewed_closure_adoption,
            output_root=output_root,
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise ObjectTransactionError(str(exc)) from exc
    if (
        binding.adoption_ref.source_release_root != selection.source_release_root
        or binding.adoption_receipt.target_source_digest
        != selection.source_digest.digest
    ):
        raise ObjectTransactionError(
            "reviewed closure adoption source changed during aggregation"
        )


__all__ = [
    "ReviewedClosureSelection",
    "copy_reviewed_closure_media",
    "revalidate_reviewed_closure_selection",
    "reviewed_closure_selection",
]
