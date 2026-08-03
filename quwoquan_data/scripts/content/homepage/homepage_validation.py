"""Validation helpers for materialized entity homepages."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from core.asset_identity import parse_post_asset_id
from governance.coverage.license import rights_proof_required

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
    assets = manifest_payload.get("assets")
    if not isinstance(assets, list):
        return [f"{label}: manifest.assets 须为数组"]
    id_to_file: dict[str, str] = {}
    file_names: set[str] = set()
    issues: list[str] = []
    vertical = str(manifest_payload.get("vertical") or "").strip()
    if not vertical:
        return [f"{label}: manifest missing vertical policy owner"]
    require_rights_proof = rights_proof_required(vertical)
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
        if require_rights_proof and not (
            str(raw.get("authorizationProof") or "").strip()
            or str(raw.get("termsUrl") or "").strip()
        ):
            issues.append(f"{label}: asset {asset_id or file_name or '<unknown>'} missing image rights proof")
        if not require_rights_proof and str(
            raw.get("rightsAuditStatus") or ""
        ) not in {"verified", "unverified", "restricted", "unknown"}:
            issues.append(
                f"{label}: asset {asset_id or file_name or '<unknown>'} missing rights audit status"
            )
    assets_dir = entity_dir / "assets"
    text_refs = manifest_payload.get("textSourceRefs") or []
    image_refs = manifest_payload.get("imageSourceRefs") or []
    if isinstance(text_refs, list) and isinstance(image_refs, list):
        if len({str(r) for r in text_refs if str(r).strip()}) > 1:
            issues.append(f"{label}: textSourceRefs must contain exactly one source unit")
        if len({str(r) for r in image_refs if str(r).strip()}) > 1:
            issues.append(f"{label}: imageSourceRefs must contain exactly one source unit")
        image_set = {str(r) for r in image_refs if str(r).strip()}
        if assets and not image_set:
            issues.append(f"{label}: imageSourceRefs must declare the asset source unit")
        for raw in assets:
            if not isinstance(raw, dict):
                continue
            source_ref = str(raw.get("sourceRef") or "").strip()
            if source_ref and source_ref not in image_set:
                issues.append(
                    f"{label}: asset {raw.get('assetId') or raw.get('fileName')} "
                    "sourceRef missing from imageSourceRefs"
                )
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


_FIGURE_OPEN_RE = re.compile(r"^:::figure\b(?P<attrs>[^\n]*)$", re.M)
_GALLERY_OPEN_RE = re.compile(r"^:::gallery\b[^\n]*$", re.M)
_RELATED_HEADING = "## 相关图片"
_LEFTOVER_PLACEHOLDER_RE = re.compile(r"\[\[IMG:[^\]]*\]\]|asset://source-inline-\d+")
_ALLOWED_MANIFEST_ROLES = {"cover", "inline", "related"}


def homepage_structure_issues(entity_dir: Path, manifest_payload: dict[str, Any], label: str) -> list[str]:
    """主页三段结构门（封面 frontmatter + 正文块级内嵌图 + 页尾相关图片）。

    契约（百科主页结构化计划 §6/§7）：
    - frontmatter 声明唯一 coverImage；正文不重复引用封面资产。
    - 正文 `:::figure` 一律 layout="fullWidth"（禁 wrapLeft/wrapRight）。
    - `:::gallery` 只允许出现在文末 `## 相关图片` 章节内，且最多一个。
    - manifest.assets.role 收敛为 cover/inline/related，cover 唯一。
    - 零 AI 占位符 / IR 占位残留。
    """
    page_path = entity_dir / "page.md"
    if not page_path.is_file():
        return []
    text = page_path.read_text(encoding="utf-8")
    issues: list[str] = []

    assets = manifest_payload.get("assets")
    if not isinstance(assets, list):
        return [f"{label}: manifest.assets 须为数组"]

    # 有媒体时必须有唯一封面；无媒体主页不得伪造封面。
    cover_asset_id = ""
    covers: list[str] = []
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        head = text[:end] if end != -1 else ""
        covers = re.findall(r"^coverImage:\s*asset://(\S+)\s*$", head, re.M)
        if assets and len(covers) != 1:
            issues.append(f"{label}: frontmatter 必须声明唯一 coverImage（实得 {len(covers)}）")
        elif not assets and covers:
            issues.append(f"{label}: 无媒体主页不得声明 coverImage")
        elif covers:
            cover_asset_id = covers[0].split("/")[-1]
    elif assets:
        issues.append(f"{label}: page.md 缺 frontmatter（coverImage 必须在 frontmatter 声明）")

    body = text[text.find("\n---\n", 4) + 5 :] if text.startswith("---\n") and "\n---\n" in text[4:] else text

    # 正文不重复展示封面。
    if cover_asset_id and re.search(rf"^asset://(?:\S*/)?{re.escape(cover_asset_id)}\s*$", body, re.M):
        issues.append(f"{label}: 封面资产 {cover_asset_id} 不得在正文重复展示（封面只在 frontmatter）")

    # 占位符残留。
    leftovers = _LEFTOVER_PLACEHOLDER_RE.findall(body)
    if leftovers:
        issues.append(f"{label}: page.md 残留占位符 {sorted(set(leftovers))[:3]}（AI 占位/IR 占位不得进入成品）")

    # figure 布局契约。
    for m in _FIGURE_OPEN_RE.finditer(body):
        attrs = m.group("attrs")
        layout_match = re.search(r'layout="([^"]*)"', attrs)
        layout = layout_match.group(1) if layout_match else ""
        if layout != "fullWidth":
            issues.append(f"{label}: 正文 figure 必须块级 fullWidth，实得 layout={layout or '<缺失>'}")

    # gallery 只允许在页尾相关图片章节。
    related_pos = body.find(_RELATED_HEADING)
    galleries = list(_GALLERY_OPEN_RE.finditer(body))
    if len(galleries) > 1:
        issues.append(f"{label}: 最多一个 :::gallery（页尾相关图片区），实得 {len(galleries)}")
    for g in galleries:
        if related_pos < 0 or g.start() < related_pos:
            issues.append(f"{label}: :::gallery 只允许出现在文末 '{_RELATED_HEADING}' 章节内")
    if related_pos >= 0:
        # 相关图片必须是文末章节：其后不得再有其它 H2 章节。
        rest = body[related_pos + len(_RELATED_HEADING) :]
        if re.search(r"^##\s", rest, re.M):
            issues.append(f"{label}: '{_RELATED_HEADING}' 必须是文末最后一个章节")

    # manifest roles 收敛。
    roles = [str(a.get("role") or "") for a in assets if isinstance(a, dict)]
    cover_count = sum(1 for r in roles if r == "cover")
    if assets and cover_count != 1:
        issues.append(f"{label}: manifest.assets 必须恰好一个 role=cover（实得 {cover_count}）")
    for role in roles:
        if role and role not in _ALLOWED_MANIFEST_ROLES:
            issues.append(f"{label}: manifest.assets.role 非法值 {role}（允许 cover/inline/related）")
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
