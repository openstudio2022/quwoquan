"""实体主页 build 真实链路：prepare 下发产出契约 + validate 采纳门。

与现行「三层目录实体」模型一致（entities/{领域}/{类型}/{名称}/）：
- prepare：读 effective task spec 的 scope.coverageTargets，为每个实体写
  inputs/entity_page/<ref>.json（含 SOP 模板路径、字数下限、region/season 菜单、
  effective conditionAxes、产出目录），并写 assistant_tasks 清单，下发给 Agent。
- Agent：按 SOP（sop/主页/<领域>/<类型>/{guide,template,example}.md，全局单一真相源、
  不拷进任务）在产出目录物化 page.md(≥800字)+_entity.json(含 conditionProfile.evidenceRefs)+manifest.json。
- validate：逐 coverage 实体校验三件套/字数/必填字段/conditionProfile 结构、取值和事实出处是否
  落在 region_catalog/season_catalog 内并能回指 page/source，作为 promote 发布门之前的采纳门。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from _common.io import read_json, write_assistant_task, write_json
from _common.entity_page_quality import entity_page_quality_issues
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

MIN_PAGE_CHARS = 800
_REQUIRED_ENTITY_FIELDS = ("label", "domain", "type", "sourceTaskId")
_ASSET_REF_RE = re.compile(r"asset://([A-Za-z0-9_./\u4e00-\u9fff-]+)")
_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*$", re.MULTILINE)
# catalog 是 committed 真相源，按脚本相对路径定位（与 QWQ_DATA_ROOT 覆盖无关）
_CATALOG_DIR = Path(__file__).resolve().parents[2] / "templates" / "_registry" / "catalogs"
_INTRODUCTION_KIND_BY_TITLE = (
    ("timeline", ("时间线", "大事记", "节点")),
    ("history", ("历史", "沿革", "背景")),
    ("keyFacts", ("核心信息", "基础信息", "关键事实", "实用信息")),
    ("relatedObjects", ("相关地点", "相关对象", "周边", "关联")),
    ("gallery", ("图片", "图集", "相册")),
    ("map", ("位置", "交通", "地图")),
)


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


def _catalog_keys(filename: str, top_key: str) -> list[str]:
    path = _CATALOG_DIR / filename
    if not path.is_file():
        return []
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return list((doc.get(top_key) or {}).keys())


def region_keys() -> list[str]:
    return _catalog_keys("region_catalog.yaml", "regions")


def season_keys() -> list[str]:
    return _catalog_keys("season_catalog.yaml", "seasons")


def _entity_base_draft(task_id: str, batch_id: str, domain: str, etype: str, name: str) -> dict[str, Any]:
    """取该实体最完整的来源单元 source.md 作为主页底稿（百科优先，质量分→长度排序）。"""
    from _common.base_draft import base_draft_candidates, load_base_draft_text

    brief = {"entityRefs": [entity_ref(domain, etype, name)]}
    candidates = base_draft_candidates(task_id, batch_id, brief)
    if not candidates:
        return {}
    best = candidates[0]
    text = load_base_draft_text(task_id, batch_id, best["sourceRef"]).strip()
    if not text:
        return {}
    return {"sourceRef": best["sourceRef"], "text": text[:4000]}


def prepare_entity_pages(task_id: str, batch_id: str, spec: dict[str, Any]) -> tuple[Path, list[str]]:
    """为 coverage 实体下发实体主页产出契约（inputs + assistant_tasks）。"""
    inputs_root = batch_root(task_id, batch_id) / "entities"
    inputs_root.mkdir(parents=True, exist_ok=True)
    axes = spec.get("conditionAxes") or {}
    data = task_data(task_id)
    refs: list[str] = []
    for target in _coverage_targets(spec):
        domain, etype, name = target["domain"], target["etype"], target["name"]
        resolve_entity_object_dir(task_id, batch_id, name, etype_hint=f"{domain}/{etype}")
        ref = _safe_ref(domain, etype, name)
        sop_dir = data.sop_dir(domain, etype)
        base_draft = _entity_base_draft(task_id, batch_id, domain, etype, name)
        input_path = batch_entity_page_input_path(task_id, batch_id, domain, etype, name)
        write_json(input_path, {
            "schemaVersion": "quwoquan_data.stage_envelope",
            "taskId": task_id,
            "batchId": batch_id,
            "step": "entity_page",
            "ref": ref,
            "payload": {
                "name": name,
                "domain": domain,
                "etype": etype,
                "entityRef": entity_ref(domain, etype, name),
                "sopDir": str(sop_dir),
                "sopTemplate": str(sop_dir / "template.md"),
                "sopGuide": str(sop_dir / "guide.md"),
                "sopExample": str(sop_dir / "example.md"),
                "minChars": MIN_PAGE_CHARS,
                "conditionAxes": axes,
                "regionMenu": region_keys(),
                "seasonMenu": season_keys(),
                "baseDraft": base_draft,
                "editingInstruction": (
                    "以上方百科底稿为基础做适度加工（轻改）：参考百度百科写法、按真实信息归类章节，"
                    "只做去语病/纠错别字/理顺语句/补证据/去版权与平台痕迹；"
                    "结构尊重底稿真实内容——SOP 模板里的章节只是『规范化参考』（用于章节命名与归类对齐），"
                    "不是必须逐节填满的清单：仅『概况』必备，其余章节有真实内容才写、无内容直接省略、禁止硬凑，"
                    "也允许按底稿增减或合并章节；章节语义须正确（如『历史沿革』必须是真实历史，否则省略）；"
                    "不要从零总结，也不要硬套固定章节模板。"
                ),
                "imageRequirement": (
                    "实体主页须配 ≥1 张真实 CC 图片：在 page.md 用 asset:// 引用并在 manifest.json 登记，"
                    "图片来自 source_plan 的结构化 imageUrls（含 license/credit/relevance）。"
                ),
                "conditionEvidenceContract": {
                    "requiredWhen": "conditionProfile.regions 或 conditionProfile.seasons 非空",
                    "field": "conditionProfile.evidenceRefs",
                    "itemShape": {
                        "field": "regions|seasons",
                        "value": "与 conditionProfile 对应数组中的值一致",
                        "source": "page.md|source.md|manual_source_plan",
                        "pathOrNote": "path 或 note 至少一个非空",
                    },
                },
                "outputDir": str(batch_entity_object_dir(task_id, batch_id, domain, etype, name)),
                "sourceTaskId": task_id,
            },
        })
        _write_entity_quality_stage(task_id, batch_id, domain, etype, name, base_draft=base_draft)
        refs.append(ref)
    manifest_path = batch_assistant_task(task_id, batch_id, "build", "entity_page")
    results_dir = batch_root(task_id, batch_id) / "entities"
    write_assistant_task(manifest_path, step="entity_page", input_dir=inputs_root, result_dir=results_dir, refs=refs)
    return inputs_root, refs


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


def _page_asset_refs(page: Path) -> set[str]:
    if not page.is_file():
        return set()
    refs: set[str] = set()
    for ref in _ASSET_REF_RE.findall(page.read_text(encoding="utf-8")):
        refs.add(ref.split("/")[-1])
    return refs


def homepage_introduction_seed_from_triplet(entity_dir: Path) -> dict[str, Any]:
    """将实体主页三件套映射为 entity-service introduction seed。

    输入只读取 `page.md`、`_entity.json`、`manifest.json`。正文由 Agent 产出的
    page.md 承担，脚本只做结构化映射；后续 importer 可直接消费该 seed。
    """
    page_path = entity_dir / "page.md"
    entity_path = entity_dir / "_entity.json"
    manifest_path = entity_dir / "manifest.json"
    if not page_path.is_file() or not entity_path.is_file() or not manifest_path.is_file():
        raise FileNotFoundError(f"missing homepage triplet under {entity_dir}")
    page_text = page_path.read_text(encoding="utf-8")
    entity_payload = read_json(entity_path)
    manifest_payload = read_json(manifest_path)
    label = str(entity_payload.get("label") or entity_payload.get("name") or entity_dir.name).strip()
    domain = str(entity_payload.get("domain") or "").strip()
    etype = str(entity_payload.get("type") or entity_payload.get("etype") or "").strip()
    homepage_id = str(
        entity_payload.get("homepageId")
        or manifest_payload.get("homepageId")
        or entity_payload.get("id")
        or _safe_ref(domain or "entity", etype or "object", label or entity_dir.name),
    ).strip()
    sections = _introduction_sections_from_markdown(page_text, manifest_payload)
    source_refs = _introduction_source_refs(entity_payload, manifest_payload, entity_dir)
    return {
        "homepageId": homepage_id,
        "displayName": label,
        "homepageType": etype,
        "coverUrl": _manifest_cover_url(manifest_payload),
        "summary": _introduction_summary(page_text, label),
        "sections": sections,
        "relatedObjects": _introduction_related_objects(entity_payload, manifest_payload),
        "sourceRefs": source_refs,
        "updatedAt": str(manifest_payload.get("updatedAt") or manifest_payload.get("generatedAt") or ""),
        "seedSource": {
            "pageMd": str(page_path),
            "entityJson": str(entity_path),
            "manifestJson": str(manifest_path),
        },
    }


def _introduction_sections_from_markdown(page_text: str, manifest_payload: dict[str, Any]) -> list[dict[str, Any]]:
    chunks: list[tuple[str, str]] = []
    matches = list(_HEADING_RE.finditer(page_text))
    if not matches:
        body = page_text.strip()
        if body:
            chunks.append(("概况", body))
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(page_text)
        title = match.group(2).strip()
        body = page_text[start:end].strip()
        if title and body:
            chunks.append((title, body))
    if not chunks and page_text.strip():
        chunks.append(("概况", page_text.strip()))
    assets = _introduction_assets(manifest_payload)
    out: list[dict[str, Any]] = []
    for index, (title, body) in enumerate(chunks):
        kind = _section_kind_for_title(title, index)
        out.append(
            {
                "kind": kind,
                "title": title,
                "bodyMarkdown": body,
                "assets": assets if index == 0 else [],
                "timelineItems": _timeline_items_from_body(body) if kind == "timeline" else [],
            }
        )
    return out


def _section_kind_for_title(title: str, index: int) -> str:
    if index == 0:
        return "overview"
    for kind, tokens in _INTRODUCTION_KIND_BY_TITLE:
        if any(token in title for token in tokens):
            return kind
    return "overview"


def _timeline_items_from_body(body: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for raw in body.splitlines():
        line = raw.strip().lstrip("-*").strip()
        if not line:
            continue
        if "：" in line:
            date_label, text = line.split("：", 1)
        elif ":" in line:
            date_label, text = line.split(":", 1)
        else:
            continue
        items.append({"dateLabel": date_label.strip(), "text": text.strip()})
    return items


def _introduction_assets(manifest_payload: dict[str, Any]) -> list[dict[str, str]]:
    assets: list[dict[str, str]] = []
    for raw in manifest_payload.get("assets") or []:
        if not isinstance(raw, dict):
            continue
        asset_id = str(raw.get("assetId") or raw.get("id") or "").strip()
        url = str(raw.get("url") or raw.get("imageUrl") or raw.get("sourceUrl") or "").strip()
        file_name = str(raw.get("fileName") or "").strip()
        if not url and file_name:
            url = f"asset://{asset_id or file_name}"
        if not asset_id or not url:
            continue
        assets.append(
            {
                "assetId": asset_id,
                "url": url,
                "caption": str(raw.get("caption") or raw.get("title") or "").strip(),
                "sourceRef": str(raw.get("sourceRef") or raw.get("license") or "").strip(),
            }
        )
    return assets


def _manifest_cover_url(manifest_payload: dict[str, Any]) -> str:
    cover = str(manifest_payload.get("coverUrl") or "").strip()
    if cover:
        return cover
    assets = _introduction_assets(manifest_payload)
    return assets[0]["url"] if assets else ""


def _introduction_summary(page_text: str, fallback: str) -> str:
    lines = [
        line.strip()
        for line in page_text.splitlines()
        if line.strip() and not line.strip().startswith("#") and not line.strip().startswith("asset://")
    ]
    if not lines:
        return f"{fallback} 的完整介绍正在整理中。"
    summary = lines[0]
    return summary[:180]


def _introduction_related_objects(entity_payload: dict[str, Any], manifest_payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_items = entity_payload.get("relatedObjects") or manifest_payload.get("relatedObjects") or []
    return [item for item in raw_items if isinstance(item, dict)]


def _introduction_source_refs(entity_payload: dict[str, Any], manifest_payload: dict[str, Any], entity_dir: Path) -> list[str]:
    refs: list[str] = []
    for raw in entity_payload.get("sourceRefs") or manifest_payload.get("sourceRefs") or []:
        value = str(raw).strip()
        if value:
            refs.append(value)
    for name in ("page.md", "_entity.json", "manifest.json"):
        refs.append(str(entity_dir / name))
    return sorted(set(refs))


def _asset_closure_issues(entity_dir: Path, manifest_payload: dict[str, Any], label: str) -> list[str]:
    """实体主页 asset:// 引用闭环：page.md → manifest.assets → assets/<fileName>。"""
    refs = _page_asset_refs(entity_dir / "page.md")
    assets = manifest_payload.get("assets") or []
    if not refs and not assets:
        # 主页强制配图：实体主页须含 ≥1 真实图片资产（page.md asset:// + manifest 登记）。
        return [f"{label}: 实体主页须配 ≥1 真实图片（page.md 用 asset:// 引用并在 manifest 登记）"]
    if not isinstance(assets, list):
        return [f"{label}: manifest.assets 须为数组"]
    id_to_file: dict[str, str] = {}
    file_names: set[str] = set()
    for raw in assets:
        if not isinstance(raw, dict):
            continue
        asset_id = str(raw.get("assetId") or raw.get("id") or "").strip()
        file_name = str(raw.get("fileName") or "").strip()
        if asset_id:
            id_to_file[asset_id] = file_name
        if file_name:
            file_names.add(file_name)
    issues: list[str] = []
    known_ids = set(id_to_file)
    for ref in sorted(refs):
        if ref not in known_ids and ref not in file_names:
            issues.append(f"{label}: page.md asset ref not in manifest: {ref}")
    assets_dir = entity_dir / "assets"
    for asset_id, file_name in sorted(id_to_file.items()):
        if not file_name:
            issues.append(f"{label}: asset {asset_id} missing fileName in manifest")
            continue
        if not (assets_dir / file_name).is_file():
            issues.append(f"{label}: asset file missing on disk: assets/{file_name} (assetId={asset_id})")
    return issues


