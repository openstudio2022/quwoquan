"""Entity aliasing and text matching helpers for auto research."""
from __future__ import annotations

import re
import urllib.parse

from core.localization import fold_to_simplified

def _normalized_title(value: str) -> str:
    return re.sub(
        r"[\s_（）()《》〈〉·•,，。:：;；-]+",
        "",
        fold_to_simplified(str(value or "")),
    ).lower()

def _dedupe_terms(values: list[str] | tuple[str, ...], *, limit: int = 12) -> list[str]:
    out: list[str] = []
    for raw in values:
        value = str(raw or "").strip()
        if not value:
            continue
        key = _normalized_title(value)
        if not key or any(_normalized_title(existing) == key for existing in out):
            continue
        out.append(value)
        if len(out) >= limit:
            break
    return out

_EN_ALIAS_SUFFIX_RE = re.compile(
    r"\b(?:scenic\s+area|scenic\s+zone|tourist\s+area|tourist\s+zone|national\s+park|"
    r"national\s+geopark|geo\s+park|geopark|mountains?|park|area|reserve)\b.*$",
    re.I,
)

def _expanded_entity_aliases(values: list[str] | tuple[str, ...], *, limit: int = 24) -> list[str]:
    expanded: list[str] = []
    for raw in values:
        value = str(raw or "").strip()
        if not value:
            continue
        expanded.append(value)
        if re.search(r"[A-Za-z]", value):
            stripped = _EN_ALIAS_SUFFIX_RE.sub("", value).strip(" ,;:-()")
            if stripped and stripped != value and len(_normalized_title(stripped)) >= 4:
                expanded.append(stripped)
    return _dedupe_terms(expanded, limit=limit)

def _entity_name_variants(entity_id: str) -> list[str]:
    """Conservative aliases for official scenic-area names.

    National scenic-area names often carry administrative prefixes, suffixes,
    or multiple sub-sites. Discovery should search those names, while the later
    candidate and asset gates still enforce entity relevance and rights.
    """
    raw = str(entity_id or "").strip()
    if not raw:
        return []
    variants: list[str] = [raw]
    cleaned = re.sub(r"[（(].*?[）)]", "", raw).strip()
    if cleaned and cleaned != raw:
        variants.append(cleaned)
    suffixes = (
        "旅游度假区",
        "文化旅游区",
        "风景名胜区",
        "风景旅游区",
        "旅游景区",
        "风景区",
        "景区",
        "公园",
        "旅游区",
    )
    for base in list(variants):
        for suffix in suffixes:
            if base.endswith(suffix) and len(base) > len(suffix) + 1:
                stripped = base[: -len(suffix)].strip(" -—－·")
                if stripped:
                    variants.append(stripped)
    split_pattern = r"[—－–\-、,，/]|及周围|及|·"
    for base in list(variants):
        for part in re.split(split_pattern, base):
            part = part.strip(" -—－·")
            if len(_normalized_title(part)) >= 3:
                variants.append(part)
    admin_prefix = re.match(r"^([\u4e00-\u9fa5]{2,8}(?:市|区|县|旗|州|盟))(.{3,})$", cleaned)
    if admin_prefix:
        variants.append(admin_prefix.group(2).strip())
    return _expanded_entity_aliases(variants, limit=12)

def _title_matches_entity(title: str, entity_id: str) -> bool:
    title_key = _normalized_title(title)
    entity_key = _normalized_title(entity_id)
    if not title_key or not entity_key:
        return False
    if title_key == entity_key:
        return True
    if entity_key in title_key:
        return True
    return title_key in entity_key and len(title_key) >= max(3, round(len(entity_key) * 0.75))

_WIKI_TITLE_ALLOWED_SUFFIXES = (
    "旅游景区",
    "景区",
    "风景区",
    "风景名胜区",
    "国家级风景名胜区",
    "国家公园",
    "自然保护区",
    "保护区",
    "森林公园",
    "地质公园",
    "公园",
    "古城",
    "古镇",
)

_WIKI_TITLE_BLOCKED_SUBSTITUTES = (
    "机场",
    "车站",
    "火车站",
    "高铁站",
    "客运站",
    "镇",
    "乡",
    "村",
    "街道",
    "县",
    "市",
    "区",
    "学校",
    "大学",
    "公司",
)

