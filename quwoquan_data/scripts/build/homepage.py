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

import shutil
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
_HOMEPAGE_PRIMARY_KIND_BONUS = (
    ("维基百科", 120),
    ("wikipedia", 120),
    ("百度百科", 110),
    ("搜狗百科", 105),
    ("字节百科", 100),
    ("百科", 95),
    ("景区官网", 90),
    ("官网", 85),
    ("官方", 85),
)
_HOMEPAGE_SUPPORT_ONLY_MARKERS = ("政府", "文旅", "政务", "gov.cn")
_HOMEPAGE_GUIDE_PENALTY = ("攻略", "游记", "评论", "点评", "小红书", "图虫", "摄影")
_HOMEPAGE_ALLOWED_LANES = ("homepage", "legacy", "")
_HOMEPAGE_FACT_NOISE_MARKERS = (
    "欢迎访问",
    "首页",
    "English",
    "中文",
    "官方网站",
    "网站首页",
    "Toggle navigation",
    "查看更多",
    "今日实时游客量",
    "旅游咨询热线",
    "为您提供景区美食大全",
    "请提前查看",
    "打开微信扫一扫",
    "扫码",
    "关注",
    "浏览全部图片",
    "查看地图",
    "更多精彩视频",
    "友情链接",
    "外部链接",
    "页面存档",
    "互联网档案馆",
    "暂停服务",
    "暂无",
)
_HOMEPAGE_HISTORY_MARKERS = (
    "历史",
    "沿革",
    "始建",
    "建成",
    "设立",
    "成立",
    "发现",
    "修建",
    "开凿",
    "遗址",
    "朝",
    "世纪",
)
_HOMEPAGE_FACT_SIGNAL_MARKERS = (
    "位于",
    "位於",
    "地处",
    "坐落",
    "分布",
    "距",
    "距离",
    "面积",
    "海拔",
    "最高点",
    "全长",
    "总长",
    "长度",
    "高度",
    "宽",
    "建于",
    "始建",
    "建成",
    "修建",
    "开凿",
    "设立",
    "成立",
    "开放",
    "開放",
    "保护",
    "遗产",
    "文物",
    "遗址",
    "博物馆",
    "景点",
    "景點",
    "景区",
    "風景区",
    "风景区",
    "風景名勝区",
    "风景名胜区",
    "風景",
    "公园",
    "古镇",
    "长城",
    "大坝",
    "水电站",
    "工程",
    "机组",
    "装机",
    "发电量",
    "AAAAA",
    "5A",
    "国家",
    "世界",
    "中国",
    "著名",
    "最早",
    "最大",
    "气候",
    "天气",
    "交通",
    "接驳",
    "步道",
    "预约",
    "票务",
    "组成",
    "包括",
    "得名",
    "扩建",
    "擴建",
    "授予",
)
_HOMEPAGE_SPATIAL_PRACTICAL_MARKERS = (
    "雪山",
    "湖泊",
    "水库",
    "水域",
    "沙漠",
    "草甸",
    "峡谷",
    "高原",
    "山地",
    "森林",
    "湿地",
    "水利",
    "交通",
    "接驳",
    "步道",
    "开放",
    "预约",
    "票务",
    "风景区",
    "風景名勝区",
    "风景名胜区",
    "景区",
)
_HOMEPAGE_LOCATION_RE = re.compile(r"(位于|位於).{2,40}[省市县縣区區镇鎮乡鄉村]")
_HOMEPAGE_FACT_UNIT_RE = re.compile(
    r"(A{1,5}级|"
    r"(\d|[一二三四五六七八九十百千万亿])"
    r".{0,8}(年|月|日|米|公里|千米|公顷|平方公里|亩|万千瓦|千瓦|MW|亿千瓦时|吨|级|A))"
)
_HOMEPAGE_TERMINAL_SPLIT_RE = re.compile(r"[^。！？；;]+[。！？；;]?")
_HOMEPAGE_SOFT_SPLIT_RE = re.compile(r"[^，,、：:]+[，,、：:]?")
_HOMEPAGE_ENTITY_SPLIT_RE = re.compile(r"[—－\-·•、/|()（）]+")
_HOMEPAGE_GENERIC_ENTITY_TOKENS = {
    "景区",
    "旅游区",
    "旅游景区",
    "风景区",
    "风景名胜区",
    "文化旅游区",
    "公园",
}
_HOMEPAGE_ALIAS_SUFFIXES = tuple(sorted(_HOMEPAGE_GENERIC_ENTITY_TOKENS, key=len, reverse=True))


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


