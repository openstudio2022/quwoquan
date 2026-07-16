"""自治对象包 CAS 引用校验与 immutable release media manifest。"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from core.paths import PUBLISH_ROOT, RELEASE_ROOT, REPO_ROOT
from core.release_layout import payload_file

_CAS_RE = re.compile(
    r"^media/objects/sha256/([0-9a-f]{2})/([0-9a-f]{2})/([0-9a-f]{64})(\.[a-z0-9]+)?$"
)
IMAGE_VARIANT_PROFILES: dict[str, dict[str, Any]] = {
    "thumbnail": {"width": 320, "format": "webp", "quality": 80, "scene": "feed_grid"},
    "display": {"width": 960, "format": "webp", "quality": 82, "scene": "article_body"},
    "cover": {"width": 1280, "format": "webp", "quality": 85, "scene": "feed_cover"},
    "full": {"width": 2048, "format": "webp", "quality": 90, "scene": "immersive_viewer"},
}
ENVIRONMENT_TOPOLOGY_MANIFEST = (
    REPO_ROOT / "quwoquan_ops" / "environments" / "environment_topology_manifest.yaml"
)


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
    source_owner: str = "qwq_data",
) -> dict[str, Any]:
    """Build the exact CAS closure for one immutable release without writing it.

    A release is an object closure, not a snapshot of the whole canonical media
    library.  Keeping construction separate from persistence lets staged release
    builders use the same contract before their directory is atomically promoted.
    """
    canonical = publish_root or PUBLISH_ROOT
    assets: dict[str, dict[str, Any]] = {}
    issues: list[str] = []
    for kind, refs in (("posts", post_refs), ("entities", entity_refs)):
        for ref in refs:
            object_root = _object_root(canonical, kind, ref)
            if not object_root.is_dir():
                issues.append(f"object missing: {kind}/{ref}")
                continue
            for row in _asset_rows(object_root):
                object_key = str(row.get("objectKey") or "")
                expected = str(row.get("sha256") or "")
                if not is_cas_media_object_key(object_key):
                    issues.append(f"non-CAS objectKey: {kind}/{ref}:{object_key}")
                    continue
                physical = canonical / object_key
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
        "schemaVersion": "quwoquan_data.release_media_manifest/1",
        "releaseId": release_id,
        "sourceOwner": source_owner,
        "assets": [assets[key] for key in sorted(assets)],
        "issues": issues,
        "counts": {"assets": len(assets), "issues": len(issues)},
    }


def materialize_release_media(
    *,
    release_id: str,
    post_refs: list[str],
    entity_refs: list[str],
    publish_root: Path | None = None,
    release_root: Path | None = None,
    source_owner: str = "qwq_data",
) -> dict[str, Any]:
    """只消费已闭包 CAS refs；绝不改 canonical manifest、复制媒体或生成 CDN URL。"""
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
    target = payload_file(release, "media_manifest.json")
    payload = _json_bytes(manifest)
    if target.exists():
        if target.read_bytes() != payload:
            raise FileExistsError(f"immutable release media manifest conflict: {target}")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    return manifest
