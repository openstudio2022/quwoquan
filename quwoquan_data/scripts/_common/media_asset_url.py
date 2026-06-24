"""Media asset URL contract helpers.

This module is the data-side source of truth for translating local publish
assets into environment-scoped object keys and CDN URLs. Markdown keeps
`asset://` logical references; publish artifacts carry the resolved manifest.
"""
from __future__ import annotations

import hashlib
import mimetypes
import shutil
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

from _common.io import read_json, write_json
from _common.paths import NOW_ISO, PUBLISH_ROOT

MEDIA_SCHEMA_VERSION = "quwoquan.media_asset_manifest.v1"
COLLISION_LEDGER_SCHEMA_VERSION = "quwoquan.media_collision_ledger.v1"

IMAGE_VARIANT_PROFILES: dict[str, dict[str, Any]] = {
    "thumbnail": {
        "width": 320,
        "format": "webp",
        "quality": 80,
        "scene": "feed_grid",
        "processing": "image/resize,w_320/format,webp/quality,q_80",
    },
    "display": {
        "width": 960,
        "format": "webp",
        "quality": 82,
        "scene": "article_body",
        "processing": "image/resize,w_960/format,webp/quality,q_82",
    },
    "cover": {
        "width": 1280,
        "format": "webp",
        "quality": 85,
        "scene": "feed_cover",
        "processing": "image/resize,w_1280/format,webp/quality,q_85",
    },
    "full": {
        "width": 2048,
        "format": "webp",
        "quality": 90,
        "scene": "immersive_viewer",
        "processing": "image/resize,w_2048/format,webp/quality,q_90",
    },
}

VIDEO_VARIANT_PROFILES: dict[str, dict[str, Any]] = {
    "adaptive": {
        "format": "adaptive",
        "scene": "video_playback",
        "fallbackToOriginal": True,
    },
    "original": {
        "format": "source",
        "scene": "original_access",
        "requiresAccess": True,
    },
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def _sha256_hex(value: str) -> str:
    raw = value.strip()
    if raw.startswith("sha256:"):
        raw = raw[len("sha256:") :]
    return raw.lower()


def _sha256_shards(sha256: str) -> tuple[str, str, str]:
    raw = _sha256_hex(sha256)
    if len(raw) != 64:
        raise ValueError(f"invalid sha256 digest: {sha256}")
    return raw[:2], raw[2:4], raw


def slug(value: str, *, fallback: str = "asset") -> str:
    out = []
    last_sep = False
    for ch in value.strip():
        if ch.isalnum() or "\u4e00" <= ch <= "\u9fff":
            out.append(ch)
            last_sep = False
        elif not last_sep:
            out.append("_")
            last_sep = True
    normalized = "".join(out).strip("_")
    return normalized or fallback


def media_kind_for_file(path: Path, explicit: str = "") -> str:
    kind = explicit.strip().lower()
    if kind in {"image", "video", "audio", "file"}:
        return kind
    suffix = path.suffix.lower()
    if suffix in {".mp4", ".mov", ".m4v", ".webm"}:
        return "video"
    if suffix in {".mp3", ".m4a", ".wav", ".aac"}:
        return "audio"
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        return "image"
    return "file"


def canonical_media_extension(path: Path, kind: str, mime_type: str) -> str:
    suffix = path.suffix.lower().lstrip(".")
    normalized_kind = kind.strip().lower()
    normalized_mime = mime_type.strip().lower()
    if normalized_mime == "image/jpeg" or suffix in {"jpeg", "jpg"}:
        return "jpg"
    if normalized_kind == "image" and suffix in {"png", "webp", "gif"}:
        return suffix
    if normalized_kind == "video" and suffix in {"mp4", "mov", "m4v", "webm"}:
        return suffix
    if normalized_kind == "audio" and suffix in {"mp3", "m4a", "wav", "aac"}:
        return suffix
    return suffix or "bin"


def build_object_key(
    *,
    source_owner: str,
    env: str,
    scope: str,
    object_type: str,
    stable_object_ref: str,
    asset_id: str,
    sha256: str,
    ext: str,
    kind: str = "file",
) -> str:
    _ = (source_owner, env, scope, object_type, stable_object_ref, asset_id)
    shard_a, shard_b, full_hash = _sha256_shards(sha256)
    normalized_kind = kind.strip().lower()
    normalized_ext = ext.lower().lstrip(".") or "bin"
    if normalized_kind not in {"image", "video", "audio", "file"}:
        normalized_kind = "file"
    return f"media/objects/sha256/{shard_a}/{shard_b}/{full_hash}.{normalized_ext}"


def is_cas_media_object_key(object_key: str) -> bool:
    normalized = object_key.strip().lstrip("/")
    parts = normalized.split("/")
    if len(parts) != 6:
        return False
    if parts[:3] != ["media", "objects", "sha256"]:
        return False
    if len(parts[3]) != 2 or len(parts[4]) != 2:
        return False
    file_name = parts[5]
    stem = file_name.split(".", 1)[0]
    return len(stem) == 64 and all(ch in "0123456789abcdef" for ch in stem)


def cdn_url_for_object_key(
    object_key: str,
    *,
    kind: str,
    image_cdn_base_url: str,
    video_cdn_base_url: str = "",
) -> str:
    normalized_kind = kind.strip().lower()
    base = (video_cdn_base_url if normalized_kind == "video" else image_cdn_base_url).strip()
    if not base:
        base = "https://media.quwoquan.invalid"
    base = base.rstrip("/")
    encoded_key = quote(object_key.lstrip("/"), safe="/._-")
    return f"{base}/{encoded_key}"


def _append_cdn_processing(url: str, processing: str) -> str:
    if not url or not processing:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}x-oss-process={quote(processing, safe='/_,')}"