def _homepage_source_text(meta: dict[str, Any]) -> str:
    fields = (
        "sourceKind",
        "platform",
        "category",
        "source_id",
        "discoveryProvider",
        "sourceRole",
        "researchLane",
        "url",
    )
    return " ".join(str(meta.get(field) or "") for field in fields).strip()


def _homepage_source_priority(meta: dict[str, Any]) -> int:
    lane = str(meta.get("researchLane") or "")
    if lane not in _HOMEPAGE_ALLOWED_LANES:
        return -1000
    source_text = _homepage_source_text(meta)
    lowered = source_text.casefold()
    if any(marker.casefold() in lowered for marker in _HOMEPAGE_GUIDE_PENALTY):
        return -1000
    if any(marker.casefold() in lowered for marker in _HOMEPAGE_SUPPORT_ONLY_MARKERS):
        return 0
    priority = 0
    for marker, score in _HOMEPAGE_PRIMARY_KIND_BONUS:
        if marker.casefold() in lowered:
            priority = max(priority, score)
    category = str(meta.get("category") or "").casefold()
    if category in {"encyclopedia", "official_site"}:
        priority = max(priority, 85)
    return priority


def _homepage_base_source_issue_text(meta: dict[str, Any]) -> tuple[str, bool, bool]:
    source_kind = str(meta.get("sourceKind") or meta.get("platform") or meta.get("category") or "").strip()
    source_text = _homepage_source_text(meta)
    lowered = source_text.casefold()
    is_primary = _homepage_source_priority(meta) > 0
    is_author_experience = any(marker.casefold() in lowered for marker in _HOMEPAGE_GUIDE_PENALTY)
    return source_kind, is_primary, is_author_experience


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


def homepage_base_draft_readiness(meta: dict[str, Any], text: str, *, entity_name: str) -> dict[str, Any]:
    """Return the shared admission verdict for entity homepage base drafts.

    This is the exact contract used before asking the Agent to write an entity
    homepage. Download gates call the same function so a retained homepage
    source cannot pass upstream and then fail `build_prepare` for missing
    usable facts.
    """
    priority = _homepage_source_priority(meta)
    if priority <= 0:
        return {
            "ready": False,
            "priority": priority,
            "factCount": 0,
            "issue": "not encyclopedia/wiki/official homepage source",
        }
    source_text = str(text or "").strip()
    if not source_text:
        return {
            "ready": False,
            "priority": priority,
            "factCount": 0,
            "issue": "empty source text",
        }
    fact_count = len(_split_fact_sentences(source_text[:4000], entity_name=entity_name))
    return {
        "ready": fact_count >= 4,
        "priority": priority,
        "factCount": fact_count,
        "issue": "" if fact_count >= 4 else f"usable facts {fact_count}<4",
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


def prepare_entity_pages(task_id: str, batch_id: str, spec: dict[str, Any]) -> tuple[Path, list[str]]:
    """为 coverage 实体下发实体主页产出契约（inputs + assistant_tasks）。"""
    inputs_root = batch_root(task_id, batch_id) / "entities"
    inputs_root.mkdir(parents=True, exist_ok=True)
    axes = spec.get("conditionAxes") or {}
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
                    "把 primaryEvidenceRef 作为事实与主题锚点，并综合 homepage_research 的其它来源。"
                    "若 sourceUseMode=factual_reference_only，只抽取可核验事实并独立组织、独立表达，"
                    "禁止沿用原文句式、段落顺序或章节结构；只有 licensed_adaptation 才能在许可范围内改编。"
                    "结构尊重底稿真实内容——SOP 模板里的章节只是『规范化参考』（用于章节命名与归类对齐），"
                    "不是必须逐节填满的清单：仅『概况』必备，其余章节有真实内容才写、无内容直接省略、禁止硬凑，"
                    "也允许按底稿增减或合并章节；章节语义须正确（如『历史沿革』必须是真实历史，否则省略）；"
                    "按章节混排来自同一主页研究链且权利合格的图片，不得借用文章或图片作品的来源计划。"
                ),
                "imageRequirement": (
                    "实体主页须配 ≥1 张真实 CC 图片：在 page.md 用 asset:// 引用并在 manifest.json 登记，"
                    "图片来自 source_plan 的结构化 imageUrls（含 license/credit/relevance），"
                    "manifest.assets[] 必须同时写 sourceRef=来源单元 source.md、sourceAssetRef=来源单元 assets/原图、"
                    "termsUrl 或 authorizationProof，禁止把 sourceRef 写成图片文件路径。"
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


def _page_asset_refs(page: Path) -> set[str]:
    if not page.is_file():
        return set()
    refs: set[str] = set()
    for ref in _ASSET_REF_RE.findall(page.read_text(encoding="utf-8")):
        refs.add(ref.split("/")[-1])
    return refs


def _strip_frontmatter(text: str) -> str:
    raw = str(text or "").strip()
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) == 3:
            raw = parts[2].strip()
    raw = re.sub(r"^=+\s*(.*?)\s*=+$", r"## \1", raw, flags=re.MULTILINE)
    raw = re.sub(r"^#{1,6}\s*", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"\[[^\]]+\]\([^)]+\)", "", raw)
    raw = re.sub(r"https?://\S+", "", raw)
    raw = re.sub(r"\s+", " ", raw)
    return raw.strip()


