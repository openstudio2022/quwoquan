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
from content.homepage.homepage_media_freeze import frozen_publishable_images
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

_SHARED_STRUCTURE_INSTRUCTION = (
    "结构尊重底稿真实内容——规范化章节只作参考（用于章节命名与归类对齐），"
    "不是必须逐节填满的清单：仅『概况』必备，其余章节有真实内容才写、无内容直接省略、禁止硬凑，"
    "只允许增减或合并不在 baseDraft.sectionOutline 必需清单中的章节；"
    "清单内标题必须原文、原层级保留。章节语义须正确（如『历史沿革』必须是真实历史，否则省略）。"
    "多级目录硬要求：底稿（百科类来源）有多级标题层级时，必须保留为 `##` / `###` 多级小标题，"
    "baseDraft.sectionOutline 列出的有实质内容的关键章节（如『技术变革』『相关古迹』）"
    "必须保留为对应级别小标题，禁止静默丢弃、拍平为单层或并入其它段落。"
    "章节均衡硬要求：任何单个章节去空白字数不得超过正文总量的一半。"
    "时间线归并硬要求：底稿把同一实体多条并列时间线分段罗列时，必须按真实时间顺序归并为单一连贯叙事，"
    "禁止首尾拼接造成时间倒错，同章节年份应大致单调推进。"
)

_LICENSED_ADAPTATION_INSTRUCTION = (
    "本篇 sourceUseMode=licensed_adaptation：署名与许可证据在场，允许以底稿为骨架轻改，"
    "保留底稿信息顺序与关键事实细节；首稿主动改写约 20%-30% 的句子，不得连续逐句照搬。"
    "执行时先按原顺序恢复完整底稿的必需标题、全部正文段落和每个图片占位符，"
    "再只对约四分之一句子做局部润色；每个底稿段落至少保留三分之二原句骨架，"
    "禁止摘要、合并或省略后半部分。"
)


def _factual_reference_instruction() -> str:
    """指令数值直接取自准出门常量，杜绝两侧各写一个阈值。"""
    from content.homepage.commercial_gate import (
        FACTUAL_COMPRESSION_TIERS,
        FACTUAL_REFERENCE_MAX_FIDELITY,
    )

    long_source_threshold, long_source_max_ratio = FACTUAL_COMPRESSION_TIERS[0]
    return (
        "本篇 sourceUseMode=factual_reference_only：底稿只是事实来源，没有沿用原文的许可。"
        "必须先做事实抽取（年份、尺度、机构、事件、地理与票务等），再用自己的话重写成连贯叙述；"
        "禁止按段落顺序逐句润色式沿用。两条准出硬门决定写法："
        f"一是 5-gram 字符重合率必须低于 {FACTUAL_REFERENCE_MAX_FIDELITY}，"
        "任何超过十余字的原文长串都会把重合率顶上去，必须换成自己的句式与语序；"
        f"二是底稿超过 {long_source_threshold} 字时，成稿去空白字数不得超过底稿的 "
        f"{long_source_max_ratio} 倍，目标压到约一半——"
        "按信息价值取舍是必需动作：保留关键事实节点，删去逐条罗列的次要细节、重复表述与冗长边界描述。"
        "事实必须准确，不得编造或改动数字；压缩与改写针对表达方式，不针对事实真实性。"
    )


def homepage_editing_instruction(source_use_mode: str) -> str:
    """按版权模式下发创作指令。

    两种模式的准出门本就不同（``copyright_mode_issues``：licensed_adaptation 不设
    fidelity 上限，factual_reference_only 有 fidelity 与压缩双硬门），指令必须随之
    分叉。历史上两模式共用一条「保留原句骨架、禁止摘要」指令，与压缩门正面冲突，
    无人值守放量时通过率恒为 0。
    """
    mode = str(source_use_mode or "").strip()
    if mode == "licensed_adaptation":
        mode_instruction = _LICENSED_ADAPTATION_INSTRUCTION
    elif mode == "factual_reference_only":
        mode_instruction = _factual_reference_instruction()
    else:
        raise ValueError(
            f"未知 sourceUseMode {mode!r}（fail-closed，允许值见 source_inputs）"
        )
    return (
        "把 primaryEvidenceRef 作为**唯一**底稿骨架与主题锚点（单底稿零参考，禁止引用其它来源）。"
        "在底稿基础上做事实校正、PII/平台痕迹清理与人设适配。"
        + mode_instruction
        + "不得脱离底稿从零另写，也不得整篇零加工照搬。"
        + _SHARED_STRUCTURE_INSTRUCTION
    )


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
        # 预排版只读 `1.download` 的冻结处置（DEC-029）：下发给创作方的占位符必须与
        # 物化落盘的那一组图完全同源，这里再算一次就等于给同一事实开第二个决策点。
        available_images = _homepage_available_images(
            frozen_publishable_images(execution_id, domain, etype, name)
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
            # geoTagRef 是物化必填（_REQUIRED_ENTITY_FIELDS），typeTagRefs 供打标物化消费（WP3），
            # coordinates 可选，物化后由 entity-service importer 写入 Homepage.location。
            **{
                key: target[key]
                for key in ("geoTagRef", "geoTagRefs", "typeTagRefs", "aliases", "coordinates")
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
            "editingInstruction": homepage_editing_instruction(
                str((base_draft or {}).get("sourceUseMode") or "factual_reference_only")
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
