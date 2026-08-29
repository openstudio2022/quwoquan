"""Fetch one source candidate and adjudicate the quality it is admitted with.

`_fetch_download_entity` owns the entity-level loop and the media closure; this
module owns what happens to a single candidate inside that loop: fetching its
payload, converting a transport failure into a typed issue instead of losing
the entity, applying the fidelity / duplicate-URL / homepage-base-draft /
attribution / compression adjudications in order, and preferring a strictly
better cached snapshot when attribution left no gap.

Isolation granularity is the point of the split: one unusable candidate must
only cost itself, never the other candidates of the same entity.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.data_issue import DataIssueError

from content.homepage.quality_policy import (
    homepage_body_char_minimum,
    homepage_fact_char_minimum,
    homepage_fact_count_minimum,
)
from content.post.article.evidence_text import (
    clean_source_markdown,
    score_source_markdown,
)
from content.source import handler_fetch_contract
from content.source.fetch_payload import fetch_source_payload
from content.source.handler_images import (
    _cached_source_quality_if_better,
    _find_source_unit_by_plan_key,
)
from content.source.source_inputs import manual_body_note, source_frontmatter
from content.source.source_unit import find_source_unit_raw_snapshot


@dataclass(frozen=True)
class AdjudicatedSourceCandidate:
    """One candidate's fetched bytes plus the quality verdict it carries."""

    source_md: str
    clean_md: str
    html_bytes: bytes | None
    raw_format: str
    status_code: int
    fetched_text: str
    inline_images: list
    source_layout: dict[str, Any] | None
    fetch_runtime: dict[str, Any]
    quality: dict[str, Any]