def _split_fact_sentences(text: str, *, entity_name: str) -> list[str]:
    if _homepage_text_looks_structured_payload(text):
        return []
    body = _strip_frontmatter(text)
    out: list[str] = []
    seen: set[str] = set()
    entity_tokens = _homepage_entity_tokens(entity_name)
    for chunk in _homepage_fact_candidates(body):
        sentence = re.sub(r"\s+", "", str(chunk or "")).strip()
        sentence = sentence.strip(" \t\r\n，,、：:；;>")
        if len(sentence) < 8:
            continue
        if any(marker in sentence for marker in _HOMEPAGE_FACT_NOISE_MARKERS):
            continue
        if not _homepage_sentence_has_fact_signal(sentence, entity_tokens=entity_tokens):
            continue
        sentence = sentence[:120]
        key = sentence[:48]
        if key in seen:
            continue
        seen.add(key)
        out.append(sentence)
        if len(out) >= 18:
            break
    return out


def _homepage_text_looks_structured_payload(text: str) -> bool:
    raw = str(text or "").lstrip()
    if not raw:
        return False
    head = raw[:1200]
    if head.startswith(("{", "[")):
        api_markers = (
            '"code"',
            '"msg"',
            '"data"',
            '"newsId"',
            '"newsName"',
            '"sightId"',
            '"sightName"',
            '"newsContext"',
            '"sightDescription"',
        )
        if sum(1 for marker in api_markers if marker in head) >= 3:
            return True
    if head.count('":"') >= 8 and head.count('","') >= 6:
        return True
    return False


def _homepage_fact_candidates(body: str) -> list[str]:
    """Return sentence/clause candidates while preserving local context.

    Official scenic-site pages often pack several facts into a single hero block
    with navigation copy before it. We therefore keep normal full sentences when
    they are usable, but also split long chunks on soft Chinese punctuation and
    emit small windows so aliases such as "云龙湖，位于徐州南部" retain enough
    context to pass the homepage fact gate.
    """
    chunks = _HOMEPAGE_TERMINAL_SPLIT_RE.findall(body) or [body]
    candidates: list[str] = []
    for chunk in chunks:
        chunk = str(chunk or "").strip()
        if not chunk:
            continue
        candidates.append(chunk)
        compact = re.sub(r"\s+", "", chunk)
        if len(compact) < 40 and not any(marker in compact for marker in _HOMEPAGE_FACT_NOISE_MARKERS):
            continue
        parts = [part.strip() for part in _HOMEPAGE_SOFT_SPLIT_RE.findall(chunk) if part.strip()]
        for part in parts:
            candidates.append(part)
        for width in (2, 3):
            if len(parts) < width:
                continue
            for idx in range(0, len(parts) - width + 1):
                candidates.append("".join(parts[idx:idx + width]))
    return candidates


