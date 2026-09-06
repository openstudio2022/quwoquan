"""Immutable release media identity, rights, and physical closure checks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from content.release.canonical.release_consistency_report import blocking_issue as _issue
from core.io import read_json
from core.media_asset_url import (
    build_public_media_slice_key,
    is_cas_media_object_key,
    is_public_media_slice_key,
    sha256_file,
)
from core.release_layout import payload_file
from core.schema import assert_valid


def release_private_storage_issues(objects: Path) -> list[dict[str, str]]:
    """Reject private CAS identity anywhere in the immutable object payload."""

    def contains_private_storage(value: Any) -> bool:
        if isinstance(value, dict):
            if "objectKey" in value:
                return True
            return any(contains_private_storage(child) for child in value.values())
        if isinstance(value, list):
            return any(contains_private_storage(child) for child in value)
        return isinstance(value, str) and value.startswith("media/objects/sha256/")

    issues: list[dict[str, str]] = []
    for path in sorted(objects.rglob("*.json")):
        if contains_private_storage(read_json(path)):
            issues.append(
                _issue(
                    "release_object_private_storage_leak",
                    "release object snapshot 禁止暴露 private CAS objectKey",
                    path.relative_to(objects).as_posix(),
                )
            )
    return issues


def _object_root(root: Path, kind: str, ref: str) -> Path:
    return root / kind / ref.removeprefix(f"{kind}/")


def _asset_rows(root: Path) -> list[dict[str, Any]]:
    paths = [
        path
        for path in (root / "asset.refs.json", root / "assets.refs.json")
        if path.is_file()
    ]
    if not paths:
        return []
    if len(paths) != 1:
        raise ValueError(f"object must own exactly one asset refs document: {root}")
    return [
        row
        for row in read_json(paths[0]).get("assets") or []
        if isinstance(row, dict)
    ]


def _canonical_media_owner_ref(ref: str) -> bool:
    if not ref or "\\" in ref:
        return False
    candidate = Path(ref)
    if candidate.is_absolute() or candidate.as_posix() != ref:
        return False
    parts = candidate.parts
    return (
        len(parts) >= 2
        and parts[0] in {"creators", "entities", "posts"}
        and all(part not in {"", ".", ".."} for part in parts[1:])
    )


def _release_rights_owner(ref: str) -> str:
    prefix = "objects/"
    marker = "/rights_snapshots/"
    if not ref.startswith(prefix):
        return ""
    value = ref.removeprefix(prefix)
    index = value.find(marker)
    return value[:index] if index > 0 else ""


def _canonical_release_rights_ref(ref: str) -> bool:
    if not ref or "\\" in ref:
        return False
    candidate = Path(ref)
    if candidate.is_absolute() or candidate.as_posix() != ref:
        return False
    owner = _release_rights_owner(ref)
    if not _canonical_media_owner_ref(owner):
        return False
    suffix = ref.removeprefix(f"objects/{owner}/rights_snapshots/")
    return (
        bool(suffix)
        and "/" not in suffix
        and suffix not in {".", ".."}
        and suffix.endswith(".json")
    )


def release_media_issues(
    *,
    contract: Mapping[str, Any],
    media_root: Path,
    objects: Path,
    release_root: Path,
) -> list[dict[str, str]]:
    release_id = str(contract.get("releaseId") or "")
    desired = (
        contract.get("desiredRefs")
        if isinstance(contract.get("desiredRefs"), Mapping)
        else {}
    )
    issues: list[dict[str, str]] = []
    expected_assets: dict[str, dict[str, Any]] = {}
    for kind in ("creators", "posts", "entities"):
        refs = {str(item) for item in desired.get(kind) or [] if str(item).strip()}
        for ref in sorted(refs):
            root = _object_root(objects, kind, ref)
            owner_ref = f"{kind}/{ref.removeprefix(f'{kind}/')}"
            for row in _asset_rows(root):
                asset_id = str(row.get("assetId") or "").strip()
                sha256 = str(row.get("sha256") or "").strip()
                if not asset_id or not sha256:
                    issues.append(
                        _issue(
                            "release_media_source_identity_invalid",
                            "asset.refs 必须声明 assetId 与 sha256",
                            f"{kind}/{ref}",
                        )
                    )
                    continue
                prior = expected_assets.get(asset_id)
                if prior is not None and prior["sha256"] != sha256:
                    issues.append(
                        _issue(
                            "release_media_source_identity_collision",
                            "同一 assetId 绑定了不同 sha256",
                            asset_id,
                        )
                    )
                    continue
                if prior is None:
                    expected_assets[asset_id] = {
                        "sha256": sha256,
                        "ownerRefs": {owner_ref},
                    }
                else:
                    prior["ownerRefs"].add(owner_ref)

    path = payload_file(release_root, "media_manifest.json")
    if not path.is_file():
        return issues
    actual = read_json(path)
    try:
        assert_valid(
            actual,
            "release",
            "media_manifest",
            label=f"release_media_manifest:{release_id}",
        )
    except ValueError as exc:
        issues.append(_issue("release_media_schema_invalid", str(exc), release_id))
    if str(actual.get("releaseId") or "") != release_id:
        issues.append(
            _issue(
                "release_media_identity_mismatch",
                "media_manifest releaseId 不一致",
                release_id,
            )
        )
    actual_assets = actual.get("assets")
    if not isinstance(actual_assets, list):
        issues.append(
            _issue(
                "release_media_assets_invalid",
                "media_manifest assets 必须为数组",
                release_id,
            )
        )
        return issues

    header_path = payload_file(release_root, "release.json")
    release_class = ""
    if header_path.is_file():
        release_class = str(read_json(header_path).get("releaseClass") or "").strip()
    if release_class not in {"research", "commercial"}:
        issues.append(
            _issue(
                "release_media_delivery_class_invalid",
                "release header 必须声明 research/commercial releaseClass",
                release_id,
            )
        )
        return issues
    private_delivery = release_class == "research"

    actual_identity: dict[str, str] = {}
    slice_owners: dict[str, str] = {}
    for row in actual_assets:
        if not isinstance(row, Mapping):
            continue
        asset_id = str(row.get("assetId") or "").strip()
        sha256 = str(row.get("sha256") or "").strip()
        public_slice_key = str(row.get("publicSliceKey") or "").strip()
        private_object_key = str(row.get("privateObjectKey") or "").strip()
        version = row.get("version")
        expected = expected_assets.get(asset_id)
        if "objectKey" in row:
            issues.append(
                _issue(
                    "release_media_private_key_leak",
                    "media_manifest 禁止暴露 private CAS objectKey",
                    asset_id,
                )
            )
        if private_delivery:
            if public_slice_key:
                issues.append(
                    _issue(
                        "release_media_delivery_class_mismatch",
                        "research release 不得携带公开交付 slice",
                        asset_id,
                    )
                )
                continue
            if not is_cas_media_object_key(private_object_key):
                issues.append(
                    _issue(
                        "release_media_private_object_key_invalid",
                        "privateObjectKey 必须是 canonical CAS media key",
                        asset_id,
                    )
                )
                continue
            digest = sha256.removeprefix("sha256:")
            if digest and digest not in private_object_key:
                issues.append(
                    _issue(
                        "release_media_private_object_key_identity_mismatch",
                        "privateObjectKey 必须与 MediaAsset sha256 内容寻址一致",
                        asset_id,
                    )
                )
                continue
            delivery_key = private_object_key
        else:
            if private_object_key:
                issues.append(
                    _issue(
                        "release_media_delivery_class_mismatch",
                        "commercial release 不得携带私有交付 key",
                        asset_id,
                    )
                )
                continue
            expected_slice_key = (
                build_public_media_slice_key(
                    asset_id=asset_id,
                    kind=str(row.get("kind") or ""),
                    version=version,
                    content_type=str(row.get("contentType") or ""),
                )
                if isinstance(version, int) and not isinstance(version, bool)
                else ""
            )
            if not is_public_media_slice_key(public_slice_key):
                issues.append(
                    _issue(
                        "release_media_public_slice_invalid",
                        "publicSliceKey 不是 avatar/image/video canonical slice",
                        asset_id,
                    )
                )
                continue
            if public_slice_key != expected_slice_key:
                issues.append(
                    _issue(
                        "release_media_public_slice_identity_mismatch",
                        "publicSliceKey 必须由 MediaAsset kind/assetId/version/contentType 唯一派生",
                        asset_id,
                    )
                )
                continue
            delivery_key = public_slice_key
        if asset_id in actual_identity:
            issues.append(
                _issue(
                    "release_media_identity_duplicated",
                    "media_manifest 内 assetId 必须唯一",
                    asset_id,
                )
            )
            continue
        # CAS keys are content-addressed and may legitimately be shared by
        # multiple assets; only derived public slices must be exclusive.
        if not private_delivery:
            slice_owner = slice_owners.get(delivery_key)
            if slice_owner is not None:
                issues.append(
                    _issue(
                        "release_media_public_slice_collision",
                        f"publicSliceKey 同时绑定 {slice_owner} 与 {asset_id}",
                        delivery_key,
                    )
                )
                continue

        raw_owner_refs = row.get("ownerRefs")
        owner_refs = (
            [str(item).strip() for item in raw_owner_refs]
            if isinstance(raw_owner_refs, list)
            else []
        )
        if (
            not owner_refs
            or len(owner_refs) != len(set(owner_refs))
            or any(not _canonical_media_owner_ref(ref) for ref in owner_refs)
        ):
            issues.append(
                _issue(
                    "release_media_owner_refs_invalid",
                    "ownerRefs 必须是唯一、canonical 的 creator/entity/post 对象引用",
                    asset_id,
                )
            )
        expected_owner_refs = (
            sorted(expected["ownerRefs"]) if expected is not None else []
        )
        if sorted(owner_refs) != expected_owner_refs:
            issues.append(
                _issue(
                    "release_media_owner_closure_mismatch",
                    "ownerRefs 必须精确等于 desired objects 的资产所有者闭包",
                    asset_id,
                )
            )

        raw_rights_refs = row.get("rightsSnapshotRefs")
        rights_refs = (
            [str(item).strip() for item in raw_rights_refs]
            if isinstance(raw_rights_refs, list)
            else []
        )
        rights_by_owner: dict[str, int] = {}
        if (
            not rights_refs
            or len(rights_refs) != len(set(rights_refs))
            or any(not _canonical_release_rights_ref(ref) for ref in rights_refs)
        ):
            issues.append(
                _issue(
                    "release_media_rights_refs_invalid",
                    "rightsSnapshotRefs 必须是唯一、canonical 的 release rights 引用",
                    asset_id,
                )
            )
        for rights_ref in rights_refs:
            if not _canonical_release_rights_ref(rights_ref):
                continue
            owner = _release_rights_owner(rights_ref)
            if owner not in owner_refs:
                issues.append(
                    _issue(
                        "release_media_rights_owner_mismatch",
                        "rights snapshot 不属于 MediaAsset ownerRefs",
                        rights_ref,
                    )
                )
                continue
            rights_path = objects / rights_ref.removeprefix("objects/")
            if not rights_path.is_file():
                issues.append(
                    _issue(
                        "release_media_rights_snapshot_missing",
                        "rights snapshot 在 immutable object closure 中不存在",
                        rights_ref,
                    )
                )
                continue
            try:
                rights = read_json(rights_path)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                issues.append(
                    _issue(
                        "release_media_rights_snapshot_invalid",
                        f"rights snapshot 无法读取: {exc}",
                        rights_ref,
                    )
                )
                continue
            if not isinstance(rights, Mapping):
                issues.append(
                    _issue(
                        "release_media_rights_snapshot_invalid",
                        "rights snapshot 必须是 JSON object",
                        rights_ref,
                    )
                )
                continue
            manifest_asset = rights.get("manifestAsset")
            if (
                str(rights.get("assetId") or "").strip() != asset_id
                or not isinstance(manifest_asset, Mapping)
                or str(manifest_asset.get("assetId") or "").strip() != asset_id
                or str(manifest_asset.get("sha256") or "").strip() != sha256
            ):
                issues.append(
                    _issue(
                        "release_media_rights_identity_mismatch",
                        "rights snapshot 未绑定同一 MediaAsset assetId/sha256",
                        rights_ref,
                    )
                )
                continue
            rights_by_owner[owner] = rights_by_owner.get(owner, 0) + 1
        for owner in owner_refs:
            if rights_by_owner.get(owner, 0) == 0:
                issues.append(
                    _issue(
                        "release_media_owner_rights_missing",
                        "每个 MediaAsset ownerRef 必须至少绑定一份 rights snapshot",
                        f"{asset_id}:{owner}",
                    )
                )

        physical = media_root / delivery_key
        if not physical.is_file():
            issues.append(
                _issue(
                    "release_media_public_slice_missing",
                    f"delivery body 不存在: {delivery_key}",
                    asset_id,
                )
            )
            continue
        if sha256_file(physical) != sha256:
            issues.append(
                _issue(
                    "release_media_public_slice_hash_mismatch",
                    "delivery body 与 MediaAsset sha256 不一致",
                    asset_id,
                )
            )
        actual_identity[asset_id] = sha256
        slice_owners[delivery_key] = asset_id

    expected_identity = {
        asset_id: str(value["sha256"])
        for asset_id, value in expected_assets.items()
    }
    if actual_identity != expected_identity:
        issues.append(
            _issue(
                "release_media_closure_mismatch",
                "media_manifest 必须精确等于 desired objects 的 MediaAsset 身份闭包",
                release_id,
            )
        )
    return issues


__all__ = ["release_media_issues", "release_private_storage_issues"]
