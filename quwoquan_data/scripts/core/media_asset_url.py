"""自治对象包 CAS 引用校验与 immutable release media manifest。"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from core.paths import PUBLISH_ROOT, RELEASE_ROOT, REPO_ROOT
from core.release_layout import payload_file

_CAS_RE = re.compile(
    r"^media/objects/sha256/([0-9a-f]{2})/([0-9a-f]{2})/([0-9a-f]{64})(\.[a-z0-9]+)?$"
)
_IMAGE_VARIANT_POLICY = (
    REPO_ROOT
    / "quwoquan_service"
    / "contracts"
    / "metadata"
    / "content"
    / "media_asset"
    / "image_variant_policy.yaml"
)
_REQUIRED_IMAGE_VARIANT_PROFILES = frozenset(
    {"thumbnail", "display", "cover", "full"}
)
ENVIRONMENT_TOPOLOGY_MANIFEST = (
    REPO_ROOT / "quwoquan_ops" / "environments" / "environment_topology_manifest.yaml"
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
            raise ValueError(f"content image variant profile is missing: {name}")
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


def resolve_media_cdn_bases(
    environment: str,
    *,
    topology_manifest: Path | None = None,
) -> tuple[str, str]:
    """从环境拓扑真相源解析图片与视频 CDN 基址。"""
    manifest = topology_manifest or ENVIRONMENT_TOPOLOGY_MANIFEST
    document = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    environments = document.get("environments") or {}
    node = environments.get(environment) or {}
    public_bases = node.get("publicBases") or {}
    image_base = str(public_bases.get("mediaImage") or "").strip().rstrip("/")
    video_base = str(public_bases.get("mediaVideo") or "").strip().rstrip("/")

    if environment == "prod":
        if "media.quwoquan.invalid" in image_base or "media.quwoquan.invalid" in video_base:
            raise SystemExit("refusing media.quwoquan.invalid for prod media CDN")
        if not image_base:
            raise SystemExit("prod media CDN base unresolved")

    return image_base, video_base


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


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON 顶层必须为 object: {path}")
    return value


def _asset_rows(root: Path) -> Iterable[dict[str, Any]]:
    path = root / "asset.refs.json"
    if not path.is_file():
        return
    for row in _read_json(path).get("assets") or []:
        if isinstance(row, dict):
            yield row


def _object_root(canonical: Path, kind: str, ref: str) -> Path:
    return canonical / kind / ref.removeprefix(f"{kind}/")


def build_release_media_manifest(
    *,
    release_id: str,
    post_refs: list[str],
    entity_refs: list[str],
    publish_root: Path | None = None,
    object_root: Path | None = None,
    media_root: Path | None = None,
    source_owner: str = "qwq_data",
) -> dict[str, Any]:
    """Build the exact CAS closure for one immutable release without writing it.

    A release is an object closure, not a snapshot of the whole canonical media
    library.  Keeping construction separate from persistence lets staged release
    builders use the same contract before their directory is atomically promoted.
    """
    canonical = publish_root or PUBLISH_ROOT
    objects = object_root or canonical
    media = media_root or canonical
    assets: dict[str, dict[str, Any]] = {}
    issues: list[str] = []
    for kind, refs in (("posts", post_refs), ("entities", entity_refs)):
        for ref in refs:
            selected_object = _object_root(objects, kind, ref)
            if not selected_object.is_dir():
                issues.append(f"object missing: {kind}/{ref}")
                continue
            for row in _asset_rows(selected_object):
                object_key = str(row.get("objectKey") or "")
                expected = str(row.get("sha256") or "")
                if not is_cas_media_object_key(object_key):
                    issues.append(f"non-CAS objectKey: {kind}/{ref}:{object_key}")
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
                normalized = {
                    "objectKey": object_key,
                    "sha256": actual,
                    "bytes": physical.stat().st_size,
                }
                old = assets.get(object_key)
                if old is not None and old != normalized:
                    issues.append(f"CAS metadata collision: {object_key}")
                assets[object_key] = normalized
    return {
        "schema": "quwoquan_data.release_media_manifest",
        "releaseId": release_id,
        "sourceOwner": source_owner,
        "assets": [assets[key] for key in sorted(assets)],
        "issues": issues,
        "counts": {"assets": len(assets), "issues": len(issues)},
    }


def copy_release_media_objects(
    *,
    manifest: Mapping[str, Any],
    source_root: Path,
    release_root: Path,
) -> None:
    """Copy the exact CAS closure into the immutable release payload."""
    assets = manifest.get("assets")
    if not isinstance(assets, list):
        raise ValueError("release media manifest assets must be an array")
    for index, row in enumerate(assets):
        if not isinstance(row, Mapping):
            raise ValueError(f"release media manifest assets[{index}] must be an object")
        object_key = str(row.get("objectKey") or "")
        expected = str(row.get("sha256") or "")
        if not is_cas_media_object_key(object_key):
            raise ValueError(f"invalid release media objectKey: {object_key}")
        source = source_root / object_key
        if not source.is_file() or sha256_file(source) != expected:
            raise ValueError(f"release media source is missing or corrupt: {object_key}")
        target = payload_file(release_root, object_key)
        if target.is_file():
            if sha256_file(target) != expected:
                raise FileExistsError(f"immutable release media conflict: {target}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".copy-tmp")
        shutil.copy2(source, temporary)
        if sha256_file(temporary) != expected:
            temporary.unlink(missing_ok=True)
            raise ValueError(f"release media post-copy hash mismatch: {object_key}")
        temporary.replace(target)


def materialize_release_media(
    *,
    release_id: str,
    post_refs: list[str],
    entity_refs: list[str],
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