def _homepage_entity_tokens(entity_name: str) -> set[str]:
    tokens = {str(entity_name or "").strip()}
    for part in _HOMEPAGE_ENTITY_SPLIT_RE.split(str(entity_name or "")):
        cleaned = part.strip()
        if len(cleaned) >= 2 and cleaned not in _HOMEPAGE_GENERIC_ENTITY_TOKENS:
            tokens.add(cleaned)
            alias = cleaned
            changed = True
            while changed:
                changed = False
                for suffix in _HOMEPAGE_ALIAS_SUFFIXES:
                    if alias.endswith(suffix) and len(alias) > len(suffix) + 1:
                        alias = alias[: -len(suffix)].strip()
                        if len(alias) >= 2:
                            tokens.add(alias)
                        changed = True
                        break
    return {token for token in tokens if token}


def _homepage_sentence_has_fact_signal(sentence: str, *, entity_tokens: set[str]) -> bool:
    has_entity_token = any(token in sentence for token in entity_tokens)
    has_signal = any(marker in sentence for marker in _HOMEPAGE_FACT_SIGNAL_MARKERS)
    has_unit_fact = bool(_HOMEPAGE_FACT_UNIT_RE.search(sentence))
    if has_entity_token and (has_signal or has_unit_fact or len(sentence) >= 20):
        return True
    if has_signal and has_unit_fact:
        return True
    if has_signal and any(token in sentence for token in ("长城", "大坝", "水电站", "遗产", "文物", "遗址", "博物馆")):
        return True
    if has_signal and any(token in sentence for token in _HOMEPAGE_SPATIAL_PRACTICAL_MARKERS) and len(sentence) >= 18:
        return True
    if has_unit_fact and any(token in sentence for token in _HOMEPAGE_SPATIAL_PRACTICAL_MARKERS) and len(sentence) >= 12:
        return True
    if has_signal and _HOMEPAGE_LOCATION_RE.search(sentence) and len(sentence) >= 10:
        return True
    if has_signal and any(token in sentence for token in ("景点", "景點", "古寺", "寺", "桥", "橋")) and len(sentence) >= 12:
        return True
    return False


def _homepage_summary(name: str, facts: list[str]) -> str:
    for fact in facts:
        if name in fact and ("位于" in fact or "遗产" in fact or "博物馆" in fact or "景区" in fact):
            return fact.rstrip("。") + "。"
    return f"{name} 是本任务覆盖的实体主页对象，本页基于百科、官方或文旅来源整理基础事实。"


def _infer_condition_profile(name: str, facts: list[str]) -> dict[str, Any]:
    text = " ".join(facts)
    regions: list[str] = []
    seasons: list[str] = []
    if any(token in text for token in ("高原", "海拔", "藏", "雪山", "冰川")):
        regions.append("高原")
    if any(token in text for token in ("雪山", "冰川")):
        regions.append("雪山")
    if any(token in text for token in ("森林", "山地", "峡谷", "沟谷", "瀑布")):
        regions.append("山地森林")
    if any(token in text for token in ("成都平原", "城市", "市区", "博物馆", "都江堰", "三星堆")):
        regions.append("平原都市")
    if not regions:
        regions.append("山地森林")
    if any(token in text for token in ("春", "花", "灌溉")):
        seasons.append("春")
    if any(token in text for token in ("夏", "避暑", "雨季")):
        seasons.append("夏")
    if any(token in text for token in ("秋", "彩林", "红叶")):
        seasons.append("秋")
    if any(token in text for token in ("冬", "冰雪", "结冰")):
        seasons.append("冬")
    if not seasons:
        seasons.extend(["春", "秋"])
    regions = list(dict.fromkeys(regions))[:3]
    seasons = list(dict.fromkeys(seasons))[:4]
    evidence_refs = [
        {
            "field": "regions",
            "value": value,
            "source": "page.md",
            "path": "page.md",
            "note": f"{name} 主页正文概况与空间特征归纳",
        }
        for value in regions
    ] + [
        {
            "field": "seasons",
            "value": value,
            "source": "page.md",
            "path": "page.md",
            "note": f"{name} 主页正文季节与游览信息归纳",
        }
        for value in seasons
    ]
    return {"regions": regions, "seasons": seasons, "evidenceRefs": evidence_refs}


