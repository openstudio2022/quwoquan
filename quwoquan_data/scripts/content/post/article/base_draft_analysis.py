"""Readable-body and length analysis for article base drafts."""
from __future__ import annotations
import re
from typing import Sequence
from content.post.article.base_draft import (
    ARTICLE_MIN_BASE_DRAFT_CHARS, _looks_like_noise_line, base_draft_is_adaptable,
)

FIDELITY_MIN = 0.55

FIDELITY_MAX = 0.995

_NGRAM = 3

_RELEVANT_BASE_MIN_CHARS = 320

_RELEVANT_BASE_MIN_RATIO = 0.55

_RELEVANT_BASE_MULTI_TOPIC_MIN_RATIO = 0.25

_RELEVANT_LINE_MIN_SIMILARITY = 0.18

_ARTICLE_BASE_BODY_RATIO = 0.72

_FIGURE_RE = re.compile(r"(?ms)^:::figure.*?:::")

_ASSET_RE = re.compile(r"asset://[^\s)]+")

_GALLERY_BASE_TARGET_CHARS = 1000

_GALLERY_BASE_BODY_RATIO = 0.7

def _normalize_embedded_newlines(text: str) -> str:
    """兼容运行时/测试里以字面量 \\n 落盘或拼接的正文。"""
    if "\\n" not in text:
        return text
    return text.replace("\\r\\n", "\n").replace("\\n", "\n")

def _readable_body(article: str) -> str:
    """剥离 figure 块/asset 引用/标题井号后的可读正文（用于贴合度比较）。"""
    article = _normalize_embedded_newlines(article)
    text = _FIGURE_RE.sub("", article)
    text = _ASSET_RE.sub("", text)
    text = re.sub(r"(?m)^#{1,6}\s*", "", text)
    return re.sub(r"\s+", "", text)

def _base_excerpt_for_image(text: str, *, body_len: int) -> str:
    """画报正文较短，只要求贴住底稿前段主线，不强求覆盖整篇长底稿。"""
    text = _normalize_embedded_newlines(text)
    source_chars = len(re.sub(r"\s+", "", text))
    if _GALLERY_BASE_BODY_RATIO > 0:
        target_chars = int(body_len / _GALLERY_BASE_BODY_RATIO)
    else:
        target_chars = int(body_len or 0)
    target_chars = max(1, min(source_chars, target_chars))
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        return text[:target_chars]
    picked: list[str] = []
    total = 0
    for paragraph in paragraphs:
        chars = len(re.sub(r"\s+", "", paragraph))
        if picked and total >= target_chars:
            break
        if picked and body_len > 0 and total >= int(body_len * 0.9):
            break
        if picked and total + chars > target_chars:
            current_gap = abs(target_chars - total)
            expanded_gap = abs(target_chars - (total + chars))
            if current_gap <= expanded_gap:
                break
        picked.append(paragraph)
        total += chars
    return "\n\n".join(picked)

def _base_comparison_lines(text: str) -> list[str]:
    """用于贴合度比较的底稿行：去掉来源头、平台壳、广告和纯导航噪声。"""
    text = _normalize_embedded_newlines(text)
    kept: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            kept.append("")
            continue
        low = stripped.lower()
        if low.startswith(("license", "alloweduse", "credit", "url", "source", "title:", "图片来源", "授权")):
            continue
        if _looks_like_noise_line(stripped):
            continue
        kept.append(stripped)
    return kept

def _compact_lines(lines: Sequence[str]) -> str:
    return re.sub(r"\s+", "", "\n".join(lines).strip())

def _cap_relevant_lines_to_body(scored_lines: Sequence[tuple[int, float, str]], *, body_len: int) -> str:
    if not scored_lines:
        return ""
    ordered_lines = [line for _index, _score, line in sorted(scored_lines, key=lambda item: item[0])]
    compact = _compact_lines(ordered_lines)
    if not body_len:
        return compact
    target_chars = int(body_len / _ARTICLE_BASE_BODY_RATIO) if _ARTICLE_BASE_BODY_RATIO > 0 else body_len
    target_chars = max(_RELEVANT_BASE_MIN_CHARS, target_chars)
    if len(compact) <= target_chars:
        return compact
    picked_rows: list[tuple[int, str]] = []
    total = 0
    for index, _score, line in sorted(scored_lines, key=lambda item: item[1], reverse=True):
        chars = len(re.sub(r"\s+", "", line))
        if picked_rows and total >= target_chars:
            break
        if picked_rows and total + chars > target_chars:
            current_gap = abs(target_chars - total)
            expanded_gap = abs(target_chars - (total + chars))
            if current_gap <= expanded_gap:
                break
        picked_rows.append((index, line))
        total += chars
    picked = [line for _index, line in sorted(picked_rows, key=lambda item: item[0])]
    return _compact_lines(picked) or compact[:target_chars]

