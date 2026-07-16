"""Entity homepage final materialization and validation."""
from __future__ import annotations
import os
import shutil
import re
from pathlib import Path
from typing import Any
import yaml
from core.io import read_json, write_assistant_task, write_json
from content.execution.runtime_contract import canonical_sha256, stage_execution_context
from core.article_package import compute_document_sha256, sha256_file, sha256_text
from content.post.draft_io import PLACEHOLDER_MARKER, is_placeholder
from core.entity_page_quality import entity_page_quality_issues
from core.localization import fold_to_simplified
from core.prompt_render import render
from content.execution.prompt_snapshot import prompt_bundle_revision, write_prompt_snapshot
from core.baike_source_contract import HOMEPAGE_SOURCE_POLICY_REVISION
from core.template_fingerprints import template_fingerprint_issues
from core.post_evidence_chain import build_finalization_report
from core.provenance import build_provenance
from core.paths import (
    STAGE_COMPOSE,
    STAGE_DRAFT,
    STAGE_QUALITY,
    STAGE_REVIEW,
    execution_entity_object_dir,
    execution_entity_stage_dir,
    execution_assistant_task,
    execution_entity_page_input_path,
    execution_root,
    relative_execution_ref,
    execution_data,
)
from governance.coverage.entity_extract import entity_ref, require_domain_etype
from content.source.source_unit import resolve_entity_object_dir
from content.homepage.homepage_introduction import (
    _normalize_homepage_manifest_assets,
    homepage_introduction_seed_from_triplet,
)
from content.homepage.homepage_text import (
    _homepage_base_source_issue_text,
    _homepage_source_text,
    _homepage_summary,
    _split_fact_sentences,
    _strip_frontmatter,
    homepage_base_draft_readiness,
)
from content.homepage.homepage_validation import _asset_closure_issues, _condition_profile_issues
from content.homepage.homepage_materialization import (
    _homepage_outline_issues,
    _homepage_source_figure_issues,
    _replace_homepage_source_asset_refs,
    _ensure_homepage_cover_frontmatter,
    _fold_homepage_manifest_assets,
    _homepage_layout_assets,
)
from content.homepage.homepage_source_catalog import _materialize_homepage_source_catalog
from content.homepage.homepage_review import (
    _entity_draft_dir,
    _entity_review_paths,
    _entity_review_payload,
    _write_entity_review_sidecars,
)
from content.homepage.homepage_refs import (
    dedupe_nonempty as _dedupe_nonempty,
    safe_ref as _safe_ref,
    same_source_unit as _same_source_unit,
)
from content.homepage.homepage_assets import (
    _asset_wiki_filename,
    _normalize_wiki_filename,
    copy_homepage_asset,
    select_homepage_assets,
    write_homepage_media_dispositions,
)
MIN_PAGE_CHARS = 350
HOMEPAGE_FIDELITY_MAX = 0.92
# 实体主页底稿下发上限：取消旧的 4000 截断（旧值会把维基百科页在中段截断，
# Agent 看不到「技术变革 / 相关古迹」等后段章节，导致多级目录与章节缺失）。
# 放宽到覆盖绝大多数百科页全文，仅兜底极端超长源避免 token 失控。
HOMEPAGE_BASE_DRAFT_MAX_CHARS = max(4000, int(os.environ.get("QWQ_HOMEPAGE_BASE_DRAFT_MAX_CHARS", "12000")))
# 计入 sectionOutline 的关键章节最小去空白正文字数（短于此视为占位/导语碎片）。
HOMEPAGE_SECTION_MIN_CHARS = 120
# 发布态 _entity.json 必填集（结构契约唯一定义 = schema/publish/entity.schema.json）。
# geoTagRef 为区县级主归属行政区标签（裁决 7：单值主归属 + 可选 geoTagRefs 全量数组），
# 自 discovery_seed/2 起为物化必填；geoTagRefs 仅跨省/跨市地点提供。
_REQUIRED_ENTITY_FIELDS = (
    "label",
    "domain",
    "type",
    "executionId",
    "geoTagRef",
    "primarySource",
    "sourceUrls",
)
_GEO_TAG_REF_PREFIX = "Topic/地理/行政区/"
_REPO_DATA_ROOT = Path(__file__).resolve().parents[2]
_CONDITION_CATALOGS_ROOT = _REPO_DATA_ROOT / "control_plane" / "_shared" / "catalogs"
_WIKI_FILE_INLINE_RE = re.compile(r"\[\[(?:File|文件):[^\]]+\]\]", re.IGNORECASE)