def _pick_homepage_asset(task_id: str, batch_id: str, domain: str, etype: str, name: str) -> dict[str, Any]:
    from _common.source_unit import object_image_candidates

    obj = batch_entity_object_dir(task_id, batch_id, domain, etype, name)
    candidates = []
    for image in object_image_candidates(obj, task_id, batch_id):
        lane = str(image.get("researchLane") or "")
        if lane not in {"homepage", "homepage_image"}:
            continue
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
            0 if str(item.get("researchLane") or "") == "homepage" else 1,
            str(item.get("sourceKind") or ""),
            str(item.get("sourceAssetRef") or ""),
        )
    )
    return candidates[0]


def _copy_homepage_asset(entity_dir: Path, image: dict[str, Any]) -> dict[str, Any]:
    src = Path(str(image.get("path") or ""))
    if not src.is_file():
        return {}
    assets_dir = entity_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    file_name = src.name
    shutil.copyfile(src, assets_dir / file_name)
    asset_id = file_name
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


def _render_homepage_markdown(name: str, facts: list[str], asset_id: str, caption: str) -> str:
    deduped_facts: list[str] = []
    seen_facts: set[str] = set()
    for fact in facts or [f"{name} 的基础事实来自已下载的百科、官方或文旅来源。"]:
        normalized = " ".join(str(fact).strip().split())
        if not normalized or normalized in seen_facts:
            continue
        seen_facts.add(normalized)
        deduped_facts.append(normalized)
    facts = deduped_facts or [f"{name} 的基础事实来自已下载的百科、官方或文旅来源。"]
    summary = _homepage_summary(name, facts)
    overview = "。".join(f.rstrip("。") for f in facts[:4]).rstrip("。") + "。"
    spatial = "。".join(f.rstrip("。") for f in facts[4:8]).rstrip("。") + "。"
    history_facts = [f for f in facts if any(token in f for token in _HOMEPAGE_HISTORY_MARKERS)]
    has_history = bool(history_facts)
    history_title = "历史沿革" if has_history else "背景信息"
    history = (
        "。".join(f.rstrip("。") for f in history_facts[:5]).rstrip("。") + "。"
        if has_history
        else (
            f"{name} 的背景信息来自已下载的百科、官方或文旅资料；"
            "当前来源未提供足够清晰的年代沿革，因此本页不强行编写历史章节。"
        )
    )
    practical = (
        f"浏览 {name} 时，建议先确认官方公告中的开放时间、预约方式、票务规则和交通接驳。"
        "如果正文涉及季节、海拔、水文或馆藏等条件信息，应以现场公告和当日天气为准；"
        "本页只保留实体介绍所需的稳定事实，不写个人游记式体验。"
    )
    culture = (
        "。".join(f.rstrip("。") for f in facts[12:16]).rstrip("。") + "。"
        if len(facts) >= 13
        else (
            f"识别 {name} 时，可以从实体类型、代表性景观、空间位置和官方名称入手；"
            "这些内容共同构成用户搜索、阅读和后续决策的基础语义。"
        )
    )
    page = (
        f"# {name}\n\n"
        f"> {summary}\n\n"
        f"{{asset://{asset_id}|wrapRight|{caption or name + '实景'}|width=45%}}\n\n"
        "## 概况\n\n"
        f"{overview}\n\n"
        "## 空间与看点\n\n"
        f"{spatial}\n\n"
        f"## {history_title}\n\n"
        f"{history}\n\n"
        "## 实用信息\n\n"
        f"{practical}\n\n"
        "## 文化与识别\n\n"
        f"{culture}\n"
    )
    supplement_templates = [
        (
            f"{name} 的主页只整理实体本身的稳定信息，重点放在位置、类型、景观或文化识别上，"
            "不把一次游玩感受写成对象属性。"
        ),
        (
            "读者可以把本页当作认识对象的入口，再进入攻略文章查看路线、季节、交通和取舍建议。"
        ),
        (
            "涉及开放、票务、预约、交通接驳和安全提示的内容，后续应继续以官方公告和现场规则校验。"
        ),
        (
            "图片只用于辅助识别实体外观或代表性场景，不能替代正文事实，也不能和来源证据脱节。"
        ),
        (
            "当不同来源对细节存在差异时，本页优先保留多来源可互相印证的稳定事实。"
        ),
        (
            "百科、官方和文旅来源提供实体骨架，社区攻略和游记只作为辅助背景，不进入主页底稿主线。"
        ),
        (
            "条件画像只描述地域、季节、海拔、水文、保护等级等可回溯信息，不推断未经证实的体验结论。"
        ),
        (
            "延展阅读可以围绕规划、体验、交通、季节和摄影角度展开，但不会反向改写实体主页。"
        ),
    ]
    supplement_index = 0
    while len("".join(page.split())) < MIN_PAGE_CHARS:
        template = supplement_templates[supplement_index % len(supplement_templates)]
        fact_hint = facts[supplement_index % len(facts)].rstrip("。")
        page += f"\n补充说明：{template} 证据线索包括：{fact_hint}。\n"
        supplement_index += 1
    return page


