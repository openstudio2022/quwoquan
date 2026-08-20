"""Minimal immutable checks for historical professional-video evidence.

Historical manifests and receipts are evidence, not documents to migrate in
place.  Their canonical document digests bind every retired field, while fresh
rebind output is independently validated against the current schema.  This
module therefore validates only the immutable identity/digest envelope; CAS
and per-asset provenance are checked by the rebind/frozen-asset consumers.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.source.professional_video_receipt import document_digest

HISTORICAL_PROVENANCE_FIELDS = (
    "assetId",
    "entityId",
    "observedEntityId",
    "provider",
    "platform",
    "displayName",
    "sourceKind",
    "acquisitionPath",
    "sourceUrl",
    "assetUrl",
    "manualFile",
    "apiEvidence",
    "accessEvidence",
    "title",
    "relevance",
    "creator",
    "capturedAt",
    "rightsStatus",
    "license",
    "termsUrl",
    "authorizationProof",
    "rightsIssues",
    "modelReleaseStatus",
    "propertyReleaseStatus",
)

_MANIFEST_SCHEMA = "quwoquan_data.professional_video_acquisition_manifest"
_RECEIPT_SCHEMA = "quwoquan_data.professional_video_acquisition_receipt"
_DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
_PAIR_IDENTITY_FIELDS = (
    "manifestId",
    "sourceRevision",
    "sourceDigest",
    "entityCatalogDigest",
)


class HistoricalVideoEvidenceError(ValueError):
    """The immutable historical evidence envelope cannot be proven."""


def _require_text(document: Mapping[str, Any], field: str, *, label: str) -> str:
    value = document.get(field)
    if not isinstance(value, str) or not value.strip():
        raise HistoricalVideoEvidenceError(f"{label}.{field} must be non-empty")
    return value


def _require_digest(document: Mapping[str, Any], field: str, *, label: str) -> str:
    value = _require_text(document, field, label=label)
    if _DIGEST_PATTERN.fullmatch(value) is None:
        raise HistoricalVideoEvidenceError(
            f"{label}.{field} must be one canonical sha256 digest"
        )
    return value


def _require_asset_sequence(
    document: Mapping[str, Any], field: str, *, label: str
) -> list[Any]:
    value = document.get(field)
    if not isinstance(value, list) or not value:
        raise HistoricalVideoEvidenceError(f"{label}.{field} must be a non-empty list")
    return value


def validate_historical_video_manifest(value: object) -> dict[str, Any]:
    """Validate immutable manifest identity without applying today's item schema."""
    if not isinstance(value, dict):
        raise HistoricalVideoEvidenceError(
            "historical video manifest must be an object"
        )
    if value.get("schema") != _MANIFEST_SCHEMA:
        raise HistoricalVideoEvidenceError(
            "historical video manifest schema is invalid"
        )
    _require_text(value, "manifestId", label="historical video manifest")
    for field in ("sourceRevision", "sourceDigest", "entityCatalogDigest"):
        _require_digest(value, field, label="historical video manifest")
    _require_asset_sequence(value, "items", label="historical video manifest")
    return value


def validate_historical_video_receipt(value: object) -> dict[str, Any]:
    """Validate immutable receipt identity/digest, ignoring retired projections."""
    if not isinstance(value, dict):
        raise HistoricalVideoEvidenceError("historical video receipt must be an object")
    if value.get("schema") != _RECEIPT_SCHEMA:
        raise HistoricalVideoEvidenceError("historical video receipt schema is invalid")
    _require_text(value, "manifestId", label="historical video receipt")
    for field in (
        "manifestDigest",
        "sourceRevision",
        "sourceDigest",
        "entityCatalogDigest",
        "receiptDigest",
    ):
        _require_digest(value, field, label="historical video receipt")
    _require_asset_sequence(value, "assets", label="historical video receipt")
    stable = {key: item for key, item in value.items() if key != "receiptDigest"}
    if value["receiptDigest"] != document_digest(stable):
        raise HistoricalVideoEvidenceError("historical video receiptDigest mismatch")
    return value


def validate_historical_video_pair(
    manifest: Mapping[str, Any], receipt: Mapping[str, Any]
) -> None:
    """Prove that one immutable receipt was issued for the supplied manifest."""
    expected_manifest_digest = document_digest(manifest)
    if receipt.get("manifestDigest") != expected_manifest_digest:
        raise HistoricalVideoEvidenceError(
            "historical video receipt does not bind the supplied manifest"
        )
    drift = [
        field
        for field in _PAIR_IDENTITY_FIELDS
        if receipt.get(field) != manifest.get(field)
    ]
    if drift:
        raise HistoricalVideoEvidenceError(
            "historical video receipt identity differs from manifest: "
            + ", ".join(drift)
        )


def validate_historical_video_receipt_path(path: Path, *, manifest_digest: str) -> None:
    """Require the historical create-once receipt's canonical digest-derived path."""
    token = manifest_digest.removeprefix("sha256:")
    if (
        path.parent.name != "receipts"
        or re.fullmatch(rf"{re.escape(token)}(-attempt-\d{{3,}})?\.json", path.name)
        is None
    ):
        raise HistoricalVideoEvidenceError(
            "historical video receipt path is not canonical"
        )


def index_historical_video_assets(
    values: object,
) -> tuple[dict[str, Mapping[str, Any]], tuple[str, ...], frozenset[str]]:
    """Index addressable assets without making one duplicate a batch failure."""
    indexed: dict[str, Mapping[str, Any]] = {}
    ordered: list[str] = []
    ambiguous: set[str] = set()
    if not isinstance(values, list):
        return indexed, (), frozenset()
    for value in values:
        if not isinstance(value, Mapping):
            continue
        asset_id = value.get("assetId")
        if not isinstance(asset_id, str) or not asset_id.strip():
            continue
        if asset_id in indexed:
            ambiguous.add(asset_id)
            continue
        indexed[asset_id] = value
        ordered.append(asset_id)
    for asset_id in ambiguous:
        indexed.pop(asset_id, None)
    return indexed, tuple(dict.fromkeys(ordered)), frozenset(ambiguous)


__all__ = [
    "HISTORICAL_PROVENANCE_FIELDS",
    "HistoricalVideoEvidenceError",
    "index_historical_video_assets",
    "validate_historical_video_manifest",
    "validate_historical_video_pair",
    "validate_historical_video_receipt",
    "validate_historical_video_receipt_path",
]
