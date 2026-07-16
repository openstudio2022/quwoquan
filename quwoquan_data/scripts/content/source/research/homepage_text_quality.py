"""Homepage source-text quality rules."""
from __future__ import annotations

import re

from content.source.research.text_match import (
    _dedupe_terms,
    _entity_name_variants,
    _normalized_title,
)

_HOMEPAGE_JSON_API_RE = re.compile(
    r'^\s*[\[{].{0,240}"(?:code|data|rows|result|success|message|msg|list|total)"',
    re.S,
)

_HOMEPAGE_REDIRECT_MARKERS = (
    "簡繁重定向",
    "简繁重定向",
    "本重定向",
    "重定向用来",
    "重定向用來",
    "redirect page",
)

_HOMEPAGE_DISAMBIG_MARKERS = (
    "可以指",
    "可指",
    "可能指",
    "指的是",
    "下列",
    "消歧义",
    "消歧義",
    "disambiguation",
)

_HOMEPAGE_FACT_MARKERS = (
    "位于",
    "位於",
    "坐落",
    "地处",
    "地處",
    "始建",
    "建于",
    "建於",
    "建成",
    "开放",
    "開放",
    "占地",
    "面積",
    "面积",
    "海拔",
    "全长",
    "全長",
    "长度",
    "长度",
    "宽度",
    "包括",
    "包含",
    "核心",
    "主要",
    "属于",
    "屬於",
    "国家级",
    "國家級",
    "AAAAA",
    "5A",
    "世界遗产",
    "世界遺產",
    "文化遗产",
    "自然遗产",
    "门票",
    "門票",
    "预约",
    "預約",
    "开放时间",
    "開放時間",
    "交通",
    "游览",
    "遊覽",
)

_HOMEPAGE_FACT_UNIT_RE = re.compile(
    r"(\d{3,4}年|\d+(?:\.\d+)?\s*(?:平方公里|公顷|亩|米|公里|千米|米|万平方米|万人次|亿元|级|A))"
)

_HOMEPAGE_DISAMBIG_LINE_RE = re.compile(
    r"^\s*(?:[-*#\d.、]+\s*)?[^。\n]{1,42}[：:][^。\n]{0,120}(?:位于|位於|位在|坐落|地处|地處)",
    re.M,
)

_HOMEPAGE_PAREN_LOCATION_LINE_RE = re.compile(
    r"[\(（][^)）]{1,16}[\)）][，,]?(?:位于|位於|位在|坐落|地处|地處)"
)

_HOMEPAGE_INSECT_CONTEXT_RE = re.compile(r"(学名|學名|胡蜂|黄蜂|黃蜂|昆虫|昆蟲|本属包括|本屬包括|下属物种|下屬物種)")

_HOMEPAGE_STATION_CONTEXT_RE = re.compile(r"(地铁|地鐵|车站|車站|站台|出入口|接驳交通)")

_HOMEPAGE_NAVIGATION_MARKERS = (
    "登录",
    "註冊",
    "注册",
    "上一页",
    "下一页",
    "扫一扫",
    "版权所有",
    "网站地图",
    "分享到",
    "返回首页",
)

def _homepage_entity_tokens(entity_id: str) -> list[str]:
    tokens = _dedupe_terms([entity_id, *_entity_name_variants(entity_id)], limit=16)
    out: list[str] = []
    for token in tokens:
        key = _normalized_title(token)
        if key and len(key) >= 2 and key not in out:
            out.append(key)
    return out

def _homepage_fact_signal_count(text: str, entity_id: str) -> int:
    tokens = _homepage_entity_tokens(entity_id)
    seen: set[str] = set()
    count = 0
    for raw in re.split(r"[。！？!?；;\n]+", str(text or "")):
        sentence = re.sub(r"\s+", " ", raw).strip()
        if len(sentence) < 8 or len(sentence) > 260:
            continue
        if any(marker in sentence for marker in _HOMEPAGE_NAVIGATION_MARKERS):
            continue
        key = _normalized_title(sentence)
        if key in seen:
            continue
        mentions_entity = any(token and token in key for token in tokens)
        has_signal = any(marker in sentence for marker in _HOMEPAGE_FACT_MARKERS) or bool(
            _HOMEPAGE_FACT_UNIT_RE.search(sentence)
        )
        if mentions_entity or has_signal:
            seen.add(key)
            count += 1
    return count

def homepage_text_quality_issue(
    text: str,
    entity_id: str,
    *,
    require_fact_ready: bool = True,
) -> str:
    """公开入口：homepage 底稿文本质量门（download fetch 阶段与 plan 阶段共用）。"""
    return _homepage_text_quality_issue(text, entity_id, require_fact_ready=require_fact_ready)


def _homepage_text_quality_issue(
    text: str,
    entity_id: str,
    *,
    require_fact_ready: bool,
) -> str:
    """Return a blocking reason when homepage text cannot support a base draft."""
    body = re.sub(r"\s+", " ", str(text or "")).strip()
    if not body:
        return "empty_homepage_text"
    if require_fact_ready and len(body) < 80:
        return "homepage_text_too_short"
    head = body[:1800]
    if _HOMEPAGE_JSON_API_RE.search(head):
        return "raw_json_api_homepage"
    if any(marker.lower() in head.lower() for marker in _HOMEPAGE_REDIRECT_MARKERS):
        return "redirect_homepage"
    disambig_hits = len(_HOMEPAGE_DISAMBIG_LINE_RE.findall(str(text or "")[:5000]))
    parenthesized_location_hits = len(_HOMEPAGE_PAREN_LOCATION_LINE_RE.findall(str(text or "")[:5000]))
    location_mentions = len(re.findall(r"(?:位于|位於|位在|坐落|地处|地處)", head))
    if disambig_hits >= 3 or (
        any(marker in head for marker in _HOMEPAGE_DISAMBIG_MARKERS)
        and (disambig_hits >= 1 or parenthesized_location_hits >= 2 or location_mentions >= 3)
    ):
        return "disambiguation_homepage"
    if require_fact_ready and _HOMEPAGE_INSECT_CONTEXT_RE.search(head) and "蜂" not in entity_id:
        return "wrong_entity_context"
    if require_fact_ready and _HOMEPAGE_STATION_CONTEXT_RE.search(head) and not entity_id.endswith("站"):
        return "wrong_entity_context"
    if require_fact_ready and _homepage_fact_signal_count(body[:5000], entity_id) < 4:
        return "insufficient_homepage_facts"
    return ""