def materialize_entity_page(task_id: str, batch_id: str, domain: str, etype: str, name: str) -> list[str]:
    """从 homepage source-ready 输入确定性物化实体主页三件套。

    这是结构化主页的生产默认路径：事实来自 `entity_page_input.json`
    选定的百科/官方底稿，图片来自同实体 homepage lane source unit。Agent
    仍可用于后续创意文章与失败修订，但主页不再因为 Cursor 启动失败而阻塞。
    """
    input_path = batch_entity_page_input_path(task_id, batch_id, domain, etype, name)
    if not input_path.is_file():
        return [f"{domain}/{etype}/{name}: entity_page_input.json 缺失"]
    envelope = read_json(input_path)
    payload = envelope.get("payload") if isinstance(envelope.get("payload"), dict) else envelope
    base = payload.get("baseDraft") if isinstance(payload.get("baseDraft"), dict) else {}
    text = str(base.get("text") or "").strip()
    if not text:
        return [f"{domain}/{etype}/{name}: homepage baseDraft.text 缺失"]
    facts = _split_fact_sentences(text, entity_name=name)
    if len(facts) < 4:
        return [f"{domain}/{etype}/{name}: homepage baseDraft 可用事实不足"]
    image = _pick_homepage_asset(task_id, batch_id, domain, etype, name)
    if not image:
        return [f"{domain}/{etype}/{name}: homepage lane 无可发布图片资产"]
    obj = batch_entity_object_dir(task_id, batch_id, domain, etype, name)
    obj.mkdir(parents=True, exist_ok=True)
    asset = _copy_homepage_asset(obj, image)
    if not asset:
        return [f"{domain}/{etype}/{name}: homepage asset copy failed"]
    page_text = _render_homepage_markdown(
        name,
        facts,
        str(asset.get("assetId") or ""),
        str(asset.get("caption") or ""),
    )
    (obj / "page.md").write_text(page_text, encoding="utf-8")
    write_json(
        obj / "_entity.json",
        {
            "label": name,
            "domain": domain,
            "type": etype,
            "sourceTaskId": task_id,
            "entityRef": entity_ref(domain, etype, name),
            "summary": _homepage_summary(name, facts)[:180],
            "conditionProfile": _infer_condition_profile(name, facts),
            "sourceRefs": [
                str(base.get("primaryEvidenceRef") or base.get("sourceRef") or ""),
                str(asset.get("sourceRef") or ""),
            ],
        },
    )
    write_json(
        obj / "manifest.json",
        {
            "entityRef": entity_ref(domain, etype, name),
            "sourceTaskId": task_id,
            "sourceRefs": [
                str(base.get("primaryEvidenceRef") or base.get("sourceRef") or ""),
                str(asset.get("sourceRef") or ""),
            ],
            "assets": [asset],
            "generator": "deterministic_homepage_builder",
        },
    )
    return []


