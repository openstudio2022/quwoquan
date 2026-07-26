"""Typed lane writers for automatic source research plans."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from core.data_issue import DataIssueCode, DataRecoveryAction
from content.source.research.plan_state import (
    _image_at,
    _record_unavailable,
    _safe_collection_id,
    _source_unavailable_for_entity,
    _write_lane,
)
from content.source.research.source_quality import (
    _collection_gate,
    _collection_admissible_image_urls,
    _evidence_reason,
)

def _independent_homepage_media_collections(
    candidates: list[dict[str, Any]],
    *,
    entity_id: str,
    entity_aliases: list[str],
    vertical: str,
    report: dict[str, Any],
    limit: int = 1,
) -> list[dict[str, Any]]:
    """Build explicit homepage media evidence without mutating text sources."""
    collections: list[dict[str, Any]] = []
    used_collection_ids: set[str] = set()
    for ordinal, raw_item in enumerate(candidates, start=1):
        if not isinstance(raw_item, dict):
            continue
        item = dict(raw_item)
        collection_id = _safe_collection_id(
            "homepage_media",
            entity_id,
            str(
                item.get("sourceCollectionId")
                or item.get("authorizationProof")
                or item.get("sourceUrl")
                or item.get("url")
                or ""
            ),
        )
        if collection_id in used_collection_ids:
            continue
        used_collection_ids.add(collection_id)
        creator = str(
            item.get("creator")
            or item.get("credit")
            or "Wikimedia Commons contributor"
        ).strip()
        collection_page = str(
            item.get("collectionPageUrl")
            or item.get("sourceUrl")
            or item.get("authorizationProof")
            or item.get("url")
            or ""
        ).strip()
        item.update(
            {
                "sourceCollectionId": collection_id,
                "creator": creator,
                "credit": item.get("credit") or creator,
                "collectionPageUrl": collection_page,
                "modelReleaseStatus": item.get("modelReleaseStatus") or "not_required",
                "researchLane": "homepage",
                "sourceId": f"homepage_media_{ordinal}",
            }
        )
        collection = {
            "sourceCollectionId": collection_id,
            "creator": creator,
            "credit": item.get("credit") or creator,
            "collectionPageUrl": collection_page,
            "platform": item.get("platform") or "Wikimedia Commons",
            "license": item.get("license") or "",
            "termsUrl": item.get("termsUrl") or "",
            "licenseSnapshot": item.get("licenseSnapshot") or "",
            "authorizationProof": item.get("authorizationProof") or collection_page,
            "usageScope": item.get("usageScope") or "app_publish",
            "modelReleaseStatus": item["modelReleaseStatus"],
            "mediaEvidenceMode": "independent_rights_cleared",
            "entityMatch": "strong",
            "discoveryProvider": "open_license_homepage_media_search",
            "evidenceReason": _evidence_reason(
                entity_id,
                "homepage",
                "Independent rights-cleared homepage media search",
                "open_license",
            ),
            "images": [item],
        }
        verdict = _collection_gate(
            collection,
            entity_id=entity_id,
            entity_aliases=entity_aliases,
            vertical=vertical,
        )
        report.setdefault("homepageMediaCollections", []).append(
            {
                "entityId": entity_id,
                "sourceCollectionId": collection_id,
                "platform": collection.get("platform") or "",
                "imageCount": 1,
                "passed": bool(verdict.get("passed")),
                "issues": list(verdict.get("issues") or []),
            }
        )
        if verdict["passed"]:
            collections.append(collection)
        if len(collections) >= max(1, limit):
            break
    return collections

def write_image_lane(
    *,
    entity_id: str,
    entity_aliases: list[str],
    vertical: str,
    plan_dir: Path,
    force: bool,
    report: dict[str, Any],
    updated: list[dict[str, Any]],
    prior_image_collections: list[dict[str, Any]],
    prior_image_pool: list[dict[str, Any]],
    openverse: list[dict[str, Any]],
    commons: list[dict[str, Any]],
    hint_commons: list[dict[str, Any]],
    wikidata_commons: list[dict[str, Any]],
    wiki_page_images: list[dict[str, Any]],
    voyage_page_images: list[dict[str, Any]],
    open_license_image_pool: list[dict[str, Any]],
    homepage_image_urls: set[str],
    required_publishable_images: int,
    required_article_bases: int,
    desired_image_works: int,
    hard_image_works: int,
    image_bonus_saturation_count: int,
    image_policy: str,
    image_strategy: str,
    requires_publishable_images: bool,
    qid: str,
    wiki_title: str,
    voyage_title: str,
) -> None:
        collections: list[dict[str, Any]] = []
        desired_image_collections = max(
            required_publishable_images + 3,
            min(12, required_publishable_images + required_article_bases + 3),
        )
        used_collection_ids: set[str] = set()
        for collection in prior_image_collections:
            collection_id = str(collection.get("sourceCollectionId") or "").strip()
            if not collection_id or collection_id in used_collection_ids:
                continue
            collection_verdict = _collection_gate(
                collection,
                entity_id=entity_id,
                entity_aliases=entity_aliases,
                vertical=vertical,
            )
            report.setdefault("imageCollections", []).append(
                {
                    "entityId": entity_id,
                    "sourceCollectionId": collection_id,
                    "platform": collection.get("platform") or "",
                    "imageCount": len(collection.get("images") or []),
                    "passed": bool(collection_verdict.get("passed")),
                    "issues": list(collection_verdict.get("issues") or []),
                    "discoveryProvider": "verified_source_pool_reuse",
                }
            )
            if not collection_verdict["passed"]:
                continue
            used_collection_ids.add(collection_id)
            collections.append(collection)
            if len(collections) >= desired_image_collections:
                break
        first_image = (
            _image_at(prior_image_pool, 0)
            or _image_at(openverse, 0)
            or _image_at(commons, 0)
            or _image_at(wikidata_commons, 0)
            or _image_at(wiki_page_images, 0)
            or _image_at(voyage_page_images, 0)
        )
        if first_image and len(collections) < desired_image_collections:
            collection_candidates = (
                openverse
                + commons
                + hint_commons
                + wikidata_commons
                + wiki_page_images
                + voyage_page_images
            )
            collection_candidates = sorted(
                collection_candidates,
                key=lambda item: str(item.get("url") or "") in homepage_image_urls,
            )
            for raw_item in collection_candidates:
                item = dict(raw_item)
                collection_id = _safe_collection_id(
                    "open_license_file",
                    entity_id,
                    str(item.get("sourceCollectionId") or item.get("sourceUrl") or item.get("url") or ""),
                )
                if collection_id in used_collection_ids:
                    continue
                used_collection_ids.add(collection_id)
                item["sourceCollectionId"] = collection_id
                item["creator"] = item.get("creator") or item.get("credit") or "Wikimedia Commons contributor"
                item["collectionPageUrl"] = item.get("collectionPageUrl") or item.get("sourceUrl") or item.get("url") or ""
                item["modelReleaseStatus"] = item.get("modelReleaseStatus") or "not_required"
                item["researchLane"] = "image"
                collection = {
                    "sourceCollectionId": collection_id,
                    "creator": item["creator"],
                    "credit": item.get("credit") or item["creator"],
                    "collectionPageUrl": item["collectionPageUrl"],
                    "platform": item.get("platform") or "Openverse",
                    "license": item.get("license") or "",
                    "termsUrl": item.get("termsUrl") or "",
                    "licenseSnapshot": item.get("licenseSnapshot") or "",
                    "authorizationProof": item.get("authorizationProof") or item["collectionPageUrl"],
                    "usageScope": "app_publish",
                    "modelReleaseStatus": item["modelReleaseStatus"],
                    "discoveryProvider": "open_license_image_search",
                    "evidenceReason": _evidence_reason(
                        entity_id, "image", "Open license image search", "open_license"
                    ),
                    "images": [item],
                }
                collection_verdict = _collection_gate(
                    collection,
                    entity_id=entity_id,
                    entity_aliases=entity_aliases,
                    vertical=vertical,
                )
                report.setdefault("imageCollections", []).append(
                    {
                        "entityId": entity_id,
                        "sourceCollectionId": collection_id,
                        "platform": collection.get("platform") or "",
                        "imageCount": len(collection.get("images") or []),
                        "passed": bool(collection_verdict.get("passed")),
                        "issues": list(collection_verdict.get("issues") or []),
                    }
                )
                if collection_verdict["passed"]:
                    collections.append(collection)
                if len(collections) >= desired_image_collections:
                    break
        if not requires_publishable_images:
            report.setdefault("imageCollections", []).append(
                {
                    "entityId": entity_id,
                    "sourceCollectionId": "",
                    "platform": "",
                    "imageCount": len(open_license_image_pool),
                    "passed": True,
                    "issues": [],
                    "discoveryProvider": "reference_only_image_strategy",
                    "imageAssetStrategy": image_strategy,
                }
            )
        elif hard_image_works and not collections:
            _record_unavailable(
                report,
                entity_id=entity_id,
                lane="image",
                reason="no single-author/single-file rights-cleared image collection",
                code=DataIssueCode.MEDIA_RIGHTS_UNAVAILABLE,
                recovery=DataRecoveryAction.STOP,
            )
        elif hard_image_works and len(collections) < hard_image_works:
            _record_unavailable(
                report,
                entity_id=entity_id,
                lane="image",
                reason=f"image collections={len(collections)} need>={hard_image_works}",
                code=DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL,
                recovery=DataRecoveryAction.STOP,
            )
        else:
            unique_publishable_images = len(
                _collection_admissible_image_urls(
                    collections,
                    entity_id=entity_id,
                    entity_aliases=entity_aliases,
                    vertical=vertical,
                )
            )
            if required_publishable_images and unique_publishable_images < required_publishable_images:
                _record_unavailable(
                    report,
                    entity_id=entity_id,
                    lane="image",
                    reason=(
                        f"unique publishable images={unique_publishable_images} "
                        f"need>={required_publishable_images}"
                    ),
                    code=DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL,
                    recovery=DataRecoveryAction.STOP,
                )
        if _write_lane(
        plan_dir / "image_source_plan.json",
            "image",
            {
                "collections": collections,
                "imageDiscoveryDiagnostics": {
                    "imageAssetStrategy": image_strategy,
                    "imageCountPolicy": image_policy,
                    "requiresPublishableImages": requires_publishable_images,
                    "desiredImageWorks": desired_image_works,
                    "imageBonusSaturationCount": image_bonus_saturation_count,
                    "requiredImageWorks": hard_image_works,
                    "requiredPublishableImages": required_publishable_images,
                    "qid": qid,
                    "wikiTitle": wiki_title,
                    "voyageTitle": voyage_title,
                    "entityAliases": entity_aliases[:24],
                    "poolCounts": {
                        "priorImageCollections": len(prior_image_collections),
                        "priorImagePool": len(prior_image_pool),
                        "commons": len(commons),
                        "hintCommons": len(hint_commons),
                        "wikidataCommons": len(wikidata_commons),
                        "openverse": len(openverse),
                        "wikiPageImages": len(wiki_page_images),
                        "voyagePageImages": len(voyage_page_images),
                        "openLicenseImagePool": len(open_license_image_pool),
                        "acceptedCollections": len(collections),
                    },
                    "sourceUnavailable": _source_unavailable_for_entity(
                        report,
                        entity_id=entity_id,
                        lane="image",
                    ),
                },
                "sourceUnavailable": _source_unavailable_for_entity(
                    report,
                    entity_id=entity_id,
                    lane="image",
                ),
            },
            force=force,
        ):
            updated.append(
                {
                    "entityId": entity_id,
                    "lane": "image",
                    "collections": len(collections),
                    "images": sum(len(c.get("images") or []) for c in collections),
                }
            )
