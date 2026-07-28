"""Text admission helpers for entity homepage content.homepage."""

from __future__ import annotations

import re
from typing import Any

from core.content_source_registry import (
    homepage_primary_authority_rank,
    resolve_homepage_source_role,
)

# 主页主锚资格唯一由 registry 的三百科闭集裁决。
_HOMEPAGE_GUIDE_PENALTY = ("攻略", "游记", "评论", "点评", "小红书", "图虫", "摄影")
_HOMEPAGE_ALLOWED_LANES = ("homepage",)
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
_HOMEPAGE_FIGURE_BLOCK_RE = re.compile(
    r"(?ms)^:::(?:figure|figuregroup)\b[^\n]*\n.*?^:::[ \t]*$"
)
_HOMEPAGE_ASSET_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(asset://[^)]+\)")
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


def _dedupe_leading_entity_name(sentence: str, *, entity_name: str) -> str:
    """Remove only an accidental repeated H1/entity prefix from a summary.

    ``_split_fact_sentences`` may join a Markdown H1 with its opening sentence.
    The finalizer must not turn ``# 普陀山`` + ``普陀山，是...`` into the
    user-visible summary ``普陀山普陀山，是...``.  This is presentation cleanup,
    not a rewrite: only contiguous copies of the same leading entity label are
    collapsed and the source sentence remains otherwise unchanged.
    """

    cleaned = re.sub(r"^#+\s*", "", str(sentence or "").strip())
    name = str(entity_name or "").strip()
    if not name:
        return cleaned
    repeated = re.compile(rf"^{re.escape(name)}(?:[\s，,、:：-]*{re.escape(name)})+")
    match = repeated.match(cleaned)
    if not match:
        return cleaned
    return name + cleaned[match.end() :]


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


def load_homepage_base_draft_text(execution_id: str, source_ref: str) -> str:
    """Read the exact frozen homepage source body used for authoring.

    Homepage evidence is an encyclopedia page, so its semantic sections and
    facts must remain intact.  The article lane's generic draft loader prefers
    ``source.clean.md`` and extracts a short prose subset; using it here made a
    source pass discovery but fail the later homepage gate.  A homepage base
    source is therefore always its canonical ``source.md`` unit, with no
    fallback to a transformed representation.
    """
    from core.paths import execution_root

    normalized_ref = str(source_ref or "").strip()
    if not normalized_ref.endswith("/source.md"):
        return ""
    path = execution_root(execution_id) / normalized_ref
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _homepage_source_priority(meta: dict[str, Any]) -> int:
    lane = str(meta.get("researchLane") or "")
    if lane not in _HOMEPAGE_ALLOWED_LANES:
        return -1000
    source_text = _homepage_source_text(meta)
    lowered = source_text.casefold()
    if any(marker.casefold() in lowered for marker in _HOMEPAGE_GUIDE_PENALTY):
        return -1000
    role = resolve_homepage_source_role(
        source_kind=str(meta.get("sourceKind") or ""),
        url=str(meta.get("canonicalUrl") or meta.get("finalUrl") or meta.get("url") or ""),
        extractor=str(meta.get("extractor") or ""),
        policy_revision=str(meta.get("policyRevision") or ""),
    )
    if role != "primary":
        return 0
    return 100 - min(20, homepage_primary_authority_rank(str(meta.get("sourceKind") or "")) * 5)


def _homepage_base_source_issue_text(meta: dict[str, Any]) -> tuple[str, bool, bool]:
    source_kind = str(meta.get("sourceKind") or meta.get("platform") or meta.get("category") or "").strip()
    source_text = _homepage_source_text(meta)
    lowered = source_text.casefold()
    is_primary = _homepage_source_priority(meta) > 0
    is_author_experience = any(marker.casefold() in lowered for marker in _HOMEPAGE_GUIDE_PENALTY)
    return source_kind, is_primary, is_author_experience


def homepage_base_draft_readiness(
    meta: dict[str, Any],
    text: str,
    *,
    entity_name: str,
    aliases: tuple[str, ...] | list[str] = (),
    unit_dir: Any = None,
    minimum_body_chars: int,
    minimum_fact_count: int,
    minimum_fact_chars: int,
) -> dict[str, Any]:
    """Return the shared admission verdict for entity homepage base drafts.

    在 registry 权威 + 事实密度之上叠加 homepage_source_judge 语义准入：
    标题精确命中实体 → 直接通过；门户首页/父级行政区替代页 → 确定性拒绝；
    灰区来源 fail-closed，等待 Agent 写回 ``source.judge.json``（结构化 verdict）。
    """
    from core.homepage_source_judge import ADMISSION_PRIMARY, source_judge_admission

    priority = _homepage_source_priority(meta)
    if priority <= 0:
        return {
            "ready": False,
            "priority": priority,
            "factCount": 0,
            "issue": "not homepage primary authority source",
        }
    source_text = str(text or "").strip()
    if not source_text:
        return {
            "ready": False,
            "priority": priority,
            "factCount": 0,
            "issue": "empty source text",
        }
    admission = source_judge_admission(
        entity_name=entity_name,
        aliases=tuple(aliases or ()),
        meta=meta,
        source_text=source_text,
        unit_dir=unit_dir,
    )
    if str(admission.get("decision") or "") != ADMISSION_PRIMARY:
        return {
            "ready": False,
            "priority": priority,
            "factCount": 0,
            "issue": str(admission.get("issue") or "homepage source judge rejected"),
            "judge": admission,
        }
    if isinstance(minimum_body_chars, bool) or minimum_body_chars < 1:
        raise ValueError("homepage minimum_body_chars must be a positive integer")
    if isinstance(minimum_fact_count, bool) or minimum_fact_count < 1:
        raise ValueError("homepage minimum_fact_count must be a positive integer")
    if isinstance(minimum_fact_chars, bool) or minimum_fact_chars < 1:
        raise ValueError("homepage minimum_fact_chars must be a positive integer")
    body_chars = len(re.sub(r"\s+", "", _strip_frontmatter(source_text)))
    facts = _split_fact_sentences(source_text[:4000], entity_name=entity_name)
    fact_count = len(facts)
    fact_chars = sum(len(fact) for fact in facts)
    ready = (
        body_chars >= minimum_body_chars
        and fact_count >= minimum_fact_count
        and fact_chars >= minimum_fact_chars
    )
    return {
        "ready": ready,
        "priority": priority,
        "bodyChars": body_chars,
        "factCount": fact_count,
        "factChars": fact_chars,
        "issue": (
            ""
            if ready
            else (
                f"usable source chars {body_chars}<{minimum_body_chars}"
                if body_chars < minimum_body_chars
                else (
                    f"usable facts {fact_count}<{minimum_fact_count}"
                    if fact_count < minimum_fact_count
                    else f"usable fact chars {fact_chars}<{minimum_fact_chars}"
                )
            )
        ),
        "judge": admission,
    }


def _strip_frontmatter(text: str) -> str:
    raw = str(text or "").strip()
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) == 3:
            raw = parts[2].strip()
    # Figure blocks are structural media anchors.  Their placeholder changes
    # after source assets are bound, so treating their syntax as prose made one
    # source pass planning and fail its later download gate.
    raw = _HOMEPAGE_FIGURE_BLOCK_RE.sub("\n", raw)
    raw = _HOMEPAGE_ASSET_IMAGE_RE.sub("", raw)
    # Headings are navigation labels, not facts. Removing just the Markdown
    # marker used to concatenate "## 概况" with the opening sentence after
    # whitespace compaction, leaking a malformed entity summary.
    raw = re.sub(r"^=+\s*.*?\s*=+\s*$", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"^#{1,6}\s+.*$", "", raw, flags=re.MULTILINE)
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
        cleaned = _dedupe_leading_entity_name(str(fact or ""), entity_name=name)
        if cleaned and name and name in cleaned:
            return (cleaned.rstrip("。") + "。")[:180]
    for fact in facts:
        cleaned = _dedupe_leading_entity_name(str(fact or ""), entity_name=name)
        if cleaned:
            return (cleaned.rstrip("。") + "。")[:180]
    body = _strip_frontmatter(base_text)
    for chunk in _HOMEPAGE_TERMINAL_SPLIT_RE.findall(body):
        sentence = re.sub(r"\s+", "", str(chunk or "")).strip(" \t\r\n，,、：:；;>")
        sentence = _dedupe_leading_entity_name(sentence, entity_name=name)
        if len(sentence) >= 8 and not any(marker in sentence for marker in _HOMEPAGE_FACT_NOISE_MARKERS):
            return (sentence[:120].rstrip("。") + "。")
    return ""
