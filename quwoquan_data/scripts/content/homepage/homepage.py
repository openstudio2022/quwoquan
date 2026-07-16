"""实体主页 build 真实链路：prepare 下发产出契约 + validate 采纳门。
与现行「三层目录实体」模型一致（entities/{领域}/{类型}/{名称}/）：
- prepare：读 execution spec，为每个实体写 compose input、prompt 与 draft 占位。
- Agent：读 prompt.md 与底稿，在底稿基础上做适度润色/事实校正/PII·平台痕迹清理/人设适配，
  把正文写回 4.draft/page.md（≥350字、保留底稿原句最小改、不脱离底稿从零另写、不机械模板凑字）。
- finalize：不拼正文，只校验 Agent 草稿并物化 page、entity、manifest 与摘要证据。
- validate：逐 coverage 实体校验三件套/字数/必填字段，并复检 generator=agent+贴合度+模板指纹，
  作为 promote 发布门之前的采纳门。
"""
from __future__ import annotations
import os
import shutil
import re
from pathlib import Path
from typing import Any
import yaml
from core.io import read_json, write_assistant_task, write_json
from core.data_issue import (
    DataIssue,
    DataIssueCode,
    DataIssueLane,
    DataIssueStage,
    DataRecoveryAction,
    data_issue,
)
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
    copy_homepage_asset,
    select_homepage_assets,
    write_homepage_media_dispositions,
)
from content.homepage.homepage_prompt import (
    _entity_available_images_block,
    _entity_base_draft_block,
    _entity_base_source_line,
    _entity_section_outline_block,
    _entity_type_focus_block,
    _homepage_base_source_issues,
    _homepage_base_text_with_image_placeholders,
    _homepage_image_placeholder_bindings,
    _homepage_section_outline,
    _homepage_structured_source_text,
    _render_entity_page_prompt,
    _write_entity_page_prompt_and_placeholder,
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
def _coverage_targets(
    spec: dict[str, Any],
    *,
    execution_id: str = "",
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    del execution_id
    for target in (spec.get("scope") or {}).get("coverageTargets") or []:
        name = str(target.get("name") or "").strip()
        if not name:
            continue
        domain, etype = require_domain_etype(
            target.get("entityType"),
            context=f"coverageTargets[{name}]",
        )
        row: dict[str, Any] = {"name": name, "domain": domain, "etype": etype}
        # 主清单（discovery_seed/2）契约字段透传：geo 主/全量归属、全量类型、别名。
        geo_tag_ref = str(target.get("geoTagRef") or "").strip()
        if geo_tag_ref:
            row["geoTagRef"] = geo_tag_ref
        for list_field in ("geoTagRefs", "typeTagRefs", "aliases"):
            values = [str(v).strip() for v in (target.get(list_field) or []) if str(v).strip()]
            if values:
                row[list_field] = values
        out.append(row)
    return out
def homepage_runtime_spec(execution_id: str, spec: dict[str, Any]) -> dict[str, Any]:
    """Return the immutable execution specification used by homepage stages."""
    del execution_id
    return dict(spec or {})
def _catalog_keys(catalog_name: str, root_key: str) -> list[str]:
    path = _CONDITION_CATALOGS_ROOT / f"{catalog_name}.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rows = payload.get(root_key) if isinstance(payload, dict) else {}
    if not isinstance(rows, dict):
        return []
    return [str(key) for key in rows.keys() if str(key).strip()]
def _condition_menu(spec: dict[str, Any], axis: str, catalog_name: str, root_key: str) -> list[str]:
    axes = spec.get("conditionAxes") if isinstance(spec.get("conditionAxes"), dict) else {}
    axis_cfg = axes.get(axis) if isinstance(axes, dict) else None
    applicable = bool(axis_cfg) if not isinstance(axis_cfg, dict) else bool(axis_cfg.get("applicable"))
    if not applicable:
        return []
    explicit = axis_cfg.get("values") if isinstance(axis_cfg, dict) else None
    if isinstance(explicit, list) and explicit:
        return [str(item) for item in explicit if str(item).strip()]
    return _catalog_keys(catalog_name, root_key)
def _entity_base_draft(
    execution_id: str,
    domain: str,
    etype: str,
    name: str,
    *,
    aliases: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Select the strongest homepage-lane evidence as the primary reference."""
    from content.post.base_draft import base_draft_candidates, load_base_draft_text
    from core.homepage_source_judge import (
        ADMISSION_PENDING_JUDGE,
        build_judge_request,
        write_judge_request,
    )
    brief = {"entityRefs": [entity_ref(domain, etype, name)]}
    candidates = base_draft_candidates(execution_id, brief)
    if not candidates:
        return {}
    homepage_candidates = []
    for candidate in candidates:
        unit_dir = Path(candidate["unitDir"])
        meta_path = unit_dir / "meta.json"
        meta = read_json(meta_path) if meta_path.is_file() else {}
        readiness = homepage_base_draft_readiness(meta, candidate_text := load_base_draft_text(
            execution_id, candidate["sourceRef"]
        ).strip(), entity_name=name, aliases=aliases, unit_dir=unit_dir)
        judge = readiness.get("judge") if isinstance(readiness.get("judge"), dict) else {}
        if str(judge.get("decision") or "") == ADMISSION_PENDING_JUDGE:
            # 灰区来源：落判别请求（幂等），等待 Agent 写回 source.judge.json。
            write_judge_request(
                unit_dir,
                build_judge_request(
                    entity_name=name,
                    entity_type=f"{domain}/{etype}",
                    aliases=aliases,
                    meta=meta,
                    source_text=candidate_text,
                    unit_ref=str(candidate.get("sourceRef") or ""),
                    prescreen=judge.get("prescreen") or {},
                ),
            )
        priority = int(readiness.get("priority") or 0)
        if priority > 0:
            homepage_candidates.append(
                {
                    **candidate,
                    "_homepagePriority": priority,
                    "_sourceKind": _homepage_source_text(meta),
                    "_factCount": int(readiness.get("factCount") or 0),
                    "_factReady": bool(readiness.get("ready")),
                    "_baseText": candidate_text,
                }
            )
    if not homepage_candidates:
        return {}
    homepage_candidates = [row for row in homepage_candidates if row.get("_factReady")]
    if not homepage_candidates:
        return {}
    homepage_candidates.sort(
        key=lambda row: (
            bool(row.get("_factReady")),
            int(row.get("_homepagePriority") or 0),
            int(row.get("_factCount") or 0),
            float(row.get("score") or 0),
            int(row.get("length") or 0),
        ),
        reverse=True,
    )
    candidates = homepage_candidates
    best = candidates[0]
    text = str(best.get("_baseText") or "").strip()
    if not text:
        return {}
    unit_dir = Path(best["unitDir"])
    meta_path = unit_dir / "meta.json"
    meta = read_json(meta_path) if meta_path.is_file() else {}
    outline = _homepage_section_outline(unit_dir, meta)
    structured_text = _homepage_structured_source_text(unit_dir, text, outline)
    from core.content_source_registry import homepage_primary_authority_rank
    return {
        "sourceRef": best["sourceRef"],
        "primaryEvidenceRef": best["sourceRef"],
        "entityName": name,
        "sourceKind": str(meta.get("sourceKind") or ""),
        "extractor": str(meta.get("extractor") or ""),
        "canonicalUrl": str(
            meta.get("canonicalUrl") or meta.get("finalUrl") or meta.get("url") or ""
        ),
        "sourceTitle": str(meta.get("title") or name),
        "policyRevision": str(meta.get("policyRevision") or ""),
        "sourceUseMode": str(meta.get("sourceUseMode") or "factual_reference_only"),
        "text": structured_text[:HOMEPAGE_BASE_DRAFT_MAX_CHARS],
        "plainText": text[:HOMEPAGE_BASE_DRAFT_MAX_CHARS],
        "sectionOutline": outline,
        # publish 质量元数据真相源：promote 时汇总进 publish 实体 manifest.quality。
        "primarySource": {
            "platform": str(meta.get("platform") or ""),
            "entityName": name,
            "sourceKind": str(meta.get("sourceKind") or ""),
            "extractor": str(meta.get("extractor") or ""),
            "canonicalUrl": str(
                meta.get("canonicalUrl") or meta.get("finalUrl") or meta.get("url") or ""
            ),
            "sourceUrl": str(meta.get("canonicalUrl") or meta.get("finalUrl") or meta.get("url") or ""),
            "title": str(meta.get("title") or name),
            "fetchedAt": str(meta.get("fetchedAt") or ""),
            "snapshotHash": str(meta.get("snapshotHash") or meta.get("cleanSha256") or ""),
            "sourceUseMode": str(meta.get("sourceUseMode") or ""),
            "policyRevision": str(meta.get("policyRevision") or ""),
            "authorityRank": homepage_primary_authority_rank(
                str(meta.get("sourceKind") or "")
            ),
            "factCount": int(best.get("_factCount") or 0),
            "fetchScore": float(best.get("score") or 0.0),
        },
    }
def _homepage_available_images(images: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """配图清单（供 prompt 了解配图语境）：首图为封面 fullWidth，其余交替环绕建议。
    实体主页 assetId 在 finalize 才分配，Agent 阶段无法内联最终 id；故配图由 finalize
    的 placement 确定性按章节 / 段落锚点注入。此清单只用于让 Agent 知道有哪些图、其语义
    说明与建议版面，避免为塞图硬拆章节。
    """
    wrap_cycle = ("wrapRight", "wrapLeft")
    wrap_index = 0
    out: list[dict[str, Any]] = []
    for index, img in enumerate(images):
        explicit = str(img.get("imageLayout") or "").strip()
        if index == 0:
            layout = "fullWidth"
        elif explicit in ("wrapLeft", "wrapRight", "fullWidth"):
            layout = explicit
        else:
            layout = wrap_cycle[wrap_index % len(wrap_cycle)]
            wrap_index += 1
        out.append(
            {
                "sourceAssetId": str(img.get("sourceAssetId") or ""),
                "sourceAssetRef": str(img.get("sourceAssetRef") or ""),
                "caption": str(img.get("caption") or img.get("relevance") or ""),
                "license": str(img.get("license") or ""),
                "suggestedLayout": layout,
                "sectionAnchor": str(img.get("sectionAnchor") or ""),
                "paragraphIndex": int(img.get("paragraphIndex") or 0),
                "placementType": str(img.get("placementType") or ""),
                "groupId": str(img.get("groupId") or ""),
                "sourceOrder": int(img.get("sourceOrder") or 0),
                "subjectKey": str(img.get("subjectKey") or ""),
            }
        )
    return out

def _entity_creator_assignment(
    domain: str,
    etype: str,
    name: str,
    *,
    spec: dict[str, Any],
) -> dict[str, Any]:
    """实体百科主页绑定虚拟作者（geo_editor 主轴，与文章 creator 契约同源）。"""
    from governance.creators.assignment import creator_assignment_from_profile
    from content.templates.creator import match_creator
    from content.templates.registry import TemplateRegistry
    try:
        registry = TemplateRegistry.load()
    except Exception:  # noqa: BLE001
        return {}
    blueprint = spec.get("creatorBlueprint") if isinstance(spec.get("creatorBlueprint"), dict) else {}
    persona = blueprint.get("creatorPersona") if isinstance(blueprint.get("creatorPersona"), dict) else {}
    if not persona.get("archetype"):
        persona = {**persona, "archetype": "geo_editor"}
        blueprint = {**blueprint, "creatorPersona": persona}
    profile = match_creator(
        registry,
        blueprint,
        carrier="article",
        region=str(spec.get("region") or domain),
        vertical=str(spec.get("vertical") or "travel"),
        seed=f"{domain}/{etype}/{name}",
        preferred_archetype="geo_editor",
    )
    return creator_assignment_from_profile(profile)


def _homepage_source_contract(base_draft: dict[str, Any]) -> dict[str, str]:
    primary_source = (
        base_draft.get("primarySource")
        if isinstance(base_draft.get("primarySource"), dict)
        else {}
    )
    source_revision = str(primary_source.get("snapshotHash") or "").strip()
    return {
        "sourcePolicyRevision": str(
            base_draft.get("policyRevision") or HOMEPAGE_SOURCE_POLICY_REVISION
        ),
        "sourceRevision": source_revision or canonical_sha256(base_draft),
    }


def prepare_entity_pages(execution_id: str, spec: dict[str, Any]) -> tuple[Path, list[str]]:
    """为 coverage 实体下发实体主页产出契约（inputs + prompt + 占位草稿 + assistant_tasks）。"""
    from core.paths import ensure_object_stages
    inputs_root = execution_root(execution_id) / "entities"
    inputs_root.mkdir(parents=True, exist_ok=True)
    refs: list[str] = []
    active_input_paths: set[Path] = set()
    for target in _coverage_targets(spec, execution_id=execution_id):
        domain, etype, name = target["domain"], target["etype"], target["name"]
        obj_dir = resolve_entity_object_dir(execution_id, name, etype_hint=f"{domain}/{etype}")
        ensure_object_stages(obj_dir)
        ref = _safe_ref(domain, etype, name)
        target_aliases = tuple(
            str(a) for a in (target.get("aliases") or []) if str(a).strip()
        )
        base_draft = _entity_base_draft(
            execution_id, domain, etype, name, aliases=target_aliases
        )
        creator_assignment = _entity_creator_assignment(domain, etype, name, spec=spec)
        primary_ref = str(
            (base_draft or {}).get("primaryEvidenceRef")
            or (base_draft or {}).get("sourceRef")
            or ""
        ).strip()
        selection = select_homepage_assets(
            execution_id,
            domain,
            etype,
            name,
            primary_ref=primary_ref,
        )
        available_images = _homepage_available_images(
            [dict(image) for image in selection.publishable]
        )
        image_placeholder_bindings = _homepage_image_placeholder_bindings(available_images)
        if base_draft:
            base_draft = dict(base_draft)
            base_draft["markdown"] = _homepage_base_text_with_image_placeholders(
                str(base_draft.get("text") or ""),
                image_placeholder_bindings,
            )
            placed_markdown = str(base_draft.get("markdown") or "")
            image_placeholder_bindings = [
                row
                for row in image_placeholder_bindings
                if f"[[IMG:{row.get('figId')}]]" in placed_markdown
            ]
        input_path = execution_entity_page_input_path(execution_id, domain, etype, name)
        active_input_paths.add(input_path)
        page_payload = {
            "name": name,
            "domain": domain,
            "etype": etype,
            "entityRef": entity_ref(domain, etype, name),
            # 主清单契约字段（discovery_seed/2）：物化时写入 _entity.json。
            # geoTagRef 是物化必填（_REQUIRED_ENTITY_FIELDS），typeTagRefs 供打标物化消费（WP3）。
            **{
                key: target[key]
                for key in ("geoTagRef", "geoTagRefs", "typeTagRefs", "aliases")
                if target.get(key)
            },
            **creator_assignment,
            "minChars": MIN_PAGE_CHARS,
            "baseDraft": base_draft,
            "availableImages": available_images,
            "imagePlaceholderBindings": image_placeholder_bindings,
            "regionMenu": _condition_menu(spec, "region", "region_catalog", "regions"),
            "seasonMenu": _condition_menu(spec, "season", "season_catalog", "seasons"),
            "editingInstruction": (
                "把 primaryEvidenceRef 作为**唯一**底稿骨架与主题锚点（单底稿零参考，禁止引用其它来源）。"
                "在底稿基础上做适度润色、事实校正、PII/平台痕迹清理与人设适配（licensed_adaptation 与 "
                "factual_reference_only 同等以底稿为骨架轻改、保留底稿信息顺序与关键事实细节、"
                "多数语句在底稿原句上做最小改动）；"
                "不得脱离底稿从零另写，也不得整篇零加工照搬。"
                "结构尊重底稿真实内容——规范化章节只作参考（用于章节命名与归类对齐），"
                "不是必须逐节填满的清单：仅『概况』必备，其余章节有真实内容才写、无内容直接省略、禁止硬凑，"
                "只允许增减或合并不在 baseDraft.sectionOutline 必需清单中的章节；"
                "清单内标题必须原文、原层级保留。章节语义须正确（如『历史沿革』必须是真实历史，否则省略）。"
                "多级目录硬要求：底稿（百科类来源）有多级标题层级时，必须保留为 `##` / `###` 多级小标题，"
                "baseDraft.sectionOutline 列出的有实质内容的关键章节（如『技术变革』『相关古迹』）"
                "必须保留为对应级别小标题，禁止静默丢弃、拍平为单层或并入其它段落。"
                "章节均衡硬要求：任何单个章节去空白字数不得超过正文总量的一半；底稿某主题（如历史沿革）"
                "篇幅极长时必须按比例压缩为精炼概述（提炼关键节点，压缩属合法轻编辑，保真针对不另写/不编造而非不许删减）。"
                "时间线归并硬要求：底稿把同一实体多条并列时间线分段罗列时，必须按真实时间顺序归并为单一连贯叙事，"
                "禁止首尾拼接造成时间倒错，同章节年份应大致单调推进。"
            ),
            "imageRequirement": (
                "正文只写文字与多级标题：底稿材料中形如 `[[IMG:fig_NN]]` 的整行"
                "是系统图片占位符，必须**原样带回**（不改 id、不移动、不复制、不删除、"
                "不新增，行尾不追加文字；图注由系统注入）。封面、图片展开、相关图片区与"
                " manifest.json 全部由 finalize 代码侧生成；Agent 不得书写任何"
                " `asset://` 或 `:::figure`。"
            ),
            "draftPage": "4.draft/page.md",
            "outputDir": str(execution_entity_object_dir(execution_id, domain, etype, name)),
            "executionId": execution_id,
        }
        execution = stage_execution_context(execution_id)
        selected_source_url = str(
            ((base_draft or {}).get("primarySource") or {}).get("sourceUrl")
            or ((base_draft or {}).get("primarySource") or {}).get("url")
            or ""
        )
        compose_envelope = {
            "schemaVersion": "quwoquan_data.stage_envelope",
            "stage": "3.compose",
            **execution,
            **_homepage_source_contract(base_draft or {}),
            "promptBundleRevision": prompt_bundle_revision("entity_homepage"),
            "executionId": execution_id,
            "step": "entity_page",
            "ref": ref,
            "selectedSourceUrls": [selected_source_url] if selected_source_url else [],
            "payload": page_payload,
        }
        from core.schema import assert_valid

        assert_valid(
            compose_envelope,
            "content",
            "entity_page_input",
            label=f"entity_page_input:{name}",
        )
        write_json(input_path, compose_envelope)
        _write_entity_quality_stage(execution_id, domain, etype, name, base_draft=base_draft)
        _write_entity_page_prompt_and_placeholder(execution_id, domain, etype, name, page_payload)
        refs.append(ref)
    for stale_input in inputs_root.glob("**/3.compose/entity_page_input.json"):
        if stale_input not in active_input_paths:
            stale_input.unlink()
    manifest_path = execution_assistant_task(execution_id, "homepage", "entity_page")
    results_dir = execution_root(execution_id) / "entities"
    write_assistant_task(manifest_path, step="entity_page", input_dir=inputs_root, result_dir=results_dir, refs=refs)
    return inputs_root, refs

def validate_entity_page_inputs(execution_id: str, spec: dict[str, Any]) -> list[DataIssue]:
    """Pre-Agent admission gate for homepage contracts.
    `build_prepare` is the last deterministic point before Cursor/Codex writes
    entity pages. A homepage input is admissible only when the homepage lane has
    already produced a readable homepage primary-authority base draft; the
    Agent must not be asked to invent or repair missing upstream facts.
    """
    issues: list[DataIssue] = []
    seen: set[tuple[DataIssueCode, str, str]] = set()
    root = execution_root(execution_id)

    def add_issue(code: DataIssueCode, name: str, message: str) -> None:
        key = (code, name, message)
        if key in seen:
            return
        seen.add(key)
        recovery = (
            DataRecoveryAction.STOP
            if code is DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL
            else DataRecoveryAction.RETRY_SOURCE_DISCOVERY
        )
        issues.append(
            data_issue(
                code,
                stage=DataIssueStage.BUILD_PREPARE,
                ref=name,
                lane=DataIssueLane.HOMEPAGE,
                recovery=recovery,
                message=message,
            )
        )

    for target in _coverage_targets(spec, execution_id=execution_id):
        domain, etype, name = target["domain"], target["etype"], target["name"]
        label = f"{domain}/{etype}/{name}"
        input_path = execution_entity_page_input_path(execution_id, domain, etype, name)
        if not input_path.is_file():
            add_issue(DataIssueCode.CONTRACT_INVALID, name, f"{label}: entity_page_input.json 缺失")
            continue
        try:
            raw = read_json(input_path)
        except Exception as exc:  # noqa: BLE001
            add_issue(
                DataIssueCode.CONTRACT_INVALID,
                name,
                f"{label}: entity_page_input.json unreadable: {type(exc).__name__}",
            )
            continue
        payload = raw.get("payload") if isinstance(raw.get("payload"), dict) else raw
        base = payload.get("baseDraft") if isinstance(payload, dict) and isinstance(payload.get("baseDraft"), dict) else {}
        source_ref = str(base.get("sourceRef") or "").strip()
        text = str(base.get("text") or "").strip()
        if not source_ref:
            add_issue(
                DataIssueCode.SOURCE_MISSING,
                name,
                f"{label}: entity homepage baseDraft.sourceRef is empty",
            )
        else:
            source_path = root / source_ref
            if not source_path.is_file():
                add_issue(
                    DataIssueCode.SOURCE_MISSING,
                    name,
                    f"{label}: entity homepage baseDraft.sourceRef missing file {source_ref}",
                )
        if not text:
            add_issue(
                DataIssueCode.SOURCE_RETAINED_SHORTFALL,
                name,
                f"{label}: homepage baseDraft.text 缺失",
            )
        else:
            fact_count = len(_split_fact_sentences(text[:HOMEPAGE_BASE_DRAFT_MAX_CHARS], entity_name=name))
            if fact_count < 4:
                add_issue(
                    DataIssueCode.SOURCE_RETAINED_SHORTFALL,
                    name,
                    f"{label}: homepage baseDraft 可用事实不足",
                )
        if source_ref and text:
            selection = select_homepage_assets(
                execution_id,
                domain,
                etype,
                name,
                primary_ref=source_ref,
            )
            if not selection.publishable:
                add_issue(
                    DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL,
                    name,
                    f"{label}: homepage lane 无可发布图片资产",
                )
        for message in _homepage_base_source_issues(execution_id, domain, etype, name):
            add_issue(DataIssueCode.SOURCE_PRIMARY_AUTHORITY_MISSING, name, message)
    return issues

def _entity_source_paths(execution_id: str, domain: str, etype: str, name: str) -> list[str]:
    from content.source.source_unit import iter_source_units
    obj = execution_entity_object_dir(execution_id, domain, etype, name)
    refs: list[str] = []
    for unit in iter_source_units(obj):
        source_md = unit / "source.md"
        if source_md.is_file():
            refs.append(relative_execution_ref(source_md, execution_id))
    return refs

def _write_entity_quality_stage(
    execution_id: str,
    domain: str,
    etype: str,
    name: str,
    *,
    base_draft: dict[str, Any],
) -> None:
    """实体对象 `2.quality/quality_analysis.json`：显式落底稿优先选择结果。"""
    from content.post.base_draft import base_draft_candidates
    brief = {"entityRefs": [entity_ref(domain, etype, name)]}
    candidates = base_draft_candidates(execution_id, brief)
    execution = stage_execution_context(execution_id)
    selected_ref = str((base_draft or {}).get("sourceRef") or "")
    payload = {
        "schemaVersion": "quwoquan_data.quality_analysis/2",
        "stage": "2.quality",
        **execution,
        **_homepage_source_contract(base_draft or {}),
        "entityRef": entity_ref(domain, etype, name),
        "baseDraft": base_draft or None,
        "candidateCount": len(candidates),
        "candidates": [
            {
                "sourceRef": row["sourceRef"],
                "score": row["score"],
                "length": row["length"],
            }
            for row in candidates
        ],
        "recommendation": "proceed" if base_draft else "needs_source_repair",
        "issues": [] if base_draft else ["no readable base draft source available for homepage"],
        "rejectionReasons": [] if base_draft else ["no_readable_base_draft"],
        "sourcePaths": _entity_source_paths(execution_id, domain, etype, name),
        "sourceAdmissions": [
            {
                "sourceRef": row["sourceRef"],
                "decision": "selected" if row["sourceRef"] == selected_ref else "eligible",
                "evidenceHash": canonical_sha256(
                    {"sourceRef": row["sourceRef"], "score": row["score"], "length": row["length"]}
                ),
            }
            for row in candidates
        ],
        "evidenceHashes": [
            canonical_sha256({"sourceRef": row["sourceRef"], "score": row["score"]})
            for row in candidates
        ],
    }
    from core.schema import assert_valid

    assert_valid(payload, "content", "quality_analysis", label=f"quality_analysis:{name}")
    write_json(
        execution_entity_stage_dir(execution_id, domain, etype, name, STAGE_QUALITY) / "quality_analysis.json",
        payload,
    )

def _page_char_count(page: Path) -> int:
    text = page.read_text(encoding="utf-8")
    return len("".join(text.split()))

def _homepage_gate_body(page_text: str) -> str:
    """剥掉 frontmatter / figure 块 / asset:// 指令 / 标题井号，得到贴合度+模板指纹门用正文。
    门禁在配图注入**之前**对 Agent 原始正文运行；此处同时剥离 `:::figure` 块与文末
    `## 图集`，使得即便 Agent 自行内联了图片，也不会污染字符贴合度与模板指纹度量。
    """
    body = _strip_frontmatter(page_text)
    body = re.sub(r"(?ms)^:::figure(?:group)?\b.*?^:::\s*", "", body)
    body = re.sub(r"(?m)^#{2,3}\s*图集\s*$", "", body)
    body = re.sub(r"\{asset://[^}]*\}", "", body)
    body = re.sub(r"^#{1,6}\s*", "", body, flags=re.MULTILINE)
    return body.strip()







def _homepage_tag_refs(domain: str, etype: str, name: str, payload: dict[str, Any]) -> list[str]:
    """主页确定性标签：主清单契约来源的类型 + 地理标签，加 compose/agent 透传 tagRefs。
    WP3 统一打标：`typeTagRefs`（Entity/地点/** 全量类型）、`geoTagRef` 主归属与
    `geoTagRefs` 全量地理归属（Topic/地理/行政区/**）全部并进 tagRefs
    → ObjectTagIndex 多值反查（「按博物馆浏览」「四川的景区」均命中）。
    仍不编造：主清单/上游没提供的维度不打。最后补 Topic/Format 最小集，
    保证 manifest.tagRefs >= 2 个合法 ref（关闭「主页零标签」缺口）。
    """
    from core.content_tags import resolved_content_tag_refs
    provided: list[str] = []
    if isinstance(payload, dict):
        provided.extend(
            str(item).strip() for item in (payload.get("typeTagRefs") or []) if str(item).strip()
        )
        geo_tag_ref = str(payload.get("geoTagRef") or "").strip()
        if geo_tag_ref:
            provided.append(geo_tag_ref)
        provided.extend(
            str(item).strip() for item in (payload.get("geoTagRefs") or []) if str(item).strip()
        )
        candidate = payload.get("tagRefs")
        if isinstance(candidate, list):
            provided.extend(str(item) for item in candidate if str(item).strip())
    brief: dict[str, Any] = {"tagRefs": list(dict.fromkeys(provided))} if provided else {}
    return resolved_content_tag_refs(brief, "article")
