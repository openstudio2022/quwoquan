"""Validation boundary for materialized entity homepages."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from content.homepage.homepage import (
    _coverage_targets,
    _entity_base_draft,
    _homepage_gate_body,
    _page_char_count,
)
from content.homepage.homepage_introduction import _normalize_homepage_manifest_assets
from content.homepage.homepage_prompt import _homepage_base_source_issues
from content.homepage.homepage_release import (
    MIN_PAGE_CHARS,
    _CONDITION_CATALOGS_ROOT,
    _GEO_TAG_REF_PREFIX,
    _REQUIRED_ENTITY_FIELDS,
)
from content.homepage.quality_policy import homepage_source_fidelity_limit
from content.homepage.homepage_review import _entity_review_paths
from content.homepage.homepage_validation import (
    _asset_closure_issues,
    _condition_profile_issues,
)
from content.source.source_unit import resolve_entity_object_dir
from core.article_package import sha256_file
from core.entity_page_quality import entity_page_quality_issues
from core.io import read_json, write_json
from core.localization import fold_to_simplified
from core.paths import execution_entity_object_dir, relative_execution_ref
from core.template_fingerprints import template_fingerprint_issues

def _homepage_authenticity_issues(
    execution_id: str,
    domain: str,
    etype: str,
    name: str,
    page: Path,
    label: str,
) -> list[str]:
    """实体主页正文真实性门：模板指纹 + 底稿贴合度（作用在最终 page.md 正文上）。
    与文章同源：finalize 已在生成时把关，这里在校验侧做防御纵深，确保任何
    手改/回归都无法把机械模板或脱离底稿的从零另写蒙混过门。
    """
    issues: list[str] = []
    try:
        page_text = page.read_text(encoding="utf-8")
    except OSError:
        return issues
    gate_body = _homepage_gate_body(page_text)
    issues.extend(f"{label}: {msg}" for msg in template_fingerprint_issues(gate_body))
    base = _entity_base_draft(execution_id, domain, etype, name)
    base_text = fold_to_simplified(str((base or {}).get("text") or "").strip())
    if base_text:
        from content.post.fidelity import base_draft_fidelity_issues
        issues.extend(
            f"{label}: {msg}"
            for msg in base_draft_fidelity_issues(
                gate_body,
                base_text,
                carrier="article",
                max_ratio=homepage_source_fidelity_limit(execution_id),
                source_use_mode=str((base or {}).get("sourceUseMode") or "factual_reference_only"),
            )
        )
    return issues

def validate_entity_page(
    execution_id: str,
    domain: str,
    etype: str,
    name: str,
) -> list[str]:
    """校验单个实体主页三件套/字数/必填字段，返回阻断问题列表。"""
    resolve_entity_object_dir(execution_id, name, etype_hint=f"{domain}/{etype}")
    obj = execution_entity_object_dir(execution_id, domain, etype, name)
    page = obj / "page.md"
    ejson = obj / "_entity.json"
    manifest = obj / "manifest.json"
    label = f"{domain}/{etype}/{name}"
    issues: list[str] = []
    if not page.is_file():
        issues.append(f"{label}: page.md 缺失")
    else:
        chars = _page_char_count(page)
        if chars < MIN_PAGE_CHARS:
            issues.append(f"{label}: page.md 去空白 {chars} 字 < {MIN_PAGE_CHARS}")
        issues.extend(entity_page_quality_issues(page, label=label))
        issues.extend(_homepage_authenticity_issues(execution_id, domain, etype, name, page, label))
    if not manifest.is_file():
        issues.append(f"{label}: manifest.json 缺失")
        manifest_payload: dict[str, Any] = {}
    else:
        try:
            manifest_payload = read_json(manifest)
        except Exception as exc:
            issues.append(f"{label}: manifest.json 不可解析: {exc}")
            manifest_payload = {}
        else:
            if _normalize_homepage_manifest_assets(manifest_payload):
                write_json(manifest, manifest_payload)
            generator = str(manifest_payload.get("generator") or "")
            if generator != "agent":
                issues.append(
                    f"{label}: manifest.generator={generator or '<空>'}（实体主页须 generator=agent，"
                    "禁止脚本拼接/确定性物化伪装作者）"
                )
    if not ejson.is_file():
        issues.append(f"{label}: _entity.json 缺失")
        return issues
    try:
        payload = read_json(ejson)
    except Exception as exc:
        issues.append(f"{label}: _entity.json 不可解析: {exc}")
        return issues
    try:
        from core.schema import assert_valid

        assert_valid(payload, "publish", "entity", label=f"entity:{label}")
    except ValueError as exc:
        issues.append(f"{label}: _entity.json schema invalid: {exc}")
    for field in _REQUIRED_ENTITY_FIELDS:
        if not payload.get(field):
            issues.append(f"{label}: _entity.json 缺字段 {field}")
    if payload.get("domain") and payload["domain"] != domain:
        issues.append(f"{label}: _entity.json domain={payload['domain']} 与目录不一致")
    if payload.get("type") and payload["type"] != etype:
        issues.append(f"{label}: _entity.json type={payload['type']} 与目录不一致")
    # 地理归属契约（schema/publish/entity.schema.json）：主归属须为行政区树路径；
    # 全量数组存在时必须包含主归属（geoTagRef ∈ geoTagRefs）。
    geo_tag_ref = str(payload.get("geoTagRef") or "").strip()
    if geo_tag_ref and not geo_tag_ref.startswith(_GEO_TAG_REF_PREFIX):
        issues.append(f"{label}: _entity.json geoTagRef '{geo_tag_ref}' 必须以 {_GEO_TAG_REF_PREFIX} 开头")
    geo_tag_refs = [str(g).strip() for g in (payload.get("geoTagRefs") or []) if str(g).strip()]
    if geo_tag_refs:
        if geo_tag_ref and geo_tag_ref not in geo_tag_refs:
            issues.append(f"{label}: _entity.json geoTagRefs 必须包含主归属 geoTagRef '{geo_tag_ref}'")
        for ref in geo_tag_refs:
            if not ref.startswith(_GEO_TAG_REF_PREFIX):
                issues.append(f"{label}: _entity.json geoTagRefs 项 '{ref}' 必须以 {_GEO_TAG_REF_PREFIX} 开头")
    source_catalog_ref = str(manifest_payload.get("sourceCatalogRef") or "")
    source_catalog_path = obj / source_catalog_ref
    if not source_catalog_ref or not source_catalog_path.is_file():
        issues.append(f"{label}: manifest.sourceCatalogRef 不可解析")
    else:
        expected_catalog_sha = str(manifest_payload.get("sourceCatalogSha256") or "")
        actual_catalog_sha = sha256_file(source_catalog_path)
        if expected_catalog_sha != actual_catalog_sha:
            issues.append(f"{label}: source catalog digest drift")
        try:
            source_catalog = read_json(source_catalog_path)
            assert_valid(
                source_catalog,
                "publish",
                "source_catalog",
                label=f"source_catalog:{label}",
            )
        except (OSError, ValueError, TypeError) as exc:
            issues.append(f"{label}: source catalog invalid: {exc}")
        else:
            catalog_sources = [
                row
                for row in (source_catalog.get("sources") or [])
                if isinstance(row, dict)
            ]
            catalog_unit_ids = {
                str(row.get("sourceUnitId") or "").strip()
                for row in catalog_sources
                if str(row.get("sourceUnitId") or "").strip()
            }
            declared_source_unit_ids = {
                Path(str(ref)).parent.name
                for ref in (manifest_payload.get("sourceRefs") or [])
                if str(ref).strip()
            }
            if catalog_unit_ids != declared_source_unit_ids:
                issues.append(
                    f"{label}: source catalog 未精确闭包 manifest.sourceRefs"
                )
            projected_primary = {
                key: (source_catalog.get("primarySource") or {}).get(key)
                for key in (
                    "sourceKind",
                    "entityName",
                    "extractor",
                    "canonicalUrl",
                    "sourceUrl",
                    "title",
                    "fetchedAt",
                    "snapshotHash",
                    "policyRevision",
                    "sourceUseMode",
                )
            }
            if payload.get("primarySource") != projected_primary:
                issues.append(f"{label}: _entity.primarySource 与 source catalog 漂移")
            if payload.get("sourceUrls") != [projected_primary.get("sourceUrl")]:
                issues.append(f"{label}: _entity.sourceUrls 与 source catalog 漂移")
    issues.extend(_condition_profile_issues(payload, label, catalogs_root=_CONDITION_CATALOGS_ROOT))
    issues.extend(_homepage_base_source_issues(execution_id, domain, etype, name))
    issues.extend(_asset_closure_issues(obj, manifest_payload, label))
    from content.homepage.homepage_validation import homepage_structure_issues
    issues.extend(homepage_structure_issues(obj, manifest_payload, label))
    declared_image_refs = {
        str(item).strip()
        for item in (payload.get("imageSourceRefs") or [])
        if str(item).strip()
    }
    for raw in manifest_payload.get("assets") or []:
        if not isinstance(raw, dict):
            continue
        asset_source = str(raw.get("sourceRef") or "")
        if asset_source and asset_source not in declared_image_refs:
            issues.append(
                f"{label}: asset {raw.get('assetId') or raw.get('fileName')} "
                "sourceRef missing from _entity.imageSourceRefs"
            )
    review_path, provenance_path, finalization_path = _entity_review_paths(
        execution_id,
        domain,
        etype,
        name,
    )
    for sidecar in (review_path, provenance_path, finalization_path):
        if not sidecar.is_file():
            issues.append(f"{label}: {relative_execution_ref(sidecar, execution_id)} 缺失")
    return issues

def validate_entity_pages(execution_id: str, spec: dict[str, Any]) -> list[str]:
    """校验全部 coverage 实体主页，返回阻断问题列表（空=采纳通过）。"""
    targets = _coverage_targets(spec, execution_id=execution_id)
    if not targets:
        return ["build validate: scope.coverageTargets 为空，无可校验实体"]
    issues: list[str] = []
    for target in targets:
        issues.extend(
            validate_entity_page(
                execution_id,
                target["domain"],
                target["etype"],
                target["name"],
            )
        )
    return issues
