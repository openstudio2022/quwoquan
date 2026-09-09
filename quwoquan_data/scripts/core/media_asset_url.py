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

from core.asset_identity import parse_post_asset_id
from core.paths import PUBLISH_ROOT, RELEASE_ROOT, REPO_ROOT
from core.release_layout import payload_file
from core.schema import assert_valid

_CAS_RE = re.compile(
    r"^media/objects/sha256/([0-9a-f]{2})/([0-9a-f]{2})/([0-9a-f]{64})(\.[a-z0-9]+)?$"
)
_SHA256_RE = re.compile(r"^sha256:([0-9a-f]{64})$")
_PUBLIC_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_UNIT_ROLE_ASSET_ID_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*):([a-z]+)$")
_CANONICAL_DECIMAL_RE = re.compile(r"^(?:0|[1-9][0-9]*)$")
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
SUFFIX_BY_CONTENT_TYPE = _SUFFIX_BY_CONTENT_TYPE


def content_addressed_media_object_key(sha256: str, *, suffix: str) -> str:
    """CAS objectKey 是 sha256 与文件后缀的确定函数：`media/objects/sha256/aa/bb/<hex><suffix>`。"""
    digest = str(sha256).removeprefix("sha256:")
    normalized_suffix = str(suffix or "").lower()
    if normalized_suffix and not normalized_suffix.startswith("."):
        normalized_suffix = "." + normalized_suffix
    return f"media/objects/sha256/{digest[:2]}/{digest[2:4]}/{digest}{normalized_suffix or '.bin'}"
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


def effective_delivery_width(profile: str, *, stored_width: int) -> int:
    """Project one profile's declared width onto the width of a stored body.

    A profile's declared width is an upper bound on delivery, never an upscale
    target: a stored body narrower than the declared width is delivered at its
    own width, because upscaling only adds bytes and no information. Every
    consumer derives its pixel result from this single projection, so a
    delivered width below the declared width is a legal outcome rather than
    profile or descriptor drift.
    """
    declared = IMAGE_VARIANT_PROFILES.get(profile)
    if declared is None:
        raise ValueError(f"content image variant profile is unknown: {profile}")
    if (
        isinstance(stored_width, bool)
        or not isinstance(stored_width, int)
        or stored_width < 1
    ):
        raise ValueError(
            f"stored image width must be a positive integer: {stored_width!r}"
        )
    return min(int(declared["width"]), stored_width)


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
    # 六步 producer 的视频资产 ID 形如 `<sourceUnit>:video` / `<sourceUnit>:poster`：
    # 冒号不能进 URL 路径，取角色做可读前缀并对整个 ID 取摘要（与 Go
    # cleanContentAssetIdentity 同一派生规则）。
    unit_role = _UNIT_ROLE_ASSET_ID_RE.fullmatch(value)
    if unit_role is not None:
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
        return f"{unit_role.group(2)}-{digest[:32]}"
    # Data post asset IDs carry Chinese display text that cannot enter a URL
    # path. The role and execution sequence are ASCII already, so the derived
    # segment keeps them readable and only hashes the parts that are not.
    try:
        identity = parse_post_asset_id(value)
    except ValueError:
        return ""
    if not _CANONICAL_DECIMAL_RE.fullmatch(identity.sequence_token):
        return ""
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"{identity.role}-{identity.sequence_token}-{digest[:32]}"


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


def _asset_rows(root: Path, *, object_kind: str) -> Iterable[dict[str, Any]]:
    path = root / ("profile.json" if object_kind == "creators" else "manifest.json")
    if not path.is_file():
        raise ValueError(f"object asset manifest missing: {path}")
    for row in _read_json(path).get("assets") or []:
        if isinstance(row, dict):
            yield row


