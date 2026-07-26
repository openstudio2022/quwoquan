"""Normalize and assess source text before it enters content evidence aggregation."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence
from core.io import read_json
from core.localization import fold_to_simplified
from core.paths import execution_root
from core.qunar_template import (
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
_INLINE_HTTP_URL_RE = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)
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
    without_urls = _INLINE_HTTP_URL_RE.sub("", line)
    url_free_letters = re.sub(
        r"[^\u4e00-\u9fffA-Za-z0-9]",
        "",
        re.sub(r"\s+", "", without_urls),
    )
    if "http" in compact.lower() and not url_free_letters:
        return True
    if re.fullmatch(r"[\d./:+\-—~～()（） ]+", compact):
        return True
    if re.fullmatch(r"(?:IP属地)?第\s*\d+\s*页|共\s*\d+\s*页", compact):
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
                # Keep the section as Markdown rather than flattening it into
                # prose.  MediaWiki rendered text and the wikitext structure
                # then retain the same paragraph boundary for fidelity checks.
                kept.append(line.strip() if markdown_heading else f"## {name}")
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
        # A factual paragraph may legitimately cite an inline URL.  The URL is
        # not publishable prose, but it must not cause the entire paragraph to
        # be classified as navigation noise.
        line_without_urls = _INLINE_HTTP_URL_RE.sub("", line).strip()
        if line_without_urls:
            kept.append(line_without_urls)
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
    # 繁→简折叠表单一真相源在 core.localization，全仓共用（R24）。
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
