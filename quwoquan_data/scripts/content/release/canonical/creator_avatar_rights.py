"""Canonical commercial-rights validation for creator avatar assets."""

from __future__ import annotations

from collections.abc import Mapping

from core.schema import assert_valid


_PUBLISHABLE_SOURCE_USE_MODES = {
    "licensed_adaptation",
    "self_generated_original",
}
_PUBLISHABLE_MODEL_RELEASE_STATUSES = {
    "not_required",
    "obtained",
}


def _text(value: object) -> str:
    return str(value or "").strip()


def creator_avatar_rights_issue(
    document: Mapping[str, object],
    *,
    asset_id: str,
    sha256: str,
    object_key: str,
    byte_count: int,
    mime_type: str,
) -> str | None:
    """Return a low-cardinality blocker for one public avatar rights snapshot."""

    manifest_asset = document.get("manifestAsset")
    rights = document.get("commercialRights")
    if not isinstance(manifest_asset, Mapping) or not isinstance(rights, Mapping):
        return "creator_avatar_rights_schema_invalid"
    if (
        _text(document.get("assetId")) != asset_id
        or _text(manifest_asset.get("assetId")) != asset_id
        or _text(manifest_asset.get("sha256")) != sha256
        or _text(rights.get("assetId")) != asset_id
    ):
        return "creator_avatar_rights_identity_drift"
    if (
        _text(rights.get("rightsAuditStatus")) != "verified"
        or rights.get("rightsAuditIssues") != []
    ):
        return "creator_avatar_rights_unverified"
    if _text(rights.get("usageScope")) != "app_publish":
        return "creator_avatar_rights_scope_invalid"
    if _text(rights.get("sourceUseMode")) not in _PUBLISHABLE_SOURCE_USE_MODES:
        return "creator_avatar_rights_source_use_invalid"
    if (
        not _text(rights.get("licenseName"))
        or not _text(rights.get("licenseShortName"))
        or not _text(rights.get("licenseUrl")).startswith("https://")
    ):
        return "creator_avatar_license_invalid"
    if not _text(rights.get("author")) or not _text(rights.get("attribution")):
        return "creator_avatar_attribution_missing"
    if not _text(rights.get("authorizationProof")).startswith("https://"):
        return "creator_avatar_authorization_invalid"
    depicts_identifiable_person = document.get("depictsIdentifiablePerson")
    model_release_status = _text(rights.get("modelReleaseStatus"))
    if not isinstance(depicts_identifiable_person, bool):
        return "creator_avatar_subject_identity_missing"
    if model_release_status not in _PUBLISHABLE_MODEL_RELEASE_STATUSES:
        return "creator_avatar_model_release_invalid"
    if depicts_identifiable_person and model_release_status != "obtained":
        return "creator_avatar_model_release_invalid"
    asset = rights.get("asset")
    rights_asset_ref = _text(asset.get("ref")) if isinstance(asset, Mapping) else ""
    digest_hex = sha256.removeprefix("sha256:")
    object_suffix = object_key.rpartition(".")[2]
    if (
        not isinstance(asset, Mapping)
        or not rights_asset_ref
        or rights_asset_ref.startswith("media/objects/sha256/")
        or digest_hex not in rights_asset_ref
        or not object_suffix
        or not rights_asset_ref.endswith(f".{object_suffix}")
        or _text(asset.get("sha256")) != sha256
        or asset.get("bytes") != byte_count
        or _text(asset.get("mimeType")) != mime_type
    ):
        return "creator_avatar_rights_asset_drift"
    try:
        assert_valid(
            dict(document),
            "release",
            "creator_avatar_rights_snapshot",
            label="creator_avatar_rights_snapshot",
        )
    except (FileNotFoundError, ValueError):
        return "creator_avatar_rights_schema_invalid"
    return None


__all__ = ["creator_avatar_rights_issue"]
