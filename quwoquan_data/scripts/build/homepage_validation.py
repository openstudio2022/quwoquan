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
    """Check manifest.assets closure; page.md MAY inline asset:// figures (must close to manifest).

    图文混排策略：正文可按章节/段落内联 `:::figure` 块引用 asset://（与文章一致），
    但每个引用都必须闭环到 manifest.assets；纯文字 page.md（无 asset://）同样合法。
    """
    page_path = entity_dir / "page.md"
    refs = _page_asset_refs(page_path)
    assets = manifest_payload.get("assets") or []
    if not assets:
        return [f"{label}: 实体主页须配 ≥1 真实图片（manifest.assets 登记）"]
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
    assets_dir = entity_dir / "assets"
    text_refs = manifest_payload.get("textSourceRefs") or []
    image_refs = manifest_payload.get("imageSourceRefs") or []
    if isinstance(text_refs, list) and isinstance(image_refs, list):
        if len({str(r) for r in text_refs if str(r).strip()}) > 1:
            issues.append(f"{label}: textSourceRefs must contain exactly one source unit")
        if len({str(r) for r in image_refs if str(r).strip()}) > 1:
            issues.append(f"{label}: imageSourceRefs must contain exactly one source unit")
        text_set = {str(r) for r in text_refs if str(r).strip()}
        image_set = {str(r) for r in image_refs if str(r).strip()}
        if text_set and image_set and text_set != image_set:
            issues.append(f"{label}: textSourceRefs and imageSourceRefs must be the same single unit")
    roles = {str(raw.get("role") or "") for raw in assets if isinstance(raw, dict)}
    if assets and "cover" not in roles:
        issues.append(f"{label}: manifest.assets must include role=cover")
    for asset_id, file_name in sorted(id_to_file.items()):
        if not file_name:
            issues.append(f"{label}: asset {asset_id} missing fileName in manifest")
            continue
        if not (assets_dir / file_name).is_file():
            issues.append(f"{label}: asset file missing on disk: assets/{file_name} (assetId={asset_id})")
    # 图文混排闭环：page.md 内联的每个 asset:// 必须命中 manifest.assets（按 assetId 或 fileName stem）。
    manifest_ids = set(id_to_file.keys())
    manifest_stems = {Path(fn).stem for fn in file_names if fn}
    for ref in sorted(refs):
        if ref not in manifest_ids and ref not in manifest_stems:
            issues.append(f"{label}: page.md 引用的 asset {ref} 不在 manifest.assets（图文未闭环）")
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
