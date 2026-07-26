"""State, persistence and reuse helpers for auto research plans."""
from __future__ import annotations

import hashlib
import os
import re
import urllib.parse
from pathlib import Path
from typing import Any, Mapping

from core.data_issue import (
    DataIssue,
    DataIssueCode, DataIssueStage,
    DataIssueLane,
    DataRecoveryAction,
    data_issue,
)
from core.baike_source_contract import (
    HOMEPAGE_SOURCE_POLICY_REVISION,
    SOURCE_EXTRACTORS,
    SOURCE_LICENSE_METADATA,
    SOURCE_USE_MODES,
    source_identity_matches_contract,
)
from core.io import read_json, write_json
from core.paths import STAGE_DOWNLOAD
from content.execution.workspace import (
    execution_command_root,
    execution_root,
    relative_execution_ref,
)
from core.source_catalog import vertical_from_task_id
from core.source_plan_contract import source_plan_rule_signature
from content.source.source_unit import resolve_entity_object_dir
from core.qunar_template import is_qunar_url

from content.source.research.source_quality import (
    _ARTICLE_BASE_CATEGORIES,
    _candidate_gate,
    _collection_gate,
    _source_category,
)
from content.source.research.source_registry import _travel_registry_url_fetchable
from content.source.research.text_match import _normalized_title, _text_mentions_entity

_MEDIAWIKI_SOURCE_HOST_SUFFIXES = ("wikipedia.org", "wikivoyage.org")

def _safe_collection_id(prefix: str, entity_id: str, ref: str) -> str:
    raw = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", str(ref or "").lower())[:60]
    raw = raw or _normalized_title(entity_id) or "source"
    digest = hashlib.sha1(str(ref or raw).encode("utf-8")).hexdigest()[:10]
    return f"{prefix}:{entity_id}:{raw}:{digest}"

def _image_at(images: list[dict[str, Any]], index: int) -> dict[str, Any] | None:
    if not images:
        return None
    return dict(images[index % len(images)])

def _image_window(
    images: list[dict[str, Any]],
    index: int,
    *,
    count: int = 3,
) -> list[dict[str, Any]]:
    """Return a small deterministic candidate window for one source unit.

    A source image is part of an article/homepage draft. Giving the downloader
    multiple rights-cleared candidates keeps the lane resilient to a broken CDN
    object without mixing in unvetted or unrelated assets.
    """
    if not images or count <= 0:
        return []
    window: list[dict[str, Any]] = []
    seen: set[str] = set()
    for offset in range(min(count, len(images))):
        image = _image_at(images, index + offset)
        if not image:
            continue
        url = str(image.get("url") or "")
        if not url or url in seen:
            continue
        seen.add(url)
        window.append(image)
    return window

def _source(
    *,
    source_id: str,
    platform: str,
    url: str,
    source_kind: str = "",
    source_title: str = "",
    qualified_authority_title: str = "",
    image: dict[str, Any] | None = None,
    images: list[dict[str, Any]] | None = None,
    category: str = "",
    discovery_provider: str = "",
    match_confidence: float = 0.0,
    evidence_reason: str = "",
    source_role: str = "supporting",
    image_evidence_mode: str = "",
    fetchable_override: bool | None = None,
) -> dict[str, Any]:
    source_category = _source_category(platform, category)
    explicit_source_kind = str(source_kind or "").strip()
    row: dict[str, Any] = {
        "source_id": source_id,
        "platform": platform,
        "url": url,
        "sourceUseMode": SOURCE_USE_MODES.get(explicit_source_kind, "factual_reference_only"),
        "category": source_category,
        "discoveryProvider": discovery_provider,
        "matchConfidence": round(float(match_confidence or 0.0), 3),
        "evidenceReason": evidence_reason,
        "sourceRole": source_role,
        "imageEvidenceMode": image_evidence_mode,
        "entityMatch": "strong" if match_confidence >= 0.72 else "weak",
    }
    if explicit_source_kind:
        row.update(
            {
                "sourceKind": explicit_source_kind,
                "sourceTitle": str(source_title or platform).strip(),
                "canonicalUrl": url,
                "extractor": SOURCE_EXTRACTORS.get(explicit_source_kind, ""),
                "policyRevision": HOMEPAGE_SOURCE_POLICY_REVISION,
            }
        )
        row.update(SOURCE_LICENSE_METADATA.get(explicit_source_kind, {}))
    if qualified_authority_title.strip():
        row["qualifiedAuthorityTitle"] = qualified_authority_title.strip()
    if fetchable_override is True:
        row["fetchable"] = True
        row["fetchableOverride"] = True
    candidates: list[dict[str, Any]] = []
    if images:
        candidates.extend(dict(item) for item in images if isinstance(item, dict))
    if image:
        candidates.append(dict(image))
    if candidates:
        seen: set[str] = set()
        row["imageUrls"] = []
        for item in candidates:
            image_url = str(item.get("url") or "")
            if not image_url or image_url in seen:
                continue
            seen.add(image_url)
            item.setdefault("modelReleaseStatus", "not_required")
            row["imageUrls"].append(item)
    return row