def materialize_entity_pages(task_id: str, batch_id: str, spec: dict[str, Any]) -> list[str]:
    """物化所有缺失或未过门的 coverage 实体主页，返回剩余物化问题。"""
    issues: list[str] = []
    region_set = set(region_keys())
    season_set = set(season_keys())
    for target in _coverage_targets(spec):
        domain, etype, name = target["domain"], target["etype"], target["name"]
        current_issues = validate_entity_page(
            task_id,
            batch_id,
            domain,
            etype,
            name,
            region_set=region_set,
            season_set=season_set,
        )
        if not current_issues:
            continue
        issues.extend(materialize_entity_page(task_id, batch_id, domain, etype, name))
    return issues


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


def _source_ref_from_asset_ref(source_asset_ref: str) -> str:
    normalized = str(source_asset_ref or "").replace("\\", "/").strip()
    if not normalized or "/assets/" not in normalized:
        return ""
    return normalized.split("/assets/", 1)[0].rstrip("/") + "/source.md"


def _normalize_homepage_manifest_assets(manifest_payload: dict[str, Any]) -> bool:
    assets = manifest_payload.get("assets")
    if not isinstance(assets, list):
        return False
    changed = False
    for raw in assets:
        if not isinstance(raw, dict):
            continue
        source_ref = str(raw.get("sourceRef") or "").strip()
        source_asset_ref = str(raw.get("sourceAssetRef") or "").strip()
        if source_ref and "/assets/" in source_ref:
            if not source_asset_ref:
                raw["sourceAssetRef"] = source_ref
                source_asset_ref = source_ref
            raw["sourceRef"] = ""
            source_ref = ""
            changed = True
        if not source_ref and source_asset_ref:
            inferred = _source_ref_from_asset_ref(source_asset_ref)
            if inferred:
                raw["sourceRef"] = inferred
                changed = True
    return changed


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
    issues: list[str] = []
    for raw in assets:
        if not isinstance(raw, dict):
            continue
        asset_id = str(raw.get("assetId") or raw.get("id") or "").strip()
        file_name = str(raw.get("fileName") or "").strip()
        source_ref = str(raw.get("sourceRef") or "").strip()
        source_asset_ref = str(raw.get("sourceAssetRef") or "").strip()
        if asset_id:
            id_to_file[asset_id] = file_name
        if file_name:
            file_names.add(file_name)
        if not source_ref or not source_asset_ref:
            issues.append(f"{label}: asset {asset_id or file_name or '<unknown>'} missing sourceRef/sourceAssetRef")
        elif "/assets/" in source_ref or not source_ref.endswith("/source.md"):
            issues.append(f"{label}: asset {asset_id or file_name} sourceRef must point to source.md")
        elif not source_asset_ref.startswith(source_ref.rsplit("/", 1)[0] + "/assets/"):
            issues.append(f"{label}: asset {asset_id or file_name} sourceAssetRef does not belong to sourceRef")
        if not (str(raw.get("authorizationProof") or "").strip() or str(raw.get("termsUrl") or "").strip()):
            issues.append(f"{label}: asset {asset_id or file_name or '<unknown>'} missing image rights proof")
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
        else:
            if _normalize_homepage_manifest_assets(manifest_payload):
                write_json(manifest, manifest_payload)
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
    issues.extend(_homepage_base_source_issues(task_id, batch_id, domain, etype, name))

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
