"""Semantic admission for article assets before content-plan freeze."""
from __future__ import annotations

import re
import urllib.parse
from collections.abc import Mapping, Sequence
from typing import Any

from core.image_rules import image_caption_quality_issue, relevance_issue


def _semantic_token(value: object) -> str:
    return "".join(
        character
        for character in str(value or "").casefold()
        if character.isalnum()
    )


_GENERIC_BODY_ANCHORS = frozenset(
    {"位于中国", "中国", "浙江省", "杭州市", "杭州", "景区", "景点", "风景"}
)


def _article_body_anchors(*values: object) -> tuple[str, ...]:
    """Extract specific CJK subjects that can be verified in the source body."""
    return tuple(
        dict.fromkeys(
            anchor
            for value in values
            for phrase in re.findall(r"[\u3400-\u9fff]{3,}", str(value or ""))
            for anchor in (
                phrase,
                *(
                    phrase[start : start + size]
                    for size in range(4, len(phrase))
                    for start in range(len(phrase) - size + 1)
                ),
            )
            if anchor not in _GENERIC_BODY_ANCHORS
        )
    )


def _subject_evidence_values(row: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(
        str(item.get("value") or "").strip()
        for item in row.get("visualSubjectEvidence") or ()
        if isinstance(item, Mapping)
        and str(item.get("commonsCategory") or "").strip()
        and re.fullmatch(r"Q[1-9][0-9]*", str(item.get("wikidataItem") or ""))
        and str(item.get("language") or "") in {"zh", "en"}
        and str(item.get("value") or "").strip()
    )


def _article_semantic_scope(
    article_text: str,
    *,
    entity_id: str,
    entity_aliases: tuple[str, ...],
) -> str:
    """Prefer the Markdown section explicitly owned by the target entity."""
    lines = str(article_text or "").splitlines()
    aliases = tuple(
        value.casefold()
        for value in (entity_id, *entity_aliases)
        if str(value or "").strip()
    )
    for index, line in enumerate(lines):
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if not heading or not any(alias in heading.group(2).casefold() for alias in aliases):
            continue
        level = len(heading.group(1))
        end = len(lines)
        for next_index in range(index + 1, len(lines)):
            next_heading = re.match(r"^(#{1,6})\s+", lines[next_index])
            if next_heading and len(next_heading.group(1)) <= level:
                end = next_index
                break
        return "\n".join(lines[index:end])
    return str(article_text or "")


def article_asset_semantic_issue(
    row: Mapping[str, Any],
    *,
    entity_id: str,
    entity_aliases: tuple[str, ...] = (),
    article_text: str = "",
) -> str:
    """Reject an image that cannot visually anchor the article entity.

    File membership and image decodability prove only provenance and safety.
    They do not make a city street, hotel or shopping-centre photo a valid
    closing image for a scenic-spot article. Admission consumes the semantic
    fields frozen by source acquisition before asset refs are frozen.
    """
    asset_id = str(row.get("sourceAssetId") or row.get("fileName") or "?").strip()
    if row.get("isRepresentativeVisual") is False:
        return f"{asset_id}: source review marks image non-representative"
    if bool(row.get("isMapLike")) or str(row.get("placementType") or "") == "locatorMap":
        return f"{asset_id}: locator/map image cannot be an article figure"

    caption = str(row.get("caption") or "").strip()
    relevance = str(row.get("relevance") or "").strip()
    visual_subject = str(row.get("visualSubject") or "").strip()
    provider_subjects = _subject_evidence_values(row)
    decoded_source_url = urllib.parse.unquote(
        str(row.get("sourceUrl") or "")
    ).replace("_", " ")
    relevance_problem = relevance_issue(
        relevance,
        entity_id=entity_id,
        asset_id=asset_id,
    )
    if relevance_problem:
        return relevance_problem
    caption_problem = image_caption_quality_issue(
        caption,
        entity_id=entity_id,
        asset_id=asset_id,
    )
    if caption_problem:
        return caption_problem
    evidence_token = _semantic_token(
        " ".join(
            (caption, relevance, visual_subject, decoded_source_url, *provider_subjects)
        )
    )
    aliases = tuple(
        token
        for token in (
            _semantic_token(value)
            for value in (entity_id, *entity_aliases)
        )
        if token
    )
    if evidence_token and any(alias in evidence_token for alias in aliases):
        return ""
    body_token = _semantic_token(
        _article_semantic_scope(
            article_text,
            entity_id=entity_id,
            entity_aliases=entity_aliases,
        )
    )
    if body_token and any(
        _semantic_token(anchor) in body_token
        for anchor in _article_body_anchors(
            caption,
            relevance,
            visual_subject,
            decoded_source_url,
            *provider_subjects,
        )
    ):
        return ""
    return (
        f"{asset_id}: caption/relevance/visualSubject cannot anchor "
        f"the image to article entity {entity_id!r} or its frozen source body"
    )


def article_target_scope(
    active_spec: Mapping[str, Any],
) -> tuple[list[str], dict[str, tuple[str, ...]]]:
    """Project ordered target names and aliases from the frozen scope."""
    rows = [
        target
        for target in ((active_spec.get("scope") or {}).get("coverageTargets") or [])
        if isinstance(target, Mapping)
    ]
    targets = [
        str(target.get("name") or "").strip()
        for target in rows
        if str(target.get("name") or "").strip()
    ]
    aliases = {
        str(target.get("name") or "").strip(): tuple(
            str(alias).strip()
            for alias in target.get("aliases") or []
            if str(alias).strip()
        )
        for target in rows
        if str(target.get("name") or "").strip()
    }
    return targets, aliases


def admitted_article_asset_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    entity_id: str,
    entity_aliases: tuple[str, ...] = (),
    article_text: str = "",
) -> tuple[list[dict[str, Any]], list[str]]:
    """Return only semantically bound rows plus exact rejection reasons."""
    admitted: list[dict[str, Any]] = []
    issues: list[str] = []
    for row in rows:
        issue = article_asset_semantic_issue(
            row,
            entity_id=entity_id,
            entity_aliases=entity_aliases,
            article_text=article_text,
        )
        if issue:
            issues.append(issue)
        else:
            admitted.append(dict(row))
    return admitted, issues


__all__ = [
    "admitted_article_asset_rows",
    "article_asset_semantic_issue",
    "article_target_scope",
]
