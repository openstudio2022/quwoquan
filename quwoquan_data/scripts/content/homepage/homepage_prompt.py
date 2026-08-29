"""Entity homepage prompt and placeholder construction."""
from __future__ import annotations
import shutil
import re
from pathlib import Path
from typing import Any
import yaml
from core.io import read_json, write_assistant_task, write_json
from content.execution.runtime_contract import canonical_sha256, stage_execution_context
from core.article_package import compute_document_sha256, sha256_file, sha256_text
from content.post.article.draft_io import PLACEHOLDER_MARKER, is_placeholder
from core.entity_page_quality import entity_page_quality_issues
from core.localization import fold_to_simplified
from core.prompt_render import render
from content.execution.prompt_snapshot import prompt_bundle_revision, write_prompt_snapshot
from content.execution.model_contract import execution_model_pair_for_execution
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
# 实体主页底稿下发上限：取消旧的 4000 截断（旧值会把维基百科页在中段截断，
# Agent 看不到「技术变革 / 相关古迹」等后段章节，导致多级目录与章节缺失）。
# 放宽到覆盖绝大多数百科页全文，仅兜底极端超长源避免 token 失控。
from core.media_processing_policy import MEDIA_PROCESSING_POLICY

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
def _homepage_section_outline(
    unit_dir: Path,
    meta: dict[str, Any],
    *,
    min_section_chars: int,
) -> list[dict[str, Any]]:
    """从来源 `source.md`（保留 wiki `==/===`）解析关键章节，供 prompt 保留多级目录。
    优先复用下载阶段已写入 meta.sectionOutline（P1 联网解析）；缺省时离线从原文解析。
    `source.clean.md` 已把标题压成无标记纯文本会丢层级，故必须读 `source.md` 原文。
    """
    from core.section_outline import (
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
        parse_section_outline(raw_text), min_body_chars=min_section_chars
    )
    return outline_to_dicts(nodes)
def _homepage_structured_base_text(base_text: str, outline_rows: list[dict[str, Any]]) -> str:
    """把来源 outline 还原进底稿正文，确保 Agent 看到的是带 `##/###` 的轻改底稿。
    旧契约只把 outline 放在底稿外侧，`baseDraft.text` 本体是无标题纯段落；
    Agent 很容易把章节拍平或静默丢掉。这里按 `charStart` 从后往前插入标题，
    只补结构标记，不改事实文本。
    """
    text = str(base_text or "").strip()
    if not text or not outline_rows:
        return text
    if any(line.lstrip().startswith("##") for line in text.splitlines()):
        return text
    inserts: list[tuple[int, str]] = []
    for row in outline_rows:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or "").strip()
        if not title:
            continue
        try:
            pos = int(row.get("charStart") or 0)
            level = int(row.get("level") or 2)
        except (TypeError, ValueError):
            continue
        if pos <= 0 or pos >= len(text):
            continue
        marker = "#" * min(max(level, 2), 6)
        inserts.append((pos, f"\n\n{marker} {title}\n\n"))
    if not inserts:
        return text
    out = text
    for pos, heading in sorted(inserts, key=lambda item: item[0], reverse=True):
        out = out[:pos].rstrip() + heading + out[pos:].lstrip()
    return re.sub(r"\n{3,}", "\n\n", out).strip()
def _strip_frontmatter_block(text: str) -> str:
    body = str(text or "")
    if body.startswith("---\n"):
        end = body.find("\n---\n", 4)
        if end != -1:
            return body[end + len("\n---\n"):].strip()
    return body.strip()
def _homepage_structured_source_text(unit_dir: Path, fallback_text: str, outline_rows: list[dict[str, Any]]) -> str:
    """优先从原始 source.md 转出带 Markdown 标题的底稿，避免 clean 文本 charStart 错位。"""
    from core.section_outline import match_heading
    raw_path = unit_dir / "source.md"
    if raw_path.is_file():
        try:
            raw_body = _strip_frontmatter_block(raw_path.read_text(encoding="utf-8"))
        except OSError:
            raw_body = ""
        if raw_body and any(match_heading(line) for line in raw_body.splitlines()):
            lines: list[str] = []
            for line in raw_body.splitlines():
                heading = match_heading(line)
                if heading is not None:
                    level, title = heading
                    lines.append(f"{'#' * min(max(level, 1), 6)} {title}")
                    continue
                cleaned = _WIKI_FILE_INLINE_RE.sub("", line).strip()
                lines.append(cleaned)
            return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return _homepage_structured_base_text(fallback_text, outline_rows)
