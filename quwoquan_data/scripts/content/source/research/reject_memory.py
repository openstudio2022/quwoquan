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
    _candidate_gate,
    _collection_gate,
    _source_category,
)
from content.source.research.source_registry import _travel_registry_url_fetchable
from content.source.research.text_match import _normalized_title, _text_mentions_entity

_MEDIAWIKI_SOURCE_HOST_SUFFIXES = ("wikipedia.org", "wikivoyage.org")

from content.source.research.plan_state import _collections_from_image_plan, _safe_collection_id

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
        keys.add(urllib.parse.unquote(normalized))
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

def _execution_dirs(execution_id: str) -> list[Path]:
    """返回唯一当前 execution 工作包；禁止跨 execution 复用运行期来源。"""
    root = execution_root(execution_id)
    return [root] if root.is_dir() else []

def _execution_root(execution_id: str) -> Path:
    return execution_root(execution_id)

def _entity_download_dirs_for_history(
    execution_id: str,
    entity_id: str,
    *,
    entity_type: str,
) -> list[Path]:
    root = _execution_root(execution_id)
    etype = str(entity_type or "景区").strip().split("/")[-1] or "景区"
    dirs: list[Path] = [
        root / "entities" / "地点" / etype / entity_id / STAGE_DOWNLOAD,
    ]
    for execution_dir in _execution_dirs(execution_id):
        dl = execution_dir / "entities" / "地点" / etype / entity_id / STAGE_DOWNLOAD
        if dl not in dirs:
            dirs.append(dl)
    return dirs

def _download_reject_memory(
    execution_id: str,
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
    root = _execution_root(execution_id)
    for dl in _entity_download_dirs_for_history(
        execution_id,
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
                    and str(meta.get("platform") or "") in {"百度百科", "今日头条百科"}
                    and not bool(quality.get("fetchSucceeded"))
                    and int(quality.get("statusCode") or 0) == 0
                    and not _travel_registry_url_fetchable(str(quality.get("url") or ""))
                )
                if not (_source_reject_should_enter_memory(quality) or homepage_fetch_retry_blocked):
                    continue
                _add_url_memory(source_urls, str(quality.get("url") or ""))

    from core.homepage_source_failure import (
        SOURCE_RECOVERY_FAILURE_KINDS,
        entity_page_failure_kind,
        read_entity_page_failure,
    )

    etype = str(entity_type or "景区").strip().split("/")[-1] or "景区"
    draft_dir = root / "entities" / "地点" / etype / entity_id / "4.draft"
    source_failure = read_entity_page_failure(draft_dir)
    if (
        source_failure is not None
        and entity_page_failure_kind(source_failure) in SOURCE_RECOVERY_FAILURE_KINDS
    ):
        for evidence in source_failure.get("evidence") or []:
            if not isinstance(evidence, Mapping):
                continue
            for url in _urls_from_issue_text(str(evidence.get("quote") or "")):
                _add_url_memory(source_urls, url)
        for reason in source_failure.get("reasons") or []:
            for url in _urls_from_issue_text(str(reason or "")):
                _add_url_memory(source_urls, url)

    gate_path = (
        execution_command_root(execution_id, "source")
        / "results"
        / "image_fetch_gate"
        / f"{entity_id}.json"
    )
    if gate_path.is_file():
        try:
            gate = read_json(gate_path)
        except Exception:  # noqa: BLE001
            gate = {}
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
    execution_id: str,
    entity_id: str,
    *,
    entity_type: str,
    vertical: str,
    entity_aliases: list[str] | tuple[str, ...] = (),
    rejected_image_urls: set[str] | None = None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Reuse already verified image collections from the current task.

    External visual discovery is intentionally broad but can be unstable across
    retries. Reusing previous source plans keeps retries deterministic while
    still re-running the asset-level collection gate before publishability.
    """
    root = _execution_root(execution_id)
    etype = str(entity_type or "景区").strip().split("/")[-1] or "景区"
    current = root / "entities" / "地点" / etype / entity_id / STAGE_DOWNLOAD / "image_source_plan.json"
    candidate_paths: list[Path] = [current]
    for execution_dir in _execution_dirs(execution_id):
        plan = execution_dir / "entities" / "地点" / etype / entity_id / STAGE_DOWNLOAD / "image_source_plan.json"
        if plan != current:
            candidate_paths.append(plan)
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
                vertical=vertical,
            )
            if not verdict["passed"]:
                continue
            collection["reuseSourcePlan"] = relative_execution_ref(path, execution_id)
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