def _relevant_base_excerpt(base_lines: Sequence[str], body: str) -> str:
    """在长底稿含广告/跨城支线时，用主体保留段落作为比较窗口。

    候选段落覆盖清洗底稿的足够比例时直接启用。对于多城/多主题游记，
    如果相关段占比偏低但自身与正文仍达到贴合度下限，也启用相关段；
    只复用少量关键词的成稿仍会回退到完整清洗底稿并触发低贴合度。
    """
    clean_base = _compact_lines(base_lines)
    if len(clean_base) < _RELEVANT_BASE_MIN_CHARS or not body:
        return clean_base
    body_grams = _char_ngrams(body)
    selected: list[tuple[int, float, str]] = []
    selected_chars = 0
    for index, line in enumerate(base_lines):
        compact = re.sub(r"\s+", "", line)
        grams = _char_ngrams(compact)
        if not grams:
            continue
        overlap = len(grams & body_grams) / len(grams)
        if overlap >= _RELEVANT_LINE_MIN_SIMILARITY:
            selected.append((index, overlap, line))
            selected_chars += len(compact)
    if selected_chars >= _RELEVANT_BASE_MIN_CHARS:
        selected_base = _cap_relevant_lines_to_body(selected, body_len=len(body))
        selected_ratio = selected_chars / len(clean_base)
        selected_grams = _char_ngrams(selected_base)
        selected_similarity = len(selected_grams & body_grams) / len(selected_grams) if selected_grams else 0.0
        if selected_ratio >= _RELEVANT_BASE_MIN_RATIO or (
            selected_ratio >= _RELEVANT_BASE_MULTI_TOPIC_MIN_RATIO
            and selected_similarity >= FIDELITY_MIN
        ):
            return selected_base
    return clean_base

def _strip_source_meta(text: str, *, carrier: str = "article", body_len: int = 0, body: str = "") -> str:
    """去掉底稿里的 license/credit/url/平台噪声，并按载体裁切公平比较窗口。"""
    base_lines = _base_comparison_lines(text)
    filtered = "\n".join(base_lines).strip()
    if carrier == "image" and filtered:
        filtered = _base_excerpt_for_image(filtered, body_len=body_len)
        return re.sub(r"\s+", "", filtered)
    return _relevant_base_excerpt(base_lines, body)

def _char_ngrams(text: str, n: int = _NGRAM) -> set[str]:
    """Shared n-grams for relevance-window selection inside this module."""
    if len(text) < n:
        return {text} if text else set()
    return {text[index : index + n] for index in range(len(text) - n + 1)}

def clean_base_draft_length(base_text: str) -> int:
    """底稿去平台噪声后的可读正文字数（去空白），用于派生 light-edit 字数目标。

    与 `baseDraftFidelity` 清洗口径同源（`_base_comparison_lines`），保证字数目标与保真度
    分母一致：成稿长度 ≈ 清洗底稿长度时，逐句轻改即可达 fidelity 下限。
    """
    return len(_compact_lines(_base_comparison_lines(str(base_text or ""))))

def base_aware_word_count(
    base_text: str,
    *,
    carrier: str = "article",
    source_use_mode: str = "licensed_adaptation",
) -> dict[str, int] | None:
    """Licensed light-edit word counts must follow the base-draft length.

    根因实测：底稿 ~8900 字、`wordCount` 上限 1600 时，成稿最多覆盖底稿 ~18% 三连，fidelity
    必崩（成稿被逼压缩+重写）。light-edit 文章应整篇保留清洗底稿，故字数目标按清洗底稿长度派生。
    `image/gallery`（短配文）与 factual/blocked 等非改编源返回 None（沿用默认，不设底稿字数门）。
    """
    if str(carrier or "").lower() == "image":
        return None
    if not base_draft_is_adaptable(source_use_mode):
        return None
    clean_len = clean_base_draft_length(base_text)
    if clean_len < ARTICLE_MIN_BASE_DRAFT_CHARS:
        return None
    lo = max(ARTICLE_MIN_BASE_DRAFT_CHARS, int(clean_len * 0.62))
    hi = max(lo + 600, int(clean_len * 1.12))
    return {"min": lo, "max": hi}