def _homepage_base_source_issues(execution_id: str, domain: str, etype: str, name: str) -> list[str]:
    label = f"{domain}/{etype}/{name}"
    quality_path = execution_entity_stage_dir(execution_id, domain, etype, name, STAGE_QUALITY) / "quality_analysis.json"
    if not quality_path.is_file():
        return [f"{label}: 2.quality/quality_analysis.json 缺失"]
    quality = read_json(quality_path)
    compose_path = execution_entity_stage_dir(execution_id, domain, etype, name, STAGE_COMPOSE) / "entity_page_input.json"
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
    meta_path = execution_root(execution_id) / base_source
    meta = read_json(meta_path.parent / "meta.json") if (meta_path.parent / "meta.json").is_file() else {}
    source_kind, is_primary, is_author_experience = _homepage_base_source_issue_text(meta)
    if not is_primary:
        issues.append(
            f"{label}: entity homepage base draft must be homepage primary authority source, got {source_kind or '<empty>'}"
        )
    if is_author_experience:
        issues.append(
            f"{label}: entity homepage base draft must not be author travelogue/guide/comment source, got {source_kind or '<empty>'}"
        )
    return issues
def _entity_base_source_line(base_ref: str, base_mode: str) -> str:
    """底稿用法只从 sourceUseMode 派生，与准出门同源（避免第二套写作口径）。"""
    if not base_ref:
        return "- 当前无可用底稿（source 不足）；不要凭空编造，先回退到 source 修复。"
    from content.homepage.homepage_prepare import homepage_editing_instruction

    return (
        f"- **底稿来源**：`{base_ref}`（sourceUseMode=`{base_mode}`）。"
        + homepage_editing_instruction(base_mode)
    )
def _entity_section_outline_block(base: dict[str, Any]) -> str:
    outline_rows = base.get("sectionOutline") if isinstance(base.get("sectionOutline"), list) else []
    if not outline_rows:
        return ""
    from core.section_outline import render_outline_tree_from_dicts
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

# 实体类型 → 读者关注点提示（仅选材优先级提示，不是必写章节清单；一切以底稿为准）。
_ENTITY_TYPE_FOCUS_HINTS: dict[str, str] = {
    "自然景观": "地理位置与成因地貌、生态与季节景致、游览方式与安全提示",
    "古镇": "历史沿革与聚落格局、街巷建筑与人文遗存、物产民俗与到访体验",
    "景区": "范围与核心景点构成、历史与文化背景、游览动线与实用信息",
    "场馆": "定位与馆藏 / 功能、建筑与历史、开放与参观信息",
    "博物馆": "馆藏与陈列脉络、建筑与历史、开放与参观信息",
    "寺庙": "宗教渊源与历史沿革、建筑与文物、参访礼仪与开放信息",
    "公园": "区位与园林格局、景观与设施、季节与游览建议",
    "水利工程": "工程规模与功能、建设历程、周边景观与参观方式",
}

def _entity_type_focus_block(etype: str) -> str:
    """按实体类型给出读者关注点提示；不命中类型则返回空（完全遵从底稿）。"""
    hint = _ENTITY_TYPE_FOCUS_HINTS.get(str(etype or "").strip())
    if not hint:
        return ""
    return (
        f"- 类型关注点（选材优先级提示，非必写章节）：该实体类型为「{etype}」，"
        f"读者通常关注：{hint}。**一切以底稿真实内容为准**：底稿没有的关注点"
        "不得虚构、不得硬凑章节。"
    )
