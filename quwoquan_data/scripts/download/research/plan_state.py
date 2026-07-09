"""State, persistence and reuse helpers for auto research plans."""
from __future__ import annotations

import hashlib
import os
import re
import urllib.parse
from pathlib import Path
from typing import Any, Mapping

from _common.io import read_json, write_json
from _common.paths import (
    STAGE_DOWNLOAD,
    batch_root,
    batches_root,
    iter_task_batch_dirs,
    relative_batch_ref,
)
from _common.source_catalog import vertical_from_task_id
from _common.source_plan_contract import source_plan_rule_signature
from _common.source_unit import resolve_entity_object_dir
from _common.qunar_template import is_qunar_url

from download.research.source_quality import (
    _ARTICLE_BASE_CATEGORIES,
    _HOMEPAGE_CORE_SOURCE_LIMIT,
    _candidate_gate,
    _collection_gate,
    _homepage_text_quality_issue,
    _source_category,
    _travel_registry_url_fetchable,
)
from download.research.text_match import _normalized_title, _text_mentions_entity

_DOWNLOAD_REJECT_MEMORY_BATCH_LIMIT = max(
    1,
    int(os.environ.get("QWQ_DOWNLOAD_REJECT_MEMORY_BATCH_LIMIT", "8")),
)

_VERIFIED_IMAGE_PLAN_SCAN_LIMIT = max(
    0,
    int(os.environ.get("QWQ_VERIFIED_IMAGE_PLAN_SCAN_LIMIT", "80")),
)