def _manifest_asset_rows(root: Path) -> dict[str, dict[str, Any]]:
    path = root / "manifest.json"
    if not path.is_file():
        return {}
    manifest = _read_json(path)
    candidates: list[object] = list(manifest.get("assets") or [])
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
    filename = "profile.json" if object_kind == "creators" else "manifest.json"
    owner = f"{object_kind}/{object_ref.removeprefix(f'{object_kind}/')}"
    document = _read_json(object_root / filename)
    assets = [row for row in document.get("assets") or [] if row.get("assetId") == asset_id]
    if len(assets) != 1 or assets[0].get("sha256") != sha256:
        return [], [f"source asset binding missing: {owner}:{asset_id}"]
    for source_ref in assets[0].get("sourceRefs") or []:
        try:
            source = _carried_path(object_root, str(source_ref))
            source_document = _read_json(source)
            assert_valid(source_document, "publish", "source")
            if not str(source_ref).startswith("sources/") or not str(source_ref).endswith("/source.json"):
                raise ValueError("source ref is not object-local")
            for evidence in source_document["evidence"]:
                body = _carried_path(source.parent, evidence["path"])
                if body.stat().st_size != evidence["bytes"] or sha256_file(body) != evidence["sha256"]:
                    raise ValueError("source evidence bytes drift")
            refs.append(f"objects/{owner}/{source_ref}")
        except (OSError, ValueError) as exc:
            issues.append(f"source binding invalid: {owner}:{asset_id}: {exc}")
    if not refs:
        issues.append(f"source binding missing: {owner}:{asset_id}")
    return sorted(set(refs)), issues


def _object_root(canonical: Path, kind: str, ref: str) -> Path:
    from content.release.canonical.aggregate_release_closure import object_root

    return object_root(canonical, kind, ref.removeprefix(f"{kind}/"))