def _entity_draft_path(task_id: str, batch_id: str, domain: str, etype: str, name: str) -> Path:
    return batch_entity_stage_dir(task_id, batch_id, domain, etype, name, STAGE_DRAFT) / "page.md"


def _write_entity_draft(task_id: str, batch_id: str, domain: str, etype: str, name: str) -> Path:
    obj = batch_entity_object_dir(task_id, batch_id, domain, etype, name)
    final_page = obj / "page.md"
    draft_page = _entity_draft_path(task_id, batch_id, domain, etype, name)
    if final_page.is_file():
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


def _condition_profile_source_paths(cprofile: dict[str, Any], task_id: str, batch_id: str) -> list[str]:
    refs: list[str] = []
    for row in (cprofile.get("evidenceRefs") or []):
        if not isinstance(row, dict):
            continue
        path = str(row.get("path") or "").strip()
        if not path:
            continue
        if path == "page.md":
            refs.append("page.md")
        else:
            refs.append(path)
    ordered: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        normalized = ref
        if ref not in {"page.md", "source.md"} and not ref.startswith("entities/"):
            candidate = batch_root(task_id, batch_id) / ref
            if candidate.is_file():
                normalized = relative_batch_ref(candidate, task_id, batch_id)
        if normalized not in seen:
            seen.add(normalized)
            ordered.append(normalized)
    return ordered


