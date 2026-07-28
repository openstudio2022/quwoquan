"""Base-draft fidelity and anti-copying quality gates."""
from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from content.post.article.base_draft_analysis import (
    FIDELITY_MAX,
    FIDELITY_MIN,
    _NGRAM,
    _normalize_embedded_newlines,
    _readable_body,
    _strip_source_meta,
)
from content.post.article.base_draft import base_draft_is_adaptable

OUT_OF_DRAFT_MAX_RATIO = 0.78
CROSS_SOURCE_OVERLAP_MIN_RUN = 80
FACTUAL_REFERENCE_MAX_NEAR_COPY_RATIO = 0.55
FACTUAL_REFERENCE_EXACT_RUN_CHARS = 80


@dataclass(frozen=True, slots=True)
class CommercialNearCopyGate:
    """Typed, replayable copyright gate for one commercial article."""

    source_use_mode: str
    article_containment_ratio: float
    exact_run_sample: str
    issues: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.issues

    def to_review_check(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "issues": list(self.issues),
            "suggestions": (
                [
                    "只保留可核验事实并重新组织结构与表达；删除来源连续长句、原段落顺序和近似复写。"
                ]
                if self.issues
                else []
            ),
            "evidence": {
                "sourceUseMode": self.source_use_mode,
                "articleContainmentRatio": round(self.article_containment_ratio, 6),
                "exactRunChars": len(self.exact_run_sample),
            },
        }


def _char_ngrams(text: str, size: int = _NGRAM) -> set[str]:
    return ({text} if text else set()) if len(text) < size else {
        text[index : index + size] for index in range(len(text) - size + 1)
    }


def _ngram_containment(body: str, source: str, *, size: int = _NGRAM) -> float:
    if not body:
        return 0.0
    if len(body) < size:
        return 1.0 if body in source else 0.0
    body_grams = Counter(
        body[index : index + size] for index in range(len(body) - size + 1)
    )
    source_grams = Counter(
        source[index : index + size] for index in range(max(0, len(source) - size + 1))
    )
    overlap = sum(
        min(count, source_grams.get(gram, 0))
        for gram, count in body_grams.items()
    )
    return overlap / sum(body_grams.values())


def _exact_run_sample(
    body: str,
    source: str,
    *,
    min_run: int = FACTUAL_REFERENCE_EXACT_RUN_CHARS,
) -> str:
    if len(body) < min_run or len(source) < min_run:
        return ""
    source_runs = {
        source[index : index + min_run]
        for index in range(len(source) - min_run + 1)
    }
    for index in range(len(body) - min_run + 1):
        sample = body[index : index + min_run]
        if sample in source_runs:
            return sample
    return ""


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
    mode = str(source_use_mode or "").strip()
    if mode == "factual_reference_only":
        # 事实参考源不拥有“贴近底稿”的最低留存合同；其商用边界由
        # commercial_article_near_copy_gate 从成稿视角独立判定。
        return []
    if mode != "licensed_adaptation":
        return [f"unsupported sourceUseMode {mode!r} (fail-closed)"]
    if not base_draft_is_adaptable(mode):
        return [f"sourceUseMode {mode!r} is not adaptable"]
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


def commercial_article_near_copy_gate(
    article: str,
    base_text: str,
    *,
    source_use_mode: str,
    carrier: str = "article",
    max_containment_ratio: float = FACTUAL_REFERENCE_MAX_NEAR_COPY_RATIO,
    exact_run_chars: int = FACTUAL_REFERENCE_EXACT_RUN_CHARS,
) -> CommercialNearCopyGate:
    """Fail closed when a factual-reference article remains a source near-copy.

    The containment denominator is the produced article, so copying one source
    excerpt from a much longer page cannot hide behind a low source-denominator
    fidelity score. A separate exact-run detector catches pasted paragraphs even
    when the rest of the article is independently written.
    """

    mode = str(source_use_mode or "").strip()
    if carrier == "image":
        return CommercialNearCopyGate(mode, 0.0, "", ())
    if mode == "licensed_adaptation":
        return CommercialNearCopyGate(mode, 0.0, "", ())
    if mode != "factual_reference_only":
        return CommercialNearCopyGate(
            mode,
            0.0,
            "",
            (f"unsupported sourceUseMode {mode!r} (fail-closed)",),
        )
    body, source = _normalized_pair(article, base_text, carrier)
    if not body or not source:
        return CommercialNearCopyGate(
            mode,
            0.0,
            "",
            ("factual_reference_only requires non-empty article and source",),
        )
    containment = _ngram_containment(body, source)
    exact_sample = _exact_run_sample(body, source, min_run=exact_run_chars)
    issues: list[str] = []
    if containment > max_containment_ratio:
        issues.append(
            "factual_reference_only article containment "
            f"{containment:.3f} > {max_containment_ratio:.3f}"
        )
    if exact_sample:
        issues.append(
            "factual_reference_only contains an exact source run "
            f">= {exact_run_chars} chars, sample『{exact_sample[:24]}…』"
        )
    return CommercialNearCopyGate(mode, containment, exact_sample, tuple(issues))


def commercial_article_sources_near_copy_gate(
    article: str,
    sources: Sequence[tuple[str, str]],
    *,
    carrier: str = "article",
) -> CommercialNearCopyGate:
    """Apply the typed gate to every source unit used by a commercial article."""

    if carrier == "image":
        return CommercialNearCopyGate("factual_reference_only", 0.0, "", ())
    if not sources:
        return CommercialNearCopyGate(
            "factual_reference_only",
            0.0,
            "",
            ("commercial article requires at least one source unit for near-copy review",),
        )
    gates = [
        commercial_article_near_copy_gate(
            article,
            source_text,
            source_use_mode=source_use_mode,
            carrier=carrier,
        )
        for source_text, source_use_mode in sources
    ]
    factual_gates = [
        gate
        for gate in gates
        if gate.source_use_mode == "factual_reference_only"
    ]
    reviewed = [
        gate
        for gate in gates
        if gate.source_use_mode == "factual_reference_only"
        or gate.issues
    ] or gates
    issues = tuple(
        dict.fromkeys(
            issue
            for gate in reviewed
            for issue in gate.issues
        )
    )
    strongest = max(
        reviewed,
        key=lambda gate: (
            gate.article_containment_ratio,
            len(gate.exact_run_sample),
        ),
    )
    return CommercialNearCopyGate(
        (
            "factual_reference_only"
            if factual_gates
            else strongest.source_use_mode
        ),
        strongest.article_containment_ratio,
        strongest.exact_run_sample,
        issues,
    )


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