def _mediawiki_title_from_url(url: str) -> tuple[str, str]:
    parsed = urllib.parse.urlparse(str(url or "").strip())
    host = str(parsed.hostname or "").strip().lower()
    if not host or not any(host.endswith(suffix) for suffix in _MEDIAWIKI_SOURCE_HOST_SUFFIXES):
        return "", ""
    if "/wiki/" not in parsed.path:
        return "", ""
    title = urllib.parse.unquote(parsed.path.split("/wiki/", 1)[1].split("#", 1)[0]).replace("_", " ").strip()
    return host, title

def _hydrate_mediawiki_same_source_images(
    source: Mapping[str, Any] | dict[str, Any],
    *,
    entity_id: str,
) -> dict[str, Any]:
    """Hydrate same-source image evidence for MediaWiki homepage sources.

    Homepage lane only allows same-source images. When a candidate is a
    MediaWiki page URL but arrives from reuse/registry without image evidence,
    re-resolve the page title from the URL and fetch page-owned images from the
    single MediaWiki truth source before the source enters the consumable content.execution.planning.
    """

    row = dict(source)
    existing_images = row.get("imageUrls") if isinstance(row.get("imageUrls"), list) else []
    if str(row.get("imageEvidenceMode") or "").strip() == "same_source" and any(
        isinstance(item, dict) and str(item.get("url") or "").strip()
        for item in existing_images
    ):
        return row
    host, title = _mediawiki_title_from_url(str(row.get("url") or ""))
    if not host or not title:
        return row
    try:
        # Local import breaks the plan_state <-> wiki_media module cycle while
        # keeping the dependency on the concrete provider explicit.
        from content.source.research.wiki_media import _mediawiki_page_images

        images = _mediawiki_page_images(
            host,
            title,
            entity_id=entity_id,
        )
    except Exception:  # noqa: BLE001
        return row
    hydrated: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for item in images or []:
        if not isinstance(item, dict):
            continue
        image_url = str(item.get("url") or "").strip()
        if not image_url or image_url in seen_urls:
            continue
        seen_urls.add(image_url)
        hydrated.append(dict(item))
    if not hydrated:
        return row
    row["imageUrls"] = hydrated
    row["imageEvidenceMode"] = "same_source"
    return row

def _accept_source(
    report: dict[str, Any],
    source: dict[str, Any],
    *,
    entity_id: str,
    lane: str,
    vertical: str,
    entity_aliases: list[str] | tuple[str, ...] = (),
) -> dict[str, Any] | None:
    verdict = _candidate_gate(
        source,
        entity_id=entity_id,
        lane=lane,
        vertical=vertical,
        entity_aliases=entity_aliases,
    )
    source["candidateGate"] = verdict
    report.setdefault("candidates", []).append(
        {
            "entityId": entity_id,
            "lane": lane,
            "source_id": source.get("source_id") or "",
            "platform": source.get("platform") or "",
            "url": source.get("url") or "",
            "category": verdict.get("category") or "",
            "discoveryProvider": source.get("discoveryProvider") or "",
            "matchConfidence": verdict.get("matchConfidence"),
            "evidenceReason": source.get("evidenceReason") or "",
            "passed": bool(verdict.get("passed")),
            "issues": list(verdict.get("issues") or []),
            "warnings": list(verdict.get("warnings") or []),
        }
    )
    return source if verdict["passed"] else None

def _reject_source_candidate(
    report: dict[str, Any],
    source: dict[str, Any],
    *,
    entity_id: str,
    lane: str,
    reason: str,
) -> None:
    verdict = {
        "passed": False,
        "issues": [reason],
        "warnings": [],
        "category": source.get("category") or "",
        "matchConfidence": source.get("matchConfidence") or 0,
        "role": source.get("sourceRole") or "supporting",
    }
    source["candidateGate"] = verdict
    report.setdefault("candidates", []).append(
        {
            "entityId": entity_id,
            "lane": lane,
            "source_id": source.get("source_id") or "",
            "platform": source.get("platform") or "",
            "url": source.get("url") or "",
            "category": verdict.get("category") or "",
            "discoveryProvider": source.get("discoveryProvider") or "",
            "matchConfidence": verdict.get("matchConfidence"),
            "evidenceReason": source.get("evidenceReason") or "",
            "passed": False,
            "issues": [reason],
            "warnings": [],
        }
    )

