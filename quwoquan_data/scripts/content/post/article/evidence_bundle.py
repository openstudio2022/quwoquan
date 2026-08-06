"""Aggregate assessed source records into route-level evidence and review gates."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence

from core.io import read_json
from core.paths import execution_root
from content.post.article.evidence_text import (
    SourceAssessment,
    _FACT_CATEGORY_MARKERS,
    _FORBIDDEN_EXCERPT_MARKERS,
    _NEGATIVE_EMOTION_MARKERS,
    _POSITIVE_EMOTION_MARKERS,
    _SCENIC_APPRAISAL_MARKERS,
    _SCENIC_VIEW_MARKERS,
    _TRANSITION_MARKERS,
    _entity_match_terms,
    _fold_zh_variants,
    _frontmatter_map,
    _value,
    anonymize_source_markdown,
    entity_names_from_refs,
    score_source_markdown,
)

def _sentences(text: str) -> list[str]:
    cleaned = anonymize_source_markdown(text)
    rows: list[str] = []
    for chunk in re.split(r"[。！？\n]", cleaned):
        sentence = re.sub(r"\s+", " ", chunk).strip(" 　;；,，。")
        if len(sentence) >= 8:
            rows.append(sentence)
    return rows

def _fact_category(sentence: str) -> str | None:
    for category, markers in _FACT_CATEGORY_MARKERS:
        if any(marker in sentence for marker in markers):
            return category
    return None

def _looks_like_scenic_admiration(sentence: str) -> bool:
    if any(marker in sentence for marker in ("风景秀丽", "峨眉天下秀", "名胜云集", "景色优美")):
        return True
    scenic_hits = sum(1 for marker in _SCENIC_VIEW_MARKERS if marker in sentence)
    appraisal_hits = sum(1 for marker in _SCENIC_APPRAISAL_MARKERS if marker in sentence)
    return scenic_hits >= 2 and appraisal_hits >= 1

def _classify_emotion(sentence: str) -> str | None:
    if any(marker in sentence for marker in _POSITIVE_EMOTION_MARKERS):
        return "like"
    if _looks_like_scenic_admiration(sentence):
        return "like"
    if any(marker in sentence for marker in _NEGATIVE_EMOTION_MARKERS):
        return "pain"
    return None

def _unique_strings(values: Iterable[str], *, limit: int) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = re.sub(r"\s+", " ", value).strip()
        if not item or item in seen:
            continue
        if any(marker in item for marker in _FORBIDDEN_EXCERPT_MARKERS):
            continue
        seen.add(item)
        result.append(item)
        if len(result) >= limit:
            break
    return result

def _unique_fact_entries(entries: Iterable[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for entry in entries:
        category = str(entry.get("category") or "")
        sentence = re.sub(r"\s+", " ", str(entry.get("sentence") or "")).strip()
        if not sentence:
            continue
        key = (category, sentence)
        if key in seen:
            continue
        seen.add(key)
        result.append({"category": category, "sentence": sentence})
        if len(result) >= limit:
            break
    return result

def _fact_categories(entries: Iterable[dict[str, Any]]) -> dict[str, list[str]]:
    categories: dict[str, list[str]] = {}
    for entry in entries:
        category = str(entry.get("category") or "")
        sentence = str(entry.get("sentence") or "").strip()
        if not category or not sentence:
            continue
        categories.setdefault(category, [])
        if sentence not in categories[category]:
            categories[category].append(sentence)
    return {key: values[:3] for key, values in categories.items()}

def extract_source_evidence(text: str, *, entity_name: str | None = None) -> dict[str, list[Any]]:
    """从单条来源中抽取事实、情感和主线证据。"""
    fact_entries: list[dict[str, Any]] = []
    emotion_entries: list[dict[str, str]] = []
    mainline_entries: list[str] = []
    entity_terms = _entity_match_terms(entity_name)
    folded_entity_terms = tuple(_fold_zh_variants(term) for term in entity_terms)
    for sentence in _sentences(text):
        folded_sentence = _fold_zh_variants(sentence)
        category = _fact_category(sentence)
        if category:
            fact_entries.append({"category": category, "sentence": sentence})
        emotion_kind = _classify_emotion(sentence)
        if emotion_kind:
            emotion_entries.append({"kind": emotion_kind, "sentence": sentence})
        if any(marker in sentence for marker in _TRANSITION_MARKERS):
            mainline_entries.append(sentence)
        elif entity_terms and any(term in sentence for term in entity_terms):
            mainline_entries.append(sentence)
        elif folded_entity_terms and any(term in folded_sentence for term in folded_entity_terms):
            mainline_entries.append(sentence)
    return {
        "factEvidence": _unique_fact_entries(fact_entries, limit=8),
        "emotionEvidence": emotion_entries[:8],
        "mainlineEvidence": _unique_strings(mainline_entries, limit=8),
    }

def _source_dirs_for_entity(
    execution_id: str,
    entity_name: str,
    *,
    entity_ref: str = "",
) -> list[Path]:
    """优先对象同构来源单元；有显式 entityRef 时禁止回退到按名字跨类型模糊搜。"""
    from content.source.source_unit import find_entity_object_dirs, iter_source_units
    dirs: list[Path] = []
    if entity_ref:
        for obj in find_entity_object_dirs(execution_id, entity_ref):
            dirs.extend(iter_source_units(obj))
    else:
        for obj in find_entity_object_dirs(execution_id, entity_name):
            dirs.extend(iter_source_units(obj))
    if dirs:
        return dirs
    return []

def _source_record_from_dir(
    execution_id: str,
    source_dir: Path,
    *,
    entity_name: str,
) -> dict[str, Any] | None:
    if not source_dir.is_dir():
        return None
    source_md = source_dir / "source.md"
    if not source_md.is_file():
        return None
    text = source_md.read_text(encoding="utf-8")
    quality_path = source_dir / "source.quality.json"
    if quality_path.exists():
        payload = read_json(quality_path)
        assessment = SourceAssessment(
            source_id=str(payload.get("sourceId") or source_dir.name),
            quality=str(payload.get("quality") or "Reject"),
            score=int(payload.get("score") or 0),
            reasons=tuple(str(item) for item in payload.get("reasons") or []),
            excerpt=str(payload.get("excerpt") or ""),
        )
        url = str(payload.get("url") or _frontmatter_map(text).get("url") or "")
    else:
        assessment = score_source_markdown(source_dir.name, text, entity_name=entity_name)
        url = _frontmatter_map(text).get("url") or ""
    return {
        "entityName": entity_name,
        "sourceId": source_dir.name,
        "sourceDir": str(source_dir),
        "sourcePath": str(source_md),
        "url": url,
        "text": text,
        "assessment": assessment,
    }

def load_source_records(
    execution_id: str,
    entity_names: Sequence[str],
    entity_refs: Sequence[str] | None = None,
    *,
    base_source_ref: str = "",
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen_source_dirs: set[Path] = set()
    base_ref = str(base_source_ref or "").strip()
    if base_ref:
        source_path = Path(base_ref)
        if not source_path.is_absolute():
            source_path = execution_root(execution_id) / base_ref
        entity_name = entity_names[0] if entity_names else ""
        meta_path = source_path.parent / "meta.json"
        if meta_path.is_file():
            try:
                meta = read_json(meta_path)
            except (OSError, ValueError, TypeError):
                meta = {}
            relevance = meta.get("relevance") if isinstance(meta.get("relevance"), Mapping) else {}
            target_refs = [str(ref) for ref in (relevance.get("targetRefs") or []) if str(ref)]
            if target_refs:
                entity_name = target_refs[0].rstrip("/").rsplit("/", 1)[-1]
        row = _source_record_from_dir(execution_id, source_path.parent, entity_name=entity_name)
        if row is not None:
            records.append(row)
            seen_source_dirs.add(source_path.parent.resolve())
    ref_by_name: dict[str, str] = {}
    for raw_ref in entity_refs or []:
        ref = str(raw_ref or "").strip()
        if not ref:
            continue
        ref_by_name.setdefault(ref.split("/")[-1], ref)
    for entity_name in entity_names:
        for source_dir in _source_dirs_for_entity(
            execution_id,
            entity_name,
            entity_ref=ref_by_name.get(entity_name, ""),
        ):
            resolved_source_dir = source_dir.resolve()
            if resolved_source_dir in seen_source_dirs:
                continue
            row = _source_record_from_dir(execution_id, source_dir, entity_name=entity_name)
            if row is not None:
                records.append(row)
                seen_source_dirs.add(resolved_source_dir)
    return records

def build_route_evidence_bundle(
    ref: str,
    brief: Mapping[str, Any],
    source_records: Sequence[Mapping[str, Any]],
    *,
    entity_refs: Sequence[str] | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    """按线路维度聚合多实体来源，避免首实体偏置。"""
    route_entity_refs = [str(item) for item in (entity_refs or brief.get("entityRefs") or []) if item]
    route_entities = entity_names_from_refs(route_entity_refs)
    if not route_entities:
        route_entities = _unique_strings((str(row.get("entityName") or "") for row in source_records), limit=12)
        route_entity_refs = [name for name in route_entities]
    route_nodes: list[dict[str, Any]] = []
    all_fact_entries: list[dict[str, Any]] = []
    all_mainline: list[str] = []
    likes: list[str] = []
    pain_points: list[str] = []
    source_quality: list[dict[str, Any]] = []
    related_topics = list(route_entities)
    for index, entity_name in enumerate(route_entities, start=1):
        entity_ref = route_entity_refs[index - 1] if index - 1 < len(route_entity_refs) else entity_name
        entity_items = [row for row in source_records if str(row.get("entityName") or "") == entity_name]
        retained_items = [row for row in entity_items if getattr(row.get("assessment"), "quality", "Reject") != "Reject"]
        effective_items = retained_items or entity_items
        fact_entries: list[dict[str, Any]] = []
        emotion_entries: list[dict[str, str]] = []
        mainline_entries: list[str] = []
        for row in effective_items:
            assessment = row.get("assessment")
            if isinstance(assessment, SourceAssessment):
                source_quality.append({**asdict(assessment), "entityName": entity_name})
            evidence = extract_source_evidence(str(row.get("text") or ""), entity_name=entity_name)
            fact_entries.extend(evidence.get("factEvidence", []))
            mainline_entries.extend(evidence.get("mainlineEvidence", []))
        # 诚实评价：Reject 源不进入后续加工，不再贡献情感/主线线索。
        for row in retained_items:
            evidence = extract_source_evidence(str(row.get("text") or ""), entity_name=entity_name)
            emotion_entries.extend(evidence.get("emotionEvidence", []))
        node_likes = _unique_strings(
            (entry.get("sentence", "") for entry in emotion_entries if entry.get("kind") == "like"),
            limit=2,
        )
        node_pains = _unique_strings(
            (entry.get("sentence", "") for entry in emotion_entries if entry.get("kind") == "pain"),
            limit=2,
        )
        likes.extend(node_likes)
        pain_points.extend(node_pains)
        all_fact_entries.extend(fact_entries)
        all_mainline.extend(mainline_entries)
        related_topics.extend(node_likes + node_pains)
        top_excerpt = ""
        for row in effective_items:
            assessment = row.get("assessment")
            if isinstance(assessment, SourceAssessment) and assessment.excerpt:
                top_excerpt = assessment.excerpt
                break
        # route 单一多目的地底稿模型：每个目的地节点各自认领「单一最佳保留源」作节点底稿，
        # 节点配图只来自该节点底稿（节点内不跨源、节点间不互借）。无保留源 ⇒ 该节点文字承载。
        node_base_id = ""
        node_base_url = ""
        if retained_items:
            best_row = max(
                retained_items,
                key=lambda r: int(getattr(r.get("assessment"), "score", 0) or 0),
            )
            node_base_id = str(best_row.get("sourceId") or "")
            node_base_url = str(best_row.get("url") or "")
        route_nodes.append(
            {
                "sequence": index,
                "entityRef": entity_ref,
                "entityName": entity_name,
                "sourceCount": len(entity_items),
                "retainedSourceCount": len(retained_items),
                "baseSourceId": node_base_id,
                "baseSourceUrl": node_base_url,
                "rejectOnly": bool(entity_items) and not retained_items,
                "topExcerpt": top_excerpt,
                "factEvidence": _unique_fact_entries(fact_entries, limit=6),
                "factCategories": _fact_categories(fact_entries),
                "emotionEvidence": {
                    "likes": node_likes,
                    "painPoints": node_pains,
                },
                "mainlineEvidence": _unique_strings(mainline_entries, limit=4),
            }
        )
    progression = [f"先从 {node['entityName']} 进入主线。" for node in route_nodes[:1]]
    for node in route_nodes[1:-1]:
        progression.append(f"再把重心转到 {node['entityName']}。")
    if len(route_nodes) >= 2:
        progression.append(f"最后留给 {route_nodes[-1]['entityName']} 做收束与回程判断。")
    source_note = ""
    retained_quality = [row for row in source_quality if row.get("quality") != "Reject" and row.get("excerpt")]
    if retained_quality:
        source_note = str(retained_quality[0]["excerpt"])
    elif route_nodes:
        source_note = (
            f"这条线不是单点打卡，而是按 {' -> '.join(node['entityName'] for node in route_nodes)} "
            "一路推进，转场和体力分配比景点数量更影响体验。"
        )
    story_spine = {
        "primaryEntity": route_nodes[0]["entityName"] if route_nodes else "",
        "routeEntities": [node["entityName"] for node in route_nodes],
        "progression": progression,
        "beats": _unique_strings(
            [
                *progression,
                *(likes[:2]),
                *(pain_points[:2]),
            ],
            limit=5,
        ),
        "sourceNote": source_note,
        "relatedTopics": _unique_strings(related_topics, limit=18),
        "mustIncludeFacts": [str(item) for item in brief.get("mustIncludeFacts") or [] if item],
        "sourceQuality": source_quality,
    }
    coverage = {
        "expectedEntityCount": len(route_entities),
        "coveredEntityCount": sum(1 for node in route_nodes if node.get("retainedSourceCount", 0) > 0),
        "rejectOnlyEntities": [node["entityName"] for node in route_nodes if node.get("rejectOnly")],
        "missingMainlineEntities": [node["entityName"] for node in route_nodes if not node.get("mainlineEvidence")],
        "missingEmotionEntities": [
            node["entityName"]
            for node in route_nodes
            if not node.get("emotionEvidence", {}).get("likes") and not node.get("emotionEvidence", {}).get("painPoints")
        ],
    }
    return {
        "schema": "quwoquan_data.route_evidence_bundle",
        "topicId": ref,
        "title": title or str(brief.get("titleHint") or ref),
        "templateId": str(brief.get("templateId") or ""),
        "routeNodes": route_nodes,
        "coverage": coverage,
        "emotionSignals": {
            "likes": _unique_strings(likes, limit=6),
            "painPoints": _unique_strings(pain_points, limit=6),
        },
        "factSignals": _fact_categories(all_fact_entries),
        "mainlineSignals": _unique_strings(all_mainline, limit=8),
        "storySpine": story_spine,
    }

def _fact_supported(fact: str, evidence_bundle: Mapping[str, Any]) -> bool:
    fact_text = str(fact).strip()
    if not fact_text:
        return True
    combined = " ".join(
        [
            json_safe_dump(evidence_bundle.get("factSignals")),
            json_safe_dump(evidence_bundle.get("mainlineSignals")),
            json_safe_dump(evidence_bundle.get("emotionSignals")),
            json_safe_dump(evidence_bundle.get("storySpine")),
        ]
    )
    if fact_text in combined:
        return True
    tokens = [token for token in re.split(r"[、/，,\s]+", fact_text) if len(token) >= 2]
    return any(token in combined for token in tokens)

def gate_route_evidence_bundle(brief: Mapping[str, Any], evidence_bundle: Mapping[str, Any]) -> list[str]:
    """检查线路级证据是否足以进入 compose。
    载体感知：image/gallery 画报是"专业图库一源一作品"的视觉载体，不承载线路/体验叙事证据
    （UGC 情感信号 likes/painPoints、storySpine 进程、路线节点覆盖、mustIncludeFacts 叙事）。
    对其施加线路叙事门属载体错配——会把开放许可图集（Wikimedia/CC 事实性 caption、无 UGC 互动）
    误判为 `missing emotion evidence` 而整批转人工。图片作品的把关由许可(rights)、资产落盘、
    相关性、works_gate 负责，不在此线路证据门内。故 image/gallery 直接放行（不产线路叙事 issue）。
    """
    if str(brief.get("carrier") or "").lower() == "image":
        return []
    issues: list[str] = []
    coverage = evidence_bundle.get("coverage") or {}
    route_nodes = evidence_bundle.get("routeNodes") or []
    route_expectations = brief.get("routeCoverageExpectations") or {}
    min_covered = int(route_expectations.get("minCoveredEntityRefs") or max(1, min(len(route_nodes), 2)))
    covered_count = int(coverage.get("coveredEntityCount") or 0)
    if covered_count < min_covered:
        issues.append(f"routeCoverage: only {covered_count} route nodes retained evidence (need >= {min_covered})")
    if route_expectations.get("requireAllPrimaryNodes") and coverage.get("rejectOnlyEntities"):
        issues.append(f"evidenceQuality: reject-only entities {coverage['rejectOnlyEntities']}")
    if coverage.get("missingMainlineEntities"):
        issues.append(f"routeCoverage: missing mainline evidence for {coverage['missingMainlineEntities']}")
    evidence_requirements = brief.get("evidenceRequirements") or {}
    if evidence_requirements.get("emotion", {}).get("required", True):
        likes = (evidence_bundle.get("emotionSignals") or {}).get("likes") or []
        pain_points = (evidence_bundle.get("emotionSignals") or {}).get("painPoints") or []
        if not likes and not pain_points:
            issues.append("evidenceQuality: missing emotion evidence")
    for fact in [str(item) for item in brief.get("mustIncludeFacts") or [] if item]:
        if not _fact_supported(fact, evidence_bundle):
            issues.append(f"evidenceQuality: missing support for fact '{fact}'")
    if not (evidence_bundle.get("storySpine") or {}).get("progression"):
        issues.append("routeCoverage: missing route progression spine")
    return issues

def build_related_search_plan(meta: Any, story_or_bundle: Mapping[str, Any]) -> dict[str, Any]:
    """基于主线和证据摘要给出扩搜词，但锁住线路主线。"""
    entity_refs = [str(item) for item in (_value(meta, "entity_refs") or _value(meta, "entityRefs") or []) if item]
    ref = str(_value(meta, "ref") or _value(meta, "title") or "")
    route_entities = story_or_bundle.get("routeEntities") or entity_names_from_refs(entity_refs)
    if not route_entities and isinstance(story_or_bundle.get("storySpine"), Mapping):
        route_entities = story_or_bundle["storySpine"].get("routeEntities") or []
    related_topics = story_or_bundle.get("relatedTopics")
    if related_topics is None and isinstance(story_or_bundle.get("storySpine"), Mapping):
        related_topics = story_or_bundle["storySpine"].get("relatedTopics")
    search_terms = _unique_strings(
        [
            *route_entities,
            *(related_topics or []),
        ],
        limit=16,
    )
    if ref and ref not in search_terms:
        search_terms.insert(0, ref)
    story_spine = story_or_bundle if "progression" in story_or_bundle else story_or_bundle.get("storySpine", {})
    return {
        "searchTerms": [term for term in search_terms if term],
        "allowedExtensionTopics": list(related_topics or []),
        "spineLock": {
            "routeEntities": list(route_entities or []),
            "progression": list(story_spine.get("progression") or []),
        },
    }

def public_byline_label(template_id: str, creator: Mapping[str, Any]) -> str:
    role_map = {
        "古镇_叙事": "在路上的旅人",
        "景区_体验": "行走的体验编辑",
        "旅行_个人游记": "旅行记录者",
        "打卡地_日记": "城市漫步者",
        "主题_图文画报": "风光摄影编辑",
        "打卡地_美图": "摄影编辑",
        "博物馆_科普": "地理编辑",
        "博物馆_体验": "讲解编辑",
        "古镇_攻略": "行程编辑",
        "线路_跟团攻略": "路线编辑",
        "线路_环线攻略": "路线编辑",
        "线路_枢纽到达": "旅行编辑",
        "线路_自驾路书": "自驾路线编辑",
        "线路_深度探险": "路线编辑",
    }
    if template_id in role_map:
        return role_map[template_id]
    archetype = str(creator.get("creatorArchetype") or "")
    archetype_map = {
        "travel_blogger": "旅行编辑",
        "self_drive_expert": "自驾路线编辑",
        "pro_guide": "路线编辑",
        "geo_editor": "地理编辑",
        "landscape_photographer": "摄影编辑",
    }
    return archetype_map.get(archetype, "内容编辑")

def json_safe_dump(value: Any) -> str:
    if isinstance(value, Mapping):
        return " ".join(f"{key}:{json_safe_dump(child)}" for key, child in value.items())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return " ".join(json_safe_dump(item) for item in value)
    return str(value or "")
