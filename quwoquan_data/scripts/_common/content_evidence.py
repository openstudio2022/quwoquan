"""内容来源脱敏、质量评分与线路证据聚合。"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence

from _common.io import read_json


@dataclass(frozen=True)
class SourceAssessment:
    source_id: str
    quality: str
    score: int
    reasons: tuple[str, ...]
    excerpt: str


_PLATFORM_MARKERS = ("马蜂窝", "携程", "小红书", "知乎", "大众点评", "去哪儿", "微博")
_META_MARKERS = (
    "来源平台：",
    "contract_fixture",
    "cold-start.local",
    "cold_start.local",
    "@",
    "用户名",
    "作者：",
    "userHandle",
)
_SCENE_MARKERS = (
    "清晨",
    "傍晚",
    "街巷",
    "茶馆",
    "徒步",
    "排队",
    "转场",
    "返程",
    "上车",
    "下车",
    "集合",
    "路口",
)
_FACT_MARKERS = (
    "门票",
    "开放",
    "交通",
    "集合",
    "成团",
    "退改",
    "费用",
    "海拔",
    "里程",
    "耗时",
    "路况",
    "补给",
    "住宿",
    "应急",
    "停留",
    "强度",
    "观光车",
)
_FACT_CATEGORY_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("transport", ("交通", "大交通", "动车", "高铁", "机场", "自驾", "车程", "耗时")),
    ("gathering", ("集合", "上车", "出发地", "出发点")),
    ("cost", ("费用", "团费", "人均", "预算", "自费")),
    ("refund", ("退改", "取消", "改签")),
    ("intensity", ("强度", "海拔", "高反", "徒步", "爬升")),
    ("stay", ("住宿", "露营", "补给", "酒店", "青旅")),
    ("risk", ("风险", "路况", "落石", "雨季", "应急", "封山", "末班")),
    ("ticket", ("门票", "预约", "开放", "观光车")),
)
_POSITIVE_EMOTION_MARKERS = ("喜欢", "愿意", "惊喜", "值", "值得", "震撼", "舒服", "推荐", "松弛", "治愈")
_NEGATIVE_EMOTION_MARKERS = ("累", "怕", "槽点", "麻烦", "失望", "排队", "高反", "后悔", "拥挤", "赶", "湿滑")
_SCENIC_VIEW_MARKERS = (
    "日出",
    "云海",
    "佛光",
    "圣灯",
    "金顶",
    "古木参天",
    "清幽",
    "景色",
    "风景",
)
_SCENIC_APPRAISAL_MARKERS = (
    "风景秀丽",
    "天下秀",
    "名胜云集",
    "奇观",
    "壮丽",
    "美誉",
    "景色优美",
    "清静雅致",
)
_TRANSITION_MARKERS = (
    "先",
    "再",
    "随后",
    "最后",
    "一路",
    "转场",
    "进入",
    "离开",
    "返程",
    "Day1",
    "Day2",
    "Day3",
    "上午",
    "下午",
)
_FORBIDDEN_EXCERPT_MARKERS = ("来源平台：", "url:", "platform:", "title:", "entity:", "retained:")
_MANUAL_SOURCE_PLAN_RE = re.compile(r"(?mi)^manual_source_plan_note:\s.*$")
_ENTITY_SUFFIXES = (
    "风景名胜旅游区",
    "风景名胜区",
    "文化旅游区",
    "旅游度假区",
    "风景旅游区",
    "旅游景区",
    "风景区",
    "旅游区",
    "景区",
)


def entity_names_from_refs(entity_refs: Sequence[str] | None) -> list[str]:
    return [ref.split("/")[-1] for ref in (entity_refs or []) if isinstance(ref, str) and ref.strip()]


def _value(source: Any, key: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(key, default)
    return getattr(source, key, default)


def _strip_frontmatter(text: str) -> tuple[str, str]:
    if not text.startswith("---"):
        return "", text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return "", text
    return parts[1], parts[2]


def _frontmatter_map(text: str) -> dict[str, str]:
    frontmatter, _ = _strip_frontmatter(text)
    data: dict[str, str] = {}
    for raw_line in frontmatter.splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip()
    return data


def _entity_match_terms(entity_name: str | None) -> tuple[str, ...]:
    raw = str(entity_name or "").strip()
    if not raw:
        return ()
    terms: list[str] = [raw]
    for suffix in _ENTITY_SUFFIXES:
        if raw.endswith(suffix) and len(raw) > len(suffix) + 1:
            terms.append(raw[: -len(suffix)])
            break
    for part in re.split(r"[·•—－/（）()，,、\s\-]+", raw):
        part = part.strip()
        if len(part) >= 2:
            terms.append(part)
            for suffix in _ENTITY_SUFFIXES:
                if part.endswith(suffix) and len(part) > len(suffix) + 1:
                    terms.append(part[: -len(suffix)])
                    break
    return tuple(dict.fromkeys(term for term in terms if len(term) >= 2))


def anonymize_source_markdown(text: str) -> str:
    """移除来源平台、作者与前台不可见的元信息。"""
    _, body = _strip_frontmatter(text)
    lines: list[str] = []
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            lines.append("")
            continue
        if line.startswith(("url:", "platform:", "title:", "entity:", "retained:", "license:", "allowedUse:")):
            continue
        if line.startswith("来源平台："):
            continue
        if any(marker in line for marker in ("cold-start.local", "cold_start.local", "contract_fixture")):
            continue
        if line.startswith(("作者：", "用户名：", "@")):
            continue
        lines.append(line)
    cleaned = "\n".join(lines)
    cleaned = _MANUAL_SOURCE_PLAN_RE.sub("", cleaned)
    cleaned = cleaned.replace("游记里还提到：", "")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def score_source_markdown(source_id: str, text: str, *, entity_name: str | None = None) -> SourceAssessment:
    """给来源打质量分，供下载/证据阶段阻断。"""
    _, body = _strip_frontmatter(text)
    cleaned = anonymize_source_markdown(text)
    compact = re.sub(r"\s+", " ", cleaned)
    score = 0
    reasons: list[str] = []

    if len(compact) > 120:
        score += 2
        reasons.append("length_ok")
    if len(compact) > 260:
        score += 1
        reasons.append("detail_rich")
    paragraph_count = len([p for p in cleaned.split("\n\n") if p.strip()])
    if paragraph_count >= 2:
        score += 1
        reasons.append("multi_paragraph")
    scene_hits = sum(1 for marker in _SCENE_MARKERS if marker in compact)
    if scene_hits >= 2:
        score += 2
        reasons.append("scene_rich")
    fact_hits = sum(1 for marker in _FACT_MARKERS if marker in compact)
    if fact_hits >= 3:
        score += 2
        reasons.append("fact_dense")
    entity_grounded = bool(entity_name and any(term in compact for term in _entity_match_terms(entity_name)))
    if entity_grounded:
        score += 1
        reasons.append("entity_grounded")

    penalties = 0
    platform_hits = sum(body.count(marker) for marker in _PLATFORM_MARKERS)
    if platform_hits:
        # UGC/攻略页面经常带导航、页脚或站内推荐。平台痕迹要留下
        # 诊断信号，但不能覆盖长篇实体相关正文的内容质量。
        if platform_hits >= 4 and not (len(compact) > 500 and entity_grounded):
            penalties += 2
        else:
            penalties += 1
        reasons.append("platform_visible")
    if any(marker in body for marker in _META_MARKERS):
        penalties += 2
        reasons.append("meta_visible")
    if "http" in body:
        penalties += 1
        reasons.append("url_visible")

    score = max(score - penalties, 0)
    if score >= 7:
        quality = "A-story"
    elif score >= 4:
        quality = "B-fact"
    elif score >= 2:
        quality = "C-context"
    else:
        quality = "Reject"

    excerpt = compact[:180].rstrip("。") + ("。" if compact else "")
    return SourceAssessment(
        source_id=source_id,
        quality=quality,
        score=score,
        reasons=tuple(dict.fromkeys(reasons)),
        excerpt=excerpt,
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
    for sentence in _sentences(text):
        category = _fact_category(sentence)
        if category:
            fact_entries.append({"category": category, "sentence": sentence})
        emotion_kind = _classify_emotion(sentence)
        if emotion_kind:
            emotion_entries.append({"kind": emotion_kind, "sentence": sentence})
        if any(marker in sentence for marker in _TRANSITION_MARKERS):
            mainline_entries.append(sentence)
        elif entity_name and entity_name in sentence:
            mainline_entries.append(sentence)
    return {
        "factEvidence": _unique_fact_entries(fact_entries, limit=8),
        "emotionEvidence": emotion_entries[:8],
        "mainlineEvidence": _unique_strings(mainline_entries, limit=8),
    }


def _source_dirs_for_entity(
    task_id: str,
    batch_id: str,
    entity_name: str,
    *,
    entity_ref: str = "",
) -> list[Path]:
    """优先对象同构来源单元；有显式 entityRef 时禁止回退到按名字跨类型模糊搜。"""
    from _common.source_unit import find_entity_object_dirs, iter_source_units

    dirs: list[Path] = []
    if entity_ref:
        for obj in find_entity_object_dirs(task_id, batch_id, entity_ref):
            dirs.extend(iter_source_units(obj))
    else:
        for obj in find_entity_object_dirs(task_id, batch_id, entity_name):
            dirs.extend(iter_source_units(obj))
    if dirs:
        return dirs
    return []


def load_source_records(task_id: str, batch_id: str, entity_names: Sequence[str], entity_refs: Sequence[str] | None = None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    ref_by_name: dict[str, str] = {}
    for raw_ref in entity_refs or []:
        ref = str(raw_ref or "").strip()
        if not ref:
            continue
        ref_by_name.setdefault(ref.split("/")[-1], ref)
    for entity_name in entity_names:
        for source_dir in _source_dirs_for_entity(
            task_id,
            batch_id,
            entity_name,
            entity_ref=ref_by_name.get(entity_name, ""),
        ):
            if not source_dir.is_dir():
                continue
            source_md = source_dir / "source.md"
            if not source_md.is_file():
                continue
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
            records.append(
                {
                    "entityName": entity_name,
                    "sourceId": source_dir.name,
                    "sourceDir": str(source_dir),
                    "sourcePath": str(source_md),
                    "url": url,
                    "text": text,
                    "assessment": assessment,
                }
            )
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

        route_nodes.append(
            {
                "sequence": index,
                "entityRef": entity_ref,
                "entityName": entity_name,
                "sourceCount": len(entity_items),
                "retainedSourceCount": len(retained_items),
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
        "schemaVersion": "quwoquan_data.route_evidence_bundle",
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
    """检查线路级证据是否足以进入 compose。"""
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


__all__ = [
    "SourceAssessment",
    "anonymize_source_markdown",
    "build_related_search_plan",
    "build_route_evidence_bundle",
    "entity_names_from_refs",
    "extract_source_evidence",
    "gate_route_evidence_bundle",
    "json_safe_dump",
    "load_source_records",
    "public_byline_label",
    "score_source_markdown",
]
