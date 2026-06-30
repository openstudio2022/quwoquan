"""实体主页 build 真实链路：prepare 下发产出契约 + validate 采纳门。

与现行「三层目录实体」模型一致（entities/{领域}/{类型}/{名称}/）：
- prepare：读 effective task spec 的 scope.coverageTargets，为每个实体写
  3.compose/entity_page_input.json（含 SOP 模板路径、字数下限、底稿）+ 人读 4.draft/prompt.md
  + 占位 4.draft/page.md，并写 assistant_tasks 清单，下发给创作 agent。
- Agent：读 prompt.md 与底稿，在底稿基础上做适度润色/事实校正/PII·平台痕迹清理/人设适配，
  把正文写回 4.draft/page.md（≥350字、保留底稿原句最小改、不脱离底稿从零另写、不机械模板凑字）。
- finalize（materialize_entity_page）：不脚本拼正文，只对创作 agent正文把关贴合度+模板指纹门，
  再据正文与已授权真实图补齐封面资产并物化 page.md+_entity.json+manifest.json(generator=agent)，
  写真实 sha256 出处。
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

from _common.io import read_json, write_assistant_task, write_json
from _common.article_package import compute_document_sha256, sha256_file, sha256_text
from _common.batch_asset_registry import allocate_post_asset_id, load_batch_asset_registry
from _common.batch_manifest import load_batch_manifest
from _common.draft_io import PLACEHOLDER_MARKER, is_placeholder
from _common.entity_page_quality import entity_page_quality_issues
from _common.prompt_render import render
from _common.template_fingerprints import template_fingerprint_issues
from _common.entity_object import sync_entity_object_to_task_mirror, write_entity_object_index
from _common.post_evidence_chain import build_finalization_report
from _common.provenance import build_provenance
from _common.paths import (
    STAGE_COMPOSE,
    STAGE_DRAFT,
    STAGE_QUALITY,
    STAGE_REVIEW,
    batch_entity_object_dir,
    batch_entity_stage_dir,
    batch_assistant_task,
    batch_entity_page_input_path,
    batch_root,
    relative_batch_ref,
    task_data,
)
from _common.entity_extract import entity_ref, require_domain_etype
from _common.source_unit import resolve_entity_object_dir
from build.homepage_introduction import (
    _normalize_homepage_manifest_assets,
    homepage_introduction_seed_from_triplet,
)
from build.homepage_text import (
    _homepage_base_source_issue_text,
    _homepage_source_text,
    _homepage_summary,
    _split_fact_sentences,
    _strip_frontmatter,
    homepage_base_draft_readiness,
)
from build.homepage_validation import _asset_closure_issues, _condition_profile_issues

MIN_PAGE_CHARS = 350
HOMEPAGE_FIDELITY_MAX = 0.92
# 实体主页底稿下发上限：取消旧的 4000 截断（旧值会把维基百科页在中段截断，
# Agent 看不到「技术变革 / 相关古迹」等后段章节，导致多级目录与章节缺失）。
# 放宽到覆盖绝大多数百科页全文，仅兜底极端超长源避免 token 失控。
HOMEPAGE_BASE_DRAFT_MAX_CHARS = max(4000, int(os.environ.get("QWQ_HOMEPAGE_BASE_DRAFT_MAX_CHARS", "12000")))
# 计入 sectionOutline 的关键章节最小去空白正文字数（短于此视为占位/导语碎片）。
HOMEPAGE_SECTION_MIN_CHARS = 120
_REQUIRED_ENTITY_FIELDS = ("label", "domain", "type", "sourceTaskId")
_REPO_DATA_ROOT = Path(__file__).resolve().parents[2]
_CONDITION_CATALOGS_ROOT = _REPO_DATA_ROOT / "templates" / "_registry" / "catalogs"


def _dedupe_nonempty(values: list[str]) -> list[str]:
    """保序去重并丢弃空串，供 sourceRefs 等列表收敛。"""
    return [v for v in dict.fromkeys(v for v in values if v)]


def _source_unit_from_ref(ref: str) -> str:
    raw = str(ref or "").replace("\\", "/").strip()
    if raw.endswith("/source.md"):
        return raw.rsplit("/", 1)[0]
    return raw


def _same_source_unit(a: str, b: str) -> bool:
    left = _source_unit_from_ref(a)
    right = _source_unit_from_ref(b)
    return bool(left and right and left == right)

def _safe_ref(domain: str, etype: str, name: str) -> str:
    return f"{domain}__{etype}__{name}".replace("/", "_")


def _coverage_targets(spec: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for target in (spec.get("scope") or {}).get("coverageTargets") or []:
        name = str(target.get("name") or "").strip()
        if not name:
            continue
        domain, etype = require_domain_etype(
            target.get("entityType"),
            context=f"coverageTargets[{name}]",
        )
        out.append({"name": name, "domain": domain, "etype": etype})
    return out


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


def _entity_base_draft(task_id: str, batch_id: str, domain: str, etype: str, name: str) -> dict[str, Any]:
    """Select the strongest homepage-lane evidence as the primary reference."""
    from _common.base_draft import base_draft_candidates, load_base_draft_text

    brief = {"entityRefs": [entity_ref(domain, etype, name)]}
    candidates = base_draft_candidates(task_id, batch_id, brief)
    if not candidates:
        return {}
    homepage_candidates = []
    for candidate in candidates:
        meta_path = Path(candidate["unitDir"]) / "meta.json"
        meta = read_json(meta_path) if meta_path.is_file() else {}
        readiness = homepage_base_draft_readiness(meta, candidate_text := load_base_draft_text(
            task_id, batch_id, candidate["sourceRef"]
        ).strip(), entity_name=name)
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
    return {
        "sourceRef": best["sourceRef"],
        "primaryEvidenceRef": best["sourceRef"],
        "sourceUseMode": str(meta.get("sourceUseMode") or "factual_reference_only"),
        "text": text[:HOMEPAGE_BASE_DRAFT_MAX_CHARS],
        "sectionOutline": _homepage_section_outline(unit_dir, meta),
    }


def _homepage_section_outline(unit_dir: Path, meta: dict[str, Any]) -> list[dict[str, Any]]:
    """从来源 `source.md`（保留 wiki `==/===`）解析关键章节，供 prompt 保留多级目录。

    优先复用下载阶段已写入 meta.sectionOutline（P1 联网解析）；缺省时离线从原文解析。
    `source.clean.md` 已把标题压成无标记纯文本会丢层级，故必须读 `source.md` 原文。
    """
    from _common.section_outline import (
        outline_required_sections,
        outline_to_dicts,
        parse_section_outline,
    )

    cached = meta.get("sectionOutline")
    if isinstance(cached, list) and cached:
        return [row for row in cached if isinstance(row, dict)]
    raw_path = unit_dir / "source.md"
    if not raw_path.is_file():
        return []
    try:
        raw_text = raw_path.read_text(encoding="utf-8")
    except OSError:
        return []
    nodes = outline_required_sections(
        parse_section_outline(raw_text), min_body_chars=HOMEPAGE_SECTION_MIN_CHARS
    )
    return outline_to_dicts(nodes)


def _homepage_base_source_issues(task_id: str, batch_id: str, domain: str, etype: str, name: str) -> list[str]:
    label = f"{domain}/{etype}/{name}"
    quality_path = batch_entity_stage_dir(task_id, batch_id, domain, etype, name, STAGE_QUALITY) / "quality_analysis.json"
    if not quality_path.is_file():
        return [f"{label}: 2.quality/quality_analysis.json 缺失"]
    quality = read_json(quality_path)
    compose_path = batch_entity_stage_dir(task_id, batch_id, domain, etype, name, STAGE_COMPOSE) / "entity_page_input.json"
    compose_payload = read_json(compose_path) if compose_path.is_file() else {}
    if isinstance(compose_payload.get("payload"), dict):
        compose_payload = compose_payload["payload"]
    base = quality.get("baseDraft") if isinstance(quality.get("baseDraft"), dict) else {}
    compose_base = compose_payload.get("baseDraft") if isinstance(compose_payload.get("baseDraft"), dict) else {}
    base_source = str(base.get("sourceRef") or "").strip()
    compose_source = str(compose_base.get("sourceRef") or "").strip()
    issues: list[str] = []
    if not base_source:
        issues.append(f"{label}: entity homepage baseDraft.sourceRef is empty")
        return issues
    if compose_source and compose_source != base_source:
        issues.append(f"{label}: entity homepage quality base draft differs from compose base draft")
    meta_path = batch_root(task_id, batch_id) / base_source
    meta = read_json(meta_path.parent / "meta.json") if (meta_path.parent / "meta.json").is_file() else {}
    source_kind, is_primary, is_author_experience = _homepage_base_source_issue_text(meta)
    if not is_primary:
        issues.append(
            f"{label}: entity homepage base draft must be encyclopedia/wiki/official-site source, got {source_kind or '<empty>'}"
        )
    if is_author_experience:
        issues.append(
            f"{label}: entity homepage base draft must not be author travelogue/guide/comment source, got {source_kind or '<empty>'}"
        )
    return issues


def _entity_base_source_line(base_ref: str, base_mode: str) -> str:
    if base_ref:
        return (
            f"- **底稿来源**：`{base_ref}`（sourceUseMode=`{base_mode}`）作为本页表达骨架，"
            "在其上做**适度润色 + 事实校正 + PII/平台痕迹清理 + 体裁适配**；"
            "licensed_adaptation 与 factual_reference_only 同等以底稿为骨架轻改。"
        )
    return "- 当前无可用底稿（source 不足）；不要凭空编造，先回退到 source 修复。"


def _entity_section_outline_block(base: dict[str, Any]) -> str:
    outline_rows = base.get("sectionOutline") if isinstance(base.get("sectionOutline"), list) else []
    if not outline_rows:
        return ""
    from _common.section_outline import render_outline_tree_from_dicts

    tree = render_outline_tree_from_dicts(outline_rows)
    if not tree:
        return ""
    return (
        "## 底稿章节结构（必须保留为对应级别多级小标题）\n\n"
        "底稿来源含以下有实质内容的章节，请在正文中**保留为对应的 `##`/`###` 多级小标题**，"
        "可微调标题措辞，但不得静默丢弃、不得拍平为单层、不得并入其它段落：\n\n"
        + tree
    )


def _entity_base_draft_block(base_text: str) -> str:
    if not base_text:
        return "## 底稿材料\n\n（无可用底稿材料；先回退 source 修复，不要凭空编造）"
    return "## 底稿材料（在此基础上轻改）\n\n```\n" + base_text + "\n```"


def _entity_available_images_block(payload: dict[str, Any]) -> str:
    available = payload.get("availableImages") if isinstance(payload.get("availableImages"), list) else []
    if not available:
        return ""
    lines = [
        "## 同源配图清单（finalize 按章节/段落自动注入正文 figure 块）",
        "",
        "以下图片均来自与底稿**同一** source unit。finalize 会按章节/段落锚点把它们注入正文"
        "（封面=第一张 fullWidth，其余 wrapLeft/wrapRight 环绕，无法定位的进文末『图集』）。"
        "你专注写**带多级小标题的正文**即可；了解配图语义有助于组织章节，但不要为塞图硬拆章。",
        "",
    ]
    for index, row in enumerate(available):
        if not isinstance(row, dict):
            continue
        caption = str(row.get("caption") or row.get("relevance") or "").strip() or "配图"
        layout = str(row.get("suggestedLayout") or "").strip()
        role = "封面" if index == 0 else "配图"
        suffix = f"（建议 {layout}）" if layout else ""
        lines.append(f"- [{role}] {caption}{suffix}")
    return "\n".join(lines)


def _render_entity_page_prompt(payload: dict[str, Any]) -> str:
    """人读写作指令：与文章 prompt 同构（指令区来自 entity_homepage 模板），写回目标是 4.draft/page.md。"""
    name = str(payload.get("name") or "")
    base = payload.get("baseDraft") if isinstance(payload.get("baseDraft"), dict) else {}
    base_ref = str(base.get("sourceRef") or base.get("primaryEvidenceRef") or "")
    base_mode = str(base.get("sourceUseMode") or "factual_reference_only")
    base_text = str(base.get("text") or "").strip()
    return render(
        "entity_homepage",
        system_vars={"min_page_chars": MIN_PAGE_CHARS},
        task_vars={
            "name": name,
            "base_source_line": _entity_base_source_line(base_ref, base_mode),
            "section_outline_block": _entity_section_outline_block(base),
            "base_draft_block": _entity_base_draft_block(base_text),
            "available_images_block": _entity_available_images_block(payload),
        },
    )


def _entity_draft_dir(task_id: str, batch_id: str, domain: str, etype: str, name: str) -> Path:
    return batch_entity_stage_dir(task_id, batch_id, domain, etype, name, STAGE_DRAFT)


def _write_entity_page_prompt_and_placeholder(
    task_id: str,
    batch_id: str,
    domain: str,
    etype: str,
    name: str,
    payload: dict[str, Any],
) -> None:
    """下发人读 prompt.md + 占位 page.md：创作 agent在 4.draft/page.md 创作正文。

    与文章一致：占位草稿用 PLACEHOLDER_MARKER 标记『尚未创作』，但绝不覆盖
    创作 agent已写回的真实正文（非占位则保留）。
    """
    draft_dir = _entity_draft_dir(task_id, batch_id, domain, etype, name)
    draft_dir.mkdir(parents=True, exist_ok=True)
    (draft_dir / "prompt.md").write_text(_render_entity_page_prompt(payload), encoding="utf-8")
    draft_page = draft_dir / "page.md"
    if draft_page.is_file() and not is_placeholder(draft_page.read_text(encoding="utf-8")):
        return
    draft_page.write_text(
        f"{PLACEHOLDER_MARKER}\n\n# {name}\n\n（待创作 agent按 prompt.md 与底稿创作实体主页正文，覆盖本占位）\n",
        encoding="utf-8",
    )


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
                "sourceAssetRef": str(img.get("sourceAssetRef") or ""),
                "caption": str(img.get("caption") or img.get("relevance") or ""),
                "license": str(img.get("license") or ""),
                "suggestedLayout": layout,
                "sectionAnchor": str(img.get("sectionAnchor") or ""),
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
    from _common.creator_assignment import creator_assignment_from_profile
    from template.creator import match_creator
    from template.registry import TemplateRegistry

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


def prepare_entity_pages(task_id: str, batch_id: str, spec: dict[str, Any]) -> tuple[Path, list[str]]:
    """为 coverage 实体下发实体主页产出契约（inputs + prompt + 占位草稿 + assistant_tasks）。"""
    from _common.paths import ensure_object_stages

    inputs_root = batch_root(task_id, batch_id) / "entities"
    inputs_root.mkdir(parents=True, exist_ok=True)
    data = task_data(task_id)
    refs: list[str] = []
    active_input_paths: set[Path] = set()
    for target in _coverage_targets(spec):
        domain, etype, name = target["domain"], target["etype"], target["name"]
        obj_dir = resolve_entity_object_dir(task_id, batch_id, name, etype_hint=f"{domain}/{etype}")
        ensure_object_stages(obj_dir)
        ref = _safe_ref(domain, etype, name)
        sop_dir = data.sop_dir(domain, etype)
        base_draft = _entity_base_draft(task_id, batch_id, domain, etype, name)
        creator_assignment = _entity_creator_assignment(domain, etype, name, spec=spec)
        input_path = batch_entity_page_input_path(task_id, batch_id, domain, etype, name)
        active_input_paths.add(input_path)
        page_payload = {
            "name": name,
            "domain": domain,
            "etype": etype,
            "entityRef": entity_ref(domain, etype, name),
            **creator_assignment,
            "sopDir": str(sop_dir),
            "sopTemplate": str(sop_dir / "template.md"),
            "sopGuide": str(sop_dir / "guide.md"),
            "sopExample": str(sop_dir / "example.md"),
            "minChars": MIN_PAGE_CHARS,
            "baseDraft": base_draft,
            "availableImages": _homepage_available_images(
                _pick_homepage_assets(
                    task_id, batch_id, domain, etype, name, limit=HOMEPAGE_MAX_ASSETS
                )
            ),
            "regionMenu": _condition_menu(spec, "region", "region_catalog", "regions"),
            "seasonMenu": _condition_menu(spec, "season", "season_catalog", "seasons"),
            "editingInstruction": (
                "把 primaryEvidenceRef 作为**唯一**底稿骨架与主题锚点（单底稿零参考，禁止引用其它来源）。"
                "在底稿基础上做适度润色、事实校正、PII/平台痕迹清理与人设适配（licensed_adaptation 与 "
                "factual_reference_only 同等以底稿为骨架轻改、保留底稿信息顺序与关键事实细节、"
                "多数语句在底稿原句上做最小改动）；"
                "不得脱离底稿从零另写，也不得整篇零加工照搬。"
                "结构尊重底稿真实内容——SOP 模板里的章节只是『规范化参考』（用于章节命名与归类对齐），"
                "不是必须逐节填满的清单：仅『概况』必备，其余章节有真实内容才写、无内容直接省略、禁止硬凑，"
                "也允许按底稿增减或合并章节；章节语义须正确（如『历史沿革』必须是真实历史，否则省略）。"
                "多级目录硬要求：底稿（百科类来源）有多级标题层级时，必须保留为 `##` / `###` 多级小标题，"
                "baseDraft.sectionOutline 列出的有实质内容的关键章节（如『技术变革』『相关古迹』）"
                "必须保留为对应级别小标题，禁止静默丢弃、拍平为单层或并入其它段落。"
                "章节均衡硬要求：任何单个章节去空白字数不得超过正文总量的一半；底稿某主题（如历史沿革）"
                "篇幅极长时必须按比例压缩为精炼概述（提炼关键节点，压缩属合法轻编辑，保真针对不另写/不编造而非不许删减）。"
                "时间线归并硬要求：底稿把同一实体多条并列时间线分段罗列时，必须按真实时间顺序归并为单一连贯叙事，"
                "禁止首尾拼接造成时间倒错，同章节年份应大致单调推进。"
            ),
            "imageRequirement": (
                "正文以**纯文字 + 多级标题**为主，**不必**手写 asset:// 或 manifest.json："
                "实体主页图片 assetId 在 finalize 阶段才分配，finalize 会从 primaryEvidenceRef "
                "**同一 source unit** 的已授权图片中，按章节/段落锚点把图片自动注入正文 figure 块"
                "（封面=第一张同源图 fullWidth，其余按章节就近 wrapLeft/wrapRight 环绕，"
                "无法定位的进文末『图集』）。"
                "你只需写好带多级小标题的正文；「同源配图清单」用于了解有哪些图及其语义，"
                "勿为塞图硬拆章节。"
            ),
            "draftPage": "4.draft/page.md",
            "outputDir": str(batch_entity_object_dir(task_id, batch_id, domain, etype, name)),
            "sourceTaskId": task_id,
        }
        write_json(input_path, {
            "schemaVersion": "quwoquan_data.stage_envelope",
            "taskId": task_id,
            "batchId": batch_id,
            "step": "entity_page",
            "ref": ref,
            "payload": page_payload,
        })
        _write_entity_quality_stage(task_id, batch_id, domain, etype, name, base_draft=base_draft)
        _write_entity_page_prompt_and_placeholder(task_id, batch_id, domain, etype, name, page_payload)
        refs.append(ref)
    for stale_input in inputs_root.glob("**/3.compose/entity_page_input.json"):
        if stale_input not in active_input_paths:
            stale_input.unlink()
    manifest_path = batch_assistant_task(task_id, batch_id, "build", "entity_page")
    results_dir = batch_root(task_id, batch_id) / "entities"
    write_assistant_task(manifest_path, step="entity_page", input_dir=inputs_root, result_dir=results_dir, refs=refs)
    return inputs_root, refs


def validate_entity_page_inputs(task_id: str, batch_id: str, spec: dict[str, Any]) -> list[str]:
    """Pre-Agent admission gate for homepage contracts.

    `build_prepare` is the last deterministic point before Cursor/Codex writes
    entity pages. A homepage input is admissible only when the homepage lane has
    already produced a readable encyclopedia/wiki/official base draft; the
    Agent must not be asked to invent or repair missing upstream facts.
    """
    issues: list[str] = []
    seen: set[str] = set()
    root = batch_root(task_id, batch_id)
    for target in _coverage_targets(spec):
        domain, etype, name = target["domain"], target["etype"], target["name"]
        label = f"{domain}/{etype}/{name}"
        input_path = batch_entity_page_input_path(task_id, batch_id, domain, etype, name)
        if not input_path.is_file():
            issue = f"{label}: entity_page_input.json 缺失"
            issues.append(issue)
            seen.add(issue)
            continue
        try:
            raw = read_json(input_path)
        except Exception as exc:  # noqa: BLE001
            issue = f"{label}: entity_page_input.json unreadable: {exc}"
            issues.append(issue)
            seen.add(issue)
            continue
        payload = raw.get("payload") if isinstance(raw.get("payload"), dict) else raw
        base = payload.get("baseDraft") if isinstance(payload, dict) and isinstance(payload.get("baseDraft"), dict) else {}
        source_ref = str(base.get("sourceRef") or "").strip()
        text = str(base.get("text") or "").strip()
        if not source_ref:
            issue = f"{label}: entity homepage baseDraft.sourceRef is empty"
            issues.append(issue)
            seen.add(issue)
        else:
            source_path = root / source_ref
            if not source_path.is_file():
                issue = f"{label}: entity homepage baseDraft.sourceRef missing file {source_ref}"
                issues.append(issue)
                seen.add(issue)
        if not text:
            issue = f"{label}: homepage baseDraft.text 缺失"
            issues.append(issue)
            seen.add(issue)
        else:
            fact_count = len(_split_fact_sentences(text[:HOMEPAGE_BASE_DRAFT_MAX_CHARS], entity_name=name))
            if fact_count < 4:
                issue = f"{label}: homepage baseDraft 可用事实不足"
                issues.append(issue)
                seen.add(issue)
        for issue in _homepage_base_source_issues(task_id, batch_id, domain, etype, name):
            if issue not in seen:
                issues.append(issue)
                seen.add(issue)
    return issues


def _entity_source_paths(task_id: str, batch_id: str, domain: str, etype: str, name: str) -> list[str]:
    from _common.source_unit import iter_source_units

    obj = batch_entity_object_dir(task_id, batch_id, domain, etype, name)
    refs: list[str] = []
    for unit in iter_source_units(obj):
        source_md = unit / "source.md"
        if source_md.is_file():
            refs.append(relative_batch_ref(source_md, task_id, batch_id))
    return refs


def _write_entity_quality_stage(
    task_id: str,
    batch_id: str,
    domain: str,
    etype: str,
    name: str,
    *,
    base_draft: dict[str, Any],
) -> None:
    """实体对象 `2.quality/quality_analysis.json`：显式落底稿优先选择结果。"""
    from _common.base_draft import base_draft_candidates

    brief = {"entityRefs": [entity_ref(domain, etype, name)]}
    candidates = base_draft_candidates(task_id, batch_id, brief)
    payload = {
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
        "sourcePaths": _entity_source_paths(task_id, batch_id, domain, etype, name),
    }
    write_json(
        batch_entity_stage_dir(task_id, batch_id, domain, etype, name, STAGE_QUALITY) / "quality_analysis.json",
        payload,
    )


def _page_char_count(page: Path) -> int:
    text = page.read_text(encoding="utf-8")
    return len("".join(text.split()))


# 主页正文最多注入的配图数量：封面 + 若干章节内图。维基页常有 5-8 张同源图，
# 旧值 3 会丢掉「相关古迹」等章节对应的真实图；放量到 8 并可经环境变量调节。
HOMEPAGE_MAX_ASSETS = max(1, int(os.environ.get("QWQ_HOMEPAGE_MAX_ASSETS", "8")))


def _pick_homepage_assets(
    task_id: str,
    batch_id: str,
    domain: str,
    etype: str,
    name: str,
    *,
    limit: int = HOMEPAGE_MAX_ASSETS,
    primary_ref: str = "",
) -> list[dict[str, Any]]:
    """主页可发布图片：仅 primaryEvidenceRef 所属 source unit 的已授权 assets。"""
    from _common.source_unit import object_image_candidates

    base = _entity_base_draft(task_id, batch_id, domain, etype, name)
    unit_ref = primary_ref or str(
        (base or {}).get("primaryEvidenceRef") or (base or {}).get("sourceRef") or ""
    ).strip()
    if not unit_ref:
        return []
    obj = batch_entity_object_dir(task_id, batch_id, domain, etype, name)
    candidates: list[dict[str, Any]] = []
    for image in object_image_candidates(obj, task_id, batch_id):
        if not _same_source_unit(str(image.get("sourceRef") or ""), unit_ref):
            continue
        if not str(image.get("sourceRef") or "").endswith("/source.md"):
            continue
        if not str(image.get("sourceAssetRef") or ""):
            continue
        if not (str(image.get("authorizationProof") or "").strip() or str(image.get("termsUrl") or "").strip()):
            continue
        candidates.append(image)
    candidates.sort(
        key=lambda item: (
            str(item.get("sourceAssetRef") or ""),
            str(item.get("caption") or ""),
        )
    )
    picked: list[dict[str, Any]] = []
    seen: set[str] = set()
    for image in candidates:
        key = str(image.get("sha256") or "") or str(image.get("sourceAssetRef") or "")
        if key in seen:
            continue
        seen.add(key)
        picked.append(image)
        if len(picked) >= max(1, limit):
            break
    return picked


def _copy_homepage_asset(
    task_id: str,
    batch_id: str,
    entity_dir: Path,
    name: str,
    image: dict[str, Any],
    *,
    role: str = "cover",
) -> dict[str, Any]:
    src = Path(str(image.get("path") or ""))
    if not src.is_file():
        return {}
    manifest = load_batch_manifest(task_id, batch_id)
    try:
        global_batch_seq = int(manifest.get("globalBatchSeq") or 0)
    except (TypeError, ValueError):
        global_batch_seq = 0
    if global_batch_seq <= 0:
        return {}
    registry = load_batch_asset_registry(task_id, batch_id, global_batch_seq)
    asset_id = allocate_post_asset_id(
        entity_name=name,
        role=role,
        ref=str(image.get("sourceAssetRef") or image.get("sourceRef") or entity_dir.as_posix()),
        global_batch_seq=global_batch_seq,
        registry=registry,
    )
    assets_dir = entity_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    suffix = src.suffix or ".jpg"
    file_name = f"{asset_id}{suffix}"
    shutil.copyfile(src, assets_dir / file_name)
    return {
        "assetId": asset_id,
        "fileName": file_name,
        "role": role,
        "caption": str(image.get("caption") or image.get("relevance") or name).strip(),
        "license": str(image.get("license") or "").strip(),
        "credit": str(image.get("creator") or "").strip(),
        "relevance": str(image.get("relevance") or "").strip(),
        "sourceRef": str(image.get("sourceRef") or "").strip(),
        "sourceAssetRef": str(image.get("sourceAssetRef") or "").strip(),
        "termsUrl": str(image.get("termsUrl") or "").strip(),
        "authorizationProof": str(image.get("authorizationProof") or "").strip(),
    }


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


def _ensure_homepage_cover_frontmatter(page_text: str, cover_asset_id: str) -> str:
    """实体主页与文章一致：frontmatter 标 coverImage，供 feed/卡片封面取图。"""
    cover_asset_id = str(cover_asset_id or "").strip()
    if not cover_asset_id:
        return page_text
    cover_line = f"coverImage: asset://{cover_asset_id}"
    if page_text.startswith("---\n"):
        end = page_text.find("\n---\n", 4)
        if end != -1:
            head = page_text[:end]
            if "coverImage:" in head:
                return page_text
            return head + "\n" + cover_line + page_text[end:]
    return f"---\n{cover_line}\n---\n\n" + page_text


def _homepage_layout_assets(assets: list[dict[str, Any]]) -> None:
    """就地为 manifest 资产标注建议版面：封面 fullWidth，其余章节图交替环绕。

    与正文 figure 块由 place_assets_in_markdown 注入时保持同一规则（封面 fullWidth、
    其余 wrapRight/wrapLeft 交替），让 manifest.imageLayout 与正文版面一致。
    """
    wrap_cycle = ("wrapRight", "wrapLeft")
    wrap_index = 0
    for index, asset in enumerate(assets):
        if asset.get("role") == "cover" or index == 0:
            asset["imageLayout"] = "fullWidth"
        else:
            asset["imageLayout"] = wrap_cycle[wrap_index % len(wrap_cycle)]
            wrap_index += 1
        asset.setdefault("sectionAnchor", str(asset.get("sectionAnchor") or ""))


def _homepage_tag_refs(domain: str, etype: str, name: str, payload: dict[str, Any]) -> list[str]:
    """主页确定性标签：复用 compose/agent 透传的 tagRefs，并补足 Topic/Format 最小集。

    保证 manifest.tagRefs >= 2 个合法 ref（关闭“主页零标签”缺口）。区域/季节等更丰富的
    证据型标签依赖 compose/agent 产出，作为后续增强（见 backlog），此处不编造区域 ref。
    """
    from _common.content_tags import resolved_content_tag_refs

    brief: dict[str, Any] = {}
    candidate = payload.get("tagRefs") if isinstance(payload, dict) else None
    if isinstance(candidate, list):
        provided = [str(item) for item in candidate if str(item).strip()]
        if provided:
            brief["tagRefs"] = provided
    return resolved_content_tag_refs(brief, "article")


def materialize_entity_page(task_id: str, batch_id: str, domain: str, etype: str, name: str) -> list[str]:
    """把创作 agent写回的 `4.draft/page.md` 正文终态化为实体主页三件套。

    不再脚本拼正文/切句/凑字：正文必须由创作 agent在底稿基础上轻改创作（generator=agent）。
    finalize 只做：① 贴合度门 + 模板指纹门把关 Agent 正文；② 从同源 unit 选封面/图库写入 manifest；
    ③ 据正文事实确定性映射 summary；④ 写 generator=agent 与真实 agentRunId provenance。
    正文 page.md 由 Agent 写纯文字 + 多级标题，finalize 按章节/段落锚点把同源真实图
    确定性注入正文 figure 块（图文混排，闭环登记到 manifest）。创作 agent未写回或仍是占位时
    返回等待项，checkpoint 阻塞等待，绝不退回脚本拼接。
    """
    label = f"{domain}/{etype}/{name}"
    input_path = batch_entity_page_input_path(task_id, batch_id, domain, etype, name)
    if not input_path.is_file():
        return [f"{label}: entity_page_input.json 缺失"]
    envelope = read_json(input_path)
    payload = envelope.get("payload") if isinstance(envelope.get("payload"), dict) else envelope
    base = payload.get("baseDraft") if isinstance(payload.get("baseDraft"), dict) else {}
    base_text = str(base.get("text") or "").strip()
    if not base_text:
        return [f"{label}: homepage baseDraft.text 缺失（先回退 source 修复，再创作主页）"]

    draft_page = _entity_draft_dir(task_id, batch_id, domain, etype, name) / "page.md"
    if not draft_page.is_file():
        return [f"{label}: 等待创作 agent写回 4.draft/page.md（generator=agent 正文）"]
    draft_text = draft_page.read_text(encoding="utf-8")
    if is_placeholder(draft_text):
        return [f"{label}: 4.draft/page.md 仍是占位，等待创作 agent按底稿创作正文"]

    from _common.figure_groups import expand_figure_groups, figure_group_integrity_issues

    # 连续图组带回完整性（P2 / R-CS10）：先对【原始正文】判 figuregroup 是否按原 id/张数带回。
    group_issues = figure_group_integrity_issues(draft_text, base_text)
    if group_issues:
        return [f"{label}: figuregroup integrity: {issue}" for issue in group_issues]
    # 通过后回填：把连续图组占位展开为 N 个同源单图块，下游门禁/配图注入统一消费单图形态。
    draft_text = expand_figure_groups(draft_text)

    gate_body = _homepage_gate_body(draft_text)
    gate_issues: list[str] = []
    gate_issues.extend(f"{label}: {msg}" for msg in template_fingerprint_issues(gate_body))
    from _common.base_draft import base_draft_fidelity_issues

    gate_issues.extend(
        f"{label}: {msg}"
        for msg in base_draft_fidelity_issues(
            gate_body,
            base_text,
            carrier="article",
            max_ratio=HOMEPAGE_FIDELITY_MAX,
            source_use_mode=str(base.get("sourceUseMode") or "factual_reference_only"),
        )
    )
    if gate_issues:
        return gate_issues

    images = _pick_homepage_assets(task_id, batch_id, domain, etype, name)
    if not images:
        return [f"{label}: homepage lane 无可发布图片资产"]
    obj = batch_entity_object_dir(task_id, batch_id, domain, etype, name)
    obj.mkdir(parents=True, exist_ok=True)
    from _common.paths import STAGE_REVIEW, ensure_object_stages

    ensure_object_stages(obj, through_stage=STAGE_REVIEW)
    assets: list[dict[str, Any]] = []
    for index, image in enumerate(images):
        manifest_role = "cover" if index == 0 else "gallery"
        # assetId 仅接受 cover/closing/detail；gallery 语义写入 manifest.role。
        asset_role = "cover" if index == 0 else "detail"
        asset = _copy_homepage_asset(
            task_id,
            batch_id,
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

    # 配图确定性注入：在门禁通过后，把同源真实图按章节锚点注入正文 figure 块
    # （封面=第一图 fullWidth、其余按章节就近 wrapLeft/wrapRight、无法定位进文末『图集』）。
    # 幂等：Agent 已内联的 asset:// 不重复注入。
    from _common.asset_placement import place_assets_in_markdown
    from _common.creator_assignment import creator_from_payload

    creator_fields = creator_from_payload(payload)
    image_placements: list[dict[str, Any]] = []
    unit_ref = str(base.get("primaryEvidenceRef") or base.get("sourceRef") or "").strip()
    if unit_ref:
        try:
            meta_path = batch_root(task_id, batch_id) / Path(unit_ref).parent / "meta.json"
            if meta_path.is_file():
                meta = read_json(meta_path)
                raw_placements = meta.get("imagePlacements") if isinstance(meta, dict) else []
                if isinstance(raw_placements, list):
                    image_placements = [row for row in raw_placements if isinstance(row, dict)]
        except (OSError, ValueError, TypeError):
            image_placements = []

    _homepage_layout_assets(assets)
    # 把 meta.imagePlacements 的 caption 回填到 manifest assets（wikitext 语义 caption）。
    placement_caption_by_file = {
        str(p.get("fileName") or "").lower(): str(p.get("caption") or "")
        for p in image_placements
        if str(p.get("caption") or "").strip()
    }
    if placement_caption_by_file:
        from urllib.parse import unquote

        for asset in assets:
            hay = unquote(
                " ".join(
                    [
                        str(asset.get("sourceAssetRef") or ""),
                        str(asset.get("fileName") or ""),
                        str(asset.get("authorizationProof") or ""),
                    ]
                )
            ).lower().replace("%20", " ")
            for file_key, cap in placement_caption_by_file.items():
                stem = Path(file_key).stem.lower()
                if file_key and (file_key in hay or stem in hay):
                    asset["caption"] = cap
                    break

    from _common.asset_placement import _caption_is_degraded

    for asset in assets:
        if str(asset.get("role") or "") != "cover":
            continue
        caption = str(asset.get("caption") or "")
        file_name = str(asset.get("fileName") or "")
        if _caption_is_degraded(caption, file_name=file_name):
            # 退化 caption 一律回退到原文标题（实体名），禁止任何领域硬编码补全。
            asset["caption"] = name

    # wikitext imagePlacements 用 fileName 锚点；finalize 已分配 assetId，在此对齐。
    resolved_placements: list[dict[str, Any]] = []
    for row in image_placements:
        if not isinstance(row, dict):
            continue
        file_name = str(row.get("fileName") or "").lower()
        matched_id = ""
        for asset in assets:
            from urllib.parse import unquote

            hay = unquote(
                " ".join(
                    [
                        str(asset.get("sourceAssetRef") or ""),
                        str(asset.get("fileName") or ""),
                        str(asset.get("authorizationProof") or ""),
                    ]
                )
            ).lower().replace("%20", " ")
            if file_name and (file_name in hay or Path(file_name).stem in hay):
                matched_id = str(asset.get("assetId") or "")
                break
        if matched_id:
            resolved_placements.append({**row, "assetId": matched_id})

    final_text = place_assets_in_markdown(
        draft_text,
        assets,
        placements=resolved_placements or image_placements,
    )
    cover_asset_id = next(
        (str(a.get("assetId") or "") for a in assets if a.get("role") == "cover"),
        str((assets[0] or {}).get("assetId") or ""),
    )
    final_text = _ensure_homepage_cover_frontmatter(final_text, cover_asset_id)
    (obj / "page.md").write_text(final_text, encoding="utf-8")

    facts = _split_fact_sentences(gate_body, entity_name=name) or _split_fact_sentences(base_text, entity_name=name)
    single_source = str(base.get("primaryEvidenceRef") or base.get("sourceRef") or "").strip()
    text_source_refs = _dedupe_nonempty([single_source])
    image_source_refs = list(text_source_refs)
    source_refs = list(text_source_refs)
    tag_refs = _homepage_tag_refs(domain, etype, name, payload)
    write_json(
        obj / "_entity.json",
        {
            "label": name,
            "domain": domain,
            "type": etype,
            "sourceTaskId": task_id,
            "entityRef": entity_ref(domain, etype, name),
            "summary": _homepage_summary(name, facts, base_text=gate_body or base_text),
            "sourceRefs": source_refs,
            "textSourceRefs": text_source_refs,
            "imageSourceRefs": image_source_refs,
            "tagRefs": tag_refs,
            **creator_fields,
        },
    )
    write_json(
        obj / "manifest.json",
        {
            "entityRef": entity_ref(domain, etype, name),
            "sourceTaskId": task_id,
            "sourceRefs": source_refs,
            "textSourceRefs": text_source_refs,
            "imageSourceRefs": image_source_refs,
            "tagRefs": tag_refs,
            "assets": assets,
            "generator": "agent",
            **creator_fields,
        },
    )
    return []


def materialize_entity_pages(task_id: str, batch_id: str, spec: dict[str, Any]) -> list[str]:
    """物化所有缺失或未过门的 coverage 实体主页，返回剩余物化问题。"""
    issues: list[str] = []
    for target in _coverage_targets(spec):
        domain, etype, name = target["domain"], target["etype"], target["name"]
        current_issues = validate_entity_page(
            task_id,
            batch_id,
            domain,
            etype,
            name,
        )
        if not current_issues:
            continue
        issues.extend(materialize_entity_page(task_id, batch_id, domain, etype, name))
    return issues


def _entity_draft_path(task_id: str, batch_id: str, domain: str, etype: str, name: str) -> Path:
    return batch_entity_stage_dir(task_id, batch_id, domain, etype, name, STAGE_DRAFT) / "page.md"


def _write_entity_draft(task_id: str, batch_id: str, domain: str, etype: str, name: str) -> Path:
    """返回创作 agent创作的 4.draft/page.md；不得用 finalize 终稿覆盖 Agent 正文。

    主页正文已由创作 agent在 4.draft/page.md 创作，finalize 只把它注入封面后写到 page.md。
    这里只在草稿意外缺失时，用终稿做一次性补写兜底，否则保留 Agent 原始草稿用于
    finalization_report 的 draft↔final 归一化对照。
    """
    obj = batch_entity_object_dir(task_id, batch_id, domain, etype, name)
    final_page = obj / "page.md"
    draft_page = _entity_draft_path(task_id, batch_id, domain, etype, name)
    if not draft_page.is_file() and final_page.is_file():
        draft_page.parent.mkdir(parents=True, exist_ok=True)
        draft_page.write_text(final_page.read_text(encoding="utf-8"), encoding="utf-8")
    return draft_page


def _entity_review_paths(task_id: str, batch_id: str, domain: str, etype: str, name: str) -> tuple[Path, Path, Path]:
    review_dir = batch_entity_stage_dir(task_id, batch_id, domain, etype, name, STAGE_REVIEW)
    return (
        review_dir / "review.json",
        review_dir / "provenance.json",
        review_dir / "finalization_report.json",
    )


def _entity_homepage_agent_run_id(
    task_id: str, batch_id: str, domain: str, etype: str, name: str
) -> str:
    draft_meta_path = _entity_draft_dir(task_id, batch_id, domain, etype, name) / "draft_meta.json"
    if draft_meta_path.is_file():
        meta = read_json(draft_meta_path)
        run_id = str(meta.get("agentRunId") or "").strip()
        if run_id and not run_id.startswith("build-homepage:"):
            return run_id
    try:
        from task.run import load_workflow_state

        state = load_workflow_state(task_id, batch_id)
    except (ImportError, OSError, ValueError, TypeError):
        return ""
    rows: list[Any] = []
    history = state.get("agentRunHistory")
    if isinstance(history, list):
        rows.extend(history)
    last = state.get("lastAgentRun")
    if isinstance(last, dict):
        rows.append(last)
    for run in reversed(rows):
        if str(run.get("stage") or "") != "build_homepage":
            continue
        for outcome in run.get("outcomes") or []:
            if not isinstance(outcome, dict):
                continue
            if str(outcome.get("status") or "") != "finished":
                continue
            run_id = str(outcome.get("runId") or "").strip()
            if run_id:
                return run_id
    return ""


def _build_entity_provenance(
    *,
    task_id: str,
    batch_id: str,
    domain: str,
    etype: str,
    name: str,
    source_paths: list[str],
    review_payload: dict[str, Any],
) -> dict[str, Any]:
    rel_page = f"entities/{domain}/{etype}/{name}/page.md"
    rel_input = f"entities/{domain}/{etype}/{name}/3.compose/entity_page_input.json"
    cited_paths = [rel_page if item == "page.md" else item for item in source_paths]
    obj = batch_entity_object_dir(task_id, batch_id, domain, etype, name)
    draft_page = _entity_draft_dir(task_id, batch_id, domain, etype, name) / "page.md"
    prompt_page = _entity_draft_dir(task_id, batch_id, domain, etype, name) / "prompt.md"
    input_path = batch_entity_page_input_path(task_id, batch_id, domain, etype, name)
    final_page = obj / "page.md"
    source_bundle_text = ""
    for rel in source_paths:
        candidate = batch_root(task_id, batch_id) / rel
        if candidate.is_file():
            source_bundle_text += candidate.read_text(encoding="utf-8", errors="ignore")
    draft_text = draft_page.read_text(encoding="utf-8") if draft_page.is_file() else ""
    final_text = final_page.read_text(encoding="utf-8") if final_page.is_file() else draft_text
    compose_payload = {
        "sourcePaths": source_paths,
        "sourceUrls": [],
        "citedSourceRefs": cited_paths or source_paths,
        "generator": "agent",
        "generatorModel": "homepage-agent",
        "articleMarkdownDigest": compute_document_sha256(final_text),
        "entityRefs": [entity_ref(domain, etype, name)],
    }
    draft_meta = {
        "generator": "agent",
        "model": "homepage-agent",
        "agentRunId": _entity_homepage_agent_run_id(task_id, batch_id, domain, etype, name),
        "agentId": "build.homepage",
        "sessionTrace": "build_homepage",
        "styleFamily": "entity-homepage",
        "openingStrategy": "base_draft_light_edit",
        "citedSourcePaths": cited_paths or source_paths,
        "promptSha256": sha256_file(prompt_page) if prompt_page.is_file() else sha256_text(""),
        "writingPackSha256": sha256_file(input_path) if input_path.is_file() else sha256_text(""),
        "sourceBundleSha256": sha256_text(source_bundle_text),
        "draftSha256": compute_document_sha256(draft_text),
    }
    manifest = {
        "publishTitle": name,
        "publishSeq": 1,
        "entityRefs": [entity_ref(domain, etype, name)],
    }
    provenance = build_provenance(
        entity_ref(domain, etype, name),
        writing_pack={"title": name, "styleFamily": "entity-homepage"},
        draft_meta=draft_meta,
        review_payload=review_payload,
        compose_payload=compose_payload,
        manifest=manifest,
    )
    provenance["agentInput"]["writingPack"] = rel_input
    provenance["agentInput"]["prompt"] = "4.draft/prompt.md"
    provenance["final"]["articleDigest"] = compute_document_sha256(final_text)
    return provenance


def _write_entity_review_sidecars(
    task_id: str,
    batch_id: str,
    domain: str,
    etype: str,
    name: str,
    *,
    source_paths: list[str],
    review_payload: dict[str, Any],
) -> None:
    obj = batch_entity_object_dir(task_id, batch_id, domain, etype, name)
    final_page = obj / "page.md"
    draft_page = _write_entity_draft(task_id, batch_id, domain, etype, name)
    review_path, provenance_path, finalization_path = _entity_review_paths(task_id, batch_id, domain, etype, name)
    review_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(review_path, review_payload)
    write_json(
        provenance_path,
        _build_entity_provenance(
            task_id=task_id,
            batch_id=batch_id,
            domain=domain,
            etype=etype,
            name=name,
            source_paths=source_paths,
            review_payload=review_payload,
        ),
    )
    write_json(
        finalization_path,
        build_finalization_report(
            entity_ref(domain, etype, name),
            draft_markdown=draft_page.read_text(encoding="utf-8") if draft_page.is_file() else "",
            final_markdown=final_page.read_text(encoding="utf-8") if final_page.is_file() else "",
            normalization_actions=["entity_homepage_draft_materialized"],
            article_source="4.draft/page.md",
            compose_snapshot_markdown=None,
            draft_ref="4.draft/page.md",
            final_ref="page.md",
            compose_snapshot_ref=None,
        ),
    )
    write_entity_object_index(task_id, batch_id, domain, etype, name)
    sync_entity_object_to_task_mirror(task_id, batch_id, domain, etype, name)


def _entity_review_payload(
    *,
    issues: list[str],
    source_paths: list[str],
    base_draft_exists: bool,
) -> dict[str, Any]:
    base_source_issue = (not source_paths) or (not base_draft_exists)
    decision = "approved" if not issues else "revision_needed"
    fallback = "build_homepage" if issues else None
    if base_source_issue:
        fallback = "needs_source_repair"
    return {
        "decision": decision,
        "issues": issues,
        "fallbackStage": fallback,
        "checks": {
            "entityPageQuality": {"passed": not issues, "issues": issues},
            "sourceReadiness": {
                "passed": not base_source_issue,
                "issues": [] if not base_source_issue else ["no readable base draft source available for homepage"],
            },
        },
    }


def _homepage_authenticity_issues(
    task_id: str,
    batch_id: str,
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
    base = _entity_base_draft(task_id, batch_id, domain, etype, name)
    base_text = str((base or {}).get("text") or "").strip()
    if base_text:
        from _common.base_draft import base_draft_fidelity_issues

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
    task_id: str,
    batch_id: str,
    domain: str,
    etype: str,
    name: str,
) -> list[str]:
    """校验单个实体主页三件套/字数/必填字段，返回阻断问题列表。"""
    resolve_entity_object_dir(task_id, batch_id, name, etype_hint=f"{domain}/{etype}")
    obj = batch_entity_object_dir(task_id, batch_id, domain, etype, name)
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
        issues.extend(_homepage_authenticity_issues(task_id, batch_id, domain, etype, name, page, label))
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

    for field in _REQUIRED_ENTITY_FIELDS:
        if not payload.get(field):
            issues.append(f"{label}: _entity.json 缺字段 {field}")
    if payload.get("domain") and payload["domain"] != domain:
        issues.append(f"{label}: _entity.json domain={payload['domain']} 与目录不一致")
    if payload.get("type") and payload["type"] != etype:
        issues.append(f"{label}: _entity.json type={payload['type']} 与目录不一致")
    issues.extend(_condition_profile_issues(payload, label, catalogs_root=_CONDITION_CATALOGS_ROOT))
    issues.extend(_homepage_base_source_issues(task_id, batch_id, domain, etype, name))

    issues.extend(_asset_closure_issues(obj, manifest_payload, label))
    primary_ref = ""
    base = _entity_base_draft(task_id, batch_id, domain, etype, name)
    primary_ref = str((base or {}).get("primaryEvidenceRef") or (base or {}).get("sourceRef") or "")
    for raw in manifest_payload.get("assets") or []:
        if not isinstance(raw, dict):
            continue
        asset_source = str(raw.get("sourceRef") or "")
        if primary_ref and asset_source and not _same_source_unit(asset_source, primary_ref):
            issues.append(
                f"{label}: asset {raw.get('assetId') or raw.get('fileName')} "
                f"sourceRef must match primaryEvidenceRef unit"
            )
    source_paths = _entity_source_paths(task_id, batch_id, domain, etype, name)
    review_payload = _entity_review_payload(
        issues=issues,
        source_paths=source_paths,
        base_draft_exists=bool(source_paths),
    )
    _write_entity_review_sidecars(
        task_id,
        batch_id,
        domain,
        etype,
        name,
        source_paths=source_paths,
        review_payload=review_payload,
    )
    return issues


def validate_entity_pages(task_id: str, batch_id: str, spec: dict[str, Any]) -> list[str]:
    """校验全部 coverage 实体主页，返回阻断问题列表（空=采纳通过）。"""
    targets = _coverage_targets(spec)
    if not targets:
        return ["build validate: scope.coverageTargets 为空，无可校验实体"]
    issues: list[str] = []
    for target in targets:
        issues.extend(
            validate_entity_page(
                task_id,
                batch_id,
                target["domain"],
                target["etype"],
                target["name"],
            )
        )
    return issues
