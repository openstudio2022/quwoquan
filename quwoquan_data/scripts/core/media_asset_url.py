"""自治对象包 CAS 引用校验与 immutable release media manifest。"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import yaml

from core.paths import PUBLISH_ROOT, RELEASE_ROOT, REPO_ROOT
from core.release_layout import payload_file
from core.schema import assert_valid

_CAS_RE = re.compile(
    r"^media/objects/sha256/([0-9a-f]{2})/([0-9a-f]{2})/([0-9a-f]{64})(\.[a-z0-9]+)?$"
)
_SHA256_RE = re.compile(r"^sha256:([0-9a-f]{64})$")
_PUBLIC_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_PUBLIC_SLICE_RE = re.compile(
    r"^media/(avatar|image|video)/s/asset/[A-Za-z0-9][A-Za-z0-9._-]*/"
    r"v([1-9][0-9]*)/source\.[a-z0-9]+$"
)
_MEDIA_KIND_BY_SUFFIX = {
    ".gif": "image",
    ".jpeg": "image",
    ".jpg": "image",
    ".png": "image",
    ".webp": "image",
    ".mp4": "video",
    ".webm": "video",
}
_CONTENT_TYPE_BY_SUFFIX = {
    ".gif": "image/gif",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
}
_SUFFIX_BY_CONTENT_TYPE = {
    "image/gif": ".gif",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
}
_IMAGE_VARIANT_POLICY = (
    REPO_ROOT
    / "quwoquan_service"
    / "services"
    / "content-service"
    / "contracts"
    / "media"
    / "media_asset"
    / "image_variant_policy.yaml"
)
_REQUIRED_IMAGE_VARIANT_PROFILES = frozenset(
    {"thumbnail", "display", "cover", "full"}
)
def _load_image_variant_policy() -> tuple[int, dict[str, dict[str, Any]]]:
    document = yaml.safe_load(_IMAGE_VARIANT_POLICY.read_text(encoding="utf-8")) or {}
    if document.get("schema") != "content_image_variant_policy":
        raise ValueError("content image variant policy schema is invalid")
    version = int(document.get("derivative_policy_version") or 0)
    profiles = document.get("profiles")
    if version <= 0 or not isinstance(profiles, dict):
        raise ValueError("content image variant policy is incomplete")
    normalized: dict[str, dict[str, Any]] = {}
    for name in sorted(_REQUIRED_IMAGE_VARIANT_PROFILES):
        profile = profiles.get(name)
        if not isinstance(profile, dict):
            raise TypeError(f"content image variant profile is missing: {name}")
        width = int(profile.get("width") or 0)
        quality = int(profile.get("quality") or 0)
        image_format = str(profile.get("format") or "").strip()
        scene = str(profile.get("scene") or "").strip()
        processing = str(profile.get("processing") or "").strip()
        if width <= 0 or not 1 <= quality <= 100 or not image_format or not scene or not processing:
            raise ValueError(f"content image variant profile is invalid: {name}")
        normalized[name] = {
            "width": width,
            "format": image_format,
            "quality": quality,
            "scene": scene,
            "processing": processing,
        }
    if set(profiles) != _REQUIRED_IMAGE_VARIANT_PROFILES:
        raise ValueError("content image variant policy has unexpected profiles")
    return version, normalized


IMAGE_VARIANT_POLICY_VERSION, IMAGE_VARIANT_PROFILES = _load_image_variant_policy()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def is_cas_media_object_key(object_key: str) -> bool:
    match = _CAS_RE.fullmatch(str(object_key))
    return bool(
        match
        and match.group(1) == match.group(3)[:2]
        and match.group(2) == match.group(3)[2:4]
    )


def is_public_media_slice_key(public_slice_key: str) -> bool:
    """Return whether a key is a kind-scoped public delivery identity."""
    return _PUBLIC_SLICE_RE.fullmatch(str(public_slice_key)) is not None


def _public_asset_segment(asset_id: str) -> str:
    value = str(asset_id).strip()
    if not value or any(character.isspace() for character in value):
        return ""
    if "/" in value or "\\" in value or any(ord(character) < 32 for character in value):
        return ""
    if _PUBLIC_ID_RE.fullmatch(value):
        return value
    # Historical Data asset IDs contain Chinese display text. Keep the logical
    # assetId unchanged in the manifest while deriving an ASCII path segment.
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"unicode-{digest[:32]}"


def build_public_media_slice_key(
    *,
    asset_id: str,
    kind: str,
    version: int,
    content_type: str,
) -> str:
    """Derive the public slice without accepting a private storage key."""
    normalized_kind = str(kind).strip().lower()
    normalized_type = str(content_type).split(";", 1)[0].strip().lower()
    segment = _public_asset_segment(asset_id)
    suffix = _SUFFIX_BY_CONTENT_TYPE.get(normalized_type, "")
    if normalized_kind not in {"avatar", "image", "video"} or not segment or not suffix:
        return ""
    if normalized_kind == "video" and not normalized_type.startswith("video/"):
        return ""
    if normalized_kind in {"avatar", "image"} and not normalized_type.startswith("image/"):
        return ""
    if version <= 0:
        return ""
    return f"media/{normalized_kind}/s/asset/{segment}/v{version}/source{suffix}"


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"JSON 顶层必须为 object: {path}")
    return value


def _asset_rows(root: Path) -> Iterable[dict[str, Any]]:
    paths = [
        path
        for path in (root / "asset.refs.json", root / "assets.refs.json")
        if path.is_file()
    ]
    if not paths:
        return
    if len(paths) != 1:
        raise ValueError(f"object must own exactly one asset refs document: {root}")
    path = paths[0]
    for row in _read_json(path).get("assets") or []:
        if isinstance(row, dict):
            yield row


def _manifest_asset_rows(root: Path) -> dict[str, dict[str, Any]]:
    path = root / "manifest.json"
    if not path.is_file():
        return {}
    manifest = _read_json(path)
    candidates: list[object] = list(manifest.get("assets") or [])
    article_manifest = manifest.get("articleAssetManifest")
    if isinstance(article_manifest, Mapping):
        candidates.extend(article_manifest.get("assets") or [])
    result: dict[str, dict[str, Any]] = {}
    for row in candidates:
        if not isinstance(row, dict):
            continue
        asset_id = str(row.get("assetId") or "").strip()
        if asset_id:
            result[asset_id] = row
    return result


def _asset_kind(
    *,
    object_kind: str,
    object_key: str,
    metadata: Mapping[str, Any],
) -> str:
    declared = str(metadata.get("kind") or "").strip().lower()
    if declared in {"avatar", "image", "video"}:
        return declared
    if object_kind == "creators":
        return "avatar"
    return _MEDIA_KIND_BY_SUFFIX.get(Path(object_key).suffix.lower(), "")


def _asset_content_type(object_key: str, metadata: Mapping[str, Any]) -> str:
    declared = str(metadata.get("mimeType") or "").split(";", 1)[0].strip().lower()
    if declared in _SUFFIX_BY_CONTENT_TYPE:
        return declared
    return _CONTENT_TYPE_BY_SUFFIX.get(Path(object_key).suffix.lower(), "")


def _rights_snapshot_refs(
    *,
    object_kind: str,
    object_ref: str,
    object_root: Path,
    asset_id: str,
    sha256: str,
) -> tuple[list[str], list[str]]:
    refs: list[str] = []
    issues: list[str] = []
    snapshots = object_root / "rights_snapshots"
    if not snapshots.is_dir():
        return refs, [
            f"rights snapshots missing: {object_kind}/{object_ref}:{asset_id}"
        ]
    for path in sorted(snapshots.glob("*.json")):
        document = _read_json(path)
        if str(document.get("assetId") or "").strip() != asset_id:
            continue
        manifest_asset = document.get("manifestAsset")
        if not isinstance(manifest_asset, Mapping):
            issues.append(f"rights snapshot lacks manifestAsset: {object_kind}/{object_ref}:{path.name}")
            continue
        source_asset = document.get("sourceAsset")
        snapshot_sha256 = str(manifest_asset.get("sha256") or "").strip()
        if not snapshot_sha256 and isinstance(source_asset, Mapping):
            snapshot_sha256 = str(source_asset.get("sha256") or "").strip()
        if (
            str(manifest_asset.get("assetId") or "").strip() != asset_id
            or snapshot_sha256 != sha256
        ):
            issues.append(f"rights snapshot identity mismatch: {object_kind}/{object_ref}:{path.name}")
            continue
        refs.append(
            f"objects/{object_kind}/{object_ref.removeprefix(f'{object_kind}/')}/"
            f"rights_snapshots/{path.name}"
        )
    if not refs:
        issues.append(
            f"rights snapshot binding missing: {object_kind}/{object_ref}:{asset_id}"
        )
    return refs, issues


def _object_root(canonical: Path, kind: str, ref: str) -> Path:
    return canonical / kind / ref.removeprefix(f"{kind}/")


def build_release_media_manifest(
    *,
    release_id: str,
    post_refs: list[str],
    entity_refs: list[str],
    creator_refs: list[str] | None = None,
    publish_root: Path | None = None,
    object_root: Path | None = None,
    media_root: Path | None = None,
    source_owner: str = "qwq_data",
) -> dict[str, Any]:
    """Build the public MediaAsset closure for one immutable release.

    A release is an object closure, not a snapshot of the whole canonical media
    library. Private CAS keys are read only while packaging and are deliberately
    absent from the returned contract.
    """
    canonical = publish_root or PUBLISH_ROOT
    objects = object_root or canonical
    media = media_root or canonical
    assets: dict[str, dict[str, Any]] = {}
    slice_owners: dict[str, str] = {}
    issues: list[str] = []
    for kind, refs in (
        ("creators", creator_refs or []),
        ("posts", post_refs),
        ("entities", entity_refs),
    ):
        for ref in refs:
            selected_object = _object_root(objects, kind, ref)
            if not selected_object.is_dir():
                issues.append(f"object missing: {kind}/{ref}")
                continue
            manifest_assets = _manifest_asset_rows(selected_object)
            for row in _asset_rows(selected_object):
                asset_id = str(row.get("assetId") or "").strip()
                object_key = str(row.get("objectKey") or "")
                expected = str(row.get("sha256") or "")
                if not asset_id:
                    issues.append(f"assetId missing: {kind}/{ref}")
                    continue
                if not is_cas_media_object_key(object_key):
                    issues.append(f"non-CAS objectKey: {kind}/{ref}:{object_key}")
                    continue
                sha_match = _SHA256_RE.fullmatch(expected)
                if sha_match is None:
                    issues.append(f"sha256 invalid: {kind}/{ref}:{asset_id}")
                    continue
                physical = media / object_key
                if not physical.is_file():
                    issues.append(f"CAS object missing: {object_key}")
                    continue
                actual = sha256_file(physical)
                if expected and actual != expected:
                    issues.append(
                        f"CAS hash mismatch: {object_key} expected={expected} actual={actual}"
                    )
                    continue
                metadata = manifest_assets.get(asset_id, row)
                metadata_key = str(metadata.get("objectKey") or "").strip()
                metadata_sha = str(metadata.get("sha256") or "").strip()
                if metadata_key and metadata_key != object_key:
                    issues.append(f"asset objectKey drift: {kind}/{ref}:{asset_id}")
                    continue
                if metadata_sha and metadata_sha != actual:
                    issues.append(f"asset sha256 drift: {kind}/{ref}:{asset_id}")
                    continue
                asset_kind = _asset_kind(
                    object_kind=kind,
                    object_key=object_key,
                    metadata=metadata,
                )
                content_type = _asset_content_type(object_key, metadata)
                public_slice_key = build_public_media_slice_key(
                    asset_id=asset_id,
                    kind=asset_kind,
                    version=1,
                    content_type=content_type,
                )
                if not public_slice_key:
                    issues.append(f"public slice unresolved: {kind}/{ref}:{asset_id}")
                    continue
                owner_ref = f"{kind}/{ref.removeprefix(f'{kind}/')}"
                rights_refs, rights_issues = _rights_snapshot_refs(
                    object_kind=kind,
                    object_ref=ref,
                    object_root=selected_object,
                    asset_id=asset_id,
                    sha256=actual,
                )
                issues.extend(rights_issues)
                normalized = {
                    "assetId": asset_id,
                    "kind": asset_kind,
                    "version": 1,
                    "contentType": content_type,
                    "publicSliceKey": public_slice_key,
                    "sha256": actual,
                    "bytes": physical.stat().st_size,
                    "ownerRefs": [owner_ref],
                    "rightsSnapshotRefs": rights_refs,
                }
                old = assets.get(asset_id)
                if old is not None:
                    comparable_fields = (
                        "kind",
                        "version",
                        "contentType",
                        "publicSliceKey",
                        "sha256",
                        "bytes",
                    )
                    if any(old[field] != normalized[field] for field in comparable_fields):
                        issues.append(f"MediaAsset identity collision: {asset_id}")
                        continue
                    old["ownerRefs"] = sorted({*old["ownerRefs"], owner_ref})
                    old["rightsSnapshotRefs"] = sorted(
                        {*old["rightsSnapshotRefs"], *rights_refs}
                    )
                    continue
                other_asset_id = slice_owners.get(public_slice_key)
                if other_asset_id is not None and other_asset_id != asset_id:
                    issues.append(
                        f"public slice collision: {public_slice_key}:"
                        f"{other_asset_id},{asset_id}"
                    )
                    continue
                assets[asset_id] = normalized
                slice_owners[public_slice_key] = asset_id
    manifest = {
        "schema": "quwoquan_data.release_media_manifest",
        "releaseId": release_id,
        "sourceOwner": source_owner,
        "assets": [assets[key] for key in sorted(assets)],
        "issues": issues,
        "counts": {"assets": len(assets), "issues": len(issues)},
    }
    assert_valid(
        manifest,
        "release",
        "media_manifest",
        label=f"release_media_manifest:{release_id}",
    )
    return manifest


def _private_cas_path(source_root: Path, sha256: str) -> Path:
    match = _SHA256_RE.fullmatch(str(sha256))
    if match is None:
        raise ValueError(f"invalid release media sha256: {sha256}")
    digest = match.group(1)
    parent = source_root / "media/objects/sha256" / digest[:2] / digest[2:4]
    matches = sorted(path for path in parent.glob(f"{digest}.*") if path.is_file())
    if len(matches) != 1:
        raise ValueError(
            f"release media private CAS identity must resolve exactly once: {sha256}"
        )
    return matches[0]


def copy_release_media_objects(
    *,
    manifest: Mapping[str, Any],
    source_root: Path,
    release_root: Path,
) -> None:
    """Materialize private CAS bytes at public slice paths in the release."""
    assets = manifest.get("assets")
    if not isinstance(assets, list):
        raise TypeError("release media manifest assets must be an array")
    for index, row in enumerate(assets):
        if not isinstance(row, Mapping):
            raise TypeError(f"release media manifest assets[{index}] must be an object")
        public_slice_key = str(row.get("publicSliceKey") or "")
        expected = str(row.get("sha256") or "")
        if not is_public_media_slice_key(public_slice_key):
            raise ValueError(f"invalid release media publicSliceKey: {public_slice_key}")
        source = _private_cas_path(source_root, expected)
        if not source.is_file() or sha256_file(source) != expected:
            raise ValueError(f"release media source is missing or corrupt: {expected}")
        target = payload_file(release_root, public_slice_key)
        if target.is_file():
            if sha256_file(target) != expected:
                raise FileExistsError(f"immutable release media conflict: {target}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".copy-tmp")
        shutil.copy2(source, temporary)
        if sha256_file(temporary) != expected:
            temporary.unlink(missing_ok=True)
            raise ValueError(
                f"release media post-copy hash mismatch: {public_slice_key}"
            )
        temporary.replace(target)


def materialize_release_media(
    *,
    release_id: str,
    post_refs: list[str],
    entity_refs: list[str],
    creator_refs: list[str] | None = None,
    publish_root: Path | None = None,
    release_root: Path | None = None,
    source_owner: str = "qwq_data",
) -> dict[str, Any]:
    """Freeze the exact canonical CAS closure into one release payload."""
    release = (release_root or RELEASE_ROOT) / release_id
    manifest = build_release_media_manifest(
        release_id=release_id,
        post_refs=post_refs,
        entity_refs=entity_refs,
        creator_refs=creator_refs,
        publish_root=publish_root,
        source_owner=source_owner,
    )
    if manifest["issues"]:
        return manifest
    copy_release_media_objects(
        manifest=manifest,
        source_root=publish_root or PUBLISH_ROOT,
        release_root=release,
    )
    target = payload_file(release, "media_manifest.json")
    payload = _json_bytes(manifest)
    if target.exists():
        if target.read_bytes() != payload:
            raise FileExistsError(f"immutable release media manifest conflict: {target}")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    return manifest