_WIKI_TITLE_ALLOWED_ALIAS_EXACT_2CHAR = {
    "太湖",
    "西湖",
    "泰山",
    "华山",
    "黄山",
    "嵩山",
    "衡山",
    "恒山",
    "庐山",
    "崂山",
}

_WIKI_ADMIN_DISAMBIGUATION_MARKERS = (
    "省",
    "市",
    "自治区",
    "特别行政区",
)


def _wiki_admin_disambiguation_matches(title: str, entity_id: str) -> bool:
    """Accept only an exact entity title plus an administrative qualifier."""
    raw_title = fold_to_simplified(str(title or "")).strip()
    raw_entity = fold_to_simplified(str(entity_id or "")).strip()
    if not raw_title or not raw_entity:
        return False
    match = re.fullmatch(
        rf"{re.escape(raw_entity)}\s*[（(]\s*([^（）()]+?)\s*[）)]",
        raw_title,
    )
    if match is None:
        return False
    qualifier = match.group(1).strip()
    return 2 <= len(qualifier) <= 12 and qualifier.endswith(
        _WIKI_ADMIN_DISAMBIGUATION_MARKERS
    )

def _wiki_title_matches_entity(title: str, entity_id: str) -> bool:
    """百科页标题必须是实体本身或景区类同义扩展，不能是机场/镇/城市替代页。"""
    if _wiki_admin_disambiguation_matches(title, entity_id):
        return True
    title_key = _normalized_title(title)
    entity_key = _normalized_title(entity_id)
    if not title_key or not entity_key:
        return False
    if title_key == entity_key:
        return True
    if title_key.startswith(entity_key):
        suffix = title_key[len(entity_key):]
        allowed = {_normalized_title(item) for item in _WIKI_TITLE_ALLOWED_SUFFIXES}
        if suffix in allowed:
            return True
        if any(marker in suffix for marker in _WIKI_TITLE_BLOCKED_SUBSTITUTES):
            return False
        return False
    if title_key.endswith(entity_key):
        prefix = title_key[: -len(entity_key)]
        return 0 < len(prefix) <= 4 and not any(
            marker in prefix for marker in _WIKI_TITLE_BLOCKED_SUBSTITUTES
        )
    return False

def _wiki_resolved_title_matches_entity(
    title: str,
    entity_id: str,
    *,
    entity_aliases: list[str] | tuple[str, ...] = (),
) -> bool:
    """Validate a resolved wiki title against the canonical entity.

    Short aliases are useful for discovery, but homepage resolution must not let
    generic aliases drift to another object, for example 北京奥林匹克公园 -> 悉尼奥林匹克公园.
    """
    if _wiki_title_matches_entity(title, entity_id):
        return True
    title_key = _normalized_title(title)
    entity_key = _normalized_title(entity_id)
    if not title_key or not entity_key:
        return False
    allowed_suffixes = {_normalized_title(item) for item in _WIKI_TITLE_ALLOWED_SUFFIXES}
    allowed_suffixes.update({"遗址", "遺址", "故里", "古镇", "古鎮", "湿地", "濕地"})
    for alias in entity_aliases:
        alias_key = _normalized_title(alias)
        if not alias_key or alias_key == entity_key or alias_key not in entity_key:
            continue
        if len(alias_key) < 3 and alias_key not in _WIKI_TITLE_ALLOWED_ALIAS_EXACT_2CHAR:
            continue
        if title_key == alias_key:
            return True
        if _wiki_admin_disambiguation_matches(title, alias):
            return True
        if title_key.startswith(alias_key):
            suffix = title_key[len(alias_key):]
            if suffix in allowed_suffixes:
                return True
            if any(marker in suffix for marker in _WIKI_TITLE_BLOCKED_SUBSTITUTES):
                return False
    return False

def _text_mentions_entity(
    value: str,
    entity_id: str,
    *,
    entity_aliases: list[str] | tuple[str, ...] = (),
) -> bool:
    text = urllib.parse.unquote(str(value or ""))
    text = re.sub(r"[_/\\\-]+", " ", text)
    if _title_matches_entity(text, entity_id):
        return True
    text_key = _normalized_title(text)
    for alias in entity_aliases:
        alias_key = _normalized_title(alias)
        if alias_key and (alias_key in text_key or _title_matches_entity(text, alias)):
            return True
    return False