def build_release_media_manifest(
    *,
    release_id: str,
    post_refs: list[str],
    entity_refs: list[str],
    creator_refs: list[str] | None = None,
    publish_root: Path | None = None,
    object_root: Path | None = None,
    source_owner: str = "qwq_data",
) -> dict[str, Any]:
    """Build the MediaAsset closure for one immutable release.

    只从所选对象的 manifest/source 与随体字节生成媒体交付闭包，不扫描全库。
    publicSliceKey 由现有资产身份协议派生，不选择发布类别；真实来源限制和
    授权记录原样保留，不把取得媒体转换为伪造授权。
    """
    canonical = publish_root or PUBLISH_ROOT
    objects = object_root or canonical
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
            for row in _asset_rows(selected_object, object_kind=kind):
                asset_id = str(row.get("assetId") or "").strip()
                object_key = str(row.get("path") or "")
                expected = str(row.get("sha256") or "")
                if not asset_id:
                    issues.append(f"assetId missing: {kind}/{ref}")
                    continue
                sha_match = _SHA256_RE.fullmatch(expected)
                if sha_match is None:
                    issues.append(f"sha256 invalid: {kind}/{ref}:{asset_id}")
                    continue
                try:
                    physical = _carried_path(selected_object, object_key)
                except (OSError, ValueError):
                    issues.append(f"carried object missing: {kind}/{ref}:{object_key}")
                    continue
                actual = sha256_file(physical)
                if actual != expected or physical.stat().st_size != row.get("bytes"):
                    issues.append(f"carried media drift: {kind}/{ref}:{object_key}")
                    continue
                metadata = manifest_assets.get(asset_id, row)
                metadata_key = str(metadata.get("path") or "").strip()
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
                delivery_field = "publicSliceKey"
                version = row.get("version", 1)
                if type(version) is not int or version < 1:
                    issues.append(f"asset version invalid: {kind}/{ref}:{asset_id}")
                    continue
                delivery_key = build_public_media_slice_key(
                    asset_id=asset_id,
                    kind=asset_kind,
                    version=version,
                    content_type=content_type,
                )
                if not delivery_key:
                    issues.append(
                        f"public slice unresolved: {kind}/{ref}:{asset_id}"
                    )
                    continue
                owner_ref = selected_object.relative_to(objects).as_posix()
                rights_refs, rights_issues = _rights_snapshot_refs(
                    object_kind=kind,
                    object_ref=owner_ref.removeprefix(f"{kind}/"),
                    object_root=selected_object,
                    asset_id=asset_id,
                    sha256=actual,
                )
                issues.extend(rights_issues)
                if rights_issues:
                    continue
                normalized = {
                    "assetId": asset_id,
                    "kind": asset_kind,
                    "version": version,
                    "contentType": content_type,
                    delivery_field: delivery_key,
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
                        delivery_field,
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
                # 派生的公开 slice 必须独占一个 assetId。
                other_asset_id = slice_owners.get(delivery_key)
                if other_asset_id is not None and other_asset_id != asset_id:
                    issues.append(
                        f"public slice collision: {delivery_key}:"
                        f"{other_asset_id},{asset_id}"
                    )
                    continue
                slice_owners[delivery_key] = asset_id
                assets[asset_id] = normalized
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


def release_media_delivery_key(row: Mapping[str, Any]) -> str:
    """Return the validated delivery key of one release media manifest row.

    Every production asset carries exactly one delivery identity (DEC-041): a
    derived anonymous ``publicSliceKey``. Private CAS delivery is retired.
    """
    if row.get("privateObjectKey"):
        raise ValueError(
            "release media asset declares retired private delivery: "
            f"{row.get('privateObjectKey')}"
        )
    public_slice_key = str(row.get("publicSliceKey") or "")
    if not is_public_media_slice_key(public_slice_key):
        raise ValueError(
            f"invalid release media publicSliceKey: {public_slice_key}"
        )
    return public_slice_key


def _carried_path(root: Path, relative: str) -> Path:
    if (not relative or relative.startswith("/") or "\\" in relative
            or any(part in {"", ".", ".."} for part in relative.split("/"))):
        raise ValueError(f"invalid carried media ref: {relative}")
    candidate = root / relative
    if any(path.is_symlink() for path in (candidate, *candidate.parents)):
        raise ValueError(f"carried media symlink: {relative}")
    if not candidate.is_file():
        raise ValueError(f"carried media missing: {relative}")
    return candidate


def _release_carried_source(release_root: Path, asset: Mapping[str, Any]) -> Path:
    objects = payload_file(release_root, "objects")
    for owner in asset.get("ownerRefs") or []:
        if not isinstance(owner, str):
            raise ValueError("invalid release media owner")
        filename = "profile.json" if owner.startswith("creators/") else "manifest.json"
        manifest_path = _carried_path(objects, owner + "/" + filename)
        document = _read_json(manifest_path)
        matches = [row for row in document.get("assets") or [] if row.get("assetId") == asset.get("assetId")]
        if len(matches) != 1:
            raise ValueError(f"carried media owner binding missing: {owner}")
        row = matches[0]
        if row.get("sha256") != asset.get("sha256"):
            raise ValueError(f"carried media owner digest drift: {owner}")
        return _carried_path(manifest_path.parent, str(row.get("path") or ""))
    raise ValueError("release media has no carried owner")


def copy_release_media_objects(
    *,
    manifest: Mapping[str, Any],
    release_root: Path,
) -> None:
    """从 release 选中对象的实际随体文件物化交付字节，不依赖作者的媒体库。"""
    assets = manifest.get("assets")
    if not isinstance(assets, list):
        raise TypeError("release media manifest assets must be an array")
    for index, row in enumerate(assets):
        if not isinstance(row, Mapping):
            raise TypeError(f"release media manifest assets[{index}] must be an object")
        delivery_key = release_media_delivery_key(row)
        expected = str(row.get("sha256") or "")
        source = _release_carried_source(release_root, row)
        if sha256_file(source) != expected or source.stat().st_size != row.get("bytes"):
            raise ValueError(f"release media source is missing or corrupt: {expected}")
        target = payload_file(release_root, delivery_key)
        if any(path.is_symlink() for path in (target, *target.parents)):
            raise ValueError(f"release media symlink: {delivery_key}")
        if target.is_file():
            if sha256_file(target) != expected or target.stat().st_size != row.get("bytes"):
                raise FileExistsError(f"immutable release media conflict: {target}")
            continue
        # release 是可搬运的独立分发包，不以可写硬链接和原对象共享唯一 inode。
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".copy-tmp")
        shutil.copyfile(source, temporary)
        if sha256_file(temporary) != expected:
            temporary.unlink(missing_ok=True)
            raise ValueError(
                f"release media post-copy hash mismatch: {delivery_key}"
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
    copy_release_media_objects(manifest=manifest, release_root=release)
    target = payload_file(release, "media_manifest.json")
    payload = _json_bytes(manifest)
    if target.exists():
        if target.read_bytes() != payload:
            raise FileExistsError(f"immutable release media manifest conflict: {target}")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    return manifest
