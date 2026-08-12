"""Source and image quality gates for auto research plans."""
from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import Any

from core.image_rules import image_caption_quality_issue
from core.media_processing_policy import MEDIA_PROCESSING_POLICY
from core.qunar_template import QUNAR_PAGE_SEARCH_RESULT, qunar_page_type
from core.source_catalog import (
    ARTICLE_BASE_SOURCE_CATEGORIES,
    known_category_ids,
    platform_category,
)
from governance.coverage.license import (
    audit_image_rights,
    rights_proof_required,
    validate_image_rights,
)

from content.source.research.homepage_source_policy import (
    _homepage_candidate_has_fetch_evidence,
)
from content.source.research.text_match import _text_mentions_entity

_SUPPORTING_ONLY_CATEGORIES = {
    "authoritative_reference",
    "official",
    "map_geo",
    "weather",
    "review",
    "transport",
    "lodging",
}

_MAX_PUBLISHABLE_IMAGE_PIXELS = (
    MEDIA_PROCESSING_POLICY.max_publishable_image_pixels
)

def _image_pixel_issue(spec: Mapping[str, Any]) -> str:
    try:
        width = int(spec.get("width") or 0)
        height = int(spec.get("height") or 0)
    except (TypeError, ValueError):
        return ""
    if width <= 0 or height <= 0:
        return ""
    pixels = width * height
    if pixels > _MAX_PUBLISHABLE_IMAGE_PIXELS:
        return (
            f"imageRights pixelCount {pixels} exceeds "
            f"maxPublishablePixels {_MAX_PUBLISHABLE_IMAGE_PIXELS}"
        )
    return ""

def _image_mentions_entity(
    image: dict[str, Any],
    entity_id: str,
    *,
    entity_aliases: list[str] | tuple[str, ...] = (),
) -> bool:
    if not entity_id:
        return True
    for field in (
        "caption",
        "relevance",
        "visualSubject",
        "title",
        "sourceUrl",
        "collectionPageUrl",
        "authorizationProof",
        "url",
    ):
        if _text_mentions_entity(
            str(image.get(field) or ""),
            entity_id,
            entity_aliases=entity_aliases,
        ):
            return True
    return False

def _license_allows_app_publish(license_name: str, license_url: str = "") -> bool:
    value = f"{license_name} {license_url}".lower()
    if not value.strip():
        return False
    if "attribution_no_watermark" in value or "attribution no watermark" in value:
        return True
    if any(token in value for token in ("nc", "noncommercial", "nd", "noderivatives", "igo")):
        return False
    if any(token in value for token in ("cc0", "publicdomain", "public domain")):
        return True
    if re.search(r"\b1\.0\b", value) and (
        "creativecommons" in value
        or "cc by" in value
        or "by-sa" in value
        or "/by" in value
    ):
        return False
    return any(token in value for token in ("pd", "by-sa", "by/sa", "by/", " by"))

def _evidence_reason(entity_id: str, lane: str, provider: str, category: str) -> str:
    lane_label = {"homepage": "实体主页", "article": "图文文章", "image": "图库作品"}.get(lane, lane)
    return f"{provider} 发现的 {entity_id} {lane_label}候选来源；类别={category or 'unknown'}"

def _source_category(platform: str, fallback: str = "") -> str:
    normalized_fallback = str(fallback or "").strip()
    # 显式传入的 registry/category 真相源优先，避免像「维基导游 + encyclopedia」
    # 这样的 homepage authority 被平台别名回写成 travelogue。
    if normalized_fallback in known_category_ids():
        return normalized_fallback
    if normalized_fallback in ARTICLE_BASE_SOURCE_CATEGORIES:
        return normalized_fallback
    return platform_category(platform) or normalized_fallback