def adjudicate_source_candidate(
    source: Mapping[str, Any],
    *,
    execution_id: str,
    entity_id: str,
    object_dir: Path,
    ordinal: int,
    seen_canonical_urls: set[str],
) -> AdjudicatedSourceCandidate:
    """Fetch one candidate and return the verdict the source unit is written with."""
    html_bytes: bytes | None = None
    status_code = 0
    fetched_text = ""
    rendered_text = ""
    raw_format = ""
    fetch_runtime: dict[str, Any] = {}
    source_layout: dict[str, Any] | None = None
    source_fetch_issue = None
    inline_images: list = []
    try:
        fetched = fetch_source_payload(
            source["url"],
            source=source,
            entity_id=entity_id,
        )
        html_bytes = fetched["htmlBytes"]
        status_code = fetched["statusCode"]
        fetched_text = str(fetched.get("text") or "").strip()
        rendered_text = str(fetched.get("renderedText") or "").strip()
        inline_images = fetched.get("inlineImages") or []
        source_layout = fetched.get("layout") if isinstance(fetched.get("layout"), dict) else None
        fetch_runtime = (
            dict(fetched.get("runtime") or {})
            if isinstance(fetched.get("runtime"), Mapping)
            else {}
        )
        raw_format = str(fetch_runtime.get("rawFormat") or "")
        source_md = source_frontmatter(source, entity_id)
        if fetched_text:
            source_md += fetched_text
    except DataIssueError:
        raise
    except Exception as exc:  # boundary conversion to a stable typed issue
        source_fetch_issue = handler_fetch_contract.source_fetch_failure_issue(
            source,
            entity_id=entity_id,
            error=exc,
        )
        source_md = source_frontmatter(source, entity_id)
    note = manual_body_note(source)
    if note:
        source_md = source_md.rstrip() + f"\n\n{note}\n"
    clean_md = clean_source_markdown(source_md, raw_format=raw_format)
    fidelity_issue = None
    if rendered_text:
        publishable_rendered_text = clean_source_markdown(
            rendered_text,
            raw_format=raw_format,
        )
        fidelity_issue = handler_fetch_contract.source_content_fidelity_issue(
            source,
            entity_id=entity_id,
            rendered_text=publishable_rendered_text,
            candidate_text=clean_md,
        )
    assessment = score_source_markdown(source["source_id"], source_md, entity_name=entity_id)
    quality_value = assessment.quality
    quality_score = assessment.score
    quality_reasons = list(assessment.reasons)
    if source_fetch_issue is not None:
        quality_reasons.append(source_fetch_issue.code.value)
        print(
            "[download] Source fetch failed "
            f"{entity_id}/{source.get('source_id')}: "
            f"{source_fetch_issue.code.value} "
            f"errorType={dict(source_fetch_issue.attributes).get('errorType', '')}",
            flush=True,
        )
    if fidelity_issue is not None:
        quality_value = "Reject"
        quality_score = 0
        quality_reasons.append(fidelity_issue.code.value)
    canonical_url = handler_fetch_contract.canonicalize_source_url(str(source.get("url") or ""))
    if canonical_url and canonical_url in seen_canonical_urls:
        quality_value = "Reject"
        quality_score = 0
        quality_reasons.append("duplicate_source_url")
    elif canonical_url:
        seen_canonical_urls.add(canonical_url)

    homepage_fact_count: int | None = None
    if (
        quality_value != "Reject"
        and str(source.get("researchLane") or "") == "homepage"
        and str(source.get("sourceRole") or "") != "support"
    ):
        resolved_title = str(fetch_runtime.get("resolvedTitle") or "").strip()
        homepage_admission = handler_fetch_contract.homepage_base_draft_admission(
            source,
            source_text=fetched_text or clean_md,
            entity_id=entity_id,
            resolved_title=resolved_title,
            minimum_body_chars=homepage_body_char_minimum(execution_id),
            minimum_fact_count=homepage_fact_count_minimum(execution_id),
            minimum_fact_chars=homepage_fact_char_minimum(execution_id),
        )
        homepage_fact_count = homepage_admission.fact_count
        if not homepage_admission.accepted:
            quality_value = "Reject"
            quality_score = 0
            quality_reasons.append(homepage_admission.issue_code.value)

    # 隔离粒度：不可归因的来源单元只丢自己。一条未登记站点曾经让整个实体的
    # fetch 抛 ValueError 被踢出 readyTargets，实体其余合法百科来源随之作废。
    source_attribution_issue = None
    if quality_value != "Reject":
        source_attribution_issue = (
            handler_fetch_contract.source_attribution_admission_issue(
                source,
                entity_id=entity_id,
            )
        )
        if source_attribution_issue is not None:
            quality_value = "Reject"
            quality_score = 0
            quality_reasons.append(source_attribution_issue.code.value)
            print(
                "[download] Source attribution unresolved "
                f"{entity_id}/{source.get('source_id')}: "
                f"{dict(source_attribution_issue.attributes).get('detail', '')}",
                flush=True,
            )
    compression_note: dict = {}
    if quality_value != "Reject" and handler_fetch_contract.requires_factual_compression(source):
        from core.factual_compression import factual_compress_text

        compressed = factual_compress_text(clean_md or fetched_text, entity_name=entity_id)
        if compressed["policy"] != "none":
            clean_md = compressed["text"]
            quality_reasons.append(f"factual_compression_{compressed['policy']}")
        compression_note = {
            "policy": compressed["policy"],
            "originalChars": compressed["originalChars"],
            "compressedChars": compressed["compressedChars"],
        }

    quality = {
        "sourceId": source["source_id"],
        "entity": entity_id,
        "quality": quality_value,
        "score": quality_score,
        "reasons": quality_reasons,
        "excerpt": assessment.excerpt,
        "url": source["url"],
        "statusCode": status_code,
        "fetchSucceeded": bool(fetched_text),
        "taskProvidedBodyPresent": bool(str(source.get("body") or "").strip()),
    }
    if homepage_fact_count is not None:
        quality["homepageBaseDraftFactCount"] = homepage_fact_count
    if compression_note:
        quality["factualCompression"] = compression_note
    if source_fetch_issue is not None:
        quality["fetchIssue"] = source_fetch_issue.as_dict()
    if source_attribution_issue is not None:
        quality["attributionIssue"] = source_attribution_issue.as_dict()
    # 归因缺口是准入裁决而非质量评分：更高分的历史快照不得把不可交付的来源复活。
    cached_quality = (
        _cached_source_quality_if_better(
            object_dir,
            ordinal=ordinal,
            source_id=source["source_id"],
            url=source["url"],
            candidate_quality=quality,
        )
        if source_attribution_issue is None
        else None
    )
    if cached_quality is not None:
        unit = _find_source_unit_by_plan_key(
            object_dir,
            ordinal=ordinal,
            source_id=source["source_id"],
            url=source["url"],
        )
        if unit is None:
            cached_quality = None
        else:
            source_md = (unit / "source.md").read_text(encoding="utf-8")
            inline_images = []
            clean_path = unit / "source.clean.md"
            clean_md = clean_path.read_text(encoding="utf-8") if clean_path.is_file() else ""
            page_path = find_source_unit_raw_snapshot(unit)
            html_bytes = page_path.read_bytes() if page_path else None
            raw_format = (
                "mediawiki_api_json"
                if page_path is not None and page_path.name == "page.raw.json"
                else raw_format
            )
            print(
                "[download] Preserve better cached source "
                f"{entity_id}/{source['source_id']}: "
                f"{cached_quality.get('quality')}({cached_quality.get('score')}) > "
                f"{quality.get('quality')}({quality.get('score')})",
                flush=True,
            )
            quality = {**cached_quality, "retainedFromCache": True}

    return AdjudicatedSourceCandidate(
        source_md=source_md,
        clean_md=clean_md,
        html_bytes=html_bytes,
        raw_format=raw_format,
        status_code=status_code,
        fetched_text=fetched_text,
        inline_images=inline_images,
        source_layout=source_layout,
        fetch_runtime=fetch_runtime,
        quality=quality,
    )


__all__ = ["AdjudicatedSourceCandidate", "adjudicate_source_candidate"]