def _entity_available_images_block(payload: dict[str, Any]) -> str:
    """AI 最小干扰协议：图片元数据不进 prompt，只声明占位符纪律（plan §11）。"""
    bindings = (
        payload.get("imagePlaceholderBindings")
        if isinstance(payload.get("imagePlaceholderBindings"), list)
        else []
    )
    if not bindings:
        return ""
    return (
        "## 图片占位符纪律\n\n"
        f"「底稿材料」中共有 {len(bindings)} 行形如 `[[IMG:fig_NN]]` 的系统图片占位符。"
        "每一行都必须**原样带回**：不改 id、不移动位置、不复制、不删除、不新增，"
        "行尾不得追加任何文字（图注由系统注入）；也不得书写任何 `asset://` 或 `:::figure`。"
        "封面与相关图片由系统在 finalize 阶段注入。"
    )
def _homepage_image_placeholder_bindings(available: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """AI 协议 bindings：只为「非封面 + 有原图注 + 有章节锚点」的同源图生成占位符。
    封面裁决与相关图片区完全不进 prompt（plan §11）；无原图注或无锚点的图由
    finalize 的 place_homepage_assets_in_markdown 代码侧裁决归置，也不进 prompt。
    figId 按 available 序号稳定命名。
    """
    bindings: list[dict[str, Any]] = []
    for index, row in enumerate(available):
        if not isinstance(row, dict) or index == 0:
            continue
        if str(row.get("placementType") or "") != "inline":
            continue
        source_asset_id = str(row.get("sourceAssetId") or "").strip()
        caption = str(row.get("caption") or "").strip()
        anchor = str(row.get("sectionAnchor") or "").strip()
        if not source_asset_id or not caption or not anchor:
            continue
        bindings.append({
            "figId": f"fig_{index + 1:02d}",
            "sourceAssetId": source_asset_id,
            "caption": re.sub(r"\s+", " ", caption),
            "sectionAnchor": str(row.get("sectionAnchor") or ""),
            "paragraphIndex": int(row.get("paragraphIndex") or 0),
        })
    return bindings
def _homepage_base_text_with_image_placeholders(
    base_text: str,
    bindings: list[dict[str, Any]],
) -> str:
    """把极简图片占位符行插入底稿正文原位（章节锚点优先），供模型原样带回。
    模型只见 `[[IMG:fig_NN]]` 单行（不含图注，图注真相源在 bindings）；
    :::figure 展开、封面与相关图片区全部收回代码侧（_common.ai_refine_protocol）。
    """
    from core.ai_refine_protocol import image_placeholder_line
    text = _strip_homepage_source_media_for_agent(base_text)
    if not text:
        return text
    # 主页的封面、图集和无可靠正文锚点图片都由 finalize 物化，不能泄漏为
    # Agent 可见的 asset://。只有已验证为 inline 的图片才获得最小占位符。
    if not bindings:
        return text
    lines = text.splitlines()
    section_line_by_slug: dict[str, tuple[int, int]] = {}
    from core.section_outline import match_heading, slugify_section
    headings: list[tuple[str, int]] = []
    for idx, line in enumerate(lines):
        heading = match_heading(line)
        if heading is None:
            continue
        headings.append((slugify_section(heading[1]), idx))
    for index, (slug, line_no) in enumerate(headings):
        next_line = headings[index + 1][1] if index + 1 < len(headings) else len(lines)
        section_line_by_slug.setdefault(slug, (line_no, next_line))

    def _paragraph_anchor(start: int, end: int, paragraph_index: int) -> int:
        if paragraph_index <= 0:
            return start
        count = 0
        in_paragraph = False
        paragraph_end = start
        for line_no in range(start + 1, end):
            stripped = lines[line_no].strip()
            structural = (
                not stripped
                or stripped.startswith(("#", "- ", "* ", "|", ":::", "asset://"))
            )
            if not structural:
                in_paragraph = True
                paragraph_end = line_no
                continue
            if in_paragraph:
                count += 1
                if count >= paragraph_index:
                    return paragraph_end
                in_paragraph = False
        if in_paragraph:
            count += 1
            if count >= paragraph_index:
                return paragraph_end
        return -1
    inserts: dict[int, list[str]] = {}
    for row in bindings:
        block = image_placeholder_line(str(row.get("figId") or ""))
        anchor = slugify_section(str(row.get("sectionAnchor") or ""))
        line_no = -1
        if anchor:
            for slug, (section_start, section_end) in section_line_by_slug.items():
                if slug and (slug == anchor or slug.startswith(anchor) or anchor.startswith(slug)):
                    line_no = _paragraph_anchor(
                        section_start,
                        section_end,
                        int(row.get("paragraphIndex") or 0),
                    )
                    break
        if line_no >= 0:
            inserts.setdefault(line_no, []).append(block)
        else:
            # 结构证据无法解析时不猜测正文位置；该资产会由 finalize 归入相关图片。
            continue
    for line_no in sorted(inserts.keys(), reverse=True):
        lines[line_no + 1:line_no + 1] = ["", *inserts[line_no], ""]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


_HOMEPAGE_SOURCE_MEDIA_BLOCK_RE = re.compile(
    r"(?ms)^:::(?:figure|figuregroup|gallery)\b[^\n]*\n.*?^:::[ \t]*$"
)
_HOMEPAGE_SOURCE_MEDIA_LINE_RE = re.compile(
    r"(?m)^.*?(?:!\[[^\]]*\]\(asset://[^)]+\)|asset://\S+).*?$"
)


def _strip_homepage_source_media_for_agent(base_text: str) -> str:
    """移除供 Agent 创作的底稿中的来源媒体语法。

    主页媒体是代码侧的结构职责：可靠 inline 图片通过 ``[[IMG:...]]``
    回插；封面、图集和无锚点图片在 finalize 时分别裁决为 cover/related。
    因此 Agent 输入绝不能同时携带旧 ``asset://``/``:::figure`` 和新占位符。
    """
    text = str(base_text or "").strip()
    if not text:
        return ""

    def _drop_media_block(match: re.Match[str]) -> str:
        block = match.group(0)
        return "" if "asset://" in block else block

    text = _HOMEPAGE_SOURCE_MEDIA_BLOCK_RE.sub(_drop_media_block, text)
    text = _HOMEPAGE_SOURCE_MEDIA_LINE_RE.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()
def _render_entity_page_prompt(payload: dict[str, Any]) -> str:
    """人读写作指令：与文章 prompt 同构（指令区来自 entity_homepage 模板），写回目标是 4.draft/page.md。"""
    name = str(payload.get("name") or "")
    base = payload.get("baseDraft") if isinstance(payload.get("baseDraft"), dict) else {}
    base_ref = str(base.get("sourceRef") or base.get("primaryEvidenceRef") or "")
    base_mode = str(base.get("sourceUseMode") or "factual_reference_only")
    base_text = str(base.get("markdown") or base.get("text") or "").strip()
    return render(
        "entity_homepage",
        system_vars={
            "min_page_chars": int(payload["minChars"]),
            "min_section_chars": int(payload["minSectionChars"]),
        },
        task_vars={
            "name": name,
            "base_source_line": _entity_base_source_line(base_ref, base_mode),
            "type_focus_block": _entity_type_focus_block(str(payload.get("etype") or "")),
            "section_outline_block": _entity_section_outline_block(base),
            "base_draft_block": _entity_base_draft_block(base_text),
            "available_images_block": _entity_available_images_block(payload),
        },
    )
def _write_entity_page_prompt_and_placeholder(
    execution_id: str,
    domain: str,
    etype: str,
    name: str,
    payload: dict[str, Any],
) -> None:
    """下发人读 prompt.md + 占位 page.md：创作 agent在 4.draft/page.md 创作正文。
    与文章一致：占位草稿用 PLACEHOLDER_MARKER 标记『尚未创作』，但绝不覆盖
    创作 agent已写回的真实正文（非占位则保留）。
    """
    draft_dir = _entity_draft_dir(execution_id, domain, etype, name)
    draft_dir.mkdir(parents=True, exist_ok=True)
    previous_source_ref = ""
    previous_snapshot_path = draft_dir / "prompt_snapshot.json"
    if previous_snapshot_path.is_file():
        try:
            previous_snapshot = read_json(previous_snapshot_path)
            previous_payload = (
                ((previous_snapshot.get("variables") or {}).get("payload") or {})
                if isinstance(previous_snapshot, dict)
                else {}
            )
            previous_base = (
                previous_payload.get("baseDraft")
                if isinstance(previous_payload, dict)
                and isinstance(previous_payload.get("baseDraft"), dict)
                else {}
            )
            previous_source_ref = str(
                previous_base.get("primaryEvidenceRef")
                or previous_base.get("sourceRef")
                or ""
            ).strip()
        except (OSError, ValueError, TypeError):
            previous_source_ref = ""
    current_base = payload.get("baseDraft") if isinstance(payload.get("baseDraft"), dict) else {}
    current_source_ref = str(
        current_base.get("primaryEvidenceRef") or current_base.get("sourceRef") or ""
    ).strip()
    source_changed = bool(
        previous_source_ref
        and current_source_ref
        and previous_source_ref != current_source_ref
    )
    prompt_text = _render_entity_page_prompt(payload)
    prompt_path = draft_dir / "prompt.md"
    prompt_path.write_text(prompt_text, encoding="utf-8")
    execution = stage_execution_context(execution_id)
    object_ref = entity_ref(domain, etype, name)
    run_id = "author_" + canonical_sha256(
        {"executionId": execution["executionId"], "objectRef": object_ref}
    ).removeprefix("sha256:")[:20]
    author_model = execution_model_pair_for_execution(execution_id).author
    prompt_sha = sha256_text(prompt_text)
    write_json(
        draft_dir / "author_job_packet.json",
        {
            "schema": "quwoquan_data.author_job_packet",
            "stage": "4.draft",
            **execution,
            "objectRef": object_ref,
            "composePacketRef": "3.compose/entity_page_input.json",
            "promptRef": "4.draft/prompt.md",
            "promptSnapshotRef": "4.draft/prompt_snapshot.json",
            "provider": author_model.provider.value,
            "model": author_model.model_id,
            "runId": run_id,
            "outputRefs": [
                "4.draft/page.md",
                "4.draft/draft_meta.json",
                "4.draft/author_self_check.json",
                "4.draft/agent_result_envelope.json",
            ],
        },
    )
    write_prompt_snapshot(
        draft_dir / "prompt_snapshot.json",
        execution_id=execution_id,
        stage="4.draft",
        template_family="entity_homepage",
        variables={"payload": payload},
        rendered_prompt=prompt_text,
        provider=author_model.provider.value,
        model=author_model.model_id,
        run_id=run_id,
        output_refs=[
            "4.draft/page.md",
            "4.draft/draft_meta.json",
            "4.draft/author_self_check.json",
            "4.draft/agent_result_envelope.json",
        ],
    )
    write_json(
        draft_dir / "draft_meta.json",
        {
            "schema": "quwoquan_data.draft_meta",
            "stage": "4.draft",
            **execution,
            "objectRef": object_ref,
            "status": "pending_agent",
            "provider": author_model.provider.value,
            "model": author_model.model_id,
            "agentRunId": run_id,
            "promptSha256": prompt_sha,
            "draftSha256": None,
            "selfCheck": {"status": "pending", "issues": []},
        },
    )
    from core.schema import assert_valid

    assert_valid(
        read_json(draft_dir / "author_job_packet.json"),
        "content",
        "author_job_packet",
        label=f"author_job_packet:{name}",
    )
    assert_valid(
        read_json(draft_dir / "prompt_snapshot.json"),
        "execution",
        "prompt_snapshot",
        label=f"prompt_snapshot:{name}",
    )
    assert_valid(
        read_json(draft_dir / "draft_meta.json"),
        "content",
        "draft_meta",
        label=f"draft_meta:{name}",
    )
    if source_changed:
        for stale_name in (
            "failure.json",
            "author_self_check.json",
            "agent_result_envelope.json",
        ):
            (draft_dir / stale_name).unlink(missing_ok=True)
        entity_dir = draft_dir.parent
        for stale_name in ("page.md", "_entity.json", "manifest.json"):
            (entity_dir / stale_name).unlink(missing_ok=True)
        shutil.rmtree(entity_dir / "assets", ignore_errors=True)
        shutil.rmtree(entity_dir / "5.review", ignore_errors=True)
    draft_page = draft_dir / "page.md"
    if (
        not source_changed
        and draft_page.is_file()
        and not is_placeholder(draft_page.read_text(encoding="utf-8"))
    ):
        return
    draft_page.write_text(
        f"{PLACEHOLDER_MARKER}\n\n# {name}\n\n（待创作 agent按 prompt.md 与底稿创作实体主页正文，覆盖本占位）\n",
        encoding="utf-8",
    )
