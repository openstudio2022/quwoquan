"""Validation helpers for materialized entity homepages."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from _common.asset_identity import parse_post_asset_id

_ASSET_REF_RE = re.compile(r"asset://([A-Za-z0-9_./\u4e00-\u9fff-]+)")


def _page_asset_refs(page: Path) -> set[str]:
    if not page.is_file():
        return set()
    refs: set[str] = set()
    for ref in _ASSET_REF_RE.findall(page.read_text(encoding="utf-8")):
        refs.add(ref.split("/")[-1])
    return refs


def _asset_closure_issues(entity_dir: Path, manifest_payload: dict[str, Any], label: str) -> list[str]:
    """Check page.md asset:// refs against manifest.assets and files on disk."""
    refs = _page_asset_refs(entity_dir / "page.md")
    assets = manifest_payload.get("assets") or []
    if not refs and not assets:
        return [f"{label}: 实体主页须配 ≥1 真实图片（page.md 用 asset:// 引用并在 manifest 登记）"]
    if not isinstance(assets, list):
        return [f"{label}: manifest.assets 须为数组"]
    id_to_file: dict[str, str] = {}
    file_names: set[str] = set()
    issues: list[str] = []
    for raw in assets:
        if not isinstance(raw, dict):
            continue
        asset_id = str(raw.get("assetId") or raw.get("id") or "").strip()
        file_name = str(raw.get("fileName") or "").strip()
        source_ref = str(raw.get("sourceRef") or "").strip()
        source_asset_ref = str(raw.get("sourceAssetRef") or "").strip()
        if asset_id:
            try:
                parse_post_asset_id(asset_id)
            except ValueError as exc:
                issues.append(f"{label}: invalid assetId {asset_id!r} ({exc})")
            id_to_file[asset_id] = file_name
        if file_name:
            file_names.add(file_name)
            if asset_id and Path(file_name).stem != asset_id:
                issues.append(f"{label}: fileName must be assetId.ext ({file_name} vs {asset_id})")
        if not source_ref or not source_asset_ref:
            issues.append(f"{label}: asset {asset_id or file_name or '<unknown>'} missing sourceRef/sourceAssetRef")
        elif "/assets/" in source_ref or not source_ref.endswith("/source.md"):
            issues.append(f"{label}: asset {asset_id or file_name} sourceRef must point to source.md")
        elif not source_asset_ref.startswith(source_ref.rsplit("/", 1)[0] + "/assets/"):
            issues.append(f"{label}: asset {asset_id or file_name} sourceAssetRef does not belong to sourceRef")
        if not (str(raw.get("authorizationProof") or "").strip() or str(raw.get("termsUrl") or "").strip()):
            issues.append(f"{label}: asset {asset_id or file_name or '<unknown>'} missing image rights proof")
    known_ids = set(id_to_file)
    for ref in sorted(refs):
        if ref not in known_ids and ref not in file_names:
            issues.append(f"{label}: page.md asset ref not in manifest: {ref}")
    assets_dir = entity_dir / "assets"
    for asset_id, file_name in sorted(id_to_file.items()):
        if not file_name:
            issues.append(f"{label}: asset {asset_id} missing fileName in manifest")
            continue
        if not (assets_dir / file_name).is_file():
            issues.append(f"{label}: asset file missing on disk: assets/{file_name} (assetId={asset_id})")
    return issues


def _catalog_keys(catalogs_root: Path, catalog_name: str, root_key: str) -> list[str]:
    path = catalogs_root / f"{catalog_name}.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rows = payload.get(root_key) if isinstance(payload, dict) else {}
    if not isinstance(rows, dict):
        return []
    return [str(key) for key in rows.keys() if str(key).strip()]


def _condition_profile_issues(entity_payload: dict[str, Any], label: str, *, catalogs_root: Path) -> list[str]:
    profile = entity_payload.get("conditionProfile")
    if not isinstance(profile, dict):
        return []
    issues: list[str] = []
    for field, catalog_name, root_key in (
        ("regions", "region_catalog", "regions"),
        ("seasons", "season_catalog", "seasons"),
    ):
        values = profile.get(field) or []
        if not isinstance(values, list):
            issues.append(f"{label}: conditionProfile.{field} 须为数组")
            continue
        allowed = set(_catalog_keys(catalogs_root, catalog_name, root_key))
        invalid = [str(value) for value in values if str(value) not in allowed]
        if invalid:
            issues.append(f"{label}: conditionProfile.{field} 越界: {', '.join(invalid)}")
    has_conditions = bool(profile.get("regions") or profile.get("seasons"))
    evidence_refs = profile.get("evidenceRefs")
    if has_conditions and not (isinstance(evidence_refs, list) and evidence_refs):
        issues.append(f"{label}: conditionProfile.evidenceRefs 缺失")
    return issues
