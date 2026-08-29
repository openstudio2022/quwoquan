"""主页正文的派生度判据：正文相对底稿的逐字重合，与正文内部的段落自我重复。

为什么需要段落粒度：整篇口径（`commercial_gate.source_fidelity`、
`base_draft_fidelity`）按全文平均，一段照抄会被其余重写段落稀释到判否线以下；
只判字数与章节均衡时，「把底稿几行原样搬过来凑够字数」是通过成本最低的写法，
判据本身在诱导复述原文。

两条判据都是纯函数：同一份 `page.md` 与同一份底稿行，任何时候得到同一组结论，
不读环境、不读时间、不读进程状态。阈值一律由调用方注入，本模块不持有默认值——
调用方拿不到 policy 声明时应当判否，而不是由这里替它挑一个数。

issue 必须点名到段落：正文段落序号 + 底稿行号区间是作者据以改稿的唯一坐标，
只给一个总分等于让作者重读全文再猜是哪一段。
"""
from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations

from content.homepage.commercial_gate import SOURCE_FIDELITY_NGRAM_CHARS

_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
_FIGURE_BLOCK_RE = re.compile(r"(?ms)^:::figure(?:group)?\b.*?^:::[ \t]*$")
_ASSET_DIRECTIVE_RE = re.compile(r"\{asset://[^}]*\}")
_HEADING_LINE_RE = re.compile(r"^#{1,6}\s")
_PLACEHOLDER_LINE_RE = re.compile(r"^\[\[IMG:fig_[0-9]{2,}\]\]$")
_PARAGRAPH_SPLIT_RE = re.compile(r"\n[ \t]*\n")


@dataclass(frozen=True, slots=True)
class SourceOverlapFinding:
    """一个正文段落逐字重合到底稿的判否事实。"""

    paragraph_index: int
    paragraph_chars: int
    overlap_ratio: float
    source_line_start: int
    source_line_end: int


@dataclass(frozen=True, slots=True)
class ParagraphRepetitionFinding:
    """正文内部两个段落互为复读的判否事实。"""

    first_paragraph_index: int
    second_paragraph_index: int
    similarity: float


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _char_ngrams(text: str) -> set[str]:
    """去空白后的字符 n-gram 集合；不足一个完整 n-gram 的文本返回空集合。

    空集合表示「这段文本短到无法度量」，与「度量后重合为零」是两件事，由调用方
    分别处理，不在这里合并。
    """
    compact = _compact(text)
    if len(compact) < SOURCE_FIDELITY_NGRAM_CHARS:
        return set()
    return {
        compact[index : index + SOURCE_FIDELITY_NGRAM_CHARS]
        for index in range(len(compact) - SOURCE_FIDELITY_NGRAM_CHARS + 1)
    }


def body_paragraphs(page_text: str) -> list[str]:
    """按空行切出面向读者的正文段落，顺序即 issue 里点名的段落序号。

    frontmatter、`:::figure` 块、`{asset://}` 指令、`##` 小标题与图片占位行都不是
    正文段落。把它们计入序号会让作者按 issue 给的序号数到另一段去，判据点名的
    精确性也就白费了。
    """
    body = _FRONTMATTER_RE.sub("", page_text or "")
    body = _FIGURE_BLOCK_RE.sub("", body)
    body = _ASSET_DIRECTIVE_RE.sub("", body)
    paragraphs: list[str] = []
    for block in _PARAGRAPH_SPLIT_RE.split(body):
        lines = [
            stripped
            for stripped in (line.strip() for line in block.splitlines())
            if stripped
            and not _HEADING_LINE_RE.match(stripped)
            and not _PLACEHOLDER_LINE_RE.match(stripped)
        ]
        if lines:
            paragraphs.append(" ".join(lines))
    return paragraphs


def _measurable_paragraphs(
    page_text: str, *, minimum_paragraph_chars: int
) -> list[tuple[int, int, set[str]]]:
    """返回可度量段落的 `(段落序号, 去空白字数, n-gram)`。

    序号取自 `body_paragraphs` 的全量顺序，因此被长度门槛排除的段落不会让后续
    段落的序号前移。
    """
    rows: list[tuple[int, int, set[str]]] = []
    for index, paragraph in enumerate(body_paragraphs(page_text), start=1):
        chars = len(_compact(paragraph))
        if chars < minimum_paragraph_chars:
            continue
        grams = _char_ngrams(paragraph)
        if not grams:
            continue
        rows.append((index, chars, grams))
    return rows