def _append_video_cover_query(url: str, cover_frame_time_ms: Any) -> str:
    if not url:
        return url
    frame = int(cover_frame_time_ms or 0)
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}variant=thumb&t={frame}"


def _image_variants_for_object(
    *,
    object_key: str,
    base_cdn_url: str,
    sha256: str,
    mime_type: str,
    width: Any = None,
    height: Any = None,
) -> dict[str, dict[str, Any]]:
    variants: dict[str, dict[str, Any]] = {}
    for profile, cfg in IMAGE_VARIANT_PROFILES.items():
        row = {
            "profile": profile,
            "objectKey": object_key,
            "cdnUrl": _append_cdn_processing(base_cdn_url, str(cfg["processing"])),
            "sourceSha256": sha256,
            "mimeType": "image/webp",
            "format": cfg["format"],
            "quality": cfg["quality"],
            "width": cfg["width"],
            "scene": cfg["scene"],
            "derivativeKind": "cdn_process",
            "processing": cfg["processing"],
        }
        if height not in (None, "") and width not in (None, ""):
            row["sourceWidth"] = width
            row["sourceHeight"] = height
        variants[profile] = row
    variants["original"] = {
        "profile": "original",
        "objectKey": object_key,
        "cdnUrl": "",
        "sourceSha256": sha256,
        "sha256": sha256,
        "mimeType": mime_type,
        "format": "source",
        "requiresAccess": True,
        "scene": "original_access",
    }
    return variants


def _video_variants_for_object(
    *,
    object_key: str,
    base_cdn_url: str,
    sha256: str,
    mime_type: str,
    duration_ms: Any = None,
) -> dict[str, dict[str, Any]]:
    thumbnail_url = _append_video_cover_query(base_cdn_url, 0)
    variants: dict[str, dict[str, Any]] = {
        "thumbnail": {
            "profile": "thumbnail",
            "objectKey": object_key,
            "cdnUrl": thumbnail_url,
            "sourceSha256": sha256,
            "mimeType": mime_type,
            "format": "image",
            "scene": "video_cover",
            "coverStrategy": "first_frame",
            "coverFrameTimeMs": 0,
        },
        "adaptive": {
            "profile": "adaptive",
            "objectKey": object_key,
            "cdnUrl": base_cdn_url,
            "sourceSha256": sha256,
            "mimeType": mime_type,
            "format": "source",
            "scene": "video_playback",
            "fallbackToOriginal": True,
        },
        "original": {
            "profile": "original",
            "objectKey": object_key,
            "cdnUrl": "",
            "sourceSha256": sha256,
            "sha256": sha256,
            "mimeType": mime_type,
            "format": "source",
            "scene": "original_access",
            "requiresAccess": True,
        },
    }
    if duration_ms not in (None, ""):
        variants["thumbnail"]["durationMs"] = duration_ms
        variants["adaptive"]["durationMs"] = duration_ms
        variants["original"]["durationMs"] = duration_ms
    return variants


def _mime_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def _collision_ledger_path(publish_root: Path) -> Path:
    return publish_root / "media" / "collision_ledger.json"