def _build_entity_provenance(
    *,
    task_id: str,
    batch_id: str,
    domain: str,
    etype: str,
    name: str,
    source_paths: list[str],
    review_payload: dict[str, Any],
    entity_payload: dict[str, Any],
) -> dict[str, Any]:
    rel_page = f"entities/{domain}/{etype}/{name}/page.md"
    rel_input = f"entities/{domain}/{etype}/{name}/3.compose/entity_page_input.json"
    cited_paths = _condition_profile_source_paths(entity_payload.get("conditionProfile") or {}, task_id, batch_id)
    if "page.md" in cited_paths:
        cited_paths = [rel_page if item == "page.md" else item for item in cited_paths]
    compose_payload = {
        "sourcePaths": source_paths,
        "sourceUrls": [],
        "citedSourceRefs": cited_paths or source_paths,
        "generator": "agent",
        "generatorModel": "homepage-agent",
        "articleMarkdownDigest": None,
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
        "promptSha256": "sha256:entity-homepage-input",
        "writingPackSha256": "sha256:entity-homepage-compose",
        "sourceBundleSha256": "sha256:entity-homepage-sources",
        "draftSha256": "sha256:entity-homepage-draft",
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
    provenance["agentInput"]["prompt"] = "4.draft/page.md"
    provenance["final"]["articleDigest"] = None
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
    entity_payload: dict[str, Any],
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
            entity_payload=entity_payload,
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


def validate_entity_page(
    task_id: str,
    batch_id: str,
    domain: str,
    etype: str,
    name: str,
    *,
    region_set: set[str],
    season_set: set[str],
) -> list[str]:
    """校验单个实体主页三件套/字数/字段/conditionProfile，返回阻断问题列表。"""
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
    if not manifest.is_file():
        issues.append(f"{label}: manifest.json 缺失")
        manifest_payload: dict[str, Any] = {}
    else:
        try:
            manifest_payload = read_json(manifest)
        except Exception as exc:
            issues.append(f"{label}: manifest.json 不可解析: {exc}")
            manifest_payload = {}
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

    cprofile = payload.get("conditionProfile")
    if cprofile is not None:
        if not isinstance(cprofile, dict):
            issues.append(f"{label}: conditionProfile 须为对象")
        else:
            regions = [str(r) for r in (cprofile.get("regions") or [])]
            seasons = [str(s) for s in (cprofile.get("seasons") or [])]
            if not regions and not seasons:
                issues.append(f"{label}: conditionProfile 须含 regions 或 seasons")
            bad_regions = [r for r in regions if r not in region_set]
            bad_seasons = [s for s in seasons if s not in season_set]
            if bad_regions:
                issues.append(f"{label}: conditionProfile.regions 越界 {bad_regions}（须 ∈ region_catalog）")
            if bad_seasons:
                issues.append(f"{label}: conditionProfile.seasons 越界 {bad_seasons}（须 ∈ season_catalog）")
            issues.extend(_condition_profile_evidence_issues(cprofile, label))
    issues.extend(_asset_closure_issues(obj, manifest_payload, label))
    source_paths = _entity_source_paths(task_id, batch_id, domain, etype, name)
    cprofile = payload.get("conditionProfile") if isinstance(payload, dict) else {}
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
        entity_payload=payload,
    )
    return issues


