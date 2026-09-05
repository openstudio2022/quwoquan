"""Mechanical binding checks for the unique AI-authored content review."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from content.release.canonical.object_transaction_contract import (
    CANONICAL_CONTENT_REVIEW_REF,
    EXECUTION_CONTENT_REVIEW_REF,
    ObjectTransactionError,
    _digest_file,
    _read_json,
)
from core.schema import assert_valid


def _normalized_object_ref(value: object) -> str:
    raw = str(value or "").strip().strip("/")
    if raw.startswith("entity/"):
        return "entities/" + raw.removeprefix("entity/")
    return raw


def _object_ref_matches(actual: object, expected: object) -> bool:
    return _normalized_object_ref(actual) == _normalized_object_ref(expected)


def _manifest_asset_refs(raw: Mapping[str, Any]) -> tuple[str, ...]:
    refs: list[str] = []
    direct = str(raw.get("sourceAssetRef") or "").strip()
    if direct:
        refs.append(direct)
    values = raw.get("sourceAssetRefs")
    if isinstance(values, list):
        refs.extend(str(value or "").strip() for value in values)
    normalized = tuple(ref for ref in refs if ref)
    if not normalized:
        raise ObjectTransactionError("published asset lacks source asset review identity")
    if len(normalized) != len(set(normalized)):
        raise ObjectTransactionError("published asset source review identities are duplicated")
    return normalized


def required_review_asset_refs(
    manifest: Mapping[str, Any], *, object_kind: str
) -> tuple[str, ...]:
    """Return the exact execution asset set the unique review must cover."""

    raw_assets = manifest.get("assets")
    if not isinstance(raw_assets, list) or any(
        not isinstance(raw, Mapping) for raw in raw_assets
    ):
        raise ObjectTransactionError("published manifest assets must be an array of objects")
    assets = [raw for raw in raw_assets if isinstance(raw, Mapping)]
    text_only = (
        object_kind == "posts"
        and str(manifest.get("contentType") or "").strip() == "article"
        and str(manifest.get("publishMediaMode") or "").strip() == "text_only"
    )
    if text_only:
        if assets:
            raise ObjectTransactionError("text-only article must publish an empty asset set")
        return ()
    if not assets:
        raise ObjectTransactionError("non-text-only object must publish at least one asset")
    refs: list[str] = []
    for raw in assets:
        refs.extend(_manifest_asset_refs(raw))
    return tuple(sorted(set(refs)))


def validate_content_review_document(
    content_review: Mapping[str, Any],
    *,
    execution_id: str,
    object_ref: str,
    required_asset_refs: Sequence[str],
    object_aliases: Sequence[str] = (),
    source_assets: Mapping[str, Mapping[str, Any]] | None = None,
    require_approved: bool = False,
) -> None:
    """Recheck identity, exact asset coverage, and recorded source hard facts."""

    try:
        assert_valid(
            dict(content_review),
            "content",
            "content_review",
            label=EXECUTION_CONTENT_REVIEW_REF,
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise ObjectTransactionError(str(exc)) from exc
    if str(content_review.get("executionId") or "") != execution_id:
        raise ObjectTransactionError("content_review execution binding drift")
    if not any(
        _object_ref_matches(content_review.get("objectRef"), candidate)
        for candidate in (object_ref, *object_aliases)
        if str(candidate or "").strip()
    ):
        raise ObjectTransactionError("content_review object binding drift")
    rows = content_review.get("assetRights")
    if not isinstance(rows, list) or any(not isinstance(row, Mapping) for row in rows):
        raise ObjectTransactionError("content_review assetRights must be an array of objects")
    reviewed = [str(row.get("assetRef") or "").strip() for row in rows]
    expected = [str(value).strip() for value in required_asset_refs]
    if any(not value for value in reviewed) or len(reviewed) != len(set(reviewed)):
        raise ObjectTransactionError("content_review assetRef values must be unique and non-empty")
    if sorted(reviewed) != sorted(expected):
        raise ObjectTransactionError("content_review asset set differs from published assets")
    if require_approved and content_review.get("decision") != "approved":
        raise ObjectTransactionError("content_review is not approved")
    if source_assets is None:
        return
    for row in rows:
        asset_ref = str(row.get("assetRef") or "")
        source = source_assets.get(asset_ref)
        if not isinstance(source, Mapping):
            raise ObjectTransactionError(
                f"content_review source asset is missing: {asset_ref}"
            )
        expected_facts = {
            "sourceUrl": source.get("sourceUrl") or source.get("url"),
            "license": source.get("license"),
            "termsUrl": source.get("termsUrl"),
            "authorizationProof": source.get("authorizationProof") or None,
        }
        if any(row.get(key) != value for key, value in expected_facts.items()):
            raise ObjectTransactionError(
                f"content_review source rights facts drift: {asset_ref}"
            )


def validate_review_authority(
    *,
    review_root: Path,
    manifest: Mapping[str, Any],
    object_kind: str,
    execution_id: str,
    object_ref: str,
    source_assets: Mapping[str, Mapping[str, Any]] | None = None,
    require_approved: bool = True,
) -> dict[str, str]:
    """Validate and bind the sole review file as evidence and rights authority."""

    review_path = review_root / "content_review.json"
    if review_path.is_symlink() or not review_path.is_file():
        raise ObjectTransactionError(f"{EXECUTION_CONTENT_REVIEW_REF} is missing")
    content_review = _read_json(review_path)
    validate_content_review_document(
        content_review,
        execution_id=execution_id,
        object_ref=object_ref,
        object_aliases=(str(manifest.get("topicId") or ""),),
        required_asset_refs=required_review_asset_refs(
            manifest,
            object_kind=object_kind,
        ),
        source_assets=source_assets,
        require_approved=require_approved,
    )
    review_scopes = {
        str(row.get("usageScope") or "").strip()
        for row in content_review["assetRights"]
        if isinstance(row, Mapping)
    }
    usage_scope = (
        "commercial"
        if review_scopes == {"commercial"} and bool(content_review["assetRights"])
        else "research"
    )
    normalized_object_ref = _normalized_object_ref(object_ref)
    if object_kind == "posts" and not normalized_object_ref.startswith("posts/"):
        normalized_object_ref = "posts/" + normalized_object_ref
    return {
        "ref": f"{normalized_object_ref}/{CANONICAL_CONTENT_REVIEW_REF}",
        "digest": _digest_file(review_path),
        "usageScope": usage_scope,
    }


__all__ = [
    "required_review_asset_refs",
    "validate_content_review_document",
    "validate_review_authority",
]