def _load_collision_ledger(publish_root: Path) -> dict[str, Any]:
    path = _collision_ledger_path(publish_root)
    if not path.is_file():
        return {
            "schemaVersion": COLLISION_LEDGER_SCHEMA_VERSION,
            "updatedAt": NOW_ISO,
            "objects": {},
        }
    data = read_json(path)
    if not isinstance(data, dict):
        raise ValueError("collision ledger must be an object")
    if data.get("schemaVersion") not in {None, COLLISION_LEDGER_SCHEMA_VERSION}:
        raise ValueError(f"unsupported collision ledger schema: {data.get('schemaVersion')}")
    data.setdefault("schemaVersion", COLLISION_LEDGER_SCHEMA_VERSION)
    objects = data.setdefault("objects", {})
    if not isinstance(objects, dict):
        raise ValueError("collision ledger objects must be an object")
    return data


def _record_collision(
    ledger: dict[str, Any],
    *,
    object_key: str,
    sha256: str,
    source_ref: str,
    release_id: str,
    kind: str,
) -> str | None:
    objects = ledger.setdefault("objects", {})
    existing = objects.get(sha256)
    if isinstance(existing, dict):
        old_key = str(existing.get("objectKey") or "")
        if old_key and old_key != object_key:
            return f"sha256 mapped to multiple objectKeys: {sha256}"
        refs = existing.get("refs")
        if refs is None:
            refs = []
        if not isinstance(refs, list):
            return f"collision ledger refs invalid for {sha256}"
    else:
        refs = []
    ref_row = {
        "sourceRef": source_ref,
        "releaseId": release_id,
        "updatedAt": NOW_ISO,
    }
    if ref_row not in refs:
        refs.append(ref_row)
    objects[sha256] = {
        "sha256": sha256,
        "objectKey": object_key,
        "kind": kind,
        "refs": refs,
        "updatedAt": NOW_ISO,
    }
    ledger["updatedAt"] = NOW_ISO
    return None


def _copy_to_media_library(
    publish_root: Path,
    source: Path,
    object_key: str,
    *,
    expected_sha256: str,
) -> tuple[str | None, str | None]:
    target = publish_root / "media" / "library" / object_key
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file():
        existing_sha256 = sha256_file(target)
        if existing_sha256 != expected_sha256:
            return None, f"existing library object hash mismatch for {object_key}"
    else:
        shutil.copy2(source, target)
    return str(target.relative_to(publish_root)), None