def _candidate_gate(
    source: dict[str, Any],
    *,
    entity_id: str,
    lane: str,
    vertical: str,
    entity_aliases: list[str] | tuple[str, ...] = (),
) -> dict[str, Any]:
    """Gate one source candidate before it can enter a lane source content.execution.planning.

    The gate is deliberately conservative. Discovery can record rejected rows in
    the diagnostic report, but only passed rows are written into consumable lane
    plans. This prevents weak wiki/search matches and city-level substitute pages
    from becoming article base evidence.
    """
    issues: list[str] = []
    url = str(source.get("url") or "").strip()
    platform = str(source.get("platform") or "").strip()
    category = str(source.get("category") or _source_category(platform) or "").strip()
    role = str(source.get("sourceRole") or "supporting").strip()
    confidence = float(source.get("matchConfidence") or 0.0)
    if not url.startswith("https://"):
        issues.append("url must use https")
    if not platform:
        issues.append("platform missing")
    if not category:
        issues.append(f"platform {platform!r} is not registered in source catalog")
    if confidence < 0.72:
        issues.append(f"matchConfidence {confidence:.2f} < 0.72")
    if str(source.get("entityMatch") or "") == "weak":
        issues.append("weak entity match is not allowed")
    if lane == "article" and role == "base":
        if category not in ARTICLE_BASE_SOURCE_CATEGORIES:
            issues.append(
                f"article base source category must be an article-quality source class, got {category or 'unknown'}"
            )
        if category in _SUPPORTING_ONLY_CATEGORIES:
            issues.append(f"{category} can only be supportingEvidence for article lane")
    if lane == "article":
        if qunar_page_type(url) == QUNAR_PAGE_SEARCH_RESULT:
            issues.append(
                "Qunar search result directory must enter discovery frontier, not article source plan"
            )
        # RC4 红线：文章配图必须同源（来自文章底稿自身图片）。same_authorized_collection
        # 表示用"另一授权图集"的图当文章配图＝跨源替代，是九寨沟问题的根因之一，显式拒绝。
        # （图片作品 image lane 的图库一源一作品才允许 same_authorized_collection。）
        if str(source.get("imageEvidenceMode") or "").strip() == "same_authorized_collection":
            issues.append(
                "article lane must not use same_authorized_collection image evidence "
                "(article images must be same-source from the article's own base draft)"
            )
    if (
        lane == "homepage"
        and category
        in {
            "encyclopedia",
            "overview_baike",
            "official",
            "official_site",
            "government",
        }
        and not _homepage_candidate_has_fetch_evidence(source, url)
    ):
        issues.append(
            "homepage source must be registry-fetchable, verified retained source, "
            "or carry a text snapshot before entering source plan"
        )
    image_warnings: list[str] = []
    valid_images: list[dict[str, Any]] = []
    enforce_rights = rights_proof_required(vertical)
    for index, image in enumerate(source.get("imageUrls") or [], start=1):
        content_issues: list[str] = []
        if not isinstance(image, dict):
            content_issues.append(f"image[{index}] must be object")
            if lane == "image":
                issues.extend(content_issues)
            else:
                image_warnings.extend(content_issues)
            continue
        if not str(image.get("url") or "").strip():
            content_issues.append(f"image[{index}] url missing")
        if entity_id and not _image_mentions_entity(
            image,
            entity_id,
            entity_aliases=entity_aliases,
        ):
            content_issues.append(f"image[{index}] metadata does not strongly mention entity")
        rights_issues = [
            f"image[{index}]: {issue}"
            for issue in audit_image_rights(image, vertical=vertical)
        ]
        if lane == "image":
            issues.extend(content_issues)
            if enforce_rights:
                issues.extend(rights_issues)
            else:
                image_warnings.extend(rights_issues)
        else:
            image_warnings.extend(content_issues)
            image_warnings.extend(rights_issues)
        if not content_issues and (not enforce_rights or not rights_issues):
            valid_images.append(image)
    if lane != "image" and "imageUrls" in source:
        if valid_images:
            source["imageUrls"] = valid_images
        else:
            source.pop("imageUrls", None)
            source["imageEvidenceMode"] = ""
    return {
        "passed": not issues,
        "issues": issues,
        "warnings": image_warnings,
        "category": category,
        "matchConfidence": confidence,
        "role": role,
    }