def _accept_source_with_reject_memory(
    report: dict[str, Any],
    source: dict[str, Any],
    *,
    entity_id: str,
    lane: str,
    vertical: str,
    entity_aliases: list[str] | tuple[str, ...] = (),
    rejected_source_urls: set[str] | None = None,
) -> dict[str, Any] | None:
    from content.source.research.reject_memory import _url_in_memory

    url = str(source.get("url") or "").strip()
    if rejected_source_urls and _url_in_memory(url, rejected_source_urls):
        if lane == "homepage" and _travel_registry_url_fetchable(url):
            return _accept_source(
                report,
                source,
                entity_id=entity_id,
                lane=lane,
                vertical=vertical,
                entity_aliases=entity_aliases,
            )
        _reject_source_candidate(
            report,
            source,
            entity_id=entity_id,
            lane=lane,
            reason="source URL previously rejected by download/source_screen gate",
        )
        return None
    return _accept_source(
        report,
        source,
        entity_id=entity_id,
        lane=lane,
        vertical=vertical,
        entity_aliases=entity_aliases,
    )

def _record_unavailable(
    report: dict[str, Any],
    *,
    entity_id: str,
    lane: str,
    reason: str,
    code: DataIssueCode,
    recovery: DataRecoveryAction,
) -> None:
    report.setdefault("sourceUnavailable", []).append(data_issue(
        code,
        stage=DataIssueStage.DOWNLOAD_PLAN,
        ref=entity_id,
        lane=DataIssueLane(lane),
        recovery=recovery,
        message=reason,
    ).as_dict())

def _source_unavailable_for_entity(
    report: Mapping[str, Any],
    *,
    entity_id: str,
    lane: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in report.get("sourceUnavailable") or []:
        if not isinstance(item, Mapping):
            raise TypeError("sourceUnavailable rows must use DataIssue objects")
        issue = DataIssue.from_dict(item)
        if issue.ref != entity_id:
            continue
        item_lane = issue.lane.value
        if item_lane not in {lane, "all"}:
            continue
        rows.append(issue.as_dict())
    return rows

def _task_spec(execution_id: str) -> dict[str, Any]:
    try:
        from content.execution import store

        return store.load_spec(execution_id)
    except Exception:  # noqa: BLE001
        return {}

def _task_content_quotas(execution_id: str) -> dict[str, int]:
    spec = _task_spec(execution_id)
    quotas = ((spec.get("content") or {}).get("quotas") or {})
    return {
        "entityArticlesPerTarget": max(0, int(quotas.get("entityArticlesPerTarget") or 0)),
        "imageWorksPerTarget": max(0, int(quotas.get("imageWorksPerTarget") or 0)),
        "entityHomepagesPerTarget": max(0, int(quotas.get("entityHomepagesPerTarget") or 0)),
    }

def _plan_has_payload(plan: dict[str, Any], lane: str) -> bool:
    payload = plan.get("payload") if isinstance(plan.get("payload"), dict) else {}
    if lane == "image":
        return bool(payload.get("collections") or plan.get("collections"))
    return bool(payload.get("sources") or plan.get("sources"))

def _write_lane(path: Path, lane: str, payload_update: dict[str, Any], *, force: bool) -> bool:
    plan = read_json(path) if path.is_file() else {}
    if not force and _plan_has_payload(plan, lane):
        return False
    payload = dict(plan.get("payload") or {})
    payload.update(payload_update)
    plan["payload"] = payload
    execution_id = str(plan.get("executionId") or "")
    entity_id = str(plan.get("ref") or payload.get("entityId") or "").strip()
    if execution_id and entity_id:
        plan["sourceRuleSignature"] = source_plan_rule_signature(
            vertical_from_task_id(execution_id),
            entity_id,
        )
    write_json(path, plan)
    return True

def _collections_from_image_plan(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        plan = read_json(path)
    except Exception:  # noqa: BLE001
        return []
    payload = plan.get("payload") if isinstance(plan.get("payload"), dict) else {}
    rows = payload.get("collections") or plan.get("collections") or []
    return [dict(row) for row in rows if isinstance(row, dict)]
