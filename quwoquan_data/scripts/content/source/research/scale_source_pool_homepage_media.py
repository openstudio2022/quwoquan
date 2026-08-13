"""homepage 冻结媒体输入：从不可变 MediaWiki 采集字节还原精确 hero 版面（拆分自 scale_source_pool_runtime）。"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from core.io import read_json

from content.source.research.scale_source_pool_runtime_blockers import _fail


def _image_rows(candidate: Mapping[str, Any], carrier: str) -> list[Mapping[str, Any]]:
    if carrier == "homepage":
        hero = candidate.get("hero")
        return [hero] if isinstance(hero, Mapping) else []
    return [row for row in candidate.get("assets") or [] if isinstance(row, Mapping)]


def _wiki_file_key(value: object) -> str:
    text = unquote(str(value or "")).strip()
    match = re.search(r"(?:File|文件):([^/?#]+)", text, re.IGNORECASE)
    if match:
        text = match.group(1)
    elif ":" in text and text.split(":", 1)[0] in {"File", "文件"}:
        text = text.split(":", 1)[1]
    return re.sub(r"\s+", " ", text.replace("_", " ")).strip().casefold()


def _frozen_homepage_media_inputs(
    *,
    capsule: Mapping[str, Any],
    evidence_root: Path,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, Any]]:
    """Restore exact selected-hero placement from immutable acquisition bytes.

    Homepage source-ready capsules intentionally bind a small carrier-selective
    media set, while their acquisition evidence retains the exact MediaWiki raw
    response.  Runtime materialization must project the selected hero's real
    placement from those frozen bytes; inventing a generic lead placement would
    hide locator maps and break the page-media enumeration contract.
    """

    from core.wiki_wikitext import parse_wikitext_layout, placements_from_layout

    from content.source.mediawiki_page import _revision_wikitext
    from content.source.research.homepage_article_source_ready_evidence import (
        assert_source_ready_evidence_matches_capsule,
        file_sha256,
        validate_source_ready_acquisition_evidence,
    )

    candidate = capsule.get("candidate")
    provenance = capsule.get("provenance")
    if not isinstance(candidate, Mapping) or not isinstance(provenance, Mapping):
        raise _fail("frozen homepage capsule lacks candidate/provenance")
    evidence_ref = Path(str(provenance.get("discoveryEvidenceRef") or ""))
    if not str(evidence_ref) or evidence_ref.is_absolute() or ".." in evidence_ref.parts:
        raise _fail("frozen homepage acquisition evidence ref is unsafe")
    try:
        evidence = read_json(evidence_root / evidence_ref)
        if not isinstance(evidence, Mapping):
            raise TypeError("acquisition evidence must be one object")
        validated = validate_source_ready_acquisition_evidence(evidence)
        assert_source_ready_evidence_matches_capsule(validated, capsule)
    except (OSError, TypeError, ValueError) as exc:
        raise _fail(f"frozen homepage acquisition evidence is invalid: {exc}") from exc
    if validated.get("carrier") != "homepage":
        raise _fail("frozen homepage acquisition evidence carrier drift")
    source = validated.get("sourceUnit")
    if not isinstance(source, Mapping) or source.get("sourceKind") != "wikipedia":
        raise _fail("frozen homepage source does not bind MediaWiki placement evidence")
    raw_ref = Path(str(source.get("rawEvidenceRef") or ""))
    if not str(raw_ref) or raw_ref.is_absolute() or ".." in raw_ref.parts:
        raise _fail("frozen homepage raw evidence ref is unsafe")
    raw_path = evidence_root / raw_ref
    try:
        if file_sha256(raw_path) != source.get("rawEvidenceFileSha256"):
            raise ValueError("rawEvidenceFileSha256 drift")
        raw_document = read_json(raw_path)
        if not isinstance(raw_document, Mapping):
            raise TypeError("raw MediaWiki evidence must be one object")
        mediawiki_raw = raw_document.get("mediawikiRaw")
        if mediawiki_raw is not None:
            if not isinstance(mediawiki_raw, str):
                raise TypeError("mediawikiRaw must be serialized JSON")
            raw_document = json.loads(mediawiki_raw)
        responses = raw_document.get("responses")
        if not isinstance(responses, list) or not responses:
            raise ValueError("MediaWiki raw evidence lacks responses")
        first = responses[0]
        query = first.get("query") if isinstance(first, Mapping) else None
        pages = query.get("pages") if isinstance(query, Mapping) else None
        page_rows = [row for row in (pages or {}).values() if isinstance(row, Mapping)]
        if len(page_rows) != 1:
            raise ValueError("MediaWiki raw evidence page identity is not exact")
        page = page_rows[0]
        revisions = page.get("revisions")
        revision_rows = [
            row for row in (revisions or []) if isinstance(row, Mapping)
        ]
        if len(revision_rows) != 1:
            raise ValueError("MediaWiki raw evidence revision identity is not exact")
        revision = revision_rows[0]
        if (
            int(page.get("pageid") or 0) != int(source.get("pageId") or 0)
            or str(page.get("title") or "") != str(source.get("resolvedTitle") or "")
            or int(revision.get("revid") or page.get("lastrevid") or 0)
            != int(source.get("revisionId") or 0)
        ):
            raise ValueError("MediaWiki raw evidence identity drift")
        wikitext = _revision_wikitext(revision).strip()
        if not wikitext:
            raise ValueError("MediaWiki raw evidence lacks revision wikitext")
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise _fail(f"frozen homepage raw evidence is invalid: {exc}") from exc

    layout = parse_wikitext_layout(
        wikitext,
        source_kind="wikipedia",
        title=str(source["resolvedTitle"]),
    )
    hero = candidate.get("hero")
    if not isinstance(hero, Mapping):
        raise _fail("frozen homepage candidate lacks hero")
    hero_key = _wiki_file_key(hero.get("sourcePageUrl"))
    matching_figures = [
        dict(block)
        for block in layout.get("blocks") or []
        if isinstance(block, Mapping)
        and block.get("type") == "figure"
        and _wiki_file_key(block.get("fileTitle")) == hero_key
    ]
    if not hero_key or not matching_figures:
        raise _fail("frozen homepage hero is absent from exact MediaWiki placements")
    selected_layout = {
        **layout,
        "blocks": matching_figures,
        "figureCount": len(matching_figures),
        "tables": [],
    }
    placements = placements_from_layout(selected_layout)
    if not placements:
        raise _fail("frozen homepage hero placement projection is empty")
    # The same source asset may appear more than once on a page.  Preserve all
    # exact occurrences in imagePlacements, while the assets index carries the
    # earliest occurrence only as its deterministic summary.
    placement = min(placements, key=lambda row: int(row.get("sourceOrder") or 0))
    asset_metadata = {
        str(hero["assetId"]): {
            "fileName": str(placement.get("fileName") or ""),
            "caption": str(placement.get("caption") or ""),
            "placeholderId": str(placement.get("placeholderId") or ""),
            "placementType": str(placement.get("placementType") or "inline"),
            "groupId": str(placement.get("groupId") or ""),
            "sectionSlug": str(placement.get("sectionSlug") or ""),
            "sourceOrder": int(placement.get("sourceOrder") or 0),
            "coverCandidateRank": int(placement.get("coverCandidateRank") or 0),
            "subjectKey": str(placement.get("subjectKey") or ""),
            "isMapLike": bool(placement.get("isMapLike")),
            "pageResolvedTitle": str(source["resolvedTitle"]),
            "pageId": int(source["pageId"]),
            "pageRevisionId": int(source["revisionId"]),
        }
    }
    funnel = {
        "candidateCount": 1,
        "keptCount": 1,
        "droppedCount": 0,
        "dedupeRemoved": 0,
        "drops": [],
        "fetchFailures": [],
    }
    return selected_layout, asset_metadata, funnel
