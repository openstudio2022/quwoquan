"""Homepage source-text quality rules."""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

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
    "可能是指",
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

# A concise MediaWiki disambiguation page can flatten its entries into one
# paragraph.  In that case neither list nor location heuristics are reliable,
# but the leading "<term> can refer to:" declaration remains authoritative.
_HOMEPAGE_DISAMBIGUATION_LEAD_RE = re.compile(
    r"^\s*[^。\n]{1,64}(?:可以|可|可能|可能是)指[：:]",
    re.M,
)

# A rendered MediaWiki disambiguation page commonly contains a short
# "可以指" lead followed by linked list items.  Those list items do not
# necessarily repeat location prose, so they are not covered by the more
# specific location-line expression above.
_HOMEPAGE_LIST_ITEM_RE = re.compile(
    r"^\s*(?:[-*#•]\s+|\d+[.、]\s+).{2,120}$",
    re.M,
)

_HOMEPAGE_PARENTHESES_LABEL_RE = re.compile(
    r"(?:^|[，,、;；\s])[^。\n（）()]{1,24}[（(][^)）]{1,24}[)）]"
)

_HOMEPAGE_PAREN_LOCATION_LINE_RE = re.compile(
    r"[\(（][^)）]{1,16}[\)）][，,]?(?:位于|位於|位在|坐落|地处|地處)"
)

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


class HomepageTextQualityIssue(str, Enum):
    """Closed rejection reasons for a homepage primary-source text."""

    EMPTY = "empty_homepage_text"
    TOO_SHORT = "homepage_text_too_short"
    RAW_JSON = "raw_json_api_homepage"
    REDIRECT = "redirect_homepage"
    DISAMBIGUATION = "disambiguation_homepage"
    INSUFFICIENT_FACTS = "insufficient_homepage_facts"


@dataclass(frozen=True, slots=True)
class HomepageTextQualityVerdict:
    """Typed primary-source text admission result shared by plan and fetch."""

    issue: HomepageTextQualityIssue | None

    @property
    def accepted(self) -> bool:
        return self.issue is None

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

def assess_homepage_text_quality(
    text: str,
    entity_id: str,
    *,
    require_fact_ready: bool = True,
) -> HomepageTextQualityVerdict:
    """Return the one typed admission verdict used before and after download."""

    raw_body = str(text or "")
    compact_body = re.sub(r"\s+", " ", raw_body).strip()
    if not compact_body:
        return HomepageTextQualityVerdict(HomepageTextQualityIssue.EMPTY)
    if require_fact_ready and len(compact_body) < 80:
        return HomepageTextQualityVerdict(HomepageTextQualityIssue.TOO_SHORT)
    head = compact_body[:1800]
    if _HOMEPAGE_JSON_API_RE.search(head):
        return HomepageTextQualityVerdict(HomepageTextQualityIssue.RAW_JSON)
    if any(marker.lower() in head.lower() for marker in _HOMEPAGE_REDIRECT_MARKERS):
        return HomepageTextQualityVerdict(HomepageTextQualityIssue.REDIRECT)
    source_window = str(text or "")[:5000]
    disambig_hits = len(_HOMEPAGE_DISAMBIG_LINE_RE.findall(source_window))
    list_item_hits = len(_HOMEPAGE_LIST_ITEM_RE.findall(source_window))
    parenthesized_label_hits = len(_HOMEPAGE_PARENTHESES_LABEL_RE.findall(source_window))
    parenthesized_location_hits = len(_HOMEPAGE_PAREN_LOCATION_LINE_RE.findall(source_window))
    location_mentions = len(re.findall(r"(?:位于|位於|位在|坐落|地处|地處)", head))
    has_disambiguation_lead = any(marker in source_window[:600] for marker in _HOMEPAGE_DISAMBIG_MARKERS)
    if _HOMEPAGE_DISAMBIGUATION_LEAD_RE.search(source_window[:600]) or disambig_hits >= 3 or (
        has_disambiguation_lead
        and (
            disambig_hits >= 1
            or list_item_hits >= 2
            or parenthesized_label_hits >= 3
            or parenthesized_location_hits >= 2
            or location_mentions >= 3
        )
    ):
        return HomepageTextQualityVerdict(HomepageTextQualityIssue.DISAMBIGUATION)
    # Preserve newlines while counting facts.  Structured encyclopedia
    # frontends often emit one fact per line without terminal punctuation;
    # flattening first turns valid evidence into one overlong sentence that the
    # signal counter intentionally ignores.
    if require_fact_ready and _homepage_fact_signal_count(raw_body[:5000], entity_id) < 4:
        return HomepageTextQualityVerdict(HomepageTextQualityIssue.INSUFFICIENT_FACTS)
    return HomepageTextQualityVerdict(None)


def homepage_text_quality_issue(
    text: str,
    entity_id: str,
    *,
    require_fact_ready: bool = True,
) -> str:
    """String projection for persisted source quality facts."""

    verdict = assess_homepage_text_quality(
        text,
        entity_id,
        require_fact_ready=require_fact_ready,
    )
    return verdict.issue.value if verdict.issue is not None else ""
