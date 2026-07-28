"""Prepare immutable homepage authoring inputs for one execution."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from content.execution.prompt_snapshot import prompt_bundle_revision
from content.execution.runtime_contract import stage_execution_context
from content.homepage.homepage import (
    _condition_menu,
    _coverage_targets,
    _entity_base_draft,
    _entity_creator_assignment,
    _homepage_available_images,
    _homepage_source_contract,
    _safe_ref,
    _write_entity_quality_stage,
)
from content.homepage.homepage_assets import select_homepage_assets
from content.homepage.quality_policy import (
    homepage_body_char_minimum,
    homepage_section_char_minimum,
)
from content.homepage.homepage_prompt import (
    _homepage_base_text_with_image_placeholders,
    _homepage_image_placeholder_bindings,
    _write_entity_page_prompt_and_placeholder,
)
from content.source.source_unit import resolve_entity_object_dir
from core.io import write_assistant_task, write_json
from core.paths import (
    execution_assistant_task,
    execution_entity_object_dir,
    execution_entity_page_input_path,
    execution_root,
)
from governance.coverage.entity_extract import entity_ref

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
            "minChars": homepage_body_char_minimum(execution_id),
            "minSectionChars": homepage_section_char_minimum(execution_id),
            "baseDraft": base_draft,
            "availableImages": available_images,
            "imagePlaceholderBindings": image_placeholder_bindings,
            "regionMenu": _condition_menu(spec, "region", "region_catalog", "regions"),
            "seasonMenu": _condition_menu(spec, "season", "season_catalog", "seasons"),
            "editingInstruction": (
                "把 primaryEvidenceRef 作为**唯一**底稿骨架与主题锚点（单底稿零参考，禁止引用其它来源）。"
                "在底稿基础上做适度润色、事实校正、PII/平台痕迹清理与人设适配（licensed_adaptation 与 "
                "factual_reference_only 同等以底稿为骨架轻改、保留底稿信息顺序与关键事实细节；"
                "首稿主动改写约 20%-30% 的句子，不得连续逐句照搬）；"
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
            "schema": "quwoquan_data.stage_envelope",
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