_MEDIAWIKI_PAGE_IMAGE_LIMIT = max(
    1,
    int(os.environ.get("QWQ_MEDIAWIKI_PAGE_IMAGE_LIMIT", "8")),
)

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
    row: dict[str, Any] = {
        "source_id": source_id,
        "platform": platform,
        "url": url,
        "sourceUseMode": "factual_reference_only",
        "category": source_category,
        "discoveryProvider": discovery_provider,
        "matchConfidence": round(float(match_confidence or 0.0), 3),
        "evidenceReason": evidence_reason,
        "sourceRole": source_role,
        "imageEvidenceMode": image_evidence_mode,
        "entityMatch": "strong" if match_confidence >= 0.72 else "weak",
    }
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
    limit: int = _MEDIAWIKI_PAGE_IMAGE_LIMIT,
) -> dict[str, Any]:
    """Hydrate same-source image evidence for MediaWiki homepage sources.

    Homepage lane only allows same-source images. When a candidate is a
    MediaWiki page URL but arrives from reuse/registry without image evidence,
    re-resolve the page title from the URL and fetch page-owned images from the
    single MediaWiki truth source before the source enters the consumable plan.
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
        import download.research_plan as research_plan_mod
    except Exception:  # noqa: BLE001
        return row
    try:
        images = research_plan_mod._mediawiki_page_images(
            host,
            title,
            entity_id=entity_id,
            limit=max(1, int(limit or _MEDIAWIKI_PAGE_IMAGE_LIMIT)),
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
    entity_aliases: list[str] | tuple[str, ...] = (),
) -> dict[str, Any] | None:
    verdict = _candidate_gate(
        source,
        entity_id=entity_id,
        lane=lane,
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
    entity_aliases: list[str] | tuple[str, ...] = (),
    rejected_source_urls: set[str] | None = None,
) -> dict[str, Any] | None:
    url = str(source.get("url") or "").strip()
    if rejected_source_urls and _url_in_memory(url, rejected_source_urls):
        if lane == "homepage" and _travel_registry_url_fetchable(url):
            return _accept_source(
                report,
                source,
                entity_id=entity_id,
                lane=lane,
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
        entity_aliases=entity_aliases,
    )

def _record_unavailable(
    report: dict[str, Any],
    *,
    entity_id: str,
    lane: str,
    reason: str,
    next_action: str = "manual_research_or_target_replacement",
) -> None:
    report.setdefault("sourceUnavailable", []).append(
        {
            "entityId": entity_id,
            "lane": lane,
            "reason": reason,
            "nextAction": next_action,
        }
    )

def _source_unavailable_for_entity(
    report: Mapping[str, Any],
    *,
    entity_id: str,
    lane: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in report.get("sourceUnavailable") or []:
        if not isinstance(item, Mapping):
            continue
        if str(item.get("entityId") or "") != entity_id:
            continue
        item_lane = str(item.get("lane") or "")
        if item_lane not in {lane, "all"}:
            continue
        rows.append(dict(item))
    return rows

def _task_spec(task_id: str) -> dict[str, Any]:
    try:
        from task import store

        return store.load_spec(task_id)
    except Exception:  # noqa: BLE001
        return {}

def _task_content_quotas(task_id: str) -> dict[str, int]:
    spec = _task_spec(task_id)
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
    task_id = str(plan.get("taskId") or "")
    entity_id = str(plan.get("ref") or payload.get("entityId") or "").strip()
    if task_id and entity_id:
        plan["sourceRuleSignature"] = source_plan_rule_signature(
            vertical_from_task_id(task_id),
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

def _url_memory_keys(url: str) -> set[str]:
    raw = str(url or "").strip()
    if not raw:
        return set()
    keys = {raw}
    try:
        unquoted = urllib.parse.unquote(raw)
    except Exception:  # noqa: BLE001
        unquoted = raw
    if unquoted:
        keys.add(unquoted)
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme and parsed.netloc:
        normalized = urllib.parse.urlunparse(
            (
                parsed.scheme.lower(),
                parsed.netloc.lower(),
                parsed.path,
                "",
                parsed.query,
                "",
            )
        )
        keys.add(normalized)
        try:
            keys.add(urllib.parse.unquote(normalized))
        except Exception:  # noqa: BLE001
            pass
    return {key for key in keys if key}

def _url_in_memory(url: str, memory: set[str]) -> bool:
    if not memory:
        return False
    return bool(_url_memory_keys(url) & memory)

def _add_url_memory(memory: set[str], url: str) -> None:
    memory.update(_url_memory_keys(url))

def _urls_from_issue_text(text: str) -> list[str]:
    urls: list[str] = []
    for match in re.finditer(r"https?://[^)\]\s\"']+", str(text or "")):
        url = match.group(0).rstrip("。；;,，")
        if url:
            urls.append(url)
    return urls

def _task_batch_dirs_recency(task_id: str) -> list[Path]:
    """该任务的所有批次目录，按 mtime 倒序（顶层 runtime/batches/ 反查，跨批次复用来源）。"""
    return sorted(
        iter_task_batch_dirs(task_id),
        key=lambda path: path.stat().st_mtime if path.exists() else 0,
        reverse=True,
    )

def _entity_download_dirs_for_history(
    task_id: str,
    batch_id: str,
    entity_id: str,
    *,
    entity_type: str,
) -> list[Path]:
    root = batch_root(task_id, batch_id)
    etype = str(entity_type or "景区").strip().split("/")[-1] or "景区"
    dirs: list[Path] = [
        root / "entities" / "地点" / etype / entity_id / STAGE_DOWNLOAD,
    ]
    for batch_dir in _task_batch_dirs_recency(task_id)[:_DOWNLOAD_REJECT_MEMORY_BATCH_LIMIT]:
        dl = batch_dir / "entities" / "地点" / etype / entity_id / STAGE_DOWNLOAD
        if dl not in dirs:
            dirs.append(dl)
    return dirs

def _download_reject_memory(
    task_id: str,
    batch_id: str,
    entity_id: str,
    *,
    entity_type: str,
) -> dict[str, set[str]]:
    """Return source/image URLs proven bad by prior fetch and screen gates.

    Source planning can reuse known-good pools, but it must also remember known
    bad URLs. Otherwise a repair loop keeps selecting pages/images that the
    deterministic fetch and source_screen stages have already rejected.
    """

    source_urls: set[str] = set()
    image_urls: set[str] = set()
    root = batch_root(task_id, batch_id)
    for dl in _entity_download_dirs_for_history(
        task_id,
        batch_id,
        entity_id,
        entity_type=entity_type,
    ):
        rejected_root = dl / "rejected_sources"
        if rejected_root.is_dir():
            for quality_path in sorted(rejected_root.glob("*/source.quality.json")):
                try:
                    quality = read_json(quality_path)
                except Exception:  # noqa: BLE001
                    continue
                try:
                    meta = read_json(quality_path.parent / "meta.json")
                except Exception:  # noqa: BLE001
                    meta = {}
                homepage_fetch_retry_blocked = (
                    str(meta.get("researchLane") or "") == "homepage"
                    and str(meta.get("platform") or "") in {"百度百科", "搜狗百科"}
                    and not bool(quality.get("fetchSucceeded"))
                    and int(quality.get("statusCode") or 0) == 0
                    and not _travel_registry_url_fetchable(str(quality.get("url") or ""))
                )
                if not (_source_reject_should_enter_memory(quality) or homepage_fetch_retry_blocked):
                    continue
                _add_url_memory(source_urls, str(quality.get("url") or ""))

    batch_dirs = [root]
    batch_dirs.extend(
        path
        for path in _task_batch_dirs_recency(task_id)[:_DOWNLOAD_REJECT_MEMORY_BATCH_LIMIT]
        if path != root
    )
    for batch_dir in batch_dirs:
        gate_path = (
            batch_dir
            / "task_download"
            / "results"
            / "image_fetch_gate"
            / f"{entity_id}.json"
        )
        if not gate_path.is_file():
            continue
        try:
            gate = read_json(gate_path)
        except Exception:  # noqa: BLE001
            continue
        payload = gate.get("payload") if isinstance(gate.get("payload"), dict) else gate
        evidence = payload.get("evidenceSummary") or payload.get("evidence_summary") or {}
        for item in evidence.get("rejectedForQuality") or []:
            text = str(item or "")
            hard_reject = any(
                marker in text
                for marker in (
                    "imageSafety",
                    "watermark",
                    "imagePixels",
                    "imageRelevance",
                    "unsupported license",
                    "missing image rights",
                    "rights",
                )
            )
            if not hard_reject:
                continue
            for url in _urls_from_issue_text(str(item)):
                _add_url_memory(image_urls, url)
    return {"sourceUrls": source_urls, "imageUrls": image_urls}

def _source_reject_should_enter_memory(quality: dict[str, Any]) -> bool:
    """Only hard source rejects enter planning memory.

    A network/policy soft failure has no page body and no quality reasons. If a
    registry policy or fetch strategy is fixed later, planning must be able to
    retry that URL instead of carrying a stale "bad source" forever.
    """

    if bool(quality.get("fetchSucceeded")):
        return True
    try:
        status_code = int(quality.get("statusCode") or 0)
    except (TypeError, ValueError):
        status_code = 0
    if status_code >= 400:
        return True
    reasons = quality.get("reasons") if isinstance(quality.get("reasons"), list) else []
    try:
        score = int(quality.get("score") or 0)
    except (TypeError, ValueError):
        score = 0
    return bool(reasons) or score > 0

def _filter_rejected_images(
    images: list[dict[str, Any]],
    rejected_image_urls: set[str],
) -> list[dict[str, Any]]:
    if not rejected_image_urls:
        return images
    filtered: list[dict[str, Any]] = []
    for image in images:
        url = str(image.get("url") or "").strip()
        source_url = str(image.get("sourceUrl") or "").strip()
        proof = str(image.get("authorizationProof") or "").strip()
        if (
            _url_in_memory(url, rejected_image_urls)
            or _url_in_memory(source_url, rejected_image_urls)
            or _url_in_memory(proof, rejected_image_urls)
        ):
            continue
        filtered.append(image)
    return filtered

def _normalize_collection_for_reuse(collection: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(collection)
    collection_id = str(normalized.get("sourceCollectionId") or "").strip()
    normalized_images: list[dict[str, Any]] = []
    for image in normalized.get("images") or []:
        if not isinstance(image, dict):
            continue
        item = dict(image)
        if collection_id and not item.get("sourceCollectionId"):
            item["sourceCollectionId"] = collection_id
        if normalized.get("creator") and not item.get("creator"):
            item["creator"] = normalized.get("creator")
        if normalized.get("collectionPageUrl") and not item.get("collectionPageUrl"):
            item["collectionPageUrl"] = normalized.get("collectionPageUrl")
        for field in (
            "license",
            "termsUrl",
            "authorizationProof",
            "licenseSnapshot",
            "usageScope",
            "modelReleaseStatus",
        ):
            if normalized.get(field) and not item.get(field):
                item[field] = normalized.get(field)
        if not item.get("modelReleaseStatus"):
            item["modelReleaseStatus"] = "not_required"
        normalized_images.append(item)
    normalized["images"] = normalized_images
    normalized.setdefault("modelReleaseStatus", "not_required")
    normalized["discoveryProvider"] = "verified_source_pool_reuse"
    return normalized

def _verified_image_collections_from_prior_plans(
    task_id: str,
    batch_id: str,
    entity_id: str,
    *,
    entity_type: str,
    entity_aliases: list[str] | tuple[str, ...] = (),
    rejected_image_urls: set[str] | None = None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Reuse already verified image collections from the current task.

    External visual discovery is intentionally broad but can be unstable across
    retries. Reusing previous source plans keeps retries deterministic while
    still re-running the asset-level collection gate before publishability.
    """
    root = batch_root(task_id, batch_id)
    runtime_root = batches_root().parent
    etype = str(entity_type or "景区").strip().split("/")[-1] or "景区"
    current = root / "entities" / "地点" / etype / entity_id / STAGE_DOWNLOAD / "image_source_plan.json"
    candidate_paths: list[Path] = [current]
    for batch_dir in _task_batch_dirs_recency(task_id):
        plan = batch_dir / "entities" / "地点" / etype / entity_id / STAGE_DOWNLOAD / "image_source_plan.json"
        if plan != current:
            candidate_paths.append(plan)
    all_batches_root = batches_root()
    if all_batches_root.is_dir() and _VERIFIED_IMAGE_PLAN_SCAN_LIMIT:
        cross_task_plans = [
            path
            for path in all_batches_root.glob(
                f"*/entities/地点/{etype}/{entity_id}/{STAGE_DOWNLOAD}/image_source_plan.json"
            )
            if path != current and path not in candidate_paths
        ]
        cross_task_plans.sort(
            key=lambda path: path.stat().st_mtime if path.exists() else 0,
            reverse=True,
        )
        candidate_paths.extend(cross_task_plans[:_VERIFIED_IMAGE_PLAN_SCAN_LIMIT])
    collections: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in candidate_paths:
        for raw_collection in _collections_from_image_plan(path):
            collection = _normalize_collection_for_reuse(raw_collection)
            if rejected_image_urls:
                collection["images"] = _filter_rejected_images(
                    list(collection.get("images") or []),
                    rejected_image_urls,
                )
            collection_id = str(collection.get("sourceCollectionId") or "").strip()
            if not collection_id or collection_id in seen:
                continue
            verdict = _collection_gate(
                collection,
                entity_id=entity_id,
                entity_aliases=entity_aliases,
                allow_verified_collection_id_match=False,
            )
            if not verdict["passed"]:
                continue
            try:
                reuse_ref = path.relative_to(runtime_root).as_posix()
            except ValueError:
                reuse_ref = path.as_posix()
            collection["reuseSourcePlan"] = reuse_ref
            collections.append(collection)
            seen.add(collection_id)
            if len(collections) >= limit:
                return collections
    return collections