def _merge_asset_entry(asset: Mapping[str, Any], resolved: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(asset)
    for key in (
        "kind",
        "fileName",
        "objectKey",
        "cdnUrl",
        "sha256",
        "mimeType",
        "sourceOwner",
        "sourceRef",
        "sourceType",
        "releaseId",
        "environment",
        "variants",
        "thumbnailUrl",
        "coverUrl",
        "coverStrategy",
        "coverFrameTimeMs",
        "durationMs",
        "width",
        "height",
    ):
        if resolved.get(key) not in (None, ""):
            merged[key] = resolved[key]
    return merged


def _asset_file(entity_or_post_dir: Path, asset: Mapping[str, Any]) -> Path | None:
    file_name = str(asset.get("fileName") or "").strip()
    if not file_name:
        return None
    path = entity_or_post_dir / "assets" / file_name
    return path if path.is_file() else None


def _resolve_one_asset(
    *,
    publish_root: Path,
    ledger: dict[str, Any],
    env: str,
    release_id: str,
    source_owner: str,
    scope: str,
    object_type: str,
    stable_object_ref: str,
    source_ref: str,
    owner_dir: Path,
    asset: Mapping[str, Any],
    image_cdn_base_url: str,
    video_cdn_base_url: str,
) -> tuple[dict[str, Any] | None, str | None]:
    asset_id = str(asset.get("assetId") or asset.get("id") or "").strip()
    if not asset_id:
        return None, f"{source_ref}: asset missing assetId"
    path = _asset_file(owner_dir, asset)
    if path is None:
        return None, f"{source_ref}: asset file missing on disk for {asset_id}"
    digest = sha256_file(path)
    kind = media_kind_for_file(path, str(asset.get("kind") or ""))
    mime_type = _mime_type(path)
    canonical_ext = canonical_media_extension(path, kind, mime_type)
    object_key = build_object_key(
        source_owner=source_owner,
        env=env,
        scope=scope,
        object_type=object_type,
        stable_object_ref=stable_object_ref,
        asset_id=asset_id,
        sha256=digest,
        ext="." + canonical_ext,
        kind=kind,
    )
    collision = _record_collision(
        ledger,
        object_key=object_key,
        sha256=digest,
        source_ref=source_ref,
        release_id=release_id,
        kind=kind,
    )
    if collision:
        return None, f"{source_ref}: {collision}"
    library_path, copy_issue = _copy_to_media_library(
        publish_root,
        path,
        object_key,
        expected_sha256=digest,
    )
    if copy_issue:
        return None, f"{source_ref}: {copy_issue}"
    assert library_path is not None
    resolved = {
        "assetId": asset_id,
        "kind": kind,
        "fileName": path.name,
        "objectKey": object_key,
        "cdnUrl": cdn_url_for_object_key(
            object_key,
            kind=kind,
            image_cdn_base_url=image_cdn_base_url,
            video_cdn_base_url=video_cdn_base_url,
        ),
        "sha256": digest,
        "mimeType": mime_type,
        "sourceOwner": source_owner,
        "sourceRef": source_ref,
        "sourceType": object_type,
        "releaseId": release_id,
        "environment": env,
        "libraryPath": library_path,
        "sourceOriginalSha256": digest,
    }
    variants = (
        _image_variants_for_object(
            object_key=object_key,
            base_cdn_url=resolved["cdnUrl"],
            sha256=digest,
            mime_type=mime_type,
            width=asset.get("width"),
            height=asset.get("height"),
        )
        if kind == "image"
        else _video_variants_for_object(
            object_key=object_key,
            base_cdn_url=resolved["cdnUrl"],
            sha256=digest,
            mime_type=mime_type,
            duration_ms=asset.get("durationMs"),
        )
        if kind == "video"
        else {}
    )
    if variants:
        resolved["variants"] = variants
    if kind == "video":
        cover_frame_time_ms = asset.get("coverFrameTimeMs", 0) or 0
        thumbnail_url = str(asset.get("thumbnailUrl") or asset.get("coverUrl") or "").strip()
        if not thumbnail_url:
            thumbnail_url = _append_video_cover_query(resolved["cdnUrl"], cover_frame_time_ms)
        resolved["thumbnailUrl"] = thumbnail_url
        resolved["coverUrl"] = thumbnail_url
        resolved["coverStrategy"] = str(asset.get("coverStrategy") or "first_frame")
        resolved["coverFrameTimeMs"] = cover_frame_time_ms
    for key in ("caption", "role", "imageLayout", "width", "height", "durationMs"):
        if asset.get(key) not in (None, ""):
            resolved[key] = asset[key]
    return resolved, None


def _update_article_asset_manifest(manifest: dict[str, Any], resolved_assets: list[dict[str, Any]]) -> None:
    by_id = {str(asset.get("assetId")): asset for asset in resolved_assets if asset.get("assetId")}
    raw_assets = manifest.get("assets")
    existing = raw_assets if isinstance(raw_assets, list) else []
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for raw in existing:
        if not isinstance(raw, dict):
            continue
        asset_id = str(raw.get("assetId") or raw.get("id") or "").strip()
        if asset_id in by_id:
            merged.append(_merge_asset_entry(raw, by_id[asset_id]))
            seen.add(asset_id)
        else:
            merged.append(dict(raw))
    for asset_id, asset in by_id.items():
        if asset_id not in seen:
            merged.append(dict(asset))
    manifest["assets"] = merged


def _materialize_post(
    *,
    publish_root: Path,
    ledger: dict[str, Any],
    ref: str,
    env: str,
    release_id: str,
    source_owner: str,
    image_cdn_base_url: str,
    video_cdn_base_url: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    post_dir = publish_root / ref
    manifest_path = post_dir / "manifest.json"
    if not manifest_path.is_file():
        return [], [f"{ref}: missing manifest.json"]
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict):
        return [], [f"{ref}: invalid manifest.json"]
    resolved: list[dict[str, Any]] = []
    issues: list[str] = []
    new_assets: list[dict[str, Any]] = []
    for raw in manifest.get("assets") or []:
        if not isinstance(raw, dict):
            continue
        row, issue = _resolve_one_asset(
            publish_root=publish_root,
            ledger=ledger,
            env=env,
            release_id=release_id,
            source_owner=source_owner,
            scope="cold_start",
            object_type="post",
            stable_object_ref=ref,
            source_ref=ref,
            owner_dir=post_dir,
            asset=raw,
            image_cdn_base_url=image_cdn_base_url,
            video_cdn_base_url=video_cdn_base_url,
        )
        if issue:
            issues.append(issue)
            new_assets.append(dict(raw))
            continue
        assert row is not None
        resolved.append(row)
        new_assets.append(_merge_asset_entry(raw, row))
    if new_assets:
        manifest["assets"] = new_assets
        _update_article_asset_manifest(manifest, resolved)
        write_json(manifest_path, manifest)
    return resolved, issues


def _materialize_entity(
    *,
    publish_root: Path,
    ledger: dict[str, Any],
    ref: str,
    env: str,
    release_id: str,
    source_owner: str,
    image_cdn_base_url: str,
    video_cdn_base_url: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    entity_dir = publish_root / "entities" / ref
    manifest_path = entity_dir / "manifest.json"
    page_path = entity_dir / "page.md"
    if not manifest_path.is_file():
        if page_path.read_text(encoding="utf-8").find("asset://") >= 0 if page_path.is_file() else False:
            return [], [f"{ref}: page.md has asset refs but entity manifest.json is missing"]
        return [], []
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict):
        return [], [f"{ref}: invalid entity manifest.json"]
    resolved: list[dict[str, Any]] = []
    issues: list[str] = []
    new_assets: list[dict[str, Any]] = []
    for raw in manifest.get("assets") or []:
        if not isinstance(raw, dict):
            continue
        row, issue = _resolve_one_asset(
            publish_root=publish_root,
            ledger=ledger,
            env=env,
            release_id=release_id,
            source_owner=source_owner,
            scope="cold_start",
            object_type="entity_homepage",
            stable_object_ref=ref,
            source_ref=f"entities/{ref}",
            owner_dir=entity_dir,
            asset=raw,
            image_cdn_base_url=image_cdn_base_url,
            video_cdn_base_url=video_cdn_base_url,
        )
        if issue:
            issues.append(issue)
            new_assets.append(dict(raw))
            continue
        assert row is not None
        resolved.append(row)
        new_assets.append(_merge_asset_entry(raw, row))
    if new_assets:
        manifest["assets"] = new_assets
        write_json(manifest_path, manifest)
    return resolved, issues


def materialize_release_media(
    *,
    env: str,
    release_id: str,
    post_refs: list[str],
    entity_refs: list[str],
    publish_root: Path | None = None,
    source_owner: str = "qwq_data",
    image_cdn_base_url: str = "",
    video_cdn_base_url: str = "",
) -> dict[str, Any]:
    root = publish_root or PUBLISH_ROOT
    assets: list[dict[str, Any]] = []
    issues: list[str] = []
    try:
        ledger = _load_collision_ledger(root)
    except Exception as exc:  # noqa: BLE001 - fail closed via manifest issue
        ledger = {
            "schemaVersion": COLLISION_LEDGER_SCHEMA_VERSION,
            "updatedAt": NOW_ISO,
            "objects": {},
        }
        issues.append(f"collision ledger invalid: {exc}")
    for ref in sorted(entity_refs):
        rows, found = _materialize_entity(
            publish_root=root,
            ledger=ledger,
            ref=ref,
            env=env,
            release_id=release_id,
            source_owner=source_owner,
            image_cdn_base_url=image_cdn_base_url,
            video_cdn_base_url=video_cdn_base_url,
        )
        assets.extend(rows)
        issues.extend(found)
    for ref in sorted(post_refs):
        rows, found = _materialize_post(
            publish_root=root,
            ledger=ledger,
            ref=ref,
            env=env,
            release_id=release_id,
            source_owner=source_owner,
            image_cdn_base_url=image_cdn_base_url,
            video_cdn_base_url=video_cdn_base_url,
        )
        assets.extend(rows)
        issues.extend(found)
    image_assets = [asset for asset in assets if asset.get("kind") == "image"]
    video_assets = [asset for asset in assets if asset.get("kind") == "video"]
    variant_count = sum(
        len(asset.get("variants") or {})
        for asset in assets
        if isinstance(asset.get("variants"), Mapping)
    )
    write_json(_collision_ledger_path(root), ledger)
    manifest = {
        "schemaVersion": MEDIA_SCHEMA_VERSION,
        "releaseId": release_id,
        "environment": env,
        "sourceOwner": source_owner,
        "generatedAt": NOW_ISO,
        "assets": assets,
        "issues": issues,
        "operationalTargets": {
            "dailyVisits": 100000,
            "minCdnHitRate": 0.9,
            "maxInlineOriginalRequests": 0,
            "trackedMetrics": [
                "cdnHitRate",
                "originFetchRate",
                "media4xx5xxRate",
                "firstImageP95Ms",
                "averageImageBytes",
                "originalRequestRatio",
                "videoFirstFrameP95Ms",
                "videoPlaybackErrorRate",
            ],
        },
        "counts": {
            "assets": len(assets),
            "imageAssets": len(image_assets),
            "videoAssets": len(video_assets),
            "variants": variant_count,
            "issues": len(issues),
        },
    }
    out = root / "media" / "releases" / release_id / f"{env}.json"
    write_json(out, manifest)
    return {**manifest, "path": str(out.relative_to(root))}
