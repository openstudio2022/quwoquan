"""实体主页 build 真实链路：prepare 下发产出契约 + validate 采纳门。

与现行「三层目录实体」模型一致（entities/{领域}/{类型}/{名称}/）：
- prepare：读 effective task spec 的 scope.coverageTargets，为每个实体写
  3.compose/entity_page_input.json（含 SOP 模板路径、字数下限、底稿）+ 人读 4.draft/prompt.md
  + 占位 4.draft/page.md，并写 assistant_tasks 清单，下发给会话模型。
- Agent：读 prompt.md 与底稿，在底稿基础上做适度润色/事实校正/PII·平台痕迹清理/人设适配，
  把正文写回 4.draft/page.md（≥350字、保留底稿原句最小改、不脱离底稿从零另写、不机械模板凑字）。
- finalize（materialize_entity_page）：不脚本拼正文，只对会话模型正文把关贴合度+模板指纹门，
  再据正文与已授权真实图补齐封面资产并物化 page.md+_entity.json+manifest.json(generator=agent)，
  写真实 sha256 出处。
- validate：逐 coverage 实体校验三件套/字数/必填字段，并复检 generator=agent+贴合度+模板指纹，
  作为 promote 发布门之前的采纳门。
"""
from __future__ import annotations

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
_REQUIRED_ENTITY_FIELDS = ("label", "domain", "type", "sourceTaskId")
_REPO_DATA_ROOT = Path(__file__).resolve().parents[2]
_CONDITION_CATALOGS_ROOT = _REPO_DATA_ROOT / "templates" / "_registry" / "catalogs"


def _dedupe_nonempty(values: list[str]) -> list[str]:
    """保序去重并丢弃空串，供 sourceRefs 等列表收敛。"""
    return [v for v in dict.fromkeys(v for v in values if v)]

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
    meta_path = Path(best["unitDir"]) / "meta.json"
    meta = read_json(meta_path) if meta_path.is_file() else {}
    return {
        "sourceRef": best["sourceRef"],
        "primaryEvidenceRef": best["sourceRef"],
        "sourceUseMode": str(meta.get("sourceUseMode") or "factual_reference_only"),
        "text": text[:4000],
    }


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


