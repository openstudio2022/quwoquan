"""非开放版权源（百度/搜狗百科等）的事实化压缩。

契约（百科主页结构化计划 · 非开放源压缩规则）：
- 全文 <= 1000 字：不压缩，原样保留。
- 1000 < 全文 <= 2000 字：轻度压缩，目标保留约 75% 字数。
- 全文 > 2000 字：事实化压缩，目标保留约 50% 字数。

策略是**句子级事实优选节选**（保结构、保顺序、不改写）：优先保留含实体名、
事实标记（位于/始建/面积/海拔/门票…）或数字单位的句子；每段首句保底。
语义改写（避免措辞侵权）由 AI 加工阶段在此节选结果上完成，代码层不造句。
"""
from __future__ import annotations

import re
from typing import Any

_FACT_MARKERS = (
    "位于", "位於", "坐落", "地处", "地處", "始建", "建于", "建於", "建成",
    "开放", "開放", "占地", "面积", "面積", "海拔", "全长", "全長", "长度",
    "宽度", "包括", "包含", "核心", "主要", "属于", "屬於", "国家级", "國家級",
    "AAAAA", "5A", "世界遗产", "世界遺產", "文化遗产", "自然遗产",
    "门票", "門票", "预约", "預約", "开放时间", "開放時間", "交通", "命名",
)

_FACT_UNIT_RE = re.compile(
    r"(\d{3,4}年|\d+(?:\.\d+)?\s*(?:平方公里|平方千米|公顷|亩|米|公里|千米|万平方米|万人次|亿元|层|座|处|个|种|株|只|级|A))"
)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?；;])")

# 结构行（标题/占位/引用块围栏）永远保留，不参与句子压缩。
_STRUCTURAL_LINE_RE = re.compile(r"^\s*(#{1,6}\s|:::|\[\[IMG:|asset://|[-*]\s|\d+\.\s|>\s|---\s*$)")


def compression_policy(char_count: int) -> tuple[str, float]:
    """返回 (policy 名, 保留比例目标)。"""
    if char_count <= 1000:
        return "none", 1.0
    if char_count <= 2000:
        return "light", 0.75
    return "factual_half", 0.5


def _sentence_score(sentence: str, entity_tokens: list[str]) -> int:
    score = 0
    if any(tok and tok in sentence for tok in entity_tokens):
        score += 2
    if any(marker in sentence for marker in _FACT_MARKERS):
        score += 2
    if _FACT_UNIT_RE.search(sentence):
        score += 1
    return score


def factual_compress_text(text: str, *, entity_name: str = "") -> dict[str, Any]:
    """按事实化压缩契约节选正文。

    返回 {text, policy, originalChars, compressedChars}；policy == "none" 时
    text 原样返回。结构行（标题/图占位/列表）不计入压缩、恒保留。
    """
    original = str(text or "")
    body_chars = len(re.sub(r"\s", "", original))
    policy, keep_ratio = compression_policy(body_chars)
    if policy == "none":
        return {
            "text": original,
            "policy": policy,
            "originalChars": body_chars,
            "compressedChars": body_chars,
        }

    entity_tokens = [t for t in re.split(r"[\s·、/（）()]+", str(entity_name or "")) if len(t) >= 2]
    target_chars = int(body_chars * keep_ratio)
    kept_chars = 0
    out_lines: list[str] = []

    for raw_line in original.split("\n"):
        line = raw_line.rstrip()
        if not line.strip():
            out_lines.append(raw_line)
            continue
        if _STRUCTURAL_LINE_RE.match(line):
            out_lines.append(raw_line)
            continue
        sentences = [s for s in _SENTENCE_SPLIT_RE.split(line) if s.strip()]
        if not sentences:
            out_lines.append(raw_line)
            continue
        kept: list[str] = []
        for idx, sentence in enumerate(sentences):
            slen = len(re.sub(r"\s", "", sentence))
            is_lead = idx == 0
            score = _sentence_score(sentence, entity_tokens)
            # 段落首句保底；事实句优先；预算耗尽后只留高分事实句。
            if is_lead or kept_chars < target_chars or score >= 3:
                if is_lead or score >= 1 or kept_chars < target_chars:
                    kept.append(sentence)
                    kept_chars += slen
        if kept:
            out_lines.append("".join(kept))

    compressed = re.sub(r"\n{3,}", "\n\n", "\n".join(out_lines)).strip()
    compressed_chars = len(re.sub(r"\s", "", compressed))
    return {
        "text": compressed,
        "policy": policy,
        "originalChars": body_chars,
        "compressedChars": compressed_chars,
    }