def _collection_image_spec(collection: Mapping[str, Any], image: Mapping[str, Any]) -> dict[str, Any]:
    spec: dict[str, Any] = {}
    for field in (
        "authorizationBasis",
        "sourceCollectionId",
        "creator",
        "credit",
        "collectionPageUrl",
        "platform",
        "license",
        "termsUrl",
        "licenseSnapshot",
        "authorizationProof",
        "usageScope",
        "sourceUrl",
        "modelReleaseRequired",
        "modelReleaseStatus",
        "propertyReleaseStatus",
        "pinUrl",
        "discoveryUrl",
        "originalAssetUrl",
        "sourceAuthor",
        "repostAttribution",
        "watermarkScan",
        "ocrScan",
        "collectedAt",
        "capturedAt",
        "contentSha256",
        "sourceId",
        "acquisitionReceiptRef",
        "professionalAssetId",
        "professionalContentSha256",
    ):
        value = image.get(field) or collection.get(field)
        if value not in ("", None):
            spec[field] = value
    rights_issues = image.get("rightsIssues") or collection.get("rightsIssues") or []
    if isinstance(rights_issues, list):
        spec["rightsIssues"] = [
            str(issue).strip() for issue in rights_issues if str(issue).strip()
        ]
    for field in (
        "url",
        "caption",
        "relevance",
        "title",
        "width",
        "height",
        "modelReleaseRequired",
        "modelReleaseStatus",
        "generationModel",
        "generationPromptHash",
        "generatedAt",
        "syntheticDisclosure",
    ):
        value = image.get(field)
        if value not in ("", None):
            spec[field] = value
    if not spec.get("sourceUrl"):
        spec["sourceUrl"] = (
            spec.get("collectionPageUrl")
            or spec.get("authorizationProof")
            or spec.get("url")
            or ""
        )
    if not spec.get("credit") and spec.get("creator"):
        spec["credit"] = spec["creator"]
    if not spec.get("creator") and spec.get("credit"):
        spec["creator"] = spec["credit"]
    return spec

def _collection_admissible_image_urls(
    collections: list[dict[str, Any]],
    *,
    entity_id: str,
    entity_aliases: list[str] | tuple[str, ...] = (),
    vertical: str,
) -> set[str]:
    urls: set[str] = set()
    for collection in collections:
        if not isinstance(collection, dict):
            continue
        verdict = _collection_gate(
            collection,
            entity_id=entity_id,
            entity_aliases=entity_aliases,
            vertical=vertical,
        )
        if not verdict["passed"]:
            continue
        for image in collection.get("images") or []:
            if not isinstance(image, dict):
                continue
            spec = _collection_image_spec(collection, image)
            url = str(spec.get("url") or "").strip()
            if not url:
                continue
            if validate_image_rights(spec, vertical=vertical):
                continue
            if rights_proof_required(vertical) and not _license_allows_app_publish(
                str(spec.get("license") or ""),
                str(spec.get("termsUrl") or ""),
            ):
                continue
            if not _image_mentions_entity(spec, entity_id, entity_aliases=entity_aliases):
                continue
            urls.add(url)
    return urls

