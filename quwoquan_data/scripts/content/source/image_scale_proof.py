"""Open-license image scale proof for source preflight."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from core.image_rules import pixel_size_issue
from core.image_asset_strategy import (
    image_count_is_hard_quota,
    image_count_policy,
    minimum_publishable_images_per_target,
)
from core.io import write_json
from core.paths import execution_root
from content.source.research.source_quality import _license_allows_app_publish  # noqa: PLC2701
from content.source.source_inputs import curated_images_for_entity
from content.execution import store
from content.execution.coverage import coverage_entity_ids, coverage_entity_type


OPEN_LICENSE_SCALE_PROOF_SCHEMA = "quwoquan_data.open_license_scale_proof"


def _quota_int(spec: Mapping[str, Any], key: str, default: int = 0) -> int:
    content = spec.get("content") if isinstance(spec.get("content"), Mapping) else {}
    quotas = content.get("quotas") if isinstance(content.get("quotas"), Mapping) else {}
    try:
        return max(0, int((quotas or {}).get(key) or default))
    except (TypeError, ValueError):
        return default


def _ratio_score(value: int, saturation: int) -> float:
    if saturation <= 0:
        return 1.0
    return round(min(max(value, 0) / saturation, 1.0), 4)


def _publishable_image_issue(image: Mapping[str, Any]) -> str:
    url = str(image.get("url") or "").strip()
    if not url:
        return "missing url"
    if str(image.get("researchLane") or "image") != "image":
        return "not image research lane"
    for field in ("license", "credit", "sourceUrl", "termsUrl", "authorizationProof", "usageScope"):
        if not str(image.get(field) or "").strip():
            return f"missing {field}"
    if str(image.get("usageScope") or "") != "app_publish":
        return f"usageScope={image.get('usageScope') or ''} is not app_publish"
    if not _license_allows_app_publish(str(image.get("license") or ""), str(image.get("termsUrl") or "")):
        return f"license {image.get('license') or ''} is not app publish compatible"
    try:
        width = int(image.get("width") or 0)
        height = int(image.get("height") or 0)
    except (TypeError, ValueError):
        width = 0
        height = 0
    pixel_issue = pixel_size_issue(width, height, asset_id=url)
    if pixel_issue:
        return pixel_issue
    collection_id = str(image.get("sourceCollectionId") or "").strip()
    if not collection_id:
        return "missing sourceCollectionId"
    return ""


def build_open_license_scale_proof(execution_id: str) -> dict[str, Any]:
    spec = store.load_spec(execution_id)
    entity_ids = coverage_entity_ids(spec)
    entity_type = coverage_entity_type(spec)
    desired_image_works = _quota_int(spec, "imageWorksPerTarget", default=0)
    minimum_image_works = (
        desired_image_works
        if image_count_is_hard_quota(spec)
        else minimum_publishable_images_per_target(spec)
    )
    desired_assets = len(entity_ids) * desired_image_works
    minimum_assets = len(entity_ids) * minimum_image_works
    count_policy = image_count_policy(spec)
    root = execution_root(execution_id)
    entity_rows: list[dict[str, Any]] = []
    all_urls: set[str] = set()
    all_collection_ids: set[str] = set()
    minimum_passed_entities = 0
    desired_passed_entities = 0
    for entity_id in entity_ids:
        images = curated_images_for_entity(
            execution_id,
            entity_id,
            entity_type,
            research_lane="image",
        )
        publishable: list[dict[str, str]] = []
        rejected: list[dict[str, str]] = []
        used_collections: set[str] = set()
        for image in images:
            url = str(image.get("url") or "").strip()
            collection_id = str(image.get("sourceCollectionId") or "").strip()
            issue = _publishable_image_issue(image)
            if issue:
                rejected.append({"url": url, "sourceCollectionId": collection_id, "reason": issue})
                continue
            if url in all_urls:
                rejected.append({"url": url, "sourceCollectionId": collection_id, "reason": "asset reused in proof"})
                continue
            if collection_id in used_collections:
                rejected.append(
                    {
                        "url": url,
                        "sourceCollectionId": collection_id,
                        "reason": "same sourceCollectionId already counted for this entity",
                    }
                )
                continue
            publishable.append({"url": url, "sourceCollectionId": collection_id})
            used_collections.add(collection_id)
            if desired_image_works and len(publishable) >= desired_image_works:
                break
        for item in publishable:
            all_urls.add(item["url"])
            all_collection_ids.add(item["sourceCollectionId"])
        minimum_passed = len(publishable) >= minimum_image_works
        desired_passed = desired_image_works <= 0 or len(publishable) >= desired_image_works
        if minimum_passed:
            minimum_passed_entities += 1
        if desired_passed:
            desired_passed_entities += 1
        image_count_score = _ratio_score(len(publishable), desired_image_works)
        entity_rows.append(
            {
                "entityId": entity_id,
                "imageCountPolicy": count_policy,
                "desiredImageWorks": desired_image_works,
                "minimumImageWorks": minimum_image_works,
                "requiredImageWorks": minimum_image_works,
                "publishableImageAssets": len(publishable),
                "publishableSourceCollections": len({item["sourceCollectionId"] for item in publishable}),
                "minimumPassed": minimum_passed,
                "desiredPassed": desired_passed,
                "passed": minimum_passed,
                "imageCountScore": image_count_score,
                "imageQualityScore": 1.0 if publishable else 0.0,
                "compositeScore": image_count_score,
                "assets": publishable,
                "rejectedSample": rejected[:8],
            }
        )
    average_image_count_score = round(
        sum(float(row.get("imageCountScore") or 0.0) for row in entity_rows) / len(entity_rows),
        4,
    ) if entity_rows else 0.0
    proof = {
        "preScreenedEntityCount": minimum_passed_entities,
        "desiredPassedEntityCount": desired_passed_entities,
        "scoredEntityCount": len(entity_rows),
        "publishableImageAssets": len(all_urls),
        "sourceCollectionCount": len(all_collection_ids),
        "imageCountPolicy": count_policy,
        "desiredImageWorksPerTarget": desired_image_works,
        "minimumImageWorksPerTarget": minimum_image_works,
        "desiredPublishableImageAssets": desired_assets,
        "minimumPublishableImageAssets": minimum_assets,
        "averageImageCountScore": average_image_count_score,
        "averageCompositeScore": average_image_count_score,
        "assetPoolPath": str(root / "entities"),
        "verifiedAt": datetime.now(timezone.utc).isoformat(),
    }
    passed = (
        minimum_passed_entities >= len(entity_ids)
        and len(all_urls) >= minimum_assets
        and (
            count_policy != "hard_quota"
            or desired_image_works <= 0
            or (
                desired_passed_entities >= len(entity_ids)
                and len(all_urls) >= desired_assets
            )
        )
    )
    report = {
        "schema": OPEN_LICENSE_SCALE_PROOF_SCHEMA,
        "executionId": execution_id,
        "requiredEntityCount": len(entity_ids),
        "imageCountPolicy": count_policy,
        "imageWorksPerTarget": desired_image_works,
        "desiredImageWorksPerTarget": desired_image_works,
        "minimumImageWorksPerTarget": minimum_image_works,
        "desiredPublishableImageAssets": desired_assets,
        "minimumPublishableImageAssets": minimum_assets,
        "requiredPublishableImageAssets": minimum_assets,
        "passed": passed,
        "desiredPassed": desired_passed_entities >= len(entity_ids) and len(all_urls) >= desired_assets,
        "averageImageCountScore": average_image_count_score,
        "averageCompositeScore": average_image_count_score,
        "proof": proof,
        "failedEntityCount": len(entity_ids) - minimum_passed_entities,
        "belowDesiredEntityCount": len(entity_ids) - desired_passed_entities,
        "failedEntitySample": [
            row["entityId"] for row in entity_rows if not row["passed"]
        ][:50],
        "belowDesiredEntitySample": [
            row["entityId"] for row in entity_rows if not row["desiredPassed"]
        ][:50],
        "rankedEntities": [
            {
                "entityId": row["entityId"],
                "minimumPassed": row["minimumPassed"],
                "desiredPassed": row["desiredPassed"],
                "publishableImageAssets": row["publishableImageAssets"],
                "imageCountScore": row["imageCountScore"],
                "compositeScore": row["compositeScore"],
            }
            for row in sorted(
                entity_rows,
                key=lambda item: (
                    -float(item.get("compositeScore") or 0.0),
                    str(item.get("entityId") or ""),
                ),
            )
        ],
        "entities": entity_rows,
    }
    return report


def write_open_license_scale_proof(report: Mapping[str, Any]) -> Path:
    path = (
        execution_root(str(report["executionId"]))
        / "_shared"
        / "open_license_scale_proof.json"
    )
    write_json(path, dict(report))
    return path


__all__ = [
    "build_open_license_scale_proof",
    "write_open_license_scale_proof",
]
