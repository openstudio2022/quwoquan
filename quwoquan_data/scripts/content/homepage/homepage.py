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
from content.post.article.draft_io import PLACEHOLDER_MARKER, is_placeholder
from core.entity_page_quality import entity_page_quality_issues
from core.localization import fold_to_simplified
from core.media_processing_policy import MEDIA_PROCESSING_POLICY
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
    load_homepage_base_draft_text,
)
from content.homepage.quality_policy import (
    homepage_body_char_minimum,
    homepage_fact_count_minimum,
    homepage_fact_char_minimum,
    homepage_source_outline_section_minimum,
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
# 实体主页底稿下发上限：取消旧的 4000 截断（旧值会把维基百科页在中段截断，
# Agent 看不到「技术变革 / 相关古迹」等后段章节，导致多级目录与章节缺失）。
# 放宽到覆盖绝大多数百科页全文，仅兜底极端超长源避免 token 失控。
HOMEPAGE_BASE_DRAFT_MAX_CHARS = MEDIA_PROCESSING_POLICY.homepage_base_draft_max_chars
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
    from content.post.article.base_draft import base_draft_candidates
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
        readiness = homepage_base_draft_readiness(
            meta,
            candidate_text := load_homepage_base_draft_text(
                execution_id, candidate["sourceRef"]
            ).strip(),
            entity_name=name,
            aliases=aliases,
            unit_dir=unit_dir,
            minimum_body_chars=homepage_body_char_minimum(execution_id),
            minimum_fact_count=homepage_fact_count_minimum(execution_id),
            minimum_fact_chars=homepage_fact_char_minimum(execution_id),
        )
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
    outline = _homepage_section_outline(
        unit_dir,
        meta,
        min_section_chars=homepage_source_outline_section_minimum(execution_id),
    )
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
    from content.post.article.base_draft import base_draft_candidates
    brief = {"entityRefs": [entity_ref(domain, etype, name)]}
    candidates = base_draft_candidates(execution_id, brief)
    execution = stage_execution_context(execution_id)
    selected_ref = str((base_draft or {}).get("sourceRef") or "")
    payload = {
        "schema": "quwoquan_data.quality_analysis",
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
    """Project only source-independent homepage tags.

    A coverage leaf's ``typeTagRefs`` is a discovery classification, not
    evidence that every fine-grained fact is stated by the selected homepage
    source.  Materializing it verbatim can turn a coverage hint such as ``5A``
    into an unsupported public claim.  The canonical object therefore keeps
    the declared entity kind, administrative ownership, and neutral delivery
    tags.  Evidence-backed fine-grained tags must be produced by the source
    qualification lane with their own cited evidence; this homepage projection
    never promotes a static coverage hint into a fact.
    """
    from core.content_tags import resolved_content_tag_refs
    provided: list[str] = [f"Entity/{domain}/{etype}"]
    if isinstance(payload, dict):
        geo_tag_ref = str(payload.get("geoTagRef") or "").strip()
        if geo_tag_ref:
            provided.append(geo_tag_ref)
        provided.extend(
            str(item).strip() for item in (payload.get("geoTagRefs") or []) if str(item).strip()
        )
    brief: dict[str, Any] = {"tagRefs": list(dict.fromkeys(provided))} if provided else {}
    return resolved_content_tag_refs(brief, "article")
