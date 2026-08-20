"""Strict, target-scoped relevance evidence for article base-source planning.

The coarse ``entityFocusScore`` counts the full length of every line containing
an aggressively shortened alias.  A city-wide page can therefore outrank an
exact entity page merely because one long paragraph mentions the target once.
This module deliberately uses only the canonical target and aliases frozen in
``0.plan/target_set.json``.  It is a source-selection signal and admission
check; it does not relax the final independent entity/title review.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence


_MIN_BODY_ANCHOR_RATIO = 0.004


@dataclass(frozen=True, slots=True)
class ArticleEntityAnchor:
    """Replayable entity-anchor assessment for one article source unit."""

    eligible: bool
    title_rank: int
    body_mention_count: int
    body_anchor_ratio: float

    def candidate_fields(self) -> dict[str, object]:
        return {
            "entityAnchorEligible": self.eligible,
            "entityTitleAnchorRank": self.title_rank,
            "entityBodyMentionCount": self.body_mention_count,
            "entityAnchorScore": round(self.body_anchor_ratio, 6),
        }

    def diagnostic(self) -> str:
        return (
            f"titleRank={self.title_rank}; mentions={self.body_mention_count}; "
            f"bodyAnchorRatio={self.body_anchor_ratio:.6f}"
        )


def _identity_tokens(target: str, aliases: Sequence[str]) -> tuple[str, ...]:
    values = {
        str(value or "").strip()
        for value in (target, *aliases)
        if len(str(value or "").strip()) >= 2
    }
    return tuple(sorted(values, key=lambda value: (-len(value), value)))


def _compact_article_prose(body: str) -> str:
    # Figure captions and alt text are media evidence, not proof that the prose
    # is about the target.  Remove both single and grouped figure fences before
    # measuring the body anchor.
    without_figures = re.sub(
        r"(?s):::figure(?:group)?\b.*?:::",
        "",
        str(body or ""),
    )
    return re.sub(r"\s+", "", without_figures)


def assess_article_entity_anchor(
    *,
    body: str,
    title: str,
    target: str,
    aliases: Sequence[str] = (),
) -> ArticleEntityAnchor:
    """Assess exact target/alias anchoring without inferred short aliases.

    A direct title plus at least one prose mention is eligible.  A creative
    title remains eligible when the body independently mentions the target at
    least twice and clears a small character-density floor.  This excludes a
    broad city overview that merely lists the entity while preserving genuine
    target articles whose titles are editorial rather than canonical.
    """

    tokens = _identity_tokens(target, aliases)
    compact_title = re.sub(r"\s+", "", str(title or "")).strip()
    compact_body = _compact_article_prose(body)
    if not tokens or not compact_body:
        return ArticleEntityAnchor(False, 0, 0, 0.0)

    title_rank = 0
    if compact_title:
        if compact_title in tokens:
            title_rank = 2
        elif any(token in compact_title for token in tokens):
            title_rank = 1

    pattern = re.compile("|".join(re.escape(token) for token in tokens))
    matches = tuple(pattern.finditer(compact_body))
    anchored_chars = sum(len(match.group(0)) for match in matches)
    ratio = anchored_chars / len(compact_body) if compact_body else 0.0
    eligible = bool(
        (title_rank > 0 and matches)
        or (len(matches) >= 2 and ratio >= _MIN_BODY_ANCHOR_RATIO)
    )
    return ArticleEntityAnchor(
        eligible=eligible,
        title_rank=title_rank,
        body_mention_count=len(matches),
        body_anchor_ratio=ratio,
    )


__all__ = ["ArticleEntityAnchor", "assess_article_entity_anchor"]