def _dominant_line_span(
    paragraph_grams: set[str], line_grams: Sequence[set[str]]
) -> tuple[int, int]:
    """返回贡献重合 n-gram 最多的连续底稿行区间（1-based 闭区间）。

    前置条件是该段落与底稿确有重合——调用点只在重合率越线后才调用本函数，因此
    返回值必然指向真实行号。逐行取 n-gram 会丢掉跨行接缝，重合率因此也按同一
    逐行口径计算，使「越线」与「能定位到行」永远同时成立。
    """
    best_count = 0
    best_span = (0, 0)
    run_start = 0
    run_count = 0
    for number, grams in enumerate(line_grams, start=1):
        if not grams:
            # 空行与过短行不承载 n-gram：它们既不算命中，也不该把底稿里本就连续的
            # 几行切成互不相连的区间（底稿段落之间有空行是常态）。
            continue
        hit = len(paragraph_grams & grams)
        if hit == 0:
            run_start = 0
            run_count = 0
            continue
        if run_start == 0:
            run_start = number
        run_count += hit
        if run_count > best_count:
            best_count = run_count
            best_span = (run_start, number)
    return best_span


def source_overlap_findings(
    page_text: str,
    source_lines: Sequence[str],
    *,
    max_overlap_ratio: float,
    minimum_paragraph_chars: int,
) -> list[SourceOverlapFinding]:
    """逐段判定正文对底稿的逐字重合，越线的段落各自形成一条判否事实。"""
    line_grams = [_char_ngrams(line) for line in source_lines]
    source_grams: set[str] = set().union(*line_grams) if line_grams else set()
    if not source_grams:
        return []
    findings: list[SourceOverlapFinding] = []
    for index, chars, grams in _measurable_paragraphs(
        page_text, minimum_paragraph_chars=minimum_paragraph_chars
    ):
        ratio = len(grams & source_grams) / len(grams)
        if ratio <= max_overlap_ratio:
            continue
        start, end = _dominant_line_span(grams, line_grams)
        findings.append(SourceOverlapFinding(index, chars, ratio, start, end))
    return findings


def paragraph_repetition_findings(
    page_text: str,
    *,
    max_similarity: float,
    minimum_paragraph_chars: int,
) -> list[ParagraphRepetitionFinding]:
    """两两判定正文段落之间的相似度，越线的每一对各自形成一条判否事实。

    要抓的是「几乎逐字」的复读，它在精确相等判定（如按段落去重）下完全不可见。
    相似度取较短段落一侧的 n-gram 命中比例（overlap coefficient）而不是 Jaccard：
    Jaccard 用并集作分母，改掉两个词或把一段截短就会把分值压到判否线以下，而这
    两种正是复读最常见的形态。分母固定取较短一侧，故对调两段得到同一个数。
    """
    rows = _measurable_paragraphs(
        page_text, minimum_paragraph_chars=minimum_paragraph_chars
    )
    findings: list[ParagraphRepetitionFinding] = []
    for (left_index, _, left), (right_index, _, right) in combinations(rows, 2):
        similarity = len(left & right) / min(len(left), len(right))
        if similarity <= max_similarity:
            continue
        findings.append(
            ParagraphRepetitionFinding(left_index, right_index, similarity)
        )
    return findings


def source_overlap_issues(
    page_text: str,
    source_lines: Sequence[str],
    *,
    max_overlap_ratio: float,
    minimum_paragraph_chars: int,
    label: str = "",
) -> list[str]:
    """把源文本重合判否事实渲染为点名到段落与底稿行号的 issue。"""
    prefix = f"{label}: " if label else ""
    return [
        f"{prefix}sourceParagraphOverlap: 正文第 {finding.paragraph_index} 段"
        f"（{finding.paragraph_chars} 字）与底稿第 "
        f"{finding.source_line_start}-{finding.source_line_end} 行逐字重合 "
        f"{finding.overlap_ratio:.3f} > {max_overlap_ratio:.3f}，"
        "该段是复述原文；只保留这些事实并重新组织表述"
        for finding in source_overlap_findings(
            page_text,
            source_lines,
            max_overlap_ratio=max_overlap_ratio,
            minimum_paragraph_chars=minimum_paragraph_chars,
        )
    ]


def paragraph_repetition_issues(
    page_text: str,
    *,
    max_similarity: float,
    minimum_paragraph_chars: int,
    label: str = "",
) -> list[str]:
    """把正文内部重复判否事实渲染为点名到两个段落的 issue。"""
    prefix = f"{label}: " if label else ""
    return [
        f"{prefix}intraBodyParagraphRepetition: 正文第 "
        f"{finding.first_paragraph_index} 段与第 {finding.second_paragraph_index} 段"
        f"相似度 {finding.similarity:.3f} > {max_similarity:.3f}，两段互为复读；"
        "删去其一或改写为该段独有的事实"
        for finding in paragraph_repetition_findings(
            page_text,
            max_similarity=max_similarity,
            minimum_paragraph_chars=minimum_paragraph_chars,
        )
    ]


__all__ = [
    "ParagraphRepetitionFinding",
    "SourceOverlapFinding",
    "body_paragraphs",
    "paragraph_repetition_findings",
    "paragraph_repetition_issues",
    "source_overlap_findings",
    "source_overlap_issues",
]