def _render_entity_page_prompt(payload: dict[str, Any]) -> str:
    """人读写作指令：与文章 prompt.md 同构，但写回目标是 4.draft/page.md。"""
    name = str(payload.get("name") or "")
    base = payload.get("baseDraft") if isinstance(payload.get("baseDraft"), dict) else {}
    base_ref = str(base.get("sourceRef") or base.get("primaryEvidenceRef") or "")
    base_mode = str(base.get("sourceUseMode") or "factual_reference_only")
    base_text = str(base.get("text") or "").strip()
    lines: list[str] = []
    lines.append(f"# 实体主页写作任务：{name}")
    lines.append("")
    lines.append("## 角色与目标")
    lines.append("")
    lines.append(
        f"你是一位熟悉「{name}」的专业讲解员 / 资深导游。请用清晰、专业又有温度的叙事口吻，"
        "向第一次了解它的读者系统讲解这处实体：它是什么、有哪些看点、地理与历史背景、"
        "以及到访前该知道的稳定信息，让人读完就能对它形成完整、可信的认知。"
    )
    lines.append("")
    lines.append(
        "- 只讲实体本身可核验的稳定事实（地理 / 历史 / 景观 / 交通 / 季节等），"
        "用导游讲解的叙事方式娓娓道来；**不写个人游记、第一人称亲历或主观打卡体验**。"
    )
    lines.append("")
    lines.append("## 底稿与改写硬合同")
    lines.append("")
    if base_ref:
        lines.append(
            f"- **底稿来源**：`{base_ref}`（sourceUseMode=`{base_mode}`）作为本页表达骨架。"
            "在底稿基础上做**适度润色 + 事实校正 + PII/平台痕迹清理 + 人设/体裁适配**。"
        )
        lines.append(
            "- licensed_adaptation 与 factual_reference_only **同等**以底稿为骨架轻改："
            "保留底稿信息顺序与关键事实细节，多数语句在底稿原句上做最小改动"
            "（去语病/错字、PII·平台痕迹清理、按讲解口吻微调用词）；"
            "**不得脱离底稿从零另写**，也**不得整篇零加工照搬**。"
        )
    else:
        lines.append("- 当前无可用底稿（source 不足）；不要凭空编造，先回退到 source 修复。")
    lines.append(
        "- 结构尊重底稿真实内容：SOP 模板章节只是规范化参考（用于命名/归类对齐），"
        "仅『概况』必备，其余章节有真实内容才写、无内容直接省略、禁止硬凑，章节语义须正确。"
    )
    lines.append("")
    if base_text:
        lines.append("## 底稿材料（在此基础上轻改）")
        lines.append("")
        lines.append("```")
        lines.append(base_text)
        lines.append("```")
        lines.append("")
    lines.append("## 产出方式")
    lines.append("")
    lines.append(f"- 把创作的正文写回同目录 `page.md`（覆盖占位 `{PLACEHOLDER_MARKER}`），正文去空白 ≥ {MIN_PAGE_CHARS} 字。")
    lines.append("- 不要手写 `asset://` 图片指令、`_entity.json` 或 `manifest.json`；图片/资产/条件画像由 finalize 据 page.md 与已授权 homepage 图片自动补齐。")
    lines.append("- 正文必须能在底稿/来源中回溯事实，禁止机械模板句、工程化口径与重复凑字。")
    lines.append("- 完成后运行 `qwq-data data workflow run --resume` 进入 finalize/采纳门；失败按 validator 提示修改正文重跑。")
    return "\n".join(lines) + "\n"


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
    """下发人读 prompt.md + 占位 page.md：会话模型在 4.draft/page.md 创作正文。

    与文章一致：占位草稿用 PLACEHOLDER_MARKER 标记『尚未创作』，但绝不覆盖
    会话模型已写回的真实正文（非占位则保留）。
    """
    draft_dir = _entity_draft_dir(task_id, batch_id, domain, etype, name)
    draft_dir.mkdir(parents=True, exist_ok=True)
    (draft_dir / "prompt.md").write_text(_render_entity_page_prompt(payload), encoding="utf-8")
    draft_page = draft_dir / "page.md"
    if draft_page.is_file() and not is_placeholder(draft_page.read_text(encoding="utf-8")):
        return
    draft_page.write_text(
        f"{PLACEHOLDER_MARKER}\n\n# {name}\n\n（待会话模型按 prompt.md 与底稿创作实体主页正文，覆盖本占位）\n",
        encoding="utf-8",
    )


