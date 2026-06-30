"""Text admission helpers for entity homepage build."""

from __future__ import annotations

import re
from typing import Any

# P3 三类解耦：实体主页 base draft 主源【只来自百科】。仅百科种类授予 primary 资格，
# 官网/官方一律降为 supporting（priority 0，可补事实但不得作 primaryEvidenceRef）。
_HOMEPAGE_PRIMARY_KIND_BONUS = (
    ("维基百科", 120),
    ("wikipedia", 120),
    ("百度百科", 110),
    ("搜狗百科", 105),
    ("字节百科", 100),
    ("百科", 95),
)
_HOMEPAGE_SUPPORT_ONLY_MARKERS = ("政府", "文旅", "政务", "gov.cn", "景区官网", "官网", "官方", "official")
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
    # 只有百科类目授予 primary；official_site 不再给 primary（已在 support-only markers 归 0）。
    if category == "encyclopedia":
        priority = max(priority, 85)
    return priority


def _homepage_base_source_issue_text(meta: dict[str, Any]) -> tuple[str, bool, bool]:
    source_kind = str(meta.get("sourceKind") or meta.get("platform") or meta.get("category") or "").strip()
    source_text = _homepage_source_text(meta)
    lowered = source_text.casefold()
    is_primary = _homepage_source_priority(meta) > 0
    is_author_experience = any(marker.casefold() in lowered for marker in _HOMEPAGE_GUIDE_PENALTY)
    return source_kind, is_primary, is_author_experience


def homepage_base_draft_readiness(meta: dict[str, Any], text: str, *, entity_name: str) -> dict[str, Any]:
    """Return the shared admission verdict for entity homepage base drafts."""
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
    if has_signal and any(token in sentence for token in _HOMEPAGE_SPATIAL_PRACTICAL_MARKERS) and len(sentence) >= 18:
        return True
    if has_unit_fact and any(token in sentence for token in _HOMEPAGE_SPATIAL_PRACTICAL_MARKERS) and len(sentence) >= 12:
        return True
    if has_signal and _HOMEPAGE_LOCATION_RE.search(sentence) and len(sentence) >= 10:
        return True
    return False


def _homepage_summary(name: str, facts: list[str], *, base_text: str = "") -> str:
    """以原文为基础派生主页摘要，绝不使用捏造模板或领域关键词补全。

    取材优先级（全部来自原文/底稿）：
    1. 提及实体名的原文事实句；
    2. 原文首个事实句；
    3. 原文正文首句（剥离 frontmatter/标题/噪声行）。
    三者皆无则返回空串，由下游按原文重新派生，不再凭空生成摘要。
    """
    for fact in facts:
        cleaned = str(fact or "").strip()
        if cleaned and name and name in cleaned:
            return (cleaned.rstrip("。") + "。")[:180]
    for fact in facts:
        cleaned = str(fact or "").strip()
        if cleaned:
            return (cleaned.rstrip("。") + "。")[:180]
    body = _strip_frontmatter(base_text)
    for chunk in _HOMEPAGE_TERMINAL_SPLIT_RE.findall(body):
        sentence = re.sub(r"\s+", "", str(chunk or "")).strip(" \t\r\n，,、：:；;>")
        if len(sentence) >= 8 and not any(marker in sentence for marker in _HOMEPAGE_FACT_NOISE_MARKERS):
            return (sentence[:120].rstrip("。") + "。")
    return ""