def _images_from_collections(collections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    images: list[dict[str, Any]] = []
    seen: set[str] = set()
    for collection in collections:
        collection_id = str(collection.get("sourceCollectionId") or "").strip()
        for image in collection.get("images") or []:
            if not isinstance(image, dict):
                continue
            item = dict(image)
            url = str(item.get("url") or "").strip()
            if not url or url in seen:
                continue
            if collection_id and not item.get("sourceCollectionId"):
                item["sourceCollectionId"] = collection_id
            seen.add(url)
            images.append(item)
    return images

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
    task_id: str,
    batch_id: str,
    entity_id: str,
    *,
    entity_type: str,
) -> set[str]:
    etype = str(entity_type or "景区").strip().split("/")[-1] or "景区"
    path = (
        batch_root(task_id, batch_id)
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
    task_id: str,
    batch_id: str,
    entity_id: str,
    *,
    entity_type: str,
    rejected_source_urls: set[str] | None = None,
    limit: int = _HOMEPAGE_CORE_SOURCE_LIMIT,
) -> list[dict[str, Any]]:
    """Reuse homepage source units that already passed source_screen.

    Source repair should not discard a working wiki/official source while
    retrying a failed Baidu/Sogou candidate. This keeps the repair loop
    monotonic and prevents the planner from cycling over known-bad URLs.
    """
    from _common.source_unit import iter_source_units

    obj = resolve_entity_object_dir(task_id, batch_id, entity_id, etype_hint=entity_type)
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
        url = str(meta.get("url") or quality.get("url") or "").strip()
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
                "sourceUseMode": str(meta.get("sourceUseMode") or "factual_reference_only"),
                "category": _source_category(platform, category),
                "discoveryProvider": "verified_homepage_source_unit_reuse",
                "matchConfidence": 0.97,
                "evidenceReason": f"reuse retained homepage source unit {unit.name}",
                "sourceRole": "primary" if not sources else "supporting",
                "imageEvidenceMode": "",
                "entityMatch": "strong",
                "reuseSourceUnit": relative_batch_ref(unit / "source.md", task_id, batch_id),
                },
                entity_id=entity_id,
            )
        )
        seen_urls.add(url)
        if len(sources) >= limit:
            break
    return sources