def _condition_profile_evidence_issues(cprofile: dict[str, Any], label: str) -> list[str]:
    """regions/seasons 是可发布事实，必须逐项回指来源或主页正文。"""
    issues: list[str] = []
    evidence_refs = cprofile.get("evidenceRefs")
    if not isinstance(evidence_refs, list) or not evidence_refs:
        if cprofile.get("regions") or cprofile.get("seasons"):
            issues.append(f"{label}: conditionProfile.regions/seasons 须含 evidenceRefs 事实出处")
        return issues

    covered: set[tuple[str, str]] = set()
    for idx, ref in enumerate(evidence_refs):
        if not isinstance(ref, dict):
            issues.append(f"{label}: conditionProfile.evidenceRefs[{idx}] 须为对象")
            continue
        field = str(ref.get("field") or "")
        value = str(ref.get("value") or "")
        source = str(ref.get("source") or "")
        path = str(ref.get("path") or "")
        note = str(ref.get("note") or "")
        if field not in {"regions", "seasons"}:
            issues.append(f"{label}: conditionProfile.evidenceRefs[{idx}].field 须为 regions 或 seasons")
            continue
        if not value:
            issues.append(f"{label}: conditionProfile.evidenceRefs[{idx}].value 缺失")
            continue
        if source not in {"page.md", "source.md", "manual_source_plan"}:
            issues.append(f"{label}: conditionProfile.evidenceRefs[{idx}].source 须为 page.md/source.md/manual_source_plan")
        if not path and not note:
            issues.append(f"{label}: conditionProfile.evidenceRefs[{idx}] 须含 path 或 note")
        covered.add((field, value))

    for field in ("regions", "seasons"):
        for value in [str(v) for v in (cprofile.get(field) or [])]:
            if (field, value) not in covered:
                issues.append(f"{label}: conditionProfile.{field}={value} 缺少对应 evidenceRefs")
    return issues


def validate_entity_pages(task_id: str, batch_id: str, spec: dict[str, Any]) -> list[str]:
    """校验全部 coverage 实体主页，返回阻断问题列表（空=采纳通过）。"""
    region_set = set(region_keys())
    season_set = set(season_keys())
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
                region_set=region_set,
                season_set=season_set,
            )
        )
    return issues