def _collection_gate(
    collection: dict[str, Any],
    *,
    entity_id: str,
    entity_aliases: list[str] | tuple[str, ...] = (),
    allow_verified_collection_id_match: bool = False,
    vertical: str,
) -> dict[str, Any]:
    issues: list[str] = []
    rights_audit_issues: list[str] = []
    collection_id = str(collection.get("sourceCollectionId") or "").strip()
    if not collection_id:
        issues.append("sourceCollectionId missing")
    verified_collection_entity_match = (
        allow_verified_collection_id_match
        and collection_id
        and _text_mentions_entity(collection_id, entity_id, entity_aliases=entity_aliases)
    )
    images = collection.get("images") if isinstance(collection.get("images"), list) else []
    if not images:
        issues.append("no images in collection")
    creators: set[str] = set()
    for index, image in enumerate(images, start=1):
        if not isinstance(image, dict):
            issues.append(f"image[{index}] must be object")
            continue
        spec = _collection_image_spec(collection, image)
        creator = str(spec.get("creator") or spec.get("credit") or "").strip()
        if creator:
            creators.add(creator)
        missing_source_fields = [
            field
            for field in ("url", "sourceCollectionId")
            if not str(spec.get(field) or "").strip()
        ]
        if missing_source_fields:
            issues.append(
                f"image[{index}] missing collection source fields {missing_source_fields}"
            )
        audit_issues = audit_image_rights(spec, vertical=vertical)
        rights_audit_issues.extend(
            f"image[{index}]: {issue}" for issue in audit_issues
        )
        blocking_rights_issues = validate_image_rights(spec, vertical=vertical)
        if blocking_rights_issues:
            issues.extend(
                f"image[{index}]: {issue}" for issue in blocking_rights_issues
            )
        elif rights_proof_required(vertical) and not _license_allows_app_publish(
            str(spec.get("license") or ""),
            str(spec.get("termsUrl") or ""),
        ):
            issues.append(f"image[{index}]: imageRights unsupported license {spec.get('license')}")
        pixel_issue = _image_pixel_issue(spec)
        if pixel_issue:
            issues.append(f"image[{index}]: {pixel_issue}")
        caption_issue = image_caption_quality_issue(
            str(spec.get("caption") or spec.get("relevance") or ""),
            entity_id=entity_id,
            asset_id=f"{collection_id or '?'}#{index}",
        )
        if caption_issue:
            issues.append(f"image[{index}]: {caption_issue}")
        from governance.content_supply_policy import load_content_supply_policy

        prohibited_indicator = load_content_supply_policy(
            vertical
        ).media_subject.prohibited_indicator(
            spec.get("caption"),
            spec.get("relevance"),
            spec.get("title"),
            spec.get("sourceUrl"),
        )
        if prohibited_indicator:
            issues.append(
                f"image[{index}] visual subject is not representative of the travel place "
                f"(indicator={prohibited_indicator})"
            )
        if (
            entity_id
            and not verified_collection_entity_match
            and not _image_mentions_entity(
                spec,
                entity_id,
                entity_aliases=entity_aliases,
            )
        ):
            issues.append(f"image[{index}] relevance does not strongly mention entity")
    if len(creators) > 1:
        issues.append("image work collection cannot mix multiple creators")
    return {
        "passed": not issues,
        "issues": issues,
        "rightsAuditStatus": "verified" if not rights_audit_issues else "unverified",
        "rightsAuditIssues": rights_audit_issues,
    }

def _article_base_candidate_limit(required_article_bases: int) -> int:
    """Fetch quota plus enough buffer for text/image/rights/dedupe attrition.

    Four article objects usually need substantially more than four discovered
    candidates because short travel notes, missing source assets and one-asset
    one-use rules are filtered later by download/content gates.
    """
    required = max(1, int(required_article_bases or 1))
    if required <= 2:
        # Small research runs still face the full canonical-media attrition
        # surface.  Keep a bounded twelve-source discovery window so a few
        # already-published or single-image pages cannot starve the lane.
        return 12
    else:
        reserve = min(max(12, math.ceil(required * 2.5)), 24)
    return min(required + reserve, 32)

def _select_article_plan_sources(
    sources: list[dict[str, Any]],
    *,
    required_article_bases: int,
    max_sources: int = 0,
) -> list[dict[str, Any]]:
    """Keep base-source redundancy without crowding out supporting categories."""
    required = max(1, int(required_article_bases or 1))
    bases = [source for source in sources if source.get("sourceRole") == "base"]
    supporting = [source for source in sources if source.get("sourceRole") != "base"]
    base_keep = min(len(bases), _article_base_candidate_limit(required))
    max_rows = max(base_keep + 3, required + 4)
    if int(max_sources or 0) > 0:
        max_rows = max(required + 3, min(max_rows, int(max_sources)))
        base_keep = min(base_keep, max(required, max_rows - 3))
    selected: list[dict[str, Any]] = list(bases[:base_keep])
    seen_ids = {str(source.get("source_id") or "") for source in selected}
    categories = {str(source.get("category") or "") for source in selected if source.get("category")}

    for source in supporting:
        category = str(source.get("category") or "")
        source_id = str(source.get("source_id") or "")
        if source_id in seen_ids:
            continue
        if category and category not in categories:
            selected.append(source)
            seen_ids.add(source_id)
            categories.add(category)
        if len(categories) >= 3:
            break

    for source in [*supporting, *bases[base_keep:]]:
        source_id = str(source.get("source_id") or "")
        if source_id in seen_ids:
            continue
        selected.append(source)
        seen_ids.add(source_id)
        if len(selected) >= max_rows:
            break
    return selected[:max_rows]
