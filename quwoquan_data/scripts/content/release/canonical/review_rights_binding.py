"""Mechanical binding checks for the AI-authored 5.review rights authority."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _digest_file,
    _read_json,
    _safe_rel,
)
from core.schema import assert_valid

_MEDIA_REVIEW_REF = "5.review/media_ref_review.json"


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
    manifest: Mapping[str, Any],
    *,
    object_kind: str,
) -> tuple[str, ...]:
    """Return the exact execution asset set that one media review must cover."""

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
        raw_refs = _manifest_asset_refs(raw)
        # A derived poster may intentionally bind the same source video as the
        # published video. Review authority follows the actual execution asset
        # set, so duplicate source refs collapse to one exact fact.
        refs.extend(raw_refs)
    return tuple(sorted(set(refs)))


def validate_media_review_document(
    media_review: Mapping[str, Any],
    *,
    execution_id: str,
    object_ref: str,
    required_asset_refs: Sequence[str],
    object_aliases: Sequence[str] = (),
    source_assets: Mapping[str, Mapping[str, Any]] | None = None,
) -> None:
    """Recheck exact facts only; the AI remains the sole rights decision maker."""

    if str(media_review.get("executionId") or "") != execution_id:
        raise ObjectTransactionError("media_ref_review execution binding drift")
    if not any(
        _object_ref_matches(media_review.get("objectRef"), candidate)
        for candidate in (object_ref, *object_aliases)
        if str(candidate or "").strip()
    ):
        raise ObjectTransactionError("media_ref_review object binding drift")
    rows = media_review.get("rightsReviews")
    if not isinstance(rows, list) or any(not isinstance(row, Mapping) for row in rows):
        raise ObjectTransactionError("media_ref_review rightsReviews must be an array of objects")
    reviewed = [str(row.get("assetRef") or "").strip() for row in rows]
    expected = [str(value).strip() for value in required_asset_refs]
    if any(not value for value in reviewed) or len(reviewed) != len(set(reviewed)):
        raise ObjectTransactionError("media_ref_review assetRef values must be unique and non-empty")
    if sorted(reviewed) != sorted(expected):
        raise ObjectTransactionError("media_ref_review asset set differs from published assets")
    if media_review.get("passed") is not True:
        raise ObjectTransactionError("media_ref_review is not passed")
    if media_review.get("mediaIssues") or media_review.get("referenceIssues"):
        raise ObjectTransactionError("passed media_ref_review carries top-level issues")
    for row in rows:
        if row.get("passed") is not True or row.get("issues") != []:
            raise ObjectTransactionError(
                f"media_ref_review rights row is not passed: {row.get('assetRef')}"
            )
        if source_assets is not None:
            asset_ref = str(row.get("assetRef") or "")
            source = source_assets.get(asset_ref)
            if not isinstance(source, Mapping):
                raise ObjectTransactionError(
                    f"media_ref_review source asset is missing: {asset_ref}"
                )
            expected_facts = {
                "sourceUrl": source.get("sourceUrl") or source.get("url"),
                "license": source.get("license"),
                "termsUrl": source.get("termsUrl"),
                "authorizationProof": source.get("authorizationProof") or None,
            }
            if any(row.get(key) != value for key, value in expected_facts.items()):
                raise ObjectTransactionError(
                    f"media_ref_review source rights facts drift: {asset_ref}"
                )


def validate_review_authority(
    *,
    review_root: Path,
    manifest: Mapping[str, Any],
    object_kind: str,
    execution_id: str,
    object_ref: str,
    attestation: Mapping[str, Any] | None = None,
    source_assets: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, str]:
    """Bind one attestation to exactly one sibling media_ref_review file."""

    media_path = review_root / "media_ref_review.json"
    if media_path.is_symlink() or not media_path.is_file():
        raise ObjectTransactionError("5.review/media_ref_review.json is missing")
    media_review = _read_json(media_path)
    try:
        assert_valid(
            media_review,
            "content",
            "media_ref_review",
            label=media_path.as_posix(),
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise ObjectTransactionError(str(exc)) from exc
    validate_media_review_document(
        media_review,
        execution_id=execution_id,
        object_ref=object_ref,
        object_aliases=(str(manifest.get("topicId") or ""),),
        required_asset_refs=required_review_asset_refs(
            manifest,
            object_kind=object_kind,
        ),
        source_assets=source_assets,
    )
    attestation_doc = dict(attestation) if isinstance(attestation, Mapping) else _read_json(review_root / "attestation.json")
    binding = attestation_doc.get("mediaRefReview")
    if not isinstance(binding, Mapping):
        raise ObjectTransactionError("attestation mediaRefReview binding is missing")
    media_ref = _safe_rel(str(binding.get("ref") or ""), label="attestation.mediaRefReview.ref")
    expected_digest = _digest_file(media_path)
    if (
        media_ref.as_posix() != _MEDIA_REVIEW_REF
        or binding.get("digest") != expected_digest
        or binding.get("status") != "passed"
        or binding.get("issues") != []
    ):
        raise ObjectTransactionError("attestation mediaRefReview exact binding drift")
    review_scopes = {
        str(row.get("usageScope") or "").strip()
        for row in media_review["rightsReviews"]
        if isinstance(row, Mapping)
    }
    usage_scope = (
        "commercial"
        if review_scopes == {"commercial"} and bool(media_review["rightsReviews"])
        else "research"
    )
    normalized_object_ref = _normalized_object_ref(object_ref)
    if object_kind == "posts" and not normalized_object_ref.startswith("posts/"):
        normalized_object_ref = "posts/" + normalized_object_ref
    return {
        "ref": f"{normalized_object_ref}/{_MEDIA_REVIEW_REF}",
        "digest": expected_digest,
        "usageScope": usage_scope,
    }


__all__ = [
    "required_review_asset_refs",
    "validate_media_review_document",
    "validate_review_authority",
]