def prepare_entity_pages(task_id: str, batch_id: str, spec: dict[str, Any]) -> tuple[Path, list[str]]:
    """为 coverage 实体下发实体主页产出契约（inputs + prompt + 占位草稿 + assistant_tasks）。"""
    inputs_root = batch_root(task_id, batch_id) / "entities"
    inputs_root.mkdir(parents=True, exist_ok=True)
    data = task_data(task_id)
    refs: list[str] = []
    active_input_paths: set[Path] = set()
    for target in _coverage_targets(spec):
        domain, etype, name = target["domain"], target["etype"], target["name"]
        resolve_entity_object_dir(task_id, batch_id, name, etype_hint=f"{domain}/{etype}")
        ref = _safe_ref(domain, etype, name)
        sop_dir = data.sop_dir(domain, etype)
        base_draft = _entity_base_draft(task_id, batch_id, domain, etype, name)
        input_path = batch_entity_page_input_path(task_id, batch_id, domain, etype, name)
        active_input_paths.add(input_path)
        page_payload = {
            "name": name,
            "domain": domain,
            "etype": etype,
            "entityRef": entity_ref(domain, etype, name),
            "sopDir": str(sop_dir),
            "sopTemplate": str(sop_dir / "template.md"),
            "sopGuide": str(sop_dir / "guide.md"),
            "sopExample": str(sop_dir / "example.md"),
            "minChars": MIN_PAGE_CHARS,
            "baseDraft": base_draft,
            "regionMenu": _condition_menu(spec, "region", "region_catalog", "regions"),
            "seasonMenu": _condition_menu(spec, "season", "season_catalog", "seasons"),
            "editingInstruction": (
                "把 primaryEvidenceRef 作为底稿骨架与主题锚点，并综合 homepage_research 的其它来源。"
                "在底稿基础上做适度润色、事实校正、PII/平台痕迹清理与人设适配（licensed_adaptation 与 "
                "factual_reference_only 同等以底稿为骨架轻改、保留底稿信息顺序与关键事实细节、"
                "多数语句在底稿原句上做最小改动）；"
                "不得脱离底稿从零另写，也不得整篇零加工照搬。"
                "结构尊重底稿真实内容——SOP 模板里的章节只是『规范化参考』（用于章节命名与归类对齐），"
                "不是必须逐节填满的清单：仅『概况』必备，其余章节有真实内容才写、无内容直接省略、禁止硬凑，"
                "也允许按底稿增减或合并章节；章节语义须正确（如『历史沿革』必须是真实历史，否则省略）。"
            ),
            "imageRequirement": (
                "正文只写文字；不要手写 asset:// 图片指令或 manifest.json。"
                "finalize 会按 page.md 与同一主页研究链中权利合格的真实 CC 图片自动补齐配图与 manifest 资产闭环。"
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
            fact_count = len(_split_fact_sentences(text[:4000], entity_name=name))
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


def _pick_homepage_asset(task_id: str, batch_id: str, domain: str, etype: str, name: str) -> dict[str, Any]:
    from _common.source_unit import object_image_candidates

    obj = batch_entity_object_dir(task_id, batch_id, domain, etype, name)
    candidates = []
    for image in object_image_candidates(obj, task_id, batch_id):
        if not str(image.get("sourceRef") or "").endswith("/source.md"):
            continue
        if not str(image.get("sourceAssetRef") or ""):
            continue
        if not (str(image.get("authorizationProof") or "").strip() or str(image.get("termsUrl") or "").strip()):
            continue
        candidates.append(image)
    if not candidates:
        return {}
    candidates.sort(
        key=lambda item: (
            0 if str(item.get("researchLane") or "") in {"homepage", "homepage_image"} else 1,
            str(item.get("sourceKind") or ""),
            str(item.get("sourceAssetRef") or ""),
        )
    )
    return candidates[0]


def _copy_homepage_asset(task_id: str, batch_id: str, entity_dir: Path, name: str, image: dict[str, Any]) -> dict[str, Any]:
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
        role="cover",
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
        "caption": str(image.get("caption") or image.get("relevance") or "实体主页图片").strip(),
        "license": str(image.get("license") or "").strip(),
        "credit": str(image.get("creator") or "").strip(),
        "relevance": str(image.get("relevance") or "").strip(),
        "sourceRef": str(image.get("sourceRef") or "").strip(),
        "sourceAssetRef": str(image.get("sourceAssetRef") or "").strip(),
        "termsUrl": str(image.get("termsUrl") or "").strip(),
        "authorizationProof": str(image.get("authorizationProof") or "").strip(),
    }


def _homepage_gate_body(page_text: str) -> str:
    """剥掉 frontmatter / asset:// 图片指令 / 标题井号，得到用于贴合度+模板指纹门的正文。"""
    body = _strip_frontmatter(page_text)
    body = re.sub(r"\{asset://[^}]*\}", "", body)
    body = re.sub(r"^#{1,6}\s*", "", body, flags=re.MULTILINE)
    return body.strip()


def _inject_homepage_asset(page_text: str, asset: dict[str, Any]) -> str:
    """把唯一封面 asset:// 指令注入到会话模型正文（紧随首个 H1，幂等）。"""
    asset_id = str(asset.get("assetId") or "").strip()
    if not asset_id:
        return page_text
    if f"asset://{asset_id}" in page_text:
        return page_text
    caption = str(asset.get("caption") or "").strip() or "实景"
    directive = f"{{asset://{asset_id}|wrapRight|{caption}|width=45%}}"
    lines = page_text.splitlines()
    for index, line in enumerate(lines):
        if line.lstrip().startswith("# "):
            lines.insert(index + 1, "")
            lines.insert(index + 2, directive)
            return "\n".join(lines) + ("\n" if page_text.endswith("\n") else "")
    return f"{directive}\n\n{page_text}"


def materialize_entity_page(task_id: str, batch_id: str, domain: str, etype: str, name: str) -> list[str]:
    """把会话模型写回的 `4.draft/page.md` 正文终态化为实体主页三件套。

    不再脚本拼正文/切句/凑字：正文必须由会话模型在底稿基础上轻改创作（generator=agent）。
    finalize 只做：① 贴合度门 + 模板指纹门把关 Agent 正文；② 补齐唯一封面资产并注入
    asset:// 指令；③ 据正文事实确定性映射 summary；④ 写 generator=agent
    与真实 sha256 provenance（不再伪造）。会话模型未写回或仍是占位时返回等待项，由
    checkpoint 阻塞等待，绝不退回脚本拼接。
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
        return [f"{label}: 等待会话模型写回 4.draft/page.md（generator=agent 正文）"]
    draft_text = draft_page.read_text(encoding="utf-8")
    if is_placeholder(draft_text):
        return [f"{label}: 4.draft/page.md 仍是占位，等待会话模型按底稿创作正文"]

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
            source_use_mode=str(base.get("sourceUseMode") or "factual_reference_only"),
        )
    )
    if gate_issues:
        return gate_issues

    image = _pick_homepage_asset(task_id, batch_id, domain, etype, name)
    if not image:
        return [f"{label}: homepage lane 无可发布图片资产"]
    obj = batch_entity_object_dir(task_id, batch_id, domain, etype, name)
    obj.mkdir(parents=True, exist_ok=True)
    asset = _copy_homepage_asset(task_id, batch_id, obj, name, image)
    if not asset:
        return [f"{label}: homepage asset copy failed"]

    final_text = _inject_homepage_asset(draft_text, asset)
    (obj / "page.md").write_text(final_text, encoding="utf-8")

    facts = _split_fact_sentences(final_text, entity_name=name) or _split_fact_sentences(base_text, entity_name=name)
    # 底稿源与封面图源常常来自同一来源单元（如 wikipedia 既给正文又给配图），
    # 去重去空，避免 sourceRefs 把同一路径列两遍。
    source_refs = _dedupe_nonempty(
        [
            str(base.get("primaryEvidenceRef") or base.get("sourceRef") or ""),
            str(asset.get("sourceRef") or ""),
        ]
    )
    write_json(
        obj / "_entity.json",
        {
            "label": name,
            "domain": domain,
            "type": etype,
            "sourceTaskId": task_id,
            "entityRef": entity_ref(domain, etype, name),
            "summary": _homepage_summary(name, facts)[:180],
            "sourceRefs": source_refs,
        },
    )
    write_json(
        obj / "manifest.json",
        {
            "entityRef": entity_ref(domain, etype, name),
            "sourceTaskId": task_id,
            "sourceRefs": source_refs,
            "assets": [asset],
            "generator": "agent",
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
    """返回会话模型创作的 4.draft/page.md；不得用 finalize 终稿覆盖 Agent 正文。

    主页正文已由会话模型在 4.draft/page.md 创作，finalize 只把它注入封面后写到 page.md。
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
        "agentRunId": f"build-homepage:{task_id}:{batch_id}:{domain}/{etype}/{name}",
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
