"""Base-draft fidelity and anti-copying quality gates."""
from __future__ import annotations

import re
from collections.abc import Mapping

from content.post.base_draft import (
    FIDELITY_MAX,
    FIDELITY_MIN,
    _NGRAM,
    _normalize_embedded_newlines,
    _readable_body,
    _strip_source_meta,
    base_draft_is_adaptable,
)

OUT_OF_DRAFT_MAX_RATIO = 0.78
CROSS_SOURCE_OVERLAP_MIN_RUN = 80


def _char_ngrams(text: str, size: int = _NGRAM) -> set[str]:
    return ({text} if text else set()) if len(text) < size else {
        text[index : index + size] for index in range(len(text) - size + 1)
    }


def _normalized_pair(article: str, base_text: str, carrier: str) -> tuple[str, str]:
    body = _readable_body(article)
    return body, _strip_source_meta(base_text, carrier=carrier, body_len=len(body), body=body)


def base_draft_similarity(article: str, base_text: str, *, carrier: str = "article") -> float:
    body, base = _normalized_pair(article, base_text, carrier)
    base_grams = _char_ngrams(base)
    return len(base_grams & _char_ngrams(body)) / len(base_grams) if body and base_grams else 0.0


def base_draft_fidelity_issues(
    article: str,
    base_text: str,
    *,
    min_ratio: float = FIDELITY_MIN,
    max_ratio: float = FIDELITY_MAX,
    carrier: str = "article",
    source_use_mode: str = "licensed_adaptation",
) -> list[str]:
    if not base_draft_is_adaptable(source_use_mode):
        return []
    body, base = _normalized_pair(article, base_text, carrier)
    if not body or not base:
        return []
    similarity = base_draft_similarity(article, base_text, carrier=carrier)
    if similarity < min_ratio:
        return [
            f"base draft fidelity {similarity * 100:.1f}% < {int(min_ratio * 100)}% "
            "(底稿留存率过低，疑似脱离底稿/从零另写，应在底稿基础上适度润色而非重写)"
        ]
    if similarity > max_ratio:
        return [
            f"base draft fidelity {similarity * 100:.1f}% > {int(max_ratio * 100)}% "
            "(零加工整篇逐字照搬，至少需完成去语病/错字、私人信息脱敏替代与作者人设用词语气适配)"
        ]
    return []


def out_of_draft_ratio(article: str, base_text: str, *, carrier: str = "article") -> float:
    body, base = _normalized_pair(article, base_text, carrier)
    body_grams = _char_ngrams(body)
    return len(body_grams - _char_ngrams(base)) / len(body_grams) if body_grams else 0.0


def out_of_draft_issues(
    article: str,
    base_text: str,
    *,
    max_ratio: float = OUT_OF_DRAFT_MAX_RATIO,
    carrier: str = "article",
    source_use_mode: str = "licensed_adaptation",
) -> list[str]:
    if not base_draft_is_adaptable(source_use_mode):
        return []
    body, base = _normalized_pair(article, base_text, carrier)
    if not body or not base:
        return []
    ratio = out_of_draft_ratio(article, base_text, carrier=carrier)
    return (
        [
            f"out-of-draft content ratio {ratio * 100:.1f}% > {int(max_ratio * 100)}% "
            "(底稿外补写过多，疑似大块脱稿/拼接，应回到底稿基础轻改而非另起炉灶)"
        ]
        if ratio > max_ratio
        else []
    )


def cross_source_overlap_issues(
    article: str,
    base_text: str,
    other_source_texts: Mapping[str, str],
    *,
    min_run: int = CROSS_SOURCE_OVERLAP_MIN_RUN,
    carrier: str = "article",
) -> list[str]:
    body, base = _normalized_pair(article, base_text, carrier)
    if len(body) < min_run:
        return []
    body_runs = {body[index : index + min_run] for index in range(len(body) - min_run + 1)}
    if len(base) >= min_run:
        body_runs -= {base[index : index + min_run] for index in range(len(base) - min_run + 1)}
    for ref, text in other_source_texts.items():
        source = re.sub(r"\s+", "", _normalize_embedded_newlines(str(text or "")))
        if len(source) < min_run:
            continue
        overlap = body_runs & {source[index : index + min_run] for index in range(len(source) - min_run + 1)}
        if overlap:
            sample = next(iter(overlap))
            return [
                f"crossSourceOverlap: 正文出现 >= {min_run} 连续字与非底稿来源 {ref} 逐字重合"
                f"（疑似拼接照搬非底稿来源），样本『{sample[:24]}…』"
            ]
    return []
