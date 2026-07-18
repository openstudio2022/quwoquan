"""Strongly typed source-content fidelity checks."""
from __future__ import annotations

from dataclasses import dataclass
import re

from core.source_layout import rendered_text_blocks


@dataclass(frozen=True, slots=True)
class SourceContentFidelity:
    authoritative_paragraph_count: int
    matched_paragraph_count: int
    missing_paragraphs: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return not self.missing_paragraphs


def _normalized_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def assess_source_content_fidelity(
    authoritative_text: str,
    candidate_text: str,
) -> SourceContentFidelity:
    """Require every expanded MediaWiki prose paragraph in the source output."""
    paragraphs = tuple(
        _normalized_text(str(block.get("text") or ""))
        for block in rendered_text_blocks(authoritative_text)
        if block.get("type") == "paragraph"
        and _normalized_text(str(block.get("text") or ""))
    )
    normalized_candidate = _normalized_text(candidate_text)
    missing = tuple(
        paragraph
        for paragraph in paragraphs
        if paragraph not in normalized_candidate
    )
    return SourceContentFidelity(
        authoritative_paragraph_count=len(paragraphs),
        matched_paragraph_count=len(paragraphs) - len(missing),
        missing_paragraphs=missing,
    )


__all__ = ["SourceContentFidelity", "assess_source_content_fidelity"]