def _qunar_reused_article_mentions_entity(
    source: Mapping[str, Any],
    *,
    entity_id: str,
    entity_aliases: list[str] | tuple[str, ...] = (),
) -> bool:
    """Current-template guard for legacy Qunar source-pool reuse.

    Older plans may have accepted same-author Qunar rows whose evidenceReason
    names the target entity while the actual travelogue title is unrelated.
    Reuse must therefore inspect only source-owned anchor fields, not the old
    generated reason text.
    """

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
    task_id: str,
    batch_id: str,
    entity_id: str,
    *,
    entity_type: str,
    entity_aliases: list[str] | tuple[str, ...] = (),
    rejected_source_urls: set[str] | None = None,
    limit: int = 24,
) -> list[dict[str, Any]]:
    root = batch_root(task_id, batch_id)
    runtime_root = batches_root().parent
    etype = str(entity_type or "景区").strip().split("/")[-1] or "景区"
    current = root / "entities" / "地点" / etype / entity_id / STAGE_DOWNLOAD / "article_source_plan.json"
    candidate_paths: list[Path] = [current]
    for batch_dir in _task_batch_dirs_recency(task_id):
        plan = batch_dir / "entities" / "地点" / etype / entity_id / STAGE_DOWNLOAD / "article_source_plan.json"
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
            try:
                source["reuseSourcePlan"] = path.relative_to(runtime_root).as_posix()
            except ValueError:
                source["reuseSourcePlan"] = path.as_posix()
            if category in _ARTICLE_BASE_CATEGORIES and not source.get("sourceRole"):
                source["sourceRole"] = "base"
            if not source.get("matchConfidence"):
                source["matchConfidence"] = (gate.get("matchConfidence") if gate else 0.86) or 0.86
            if not _qunar_reused_article_mentions_entity(
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
