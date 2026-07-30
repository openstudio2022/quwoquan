"""Materialize one commercial creator avatar from canonical publish evidence."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from content.release.canonical.creator_avatar_rights import (
    creator_avatar_rights_issue,
)
from core.image_variants import build_center_square_cover_derivative
from core.media_asset_url import is_cas_media_object_key
from core.paths import CONTROL_PLANE_CREATOR_POOL_ROOT, PUBLISH_ROOT
from core.schema import assert_valid
from governance.creators.avatar_materialization import (
    CreatorAvatarError,
    persist_creator_avatar,
)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CreatorAvatarError(f"JSON unreadable: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CreatorAvatarError(f"JSON root must be an object: {path}")
    return value


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _safe_id(value: str, *, label: str) -> str:
    normalized = str(value or "").strip()
    if (
        not normalized
        or normalized in {".", ".."}
        or "/" in normalized
        or "\\" in normalized
    ):
        raise CreatorAvatarError(f"invalid {label}: {value!r}")
    return normalized


def _safe_relative(value: str, *, label: str) -> Path:
    normalized = str(value or "").strip().strip("/")
    relative = Path(normalized)
    if (
        not normalized
        or relative.is_absolute()
        or ".." in relative.parts
        or any(part in {"", "."} for part in relative.parts)
    ):
        raise CreatorAvatarError(f"unsafe {label}: {value!r}")
    return relative


def _profile_path(creator_ref: str) -> Path:
    matches: list[Path] = []
    profiles = CONTROL_PLANE_CREATOR_POOL_ROOT / "profiles"
    for path in sorted(profiles.rglob("*.creator.yaml")):
        try:
            value = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise CreatorAvatarError(
                f"creator profile unreadable: {path}: {exc}"
            ) from exc
        if (
            isinstance(value, Mapping)
            and str(value.get("creatorProfileId") or "") == creator_ref
        ):
            matches.append(path)
    if len(matches) != 1:
        raise CreatorAvatarError(
            f"creator profile must resolve exactly once: {creator_ref}: found={len(matches)}"
        )
    return matches[0]


def _source_root(source_object_ref: str) -> tuple[Path, Path]:
    relative = _safe_relative(source_object_ref, label="source-object-ref")
    if len(relative.parts) < 2 or relative.parts[0] not in {"entities", "posts"}:
        raise CreatorAvatarError(
            "source-object-ref must identify a canonical entities/** or posts/** object"
        )
    root = PUBLISH_ROOT / relative
    if not root.is_dir() or root.is_symlink():
        raise CreatorAvatarError(
            f"canonical source object missing: {relative.as_posix()}"
        )
    return root, relative


def _source_asset(
    source_root: Path,
    *,
    source_asset_id: str,
) -> tuple[dict[str, Any], Path, bytes, str]:
    refs_paths = [
        path
        for path in (source_root / "asset.refs.json", source_root / "assets.refs.json")
        if path.is_file()
    ]
    if len(refs_paths) != 1:
        raise CreatorAvatarError(
            "source object must own exactly one asset refs document"
        )
    assets = _read_json(refs_paths[0]).get("assets")
    matches = (
        [
            row
            for row in assets or []
            if isinstance(row, dict)
            and str(row.get("assetId") or "") == source_asset_id
        ]
        if isinstance(assets, list)
        else []
    )
    if len(matches) != 1:
        raise CreatorAvatarError(
            f"source asset must resolve exactly once: {source_asset_id}: found={len(matches)}"
        )
    row = dict(matches[0])
    digest = str(row.get("sha256") or "")
    object_key = str(row.get("objectKey") or "")
    byte_count = row.get("bytes")
    if (
        not is_cas_media_object_key(object_key)
        or not digest.startswith("sha256:")
        or not isinstance(byte_count, int)
        or isinstance(byte_count, bool)
        or byte_count <= 0
    ):
        raise CreatorAvatarError("source asset does not bind canonical CAS identity")
    physical = PUBLISH_ROOT / _safe_relative(object_key, label="source objectKey")
    if physical.is_symlink() or not physical.is_file():
        raise CreatorAvatarError(f"source CAS bytes missing: {object_key}")
    body = physical.read_bytes()
    if len(body) != byte_count or _sha256_bytes(body) != digest:
        raise CreatorAvatarError(f"source CAS bytes drifted: {object_key}")
    return row, physical, body, object_key


def _source_rights(
    source_root: Path,
    *,
    source_asset_id: str,
    source_digest: str,
) -> tuple[dict[str, Any], Path, bytes, str]:
    matches: list[tuple[dict[str, Any], Path]] = []
    for path in sorted((source_root / "rights_snapshots").glob("*.json")):
        document = _read_json(path)
        source_asset = document.get("sourceAsset")
        if (
            str(document.get("assetId") or "") == source_asset_id
            and isinstance(source_asset, Mapping)
            and str(source_asset.get("sha256") or "") == source_digest
        ):
            matches.append((document, path))
    if len(matches) != 1:
        raise CreatorAvatarError(
            f"source rights snapshot must resolve exactly once: {source_asset_id}: "
            f"found={len(matches)}"
        )
    document, path = matches[0]
    body = path.read_bytes()
    try:
        relative = path.relative_to(PUBLISH_ROOT).as_posix()
    except ValueError as exc:
        raise CreatorAvatarError(
            "source rights snapshot is outside canonical publish"
        ) from exc
    return document, path, body, relative


def _source_fetched_at(source_root: Path, source_asset_ref: str) -> str:
    relative = _safe_relative(source_asset_ref, label="sourceAssetRef")
    if len(relative.parts) < 3 or relative.parts[0] != "sources":
        raise CreatorAvatarError("source rights snapshot has invalid sourceAssetRef")
    source_unit_id = relative.parts[1]
    sources = _read_json(source_root / "source_catalog.json").get("sources")
    matches = (
        [
            row
            for row in sources or []
            if isinstance(row, Mapping)
            and str(row.get("sourceUnitId") or "") == source_unit_id
        ]
        if isinstance(sources, list)
        else []
    )
    if len(matches) != 1:
        raise CreatorAvatarError(
            f"source catalog timestamp must resolve exactly once: {source_unit_id}"
        )
    fetched_at = str(matches[0].get("fetchedAt") or "").strip()
    if not fetched_at:
        raise CreatorAvatarError("source catalog fetchedAt is missing")
    return fetched_at


def _verified_source_rights(
    document: Mapping[str, object],
    *,
    source_asset_id: str,
    source_digest: str,
) -> Mapping[str, object]:
    if str(document.get("schema") or "") != "quwoquan_data.asset_rights_snapshot":
        raise CreatorAvatarError("source rights snapshot schema is invalid")
    source_asset = document.get("sourceAsset")
    if not isinstance(source_asset, Mapping):
        raise CreatorAvatarError("source rights snapshot is missing sourceAsset")
    if (
        str(document.get("assetId") or "") != source_asset_id
        or str(source_asset.get("sha256") or "") != source_digest
    ):
        raise CreatorAvatarError("source rights snapshot identity drift")
    if (
        str(source_asset.get("rightsAuditStatus") or "") != "verified"
        or source_asset.get("rightsAuditIssues") != []
        or str(source_asset.get("usageScope") or "") != "app_publish"
        or str(source_asset.get("modelReleaseStatus") or "") != "not_required"
    ):
        raise CreatorAvatarError(
            "source asset is not clean app-publish rights evidence"
        )
    required_https = {
        "authorizationProof": source_asset.get("authorizationProof"),
        "termsUrl": source_asset.get("termsUrl"),
    }
    for label, value in required_https.items():
        if not str(value or "").startswith("https://"):
            raise CreatorAvatarError(
                f"source asset {label} is not canonical HTTPS evidence"
            )
    if not str(source_asset.get("license") or "").strip():
        raise CreatorAvatarError("source asset license is missing")
    if not str(source_asset.get("creator") or source_asset.get("credit") or "").strip():
        raise CreatorAvatarError("source asset attribution owner is missing")
    original_url = str(
        source_asset.get("normalizedFromUrl")
        or source_asset.get("requestedUrl")
        or source_asset.get("url")
        or ""
    )
    if not original_url.startswith("https://"):
        raise CreatorAvatarError(
            "source asset original URL is not canonical HTTPS evidence"
        )
    return source_asset


def _page_revision(source_asset: Mapping[str, object], snapshot_digest: str) -> str:
    revision_id = str(source_asset.get("pageRevisionId") or "").strip()
    if revision_id:
        return revision_id
    page_digest = str(source_asset.get("pageContentSha256") or "").strip()
    if len(page_digest) == 64 and all(
        character in "0123456789abcdef" for character in page_digest
    ):
        return f"sha256:{page_digest}"
    return snapshot_digest


def _rights_document(
    *,
    asset_id: str,
    derivative: Mapping[str, object],
    source_asset: Mapping[str, object],
    source_rights_ref: str,
    source_rights_body: bytes,
    fetched_at: str,
) -> dict[str, object]:
    digest = str(derivative["sha256"])
    digest_hex = digest.removeprefix("sha256:")
    author = str(
        source_asset.get("creator") or source_asset.get("credit") or ""
    ).strip()
    credit = str(source_asset.get("credit") or author).strip()
    license_name = str(source_asset.get("license") or "").strip()
    canonical_page = str(
        source_asset.get("authorizationProof") or source_asset.get("sourceUrl") or ""
    )
    original_url = str(
        source_asset.get("normalizedFromUrl")
        or source_asset.get("requestedUrl")
        or source_asset.get("url")
        or ""
    )
    crop_box = derivative["cropBox"]
    modifications = (
        f"deterministic center-square crop {crop_box} from "
        f"{derivative['sourceWidth']}x{derivative['sourceHeight']}; "
        f"RGB; LANCZOS {derivative['width']}x{derivative['height']}; "
        f"WebP quality={derivative['quality']} method={derivative['method']}; "
        f"derivative_policy_version={derivative['policyVersion']}"
    )
    snapshot_digest = _sha256_bytes(source_rights_body)
    return {
        "schema": "quwoquan_data.creator_avatar_rights_snapshot",
        "assetId": asset_id,
        "depictsIdentifiablePerson": False,
        "manifestAsset": {"assetId": asset_id, "sha256": digest},
        "commercialRights": {
            "assetId": asset_id,
            "sourceKind": "creator_avatar_derivative",
            "sourceUseMode": "licensed_adaptation",
            "canonicalFilePage": canonical_page,
            "snapshotUrl": canonical_page,
            "pageRevision": _page_revision(source_asset, snapshot_digest),
            "originalAssetUrl": original_url,
            "author": author,
            "source": canonical_page,
            "licenseName": license_name,
            "licenseShortName": license_name,
            "licenseUrl": str(source_asset.get("termsUrl") or ""),
            "usageScope": "app_publish",
            "attribution": f"{credit} / {license_name}",
            "caption": str(source_asset.get("caption") or ""),
            "captionSource": source_rights_ref,
            "modifications": modifications,
            "fetchedAt": fetched_at,
            "snapshot": {
                "ref": source_rights_ref,
                "sha256": snapshot_digest,
                "bytes": len(source_rights_body),
            },
            "asset": {
                "ref": f"cas/{digest_hex}.webp",
                "sha256": digest,
                "bytes": derivative["byteSize"],
                "mimeType": derivative["mimeType"],
                "width": derivative["width"],
                "height": derivative["height"],
            },
            "authorizationProof": canonical_page,
            "modelReleaseStatus": "not_required",
            "rightsAuditStatus": "verified",
            "rightsAuditIssues": [],
        },
    }


def materialize_creator_avatar(
    *,
    creator_ref: str,
    source_object_ref: str,
    source_asset_id: str,
    confirm_non_identifiable_person: bool,
) -> dict[str, object]:
    """Derive, attest and project one creator avatar through canonical seams."""

    creator_ref = _safe_id(creator_ref, label="creator-ref")
    source_asset_id = _safe_id(source_asset_id, label="source-asset-id")
    if not confirm_non_identifiable_person:
        raise CreatorAvatarError(
            "--confirm-non-identifiable-person is required for model-release closure"
        )
    profile_path = _profile_path(creator_ref)
    source_root, source_relative = _source_root(source_object_ref)
    source_row, _, source_body, source_object_key = _source_asset(
        source_root,
        source_asset_id=source_asset_id,
    )
    source_digest = str(source_row["sha256"])
    rights, _, source_rights_body, source_rights_ref = _source_rights(
        source_root,
        source_asset_id=source_asset_id,
        source_digest=source_digest,
    )
    source_rights = _verified_source_rights(
        rights,
        source_asset_id=source_asset_id,
        source_digest=source_digest,
    )
    if source_rights.get("bytes") != len(source_body):
        raise CreatorAvatarError("source rights byte identity drift")
    fetched_at = _source_fetched_at(
        source_root,
        str(rights.get("sourceAssetRef") or ""),
    )
    derivative = build_center_square_cover_derivative(source_body)
    if derivative is None:
        raise CreatorAvatarError(
            "source image cannot produce the canonical center-square cover without upscale"
        )
    digest = str(derivative["sha256"])
    digest_hex = digest.removeprefix("sha256:")
    asset_id = f"creator-avatar-{creator_ref}-{digest_hex[:16]}"
    object_key = (
        f"media/objects/sha256/{digest_hex[:2]}/{digest_hex[2:4]}/{digest_hex}.webp"
    )
    rights_document = _rights_document(
        asset_id=asset_id,
        derivative=derivative,
        source_asset=source_rights,
        source_rights_ref=source_rights_ref,
        source_rights_body=source_rights_body,
        fetched_at=fetched_at,
    )
    try:
        assert_valid(
            rights_document,
            "release",
            "creator_avatar_rights_snapshot",
            label=f"creator avatar rights {creator_ref}",
        )
    except (FileNotFoundError, ValueError) as exc:
        raise CreatorAvatarError(str(exc)) from exc
    rights_issue = creator_avatar_rights_issue(
        rights_document,
        asset_id=asset_id,
        sha256=digest,
        object_key=object_key,
        byte_count=int(derivative["byteSize"]),
        mime_type=str(derivative["mimeType"]),
    )
    if rights_issue:
        raise CreatorAvatarError(f"derived avatar rights invalid: {rights_issue}")

    rights_ref = f"evidence/avatar_rights/{creator_ref}/{digest_hex}.json"
    avatar_asset = {
        "assetId": asset_id,
        "kind": "avatar",
        "sha256": digest,
        "objectKey": object_key,
        "bytes": int(derivative["byteSize"]),
        "mimeType": str(derivative["mimeType"]),
        "rightsSnapshotRef": rights_ref,
    }
    created = persist_creator_avatar(
        creator_ref=creator_ref,
        profile_path=profile_path,
        publish_root=PUBLISH_ROOT,
        creator_pool_root=CONTROL_PLANE_CREATOR_POOL_ROOT,
        object_key=object_key,
        derivative_body=derivative["bytes"],
        rights_ref=rights_ref,
        rights_document=rights_document,
        avatar_asset=avatar_asset,
    )

    return {
        "schema": "quwoquan_data.creator_avatar_materialization",
        "creatorRef": creator_ref,
        "sourceObjectRef": source_relative.as_posix(),
        "sourceAssetId": source_asset_id,
        "sourceSha256": source_digest,
        "sourceObjectKey": source_object_key,
        "sourceRightsSnapshotRef": source_rights_ref,
        "assetId": asset_id,
        "sha256": digest,
        "objectKey": object_key,
        "rightsSnapshotRef": rights_ref,
        "cropBox": derivative["cropBox"],
        "sourceDimensions": [
            derivative["sourceWidth"],
            derivative["sourceHeight"],
        ],
        "dimensions": [derivative["width"], derivative["height"]],
        "mimeType": derivative["mimeType"],
        "policyVersion": derivative["policyVersion"],
        "created": created,
        "idempotent": not any(created.values()),
    }


__all__ = [
    "CreatorAvatarError",
    "materialize_creator_avatar",
]
