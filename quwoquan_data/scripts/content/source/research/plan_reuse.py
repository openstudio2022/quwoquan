"""Read-only reuse of retained source plans and source units."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.baike_source_contract import SOURCE_LICENSE_METADATA, source_identity_matches_contract
from core.io import read_json
from core.paths import STAGE_DOWNLOAD
from content.execution.workspace import relative_execution_ref
from content.source.source_unit import resolve_entity_object_dir
from core.qunar_template import is_qunar_url
from content.source.research.plan_state import (
    _hydrate_mediawiki_same_source_images,
)
from content.source.research.reject_memory import (
    _execution_dirs,
    _execution_root,
)
from content.source.research.reject_memory import _url_in_memory
from content.source.research.source_quality import (
    _ARTICLE_BASE_CATEGORIES,
    _candidate_gate,
    _source_category,
)
from core.content_source_registry import homepage_core_source_limit
from content.source.research.homepage_text_quality import _homepage_text_quality_issue
from content.source.research.text_match import _normalized_title, _text_mentions_entity

def _sources_from_article_plan(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        plan = read_json(path)
    except Exception:  # noqa: BLE001
        return []
    payload = plan.get("payload") if isinstance(plan.get("payload"), dict) else {}
    rows = payload.get("sources") or plan.get("sources") or []
    return [dict(row) for row in rows if isinstance(row, dict)]

def _homepage_urls_from_current_plan(
    execution_id: str,
    entity_id: str,
    *,
    entity_type: str,
) -> set[str]:
    etype = str(entity_type or "景区").strip().split("/")[-1] or "景区"
    path = (
        _execution_root(execution_id)
        / "entities"
        / "地点"
        / etype
        / entity_id
        / STAGE_DOWNLOAD
        / "homepage_source_plan.json"
    )
    return {
        str(source.get("url") or "").strip()
        for source in _sources_from_article_plan(path)
        if str(source.get("url") or "").strip()
    }

def _verified_homepage_sources_from_source_units(
    execution_id: str,
    entity_id: str,
    *,
    entity_type: str,
    rejected_source_urls: set[str] | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Reuse homepage source units that already passed source_screen.

    Source repair should not discard a working closed-set encyclopedia source
    while retrying another candidate. This keeps the repair loop
    monotonic and prevents the planner from cycling over known-bad URLs.
    """
    from content.source.source_unit import iter_source_units

    resolved_limit = limit if limit is not None else homepage_core_source_limit()

    obj = resolve_entity_object_dir(execution_id, entity_id, etype_hint=entity_type)
    sources: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for unit in iter_source_units(obj):
        meta_path = unit / "meta.json"
        quality_path = unit / "source.quality.json"
        if not meta_path.is_file() or not quality_path.is_file():
            continue
        try:
            meta = read_json(meta_path)
            quality = read_json(quality_path)
        except Exception:  # noqa: BLE001
            continue
        if str(meta.get("researchLane") or "") != "homepage":
            continue
        if str(quality.get("quality") or "") == "Reject":
            continue
        text_path = unit / "source.clean.md"
        if not text_path.is_file():
            text_path = unit / "source.md"
        if not text_path.is_file():
            continue
        try:
            source_text = text_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:  # noqa: BLE001
            continue
        issue = _homepage_text_quality_issue(
            source_text,
            entity_id,
            require_fact_ready=True,
        )
        if issue:
            continue
        url = str(
            meta.get("canonicalUrl")
            or meta.get("finalUrl")
            or meta.get("url")
            or quality.get("url")
            or ""
        ).strip()
        source_kind = str(meta.get("sourceKind") or "")
        extractor = str(meta.get("extractor") or "")
        policy_revision = str(meta.get("policyRevision") or "")
        if not source_identity_matches_contract(
            source_kind=source_kind,
            url=url,
            extractor=extractor,
            policy_revision=policy_revision,
        ):
            continue
        if not url or url in seen_urls:
            continue
        if rejected_source_urls and _url_in_memory(url, rejected_source_urls):
            continue
        source_id = str(meta.get("sourceId") or unit.name.split(".", 1)[-1] or "home_verified").strip()
        platform = str(meta.get("platform") or meta.get("sourceKind") or "百科").strip()
        category = str(meta.get("category") or meta.get("sourceKind") or "").strip()
        sources.append(
            _hydrate_mediawiki_same_source_images(
                {
                "source_id": source_id,
                "platform": platform,
                "url": url,
                "canonicalUrl": url,
                "sourceKind": source_kind,
                "sourceTitle": str(meta.get("title") or entity_id),
                "extractor": extractor,
                "policyRevision": policy_revision,
                "sourceUseMode": str(meta.get("sourceUseMode") or "factual_reference_only"),
                **SOURCE_LICENSE_METADATA.get(source_kind, {}),
                "category": _source_category(platform, category),
                "discoveryProvider": "verified_homepage_source_unit_reuse",
                "matchConfidence": 0.97,
                "evidenceReason": f"reuse retained homepage source unit {unit.name}",
                "sourceRole": "primary" if not sources else "supporting",
                "imageEvidenceMode": "",
                "entityMatch": "strong",
                "reuseSourceUnit": relative_execution_ref(unit / "source.md", execution_id),
                },
                entity_id=entity_id,
            )
        )
        seen_urls.add(url)
        if len(sources) >= resolved_limit:
            break
    return sources

