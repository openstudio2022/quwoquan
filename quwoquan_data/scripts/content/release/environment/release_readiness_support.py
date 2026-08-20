"""Immutable release graph and readback assertion helpers."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from core.io import read_json
from core.release_layout import objects_merkle, payload_file


class ReleaseReadinessClosureError(ValueError):
    """The release graph and its environment readback do not close exactly."""


def _object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = read_json(path)
    except (OSError, TypeError, ValueError) as exc:
        raise ReleaseReadinessClosureError(f"{label} is unreadable: {path}") from exc
    if not isinstance(value, Mapping):
        raise ReleaseReadinessClosureError(f"{label} must be an object: {path}")
    return dict(value)


def _text(value: object, *, label: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ReleaseReadinessClosureError(f"{label} must be non-empty")
    return result


def _normalized_ref(value: object, *, kind: str) -> str:
    result = _text(value, label=f"{kind} ref").strip("/")
    singular = {
        "creators": "creator",
        "entities": "entity",
        "posts": "post",
        "tags": "tag",
    }.get(kind)
    if singular is None:
        raise ReleaseReadinessClosureError(f"unsupported release object kind: {kind}")
    prefixes = (f"{kind}/", f"{singular}/")
    for prefix in prefixes:
        if result.startswith(prefix):
            result = result[len(prefix) :]
            break
    if not result or ".." in Path(result).parts:
        raise ReleaseReadinessClosureError(f"unsafe {kind} ref: {value}")
    return result


def _url_slice(value: object, *, label: str, allow_query: bool = False) -> str:
    parsed = urlsplit(_text(value, label=label))
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or (parsed.query and not allow_query)
        or parsed.fragment
    ):
        raise ReleaseReadinessClosureError(f"{label} must be one canonical HTTPS URL")
    return parsed.path.lstrip("/")


def _media_rows(media_manifest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    assets = media_manifest.get("assets")
    issues = media_manifest.get("issues")
    counts = media_manifest.get("counts")
    if not isinstance(assets, list) or not isinstance(issues, list) or issues:
        raise ReleaseReadinessClosureError(
            "release media manifest must contain an issue-free asset array"
        )
    if (
        not isinstance(counts, Mapping)
        or counts.get("assets") != len(assets)
        or counts.get("issues") != len(issues)
    ):
        raise ReleaseReadinessClosureError("release media manifest counts drift")
    result: dict[str, dict[str, Any]] = {}
    for raw in assets:
        if not isinstance(raw, Mapping):
            raise ReleaseReadinessClosureError("release media asset must be an object")
        row = dict(raw)
        asset_id = _text(row.get("assetId"), label="release media assetId")
        if asset_id in result:
            raise ReleaseReadinessClosureError(
                f"release media assetId is duplicated: {asset_id}"
            )
        result[asset_id] = row
    if not result:
        raise ReleaseReadinessClosureError("release media manifest must not be empty")
    return result


def _assert_media_rights_closure(
    *,
    release_root: Path,
    media_by_id: Mapping[str, Mapping[str, Any]],
    desired: Mapping[str, list[str]],
) -> None:
    allowed_owners = {
        f"{kind}/{_normalized_ref(ref, kind=kind)}"
        for kind in ("creators", "entities", "posts")
        for ref in desired[kind]
    }
    for asset_id, asset in media_by_id.items():
        owner_refs = asset.get("ownerRefs")
        rights_refs = asset.get("rightsSnapshotRefs")
        if (
            not isinstance(owner_refs, list)
            or not owner_refs
            or len(owner_refs) != len(set(owner_refs))
            or not set(owner_refs).issubset(allowed_owners)
            or not isinstance(rights_refs, list)
            or not rights_refs
            or len(rights_refs) != len(set(rights_refs))
        ):
            raise ReleaseReadinessClosureError(
                f"release media owner/rights refs are not canonical: {asset_id}"
            )
        owners_with_rights: set[str] = set()
        for raw_ref in rights_refs:
            rights_ref = str(raw_ref or "").strip()
            candidate = Path(rights_ref)
            marker = "/rights_snapshots/"
            if (
                candidate.is_absolute()
                or candidate.as_posix() != rights_ref
                or ".." in candidate.parts
                or not rights_ref.startswith("objects/")
                or marker not in rights_ref
                or not rights_ref.endswith(".json")
            ):
                raise ReleaseReadinessClosureError(
                    f"release media rights ref is not canonical: {asset_id}"
                )
            owner = rights_ref.removeprefix("objects/").split(marker, 1)[0]
            if owner not in owner_refs:
                raise ReleaseReadinessClosureError(
                    f"release media rights owner drifts: {asset_id}"
                )
            rights = _object(
                payload_file(release_root, rights_ref),
                label=f"release media rights snapshot {asset_id}",
            )
            manifest_asset = rights.get("manifestAsset")
            if (
                rights.get("assetId") != asset_id
                or not isinstance(manifest_asset, Mapping)
                or manifest_asset.get("assetId") != asset_id
                or manifest_asset.get("sha256") != asset.get("sha256")
            ):
                raise ReleaseReadinessClosureError(
                    f"release media rights identity drifts: {asset_id}"
                )
            owners_with_rights.add(owner)
        if owners_with_rights != set(owner_refs):
            raise ReleaseReadinessClosureError(
                f"release media owner lacks rights snapshot: {asset_id}"
            )


def _assert_attestation_projection(
    *,
    release_root: Path,
    header: Mapping[str, Any],
    attestation: Mapping[str, Any],
    desired: Mapping[str, list[str]],
) -> None:
    projected_fields = (
        "releaseId",
        "sourceOwner",
        "releaseKind",
        "releaseClass",
        "productLifecycleState",
        "containsUnverifiedAssets",
        "rightsStatusCounts",
        "authorizationRequiredAssetIds",
        "researchAcceptedCount",
        "commercialAcceptedCount",
        "executionIds",
        "canonicalMerkle",
        "sourceRevision",
        "sourceDigest",
        "entityCatalogDigest",
        "sourceDigests",
    )
    drifted = [
        field
        for field in projected_fields
        if attestation.get(field) != header.get(field)
    ]
    if drifted:
        raise ReleaseReadinessClosureError(
            "release attestation/header projection drift: " + ", ".join(drifted)
        )
    expected_counts = {
        "entityCount": len(desired["entities"]),
        "postCount": len(desired["posts"]),
        "creatorCount": len(desired["creators"]),
        "tagCount": len(desired["tags"]),
    }
    if any(attestation.get(field) != value for field, value in expected_counts.items()):
        raise ReleaseReadinessClosureError(
            "release attestation object counts drift from desiredRefs"
        )
    actual_merkle = objects_merkle(release_root)
    if header.get("canonicalMerkle") != actual_merkle:
        raise ReleaseReadinessClosureError(
            "release canonicalMerkle drifts from immutable object closure"
        )


def _assert_import_counts(
    *,
    import_report: Mapping[str, Any],
    creator_report: Mapping[str, Any],
    desired: Mapping[str, list[str]],
) -> None:
    content_counts = import_report.get("counts")
    creator_counts = creator_report.get("counts")
    if not isinstance(content_counts, Mapping) or (
        content_counts.get("postsLoaded") != len(desired["posts"])
        or content_counts.get("entitiesLoaded") != len(desired["entities"])
    ):
        raise ReleaseReadinessClosureError(
            "content import counts drift from immutable desiredRefs"
        )
    if not isinstance(creator_counts, Mapping) or creator_counts.get(
        "creatorsLoaded"
    ) != len(desired["creators"]):
        raise ReleaseReadinessClosureError(
            "creator import counts drift from immutable desiredRefs"
        )


def _assert_probe_matches_asset(
    *,
    probe: Mapping[str, Any],
    asset: Mapping[str, Any],
    require_full_hash: bool,
) -> None:
    asset_id = _text(asset.get("assetId"), label="release media assetId")
    expected_kind = "video" if asset.get("kind") == "video" else "image"
    expected_fields_present = "expectedBytes" in probe or "expectedSha256" in probe
    if (
        (
            probe.get("kind") != expected_kind
            and not (asset.get("kind") == "avatar" and "kind" not in probe)
        )
        or (
            expected_fields_present
            and (
                probe.get("expectedBytes") != asset.get("bytes")
                or probe.get("expectedSha256") != asset.get("sha256")
            )
        )
        or probe.get("mimeType") != asset.get("contentType")
        or _url_slice(
            probe.get("publicUrl"),
            label=f"media probe URL {asset_id}",
            allow_query=asset.get("kind") == "avatar",
        )
        != asset.get("publicSliceKey")
    ):
        raise ReleaseReadinessClosureError(
            f"media probe drifts from release authority: {asset_id}"
        )
    if require_full_hash:
        if (
            probe.get("status") != 200
            or probe.get("hashVerified") is not True
            or probe.get("bytes") != asset.get("bytes")
            or probe.get("sha256") != asset.get("sha256")
        ):
            raise ReleaseReadinessClosureError(
                f"image probe lacks full release identity: {asset_id}"
            )
    elif (
        not expected_fields_present
        or probe.get("status") != 206
        or probe.get("hashVerified") is not False
        or not str(probe.get("mimeType") or "").startswith("video/")
        or int(probe.get("bytes") or 0) <= 0
        or int(probe.get("bytes") or 0) > int(asset.get("bytes") or 0)
    ):
        raise ReleaseReadinessClosureError(
            f"video probe lacks playable byte-range evidence: {asset_id}"
        )


__all__ = [
    "ReleaseReadinessClosureError",
    "_assert_attestation_projection",
    "_assert_import_counts",
    "_assert_media_rights_closure",
    "_assert_probe_matches_asset",
    "_media_rows",
    "_normalized_ref",
    "_object",
    "_text",
    "_url_slice",
]