from content.homepage.homepage import (
    _coverage_targets,
    _entity_base_draft,
    _entity_source_paths,
    _homepage_gate_body,
    _homepage_tag_refs,
    _page_char_count,
)
from content.homepage.homepage_prompt import _homepage_base_source_issues

def materialize_entity_page(execution_id: str, domain: str, etype: str, name: str) -> list[str]:
    """把创作 agent写回的 `4.draft/page.md` 正文终态化为实体主页三件套。
    不再脚本拼正文/切句/凑字：正文必须由创作 agent在底稿基础上轻改创作（generator=agent）。
    finalize 只做：① 贴合度门 + 模板指纹门把关 Agent 正文；② 从同源 unit 选封面/图库写入 manifest；
    ③ 据正文事实确定性映射 summary；④ 写 generator=agent 与真实 agentRunId provenance。
    正文 page.md 由 Agent 写纯文字 + 多级标题，finalize 按章节/段落锚点把同源真实图
    确定性注入正文 figure 块（图文混排，闭环登记到 manifest）。创作 agent未写回或仍是占位时
    返回等待项，checkpoint 阻塞等待，绝不退回脚本拼接。
    """
    label = f"{domain}/{etype}/{name}"
    input_path = execution_entity_page_input_path(execution_id, domain, etype, name)
    if not input_path.is_file():
        return [f"{label}: entity_page_input.json 缺失"]
    envelope = read_json(input_path)
    payload = envelope.get("payload") if isinstance(envelope.get("payload"), dict) else envelope
    base = payload.get("baseDraft") if isinstance(payload.get("baseDraft"), dict) else {}
    base_text = str(base.get("text") or "").strip()
    if not base_text:
        return [f"{label}: homepage baseDraft.text 缺失（先回退 source 修复，再创作主页）"]
    draft_dir = _entity_draft_dir(execution_id, domain, etype, name)
    # 失败协议：Agent 判定底稿与实体不一致/不足以支撑主页时写 failure.json，
    # finalize 结构化阻断并指回 source 修复，绝不带病物化。
    from core.homepage_source_judge import entity_page_failure_issues, read_entity_page_failure
    failure = read_entity_page_failure(draft_dir)
    if failure is not None:
        failure_problems = entity_page_failure_issues(failure, entity_name=name)
        if failure_problems:
            return [f"{label}: 4.draft/failure.json 不合法: {p}" for p in failure_problems]
        failure_reasons = "; ".join(
            str(r).strip() for r in (failure.get("reasons") or []) if str(r).strip()
        )
        return [
            f"{label}: Agent 失败协议（{failure.get('failureKind')}）：{failure_reasons or '底稿与实体不一致'}"
            "；已阻断 finalize，请回退 source 修复/更换底稿后删除 failure.json 重跑"
        ]
    draft_page = draft_dir / "page.md"
    if not draft_page.is_file():
        return [f"{label}: 等待创作 agent写回 4.draft/page.md（generator=agent 正文）"]
    draft_text = draft_page.read_text(encoding="utf-8")
    if is_placeholder(draft_text):
        return [f"{label}: 4.draft/page.md 仍是占位，等待创作 agent按底稿创作正文"]
    draft_meta_path = draft_dir / "draft_meta.json"
    if not draft_meta_path.is_file():
        return [f"{label}: 4.draft/draft_meta.json 缺失"]
    try:
        from core.schema import assert_valid

        draft_meta = read_json(draft_meta_path)
        assert_valid(draft_meta, "content", "draft_meta", label=f"draft_meta:{name}")
    except (OSError, ValueError, TypeError) as exc:
        return [f"{label}: 4.draft/draft_meta.json 不合法: {exc}"]
    if str(draft_meta.get("status") or "") != "completed":
        return [f"{label}: 4.draft/draft_meta.status 必须为 completed"]
    self_check = draft_meta.get("selfCheck") if isinstance(draft_meta.get("selfCheck"), dict) else {}
    if str(self_check.get("status") or "") != "passed" or list(self_check.get("issues") or []):
        return [f"{label}: 4.draft/draft_meta.selfCheck 必须通过"]
    if str(draft_meta.get("draftSha256") or "") != compute_document_sha256(draft_text):
        return [f"{label}: 4.draft/draft_meta.draftSha256 与 page.md 不一致"]
    if not str(draft_meta.get("agentRunId") or "").strip():
        return [f"{label}: 4.draft/draft_meta.agentRunId 缺失"]
    # 主页不复用文章的 figuregroup 回带协议。图集成员不会进入 Agent 底稿，
    # 而是由 imagePlacements 在 finalize 时统一写入「相关图片」。
    draft_text = fold_to_simplified(draft_text)
    structure_issues = _homepage_outline_issues(
        [row for row in (base.get("sectionOutline") or []) if isinstance(row, dict)],
        draft_text,
        label,
    )
    structure_issues.extend(_homepage_source_figure_issues(base, draft_text, label))
    # AI 最小干扰协议：占位符一致性校验（缺失/新增/重复/行尾追加文字 → 结构化 reject），
    # 通过后代码侧把 [[IMG:fig_NN]] 展开为块级 fullWidth figure（caption 只用 bindings 原图注）。
    from core.ai_refine_protocol import expand_image_placeholders, placeholder_consistency_issues
    # draft_text 已做繁简折叠，bindings caption 同步折叠避免繁体图注误判「被改写」。
    placeholder_bindings = [
        {**row, "caption": fold_to_simplified(str(row.get("caption") or ""))}
        for row in (payload.get("imagePlaceholderBindings") or [])
        if isinstance(row, dict)
    ]
    structure_issues.extend(
        placeholder_consistency_issues(draft_text, placeholder_bindings, label=label)
    )
    if structure_issues:
        return structure_issues
    draft_text = expand_image_placeholders(draft_text, placeholder_bindings)
    gate_body = _homepage_gate_body(draft_text)
    base_text_for_gate = fold_to_simplified(base_text)
    gate_issues: list[str] = []
    gate_issues.extend(f"{label}: {msg}" for msg in template_fingerprint_issues(gate_body))
    from content.post.fidelity import base_draft_fidelity_issues
    gate_issues.extend(
        f"{label}: {msg}"
        for msg in base_draft_fidelity_issues(
            gate_body,
            base_text_for_gate,
            carrier="article",
            max_ratio=HOMEPAGE_FIDELITY_MAX,
            source_use_mode=str(base.get("sourceUseMode") or "factual_reference_only"),
        )
    )
    if gate_issues:
        return gate_issues
    selection = select_homepage_assets(
        execution_id,
        domain,
        etype,
        name,
        primary_ref=str(
            base.get("primaryEvidenceRef") or base.get("sourceRef") or ""
        ).strip(),
    )
    images = [dict(image) for image in selection.publishable]
    if not images:
        return [f"{label}: homepage lane 无可发布图片资产"]
    obj = execution_entity_object_dir(execution_id, domain, etype, name)
    obj.mkdir(parents=True, exist_ok=True)
    from core.paths import STAGE_REVIEW, ensure_object_stages
    ensure_object_stages(obj, through_stage=STAGE_REVIEW)
    assets: list[dict[str, Any]] = []
    for index, image in enumerate(images):
        # 三段角色契约（cover/inline/related）：初始非封面图默认 related，
        # place_homepage_assets_in_markdown 按锚点+原图注裁决是否提升为 inline。
        manifest_role = "cover" if index == 0 else "related"
        # assetId 仅接受 cover/closing/detail；inline/related 语义写入 manifest.role。
        asset_role = "cover" if index == 0 else "detail"
        asset = copy_homepage_asset(
            execution_id,
            obj,
            name,
            image,
            role=asset_role,
        )
        if asset:
            asset["role"] = manifest_role
            assets.append(asset)
    if not assets:
        return [f"{label}: homepage asset copy failed"]
    draft_text = _replace_homepage_source_asset_refs(draft_text, assets)
    # 配图确定性注入（主页三段契约）：封面只进 frontmatter；有原图注的图按章节锚点
    # 注入正文块级 fullWidth figure（每章节最多 1 张）；其余进文末『## 相关图片』gallery。
    # 幂等：Agent 已内联的 asset:// 不重复注入。
    from core.asset_placement import place_homepage_assets_in_markdown
    from governance.creators.assignment import creator_from_payload
    creator_fields = creator_from_payload(payload)
    image_placements: list[dict[str, Any]] = []
    unit_ref = str(base.get("primaryEvidenceRef") or base.get("sourceRef") or "").strip()
    if unit_ref:
        try:
            meta_path = execution_root(execution_id) / Path(unit_ref).parent / "meta.json"
            if meta_path.is_file():
                meta = read_json(meta_path)
                raw_placements = meta.get("imagePlacements") if isinstance(meta, dict) else []
                if isinstance(raw_placements, list):
                    image_placements = [row for row in raw_placements if isinstance(row, dict)]
        except (OSError, ValueError, TypeError):
            image_placements = []
    _homepage_layout_assets(assets)
    # 把 meta.imagePlacements 的 caption 回填到 manifest assets（wikitext 语义 caption）。
    # 用规范化原始 wiki 文件名精确等值匹配；禁止子串匹配（实体名会污染批次路径）。
    placement_caption_by_file = {
        _normalize_wiki_filename(str(p.get("fileName") or "")): str(p.get("caption") or "")
        for p in image_placements
        if str(p.get("fileName") or "").strip() and str(p.get("caption") or "").strip()
    }
    if placement_caption_by_file:
        for asset in assets:
            key = _asset_wiki_filename(asset)
            cap = placement_caption_by_file.get(key) if key else None
            if cap:
                asset["caption"] = fold_to_simplified(cap)
    from core.asset_placement import _caption_is_degraded
    for asset in assets:
        caption = str(asset.get("caption") or "")
        file_name = str(asset.get("fileName") or "")
        if str(asset.get("role") or "") == "cover":
            if _caption_is_degraded(caption, file_name=file_name):
                # 封面退化 caption 回退到原文标题（实体名），禁止任何领域硬编码补全。
                asset["caption"] = name
            else:
                asset["caption"] = fold_to_simplified(caption)
        elif _caption_is_degraded(caption, file_name=file_name):
            # 非封面图退化 caption 一律清空：无原图注不加说明、禁止虚构或文件名占位。
            asset["caption"] = ""
        else:
            asset["caption"] = fold_to_simplified(caption)
    # wikitext imagePlacements 用 fileName 锚点；finalize 已分配 assetId，在此对齐。
    # 同样用原始 wiki 文件名精确等值匹配，杜绝实体名子串误命中。
    asset_id_by_wiki_name: dict[str, str] = {}
    for asset in assets:
        key = _asset_wiki_filename(asset)
        if key and key not in asset_id_by_wiki_name:
            asset_id_by_wiki_name[key] = str(asset.get("assetId") or "")
    resolved_placements: list[dict[str, Any]] = []
    for row in image_placements:
        if not isinstance(row, dict):
            continue
        key = _normalize_wiki_filename(str(row.get("fileName") or ""))
        matched_id = asset_id_by_wiki_name.get(key, "") if key else ""
        if matched_id:
            resolved_placements.append({**row, "assetId": matched_id})
    final_text = place_homepage_assets_in_markdown(
        draft_text,
        assets,
        placements=resolved_placements or image_placements,
    )
    cover_asset_id = next(
        (str(a.get("assetId") or "") for a in assets if a.get("role") == "cover"),
        str((assets[0] or {}).get("assetId") or ""),
    )
    final_text = _ensure_homepage_cover_frontmatter(final_text, cover_asset_id)
    final_text = fold_to_simplified(final_text)
    from core.page_media import HomepageAssetDisposition, HomepageMediaDisposition

    media_dispositions = list(selection.excluded)
    media_dispositions.extend(
        HomepageMediaDisposition(
            source_asset_ref=str(asset.get("sourceAssetRef") or "").strip(),
            source_asset_id=str(asset.get("sourceAssetId") or "").strip(),
            asset_id=str(asset.get("assetId") or "").strip(),
            disposition=HomepageAssetDisposition(str(asset.get("role") or "")),
            reason="published",
        )
        for asset in assets
    )
    write_homepage_media_dispositions(
        entity_dir=obj,
        execution_id=execution_id,
        object_ref=entity_ref(domain, etype, name),
        records=media_dispositions,
    )
    _fold_homepage_manifest_assets(assets, obj / "assets", execution_id=execution_id)
    (obj / "page.md").write_text(final_text, encoding="utf-8")
    facts = _split_fact_sentences(gate_body, entity_name=name) or _split_fact_sentences(base_text_for_gate, entity_name=name)
    single_source = str(base.get("primaryEvidenceRef") or base.get("sourceRef") or "").strip()
    text_source_refs = _dedupe_nonempty([single_source])
    image_source_refs = _dedupe_nonempty(
        [str(asset.get("sourceRef") or "").strip() for asset in assets]
    )
    source_refs = _dedupe_nonempty([*text_source_refs, *image_source_refs])
    tag_refs = _homepage_tag_refs(domain, etype, name, payload)
    # 地理归属写入通路（裁决 7 / schema/publish/entity.schema.json）：
    # geoTagRef 单值主归属为物化必填（缺失由 validate_entity_page 阻断），
    # geoTagRefs 全量数组与 aliases 仅在上游（主清单→coverageTargets→payload）提供时写入。
    geo_tag_ref = str(payload.get("geoTagRef") or "").strip()
    geo_tag_refs = _dedupe_nonempty([str(g).strip() for g in (payload.get("geoTagRefs") or [])])
    entity_aliases = _dedupe_nonempty([str(a).strip() for a in (payload.get("aliases") or [])])
    geo_fields: dict[str, Any] = {}
    if geo_tag_ref:
        geo_fields["geoTagRef"] = geo_tag_ref
    if geo_tag_refs:
        geo_fields["geoTagRefs"] = geo_tag_refs
    if entity_aliases:
        geo_fields["aliases"] = entity_aliases
    try:
        primary_source, source_urls, primary_evidence_ref, source_catalog_sha = (
            _materialize_homepage_source_catalog(
                execution_id,
                obj,
                base,
                fallback_title=name,
            )
        )
    except (OSError, ValueError, TypeError) as exc:
        return [f"{label}: homepage source catalog materialize failed: {exc}"]
    entity_payload = {
        "label": name,
        "domain": domain,
        "type": etype,
        "executionId": execution_id,
        "entityRef": entity_ref(domain, etype, name),
        "summary": _homepage_summary(name, facts, base_text=gate_body or base_text),
        "sourceRefs": source_refs,
        "sourceUrls": source_urls,
        "primarySource": primary_source,
        "textSourceRefs": text_source_refs,
        "imageSourceRefs": image_source_refs,
        "tagRefs": tag_refs,
        **geo_fields,
        **creator_fields,
    }
    from core.schema import assert_valid

    assert_valid(entity_payload, "publish", "entity", label=f"entity:{name}")
    write_json(obj / "_entity.json", entity_payload)
    write_json(
        obj / "manifest.json",
        {
            "entityRef": entity_ref(domain, etype, name),
            "executionId": execution_id,
            "sourceCatalogRef": "evidence/source_catalog.json",
            "sourceCatalogSha256": source_catalog_sha,
            "primaryEvidenceRef": primary_evidence_ref,
            "sourceRefs": source_refs,
            "textSourceRefs": text_source_refs,
            "imageSourceRefs": image_source_refs,
            "tagRefs": tag_refs,
            "assets": assets,
            "generator": "agent",
            "provider": str(draft_meta.get("provider") or ""),
            "model": str(draft_meta.get("model") or ""),
            "agentRunId": str(draft_meta.get("agentRunId") or ""),
            "agentId": str(draft_meta.get("agentId") or ""),
            **creator_fields,
        },
    )
    source_paths = _entity_source_paths(execution_id, domain, etype, name)
    review_payload = _entity_review_payload(
        issues=[],
        source_paths=source_paths,
        base_draft_exists=bool(source_paths),
    )
    _write_entity_review_sidecars(
        execution_id,
        domain,
        etype,
        name,
        source_paths=source_paths,
        review_payload=review_payload,
    )
    return []

def materialize_entity_pages(execution_id: str, spec: dict[str, Any]) -> list[str]:
    """物化所有缺失或未过门的 coverage 实体主页，返回剩余物化问题。"""
    issues: list[str] = []
    for target in _coverage_targets(spec, execution_id=execution_id):
        domain, etype, name = target["domain"], target["etype"], target["name"]
        current_issues = validate_entity_page(
            execution_id,
            domain,
            etype,
            name,
        )
        if not current_issues:
            continue
        issues.extend(materialize_entity_page(execution_id, domain, etype, name))
    return issues

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
                max_ratio=HOMEPAGE_FIDELITY_MAX,
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