def _qunar_article_mentions_entity(
    source: Mapping[str, Any],
    *,
    entity_id: str,
    entity_aliases: list[str] | tuple[str, ...] = (),
) -> bool:
    """Require Qunar source-owned anchors to mention the target entity."""

    url = str(source.get("url") or "").strip()
    if not is_qunar_url(url):
        return True
    route = source.get("travelRoute") if isinstance(source.get("travelRoute"), list) else []
    anchor_text = " ".join(
        [
            str(source.get("title") or ""),
            " ".join(str(item or "") for item in route),
            str(source.get("cityName") or ""),
        ]
    )
    return _text_mentions_entity(anchor_text, entity_id, entity_aliases=entity_aliases)


def _verified_article_sources_from_prior_plans(
    execution_id: str,
    entity_id: str,
    *,
    entity_type: str,
    entity_aliases: list[str] | tuple[str, ...] = (),
    rejected_source_urls: set[str] | None = None,
    limit: int = 24,
) -> list[dict[str, Any]]:
    root = _execution_root(execution_id)
    etype = str(entity_type or "景区").strip().split("/")[-1] or "景区"
    current = root / "entities" / "地点" / etype / entity_id / STAGE_DOWNLOAD / "article_source_plan.json"
    candidate_paths: list[Path] = [current]
    for execution_dir in _execution_dirs(execution_id):
        plan = execution_dir / "entities" / "地点" / etype / entity_id / STAGE_DOWNLOAD / "article_source_plan.json"
        if plan != current:
            candidate_paths.append(plan)
    sources: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for path in candidate_paths:
        for raw_source in _sources_from_article_plan(path):
            url = str(raw_source.get("url") or "").strip()
            if not url or url in seen_urls:
                continue
            if rejected_source_urls and _url_in_memory(url, rejected_source_urls):
                continue
            gate = raw_source.get("candidateGate") if isinstance(raw_source.get("candidateGate"), dict) else {}
            if gate and gate.get("passed") is False:
                continue
            category = str(raw_source.get("category") or "").strip()
            source = dict(raw_source)
            original_id = str(source.get("source_id") or "article_source").strip()
            source["originalSourceId"] = original_id
            source["source_id"] = f"article_reused_{len(sources) + 1}_{_normalized_title(original_id)[:24]}"
            source["discoveryProvider"] = "verified_source_pool_reuse"
            source["reuseSourcePlan"] = relative_execution_ref(path, execution_id)
            if category in _ARTICLE_BASE_CATEGORIES and not source.get("sourceRole"):
                source["sourceRole"] = "base"
            if not source.get("matchConfidence"):
                source["matchConfidence"] = (gate.get("matchConfidence") if gate else 0.86) or 0.86
            if not _qunar_article_mentions_entity(
                source,
                entity_id=entity_id,
                entity_aliases=entity_aliases,
            ):
                continue
            current_gate = _candidate_gate(
                source,
                entity_id=entity_id,
                lane="article",
                entity_aliases=entity_aliases,
            )
            if not current_gate["passed"]:
                continue
            source["candidateGate"] = current_gate
            sources.append(source)
            seen_urls.add(url)
            if len(sources) >= limit:
                return sources
    return sources
