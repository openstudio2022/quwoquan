"""内容来源脱敏、质量评分与线路证据聚合。"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence
from _common.io import read_json
from _common.localization import fold_to_simplified
from _common.paths import batch_root
from _common.qunar_template import (
    QUNAR_FRESH_STALE_OVER_3Y,
    QUNAR_PAGE_SEARCH_RESULT,
    qunar_template_metadata,
)

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
_POSITIVE_EMOTION_MARKERS = (
    "喜欢",
    "愿意",
    "惊喜",
    "值",
    "值得",
    "震撼",
    "舒服",
    "推荐",
    "松弛",
    "治愈",
    "心心念念",
    "幸运",
    "幸福",
    "美味",
    "满足",
    "惊艳",
    "太美",
    "好吃",
    "巴适",
)
_NEGATIVE_EMOTION_MARKERS = (
    "累",
    "怕",
    "害怕",
    "槽点",
    "麻烦",
    "失望",
    "排队",
    "高反",
    "后悔",
    "拥挤",
    "赶",
    "湿滑",
    "腿抖",
    "担心",
    "辛苦",
)
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
# 样板/导航/页脚/广告行标记：来源单元净化与底稿正文提取共用同一份唯一真相源，
# 避免在 base_draft / content_evidence 各维护一份漂移列表（编码军规 R25/single-source）。
SOURCE_BOILERPLATE_MARKERS: tuple[str, ...] = (
    "登录",
    "注册",
    "联系客服",
    "我的订单",
    "举报",
    "点赞",
    "写点评",
    "上一页",
    "下一页",
    "回到顶部",
    "用户问答",
    "附近景点",
    "推荐景点",
    "附近美食",
    "附近购物",
    "热门旅游目的地推荐",
    "旅游攻略导航",
    "微信小程序",
    "扫码前往",
    "扫码",
    "值机选座",
    "退票改签",
    "报销凭证",
    "AI行程助手",
    "特价机票",
    "企业商旅",
    "体验更流畅",
    "赢积分换大奖",
    "PICC",
    "中国人民保险",
    "中国人保",
    "人保守护",
    "优游保",
    "境内自驾游保险",
    "保单管理",
    "增值服务",
    "在线理赔",
    "在线客服",
    "新冠",
    "友情链接",
    "查看更多",
    "查看地图",
    "打开微信扫一扫",
    "页面存档",
    "互联网档案馆",
    "Toggle navigation",
)
# 维基/百科常见的"非正文尾节"，命中该节标题后整节剔除（含其子节），
# 直到出现一个不在剔除集合内的同级或更高级标题。
_CLEAN_DROP_SECTIONS: tuple[str, ...] = (
    "参见",
    "參見",
    "参考文献",
    "參考文獻",
    "参考资料",
    "參考資料",
    "参考来源",
    "參考來源",
    "注释",
    "註釋",
    "注脚",
    "註腳",
    "脚注",
    "腳註",
    "外部链接",
    "外部連結",
    "延伸阅读",
    "延伸閱讀",
    "扩展阅读",
    "擴展閱讀",
    "相关条目",
    "相關條目",
    "相关链接",
    "相關連結",
    "分类",
    "分類",
    "图集",
    "圖集",
    "来源",
    "來源",
    "评论",
    "評論",
    "相关游记",
    "相關遊記",
    "相关攻略",
    "相關攻略",
    "热门游记",
    "熱門遊記",
)
# 行内引用/失链标记：[1]、[12]、[来源请求]、[註 3]、[失效链接] 等。
_CITATION_MARKER_RE = re.compile(
    r"\[(?:\d{1,3}"
    r"|来源请求|來源請求|需要更新|引用错误|引用錯誤"
    r"|失效链接|失效連結|永久失效链接|永久失效連結"
    r"|註\s*\d+|注\s*\d+|n\s*\d+|a\s*\d+)\]"
)
# MediaWiki explaintext(默认 exsectionformat=wiki)的小节标题：== 标题 == / === 标题 ===。
_WIKI_HEADING_RE = re.compile(r"^\s*(={2,6})\s*(.+?)\s*=*\s*$")
_MARKDOWN_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
_QUNAR_PRIVATE_ICON_RE = re.compile(r"^[\uf000-\uf8ff]")
_QUNAR_TAG_LINE_RE = re.compile(r"^(人物|玩法|人均|天数|出发|目的地|行程)[/：:].{0,48}$")

_STRUCTURAL_FIGURE_LINE_RE = re.compile(r"^\s*(?::::|!\[[^\]]*\]\(asset://)")
# GFM 表格结构行：`| a | b |` 数据/表头行与 `|---|---|` 分隔行。
# 分隔行不含字母数字，会被「无字母→样板噪声」误删，必须整体豁免。
_GFM_TABLE_LINE_RE = re.compile(r"^\s*\|.*\|\s*$")
# wikitable cell 属性残留行：`valign=top|…`、`avlign=top|…`、`style="…"|…`。
# 解析层已按语法位置剥离；此处是 clean 层兜底，防旧产物/其它前端漏网。
_CELL_ATTR_RESIDUE_RE = re.compile(
    r"^(?P<marker>[-*]\s+)?"
    r"(?:[A-Za-z][A-Za-z0-9_-]*\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^|\s]+)\s*)+\|\s*"
    r"(?P<rest>.*)$"
)

def _is_structural_figure_line(line: str) -> bool:
    """图文混排结构行：`:::figure` / `:::figuregroup` / 收尾 `:::` 围栏，或 `![..](asset://..)` 图片引用。"""
    return bool(_STRUCTURAL_FIGURE_LINE_RE.match(str(line or "")))

def _is_gfm_table_line(line: str) -> bool:
    return bool(_GFM_TABLE_LINE_RE.match(str(line or "")))

def source_line_is_boilerplate(line: str) -> bool:
    """判断一行是否为导航/页脚/广告/纯链接等样板噪声（净化与底稿提取共用）。"""
    compact = re.sub(r"\s+", "", line)
    letters = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", compact)
    if not letters:
        return True
    if _QUNAR_PRIVATE_ICON_RE.match(line.strip()):
        return True
    if _QUNAR_TAG_LINE_RE.match(compact):
        return True
    if any(marker in line for marker in SOURCE_BOILERPLATE_MARKERS):
        return True
    if "http" in compact.lower():
        return True
    if re.fullmatch(r"[\d./:+\-—~～()（） ]+", compact):
        return True
    if compact.startswith(("IP属地", "第", "共")) and any(ch.isdigit() for ch in compact):
        return True
    return False

def clean_source_markdown(text: str, *, raw_format: str = "") -> str:
    """结构化净化来源正文，产出 source.clean.md。
    在 anonymize（脱敏/去平台/去元信息）基础上再做：
    - 剔除维基/百科尾节（参考文献/外部链接/参见/注释/分类等，含子节）；
    - 去除行内引用/失链标记（[1]、[来源请求]、[失效链接]…）；
    - 去除导航/页脚/广告/纯链接等样板行；
    - 折叠多余空行。
    raw_format 预留给来源类型分流（如 mediawiki_api_json），当前净化规则对各来源通用。
    """
    anon = anonymize_source_markdown(text)
    anon = _CITATION_MARKER_RE.sub("", anon)
    kept: list[str] = []
    dropping = False
    drop_level = 0
    for raw_line in anon.splitlines():
        line = raw_line.rstrip()
        wiki_heading = _WIKI_HEADING_RE.match(line)
        markdown_heading = _MARKDOWN_HEADING_RE.match(line)
        heading = wiki_heading or markdown_heading
        if heading:
            level = len(heading.group(1))
            name = heading.group(2).strip()
            if dropping and level > drop_level:
                continue
            if any(name == sec or name.startswith(sec) for sec in _CLEAN_DROP_SECTIONS):
                dropping = True
                drop_level = level
                continue
            dropping = False
            drop_level = 0
            if name:
                kept.append(line.strip() if markdown_heading else name)
            continue
        if dropping:
            continue
        if not line.strip():
            kept.append("")
            continue
        if _is_structural_figure_line(line):
            # 图文混排结构行（:::figure/:::figuregroup 围栏、asset:// 图片引用）必须保结构原样保留，
            # 不能被「无字母→样板噪声」误删（否则 source.clean.md 里的图文块围栏被打散，P2 图文混排丢失）。
            kept.append(line.strip())
            continue
        if _is_gfm_table_line(line):
            # GFM 表格行整体保留：分隔行 `|---|---|` 无字母数字，会被样板噪声规则误删打散表格。
            kept.append(line.strip())
            continue
        attr_residue = _CELL_ATTR_RESIDUE_RE.match(line.strip())
        if attr_residue:
            # wikitable cell 属性残留（valign=top| / avlign=top| / style="…"|）不得进入 clean 文本；
            # 属性后仍有正文则剥前缀保正文，纯属性行整行剔除。
            rest = attr_residue.group("rest").strip()
            if rest:
                kept.append(f"{attr_residue.group('marker') or ''}{rest}".strip())
            continue
        if source_line_is_boilerplate(line):
            continue
        kept.append(line.strip())
    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()
    return cleaned
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
def _fold_zh_variants(value: str) -> str:
    # 繁→简折叠表单一真相源在 _common.localization，全仓共用（R24）。
    return fold_to_simplified(value)

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
    qunar_meta = qunar_template_metadata(text=text)
    if qunar_meta.get("pageType") == QUNAR_PAGE_SEARCH_RESULT:
        links = qunar_meta.get("discoveredDetailLinks") or []
        return SourceAssessment(
            source_id=source_id,
            quality="Reject",
            score=0,
            reasons=("qunar_search_result_directory", "detail_links_discovered" if links else "no_detail_link"),
            excerpt="去哪儿搜索结果页是目录页，必须下钻到具体游记详情后才可作为候选底稿。",
        )
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
    if not entity_grounded and entity_name:
        folded_compact = _fold_zh_variants(compact)
        entity_grounded = any(_fold_zh_variants(term) in folded_compact for term in _entity_match_terms(entity_name))
    if entity_grounded:
        score += 1
        reasons.append("entity_grounded")
    content_score = score
    # 详尽且实体相关的正文（detail_rich + entity_grounded）即便残留页眉页脚/导航/外链，
    # 也只是 source.clean.md 还没清干净的「噪声」，不该被惩罚直接打成 Reject。
    substantive = entity_grounded and len(compact) > 260
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
    if qunar_meta.get("freshnessTier") == QUNAR_FRESH_STALE_OVER_3Y:
        penalties += 2
        reasons.append("qunar_stale_over_3y")
    score = max(score - penalties, 0)
    if not reasons:
        reasons.append("empty_or_unfetchable_body")
    if score >= 7:
        quality = "A-story"
    elif score >= 4:
        quality = "B-fact"
    elif score >= 2:
        quality = "C-context"
    elif substantive and content_score >= 4:
        # 实质达标但被噪声惩罚跌破阈值：保底为 C-context（可用上下文），不误杀。
        quality = "C-context"
        score = 2
        reasons.append("noise_penalized_kept_as_context")
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

def _source_record_from_dir(
    task_id: str,
    batch_id: str,
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
    task_id: str,
    batch_id: str,
    entity_names: Sequence[str],
    entity_refs: Sequence[str] | None = None,
    *,
    base_source_ref: str = "",
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    base_ref = str(base_source_ref or "").strip()
    if base_ref:
        source_path = Path(base_ref)
        if not source_path.is_absolute():
            source_path = batch_root(task_id, batch_id) / base_ref
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
        row = _source_record_from_dir(task_id, batch_id, source_path.parent, entity_name=entity_name)
        return [row] if row is not None else []
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
            row = _source_record_from_dir(task_id, batch_id, source_dir, entity_name=entity_name)
            if row is not None:
                records.append(row)
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
    """检查线路级证据是否足以进入 compose。
    载体感知：image/gallery 画报是"专业图库一源一作品"的视觉载体，不承载线路/体验叙事证据
    （UGC 情感信号 likes/painPoints、storySpine 进程、路线节点覆盖、mustIncludeFacts 叙事）。
    对其施加线路叙事门属载体错配——会把开放许可图集（Wikimedia/CC 事实性 caption、无 UGC 互动）
    误判为 `missing emotion evidence` 而整批转人工。图片作品的把关由许可(rights)、资产落盘、
    相关性、works_gate 负责，不在此线路证据门内。故 image/gallery 直接放行（不产线路叙事 issue）。
    """
    if str(brief.get("carrier") or "").lower() in ("image", "gallery"):
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
