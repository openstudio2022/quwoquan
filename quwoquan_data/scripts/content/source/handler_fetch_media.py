"""Materialize standalone image collections and close per-entity media gates."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.data_issue import (
    DataIssueCode,
    DataIssueLane,
    DataIssueStage,
    DataRecoveryAction,
    data_issues,
)
from core.paths import execution_source_unit_dir

from content.execution.stage_reports import write_gate_report
from content.source.handler_images import (
    _prune_stale_rejected_source_units,
    _prune_stale_source_units,
)
from content.source.handler_plan import _write_download_progress
from content.source.source_unit import slugify, write_source_unit


@dataclass(frozen=True)
class EntityMediaClosureInput:
    execution_id: str
    entity_id: str
    entity_index: int
    entity_count: int
    object_dir: Path
    target_ref: str
    sources: tuple[Mapping[str, Any], ...]
    image_specs: tuple[Mapping[str, Any], ...]
    pending_images: tuple[dict[str, Any], ...]
    provider_asset_counts: tuple[Mapping[str, Any], ...]
    existing_image_source_dirs: frozenset[Path]
    written_source_dirs: frozenset[Path]
    written_rejected_source_dirs: frozenset[Path]
    selected_lanes: frozenset[str] | None
    image_rights_issues: tuple[str, ...]
    image_quality_issues: tuple[str, ...]
    rejected_by_category: Mapping[str, int]
    image_lane_selected: bool
    homepage_media_selected: bool
    required_image_work_images: int
    required_homepage_media: int
    required_images: int
    planned_homepage_source_images: int
    kept_source_homepage_images: int


def _source_collection_title(image: Mapping[str, Any]) -> str:
    """Keep only an explicit source title; collection identifiers are not copy."""

    return str(image.get("title") or "").strip()


def _image_collection_source_use_mode(images: list[dict[str, Any]]) -> str:
    professional = [
        image
        for image in images
        if str(image.get("acquisitionReceiptRef") or "").strip()
    ]
    if not professional:
        return "licensed_adaptation"
    if len(professional) != len(images):
        raise ValueError("image collection cannot mix professional and ordinary assets")
    for image in professional:
        identity = (
            str(image.get("acquisitionReceiptRef") or "").strip(),
            str(image.get("professionalAssetId") or "").strip(),
            str(image.get("professionalContentSha256") or "").strip(),
        )
        if not all(identity):
            raise ValueError(
                "professional image collection lacks exact acquisition identity"
            )
        if image.get("distributionDecision") not in {
            "research_allowed",
            "commercial_allowed",
        }:
            raise ValueError("professional image collection is not distribution-admitted")
        if image.get("rightsStatus") not in {"verified", "unverified", "unknown"}:
            raise ValueError("professional image collection rights status is blocked")
    return (
        "licensed_adaptation"
        if all(image.get("rightsStatus") == "verified" for image in professional)
        else "rights_audit_only"
    )


def _materialize_image_collections(spec: EntityMediaClosureInput) -> set[Path]:
    written = set(spec.written_source_dirs)
    image_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for image in spec.pending_images:
        lane = str(image.get("researchLane") or "image")
        collection_id = str(image.get("sourceCollectionId") or "").strip()
        if collection_id:
            image_groups[(lane, collection_id)].append(image)
    for offset, ((lane, collection_id), group) in enumerate(
        sorted(image_groups.items()), start=1
    ):
        first = group[0]
        source_id = str(first.get("sourceId") or "").strip() or f"{lane}_{slugify(collection_id)}"
        unit_lane = "homepage_image" if lane == "homepage" else lane
        collection_page = str(first.get("collectionPageUrl") or first.get("sourceUrl") or "")
        # Collections without a formal page title still retain a verified
        # provider caption.  It is evidence from the source record, unlike
        # the internal collection ID, and lets the source-unit schema expose
        # a human-reviewable title without inventing one.
        collection_title = _source_collection_title(first) or str(
            first.get("caption") or ""
        ).strip()
        collection_md = (
            "---\n"
            f"researchLane: {unit_lane}\n"
            f"sourceCollectionId: {collection_id}\n"
            f"creator: {first.get('creator') or first.get('credit') or ''}\n"
            f"url: {collection_page}\n"
            f"license: {first.get('license') or ''}\n"
            "---\n\n"
            f"{spec.entity_id} 图片来源集合，仅供结构化资产与授权链使用。\n"
        )
        manifest = write_source_unit(
            spec.object_dir,
            ordinal=len(spec.sources) + offset,
            source_id=source_id,
            source_md=collection_md,
            quality={
                "sourceId": source_id,
                "entity": spec.entity_id,
                "quality": "B-fact",
                "score": 1,
                "reasons": ["structured image collection"],
                "url": collection_page,
                "fetchSucceeded": True,
            },
            platform=str(first.get("platform") or "image_collection"),
            source_category="image_collection",
            source_kind="image_collection",
            extractor="image_collection_download",
            policy_revision="image-collection-attribution",
            source_use_mode=_image_collection_source_use_mode(group),
            research_lane=unit_lane,
            license_value=str(first.get("license") or ""),
            url=collection_page,
            title=collection_title,
            target_ref=spec.target_ref,
            relevance=f"{spec.entity_id} 同一来源图片集合",
            images=group,
            execution_id=spec.execution_id,
            build_variants=False,
        )
        written.add(
            execution_source_unit_dir(
                spec.execution_id, str(manifest.get("sourceUnitId") or "")
            )
        )
    return written


def _media_gate_issues(
    spec: EntityMediaClosureInput,
    *,
    kept_by_lane: Mapping[str, int],
    kept_images: int,
) -> tuple[list[str], list[str], list[Any]]:
    image_count_issues: list[str] = []
    homepage_count_issues: list[str] = []
    if spec.image_lane_selected and kept_by_lane["image"] < spec.required_image_work_images:
        image_count_issues.append(
            f"imageCount: {spec.entity_id} image lane 仅下到 {kept_by_lane['image']} 张合格图"
            f"（要求 ≥{spec.required_image_work_images}）"
        )
    if spec.homepage_media_selected and kept_by_lane["homepage"] < spec.required_homepage_media:
        homepage_count_issues.append(
            f"homepageMediaCount: {spec.entity_id} 独立主页媒体仅下到 "
            f"{kept_by_lane['homepage']} 张合格图（要求 ≥{spec.required_homepage_media}）"
        )
    count_issues = [
        *image_count_issues,
        *homepage_count_issues,
    ]
    all_rights_issues = list(spec.image_rights_issues)
    fetch_issues = [*all_rights_issues, *count_issues]
    if spec.required_images > 0 and kept_images == 0 and not all_rights_issues:
        fetch_issues.append(
            "imageFetch: 未下到真实图片，请在 source_plan 提供可用 imageUrls(CC/PD/授权)"
        )
    blocking_issues = fetch_issues if spec.required_images > 0 else []
    typed_issues: list[Any] = []
    if spec.required_images > 0:
        typed_issues.extend(data_issues(
            DataIssueCode.MEDIA_RIGHTS_UNAVAILABLE,
            stage=DataIssueStage.IMAGE_FETCH,
            ref=spec.entity_id,
            lane=DataIssueLane.IMAGE,
            messages=spec.image_rights_issues,
            recovery=DataRecoveryAction.REPLACE_MEDIA,
        ))
        typed_issues.extend(data_issues(
            DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL,
            stage=DataIssueStage.IMAGE_FETCH,
            ref=spec.entity_id,
            lane=DataIssueLane.IMAGE,
            messages=image_count_issues,
            recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
        ))
        typed_issues.extend(data_issues(
            DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL,
            stage=DataIssueStage.IMAGE_FETCH,
            ref=spec.entity_id,
            lane=DataIssueLane.HOMEPAGE,
            messages=homepage_count_issues,
            recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
        ))
        remaining = [
            issue for issue in blocking_issues
            if issue not in all_rights_issues and issue not in count_issues
        ]
        typed_issues.extend(data_issues(
            DataIssueCode.MEDIA_FETCH_FAILED,
            stage=DataIssueStage.IMAGE_FETCH,
            ref=spec.entity_id,
            lane=DataIssueLane.IMAGE,
            messages=remaining,
            recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
        ))
    return fetch_issues, blocking_issues, typed_issues


def close_entity_media(spec: EntityMediaClosureInput) -> tuple[int, bool]:
    rejected_by_category = dict(spec.rejected_by_category)
    image_quality_issues = list(spec.image_quality_issues)
    for image in spec.pending_images:
        if str(image.get("sourceCollectionId") or "").strip():
            continue
        image_quality_issues.append(
            f"imageCollection: {image.get('url') or '?'} missing sourceCollectionId"
        )
        rejected_by_category["other"] = rejected_by_category.get("other", 0) + 1

    written_source_dirs = _materialize_image_collections(spec)
    kept_images = len(spec.pending_images) + spec.kept_source_homepage_images
    kept_by_lane = {
        lane: sum(
            1 for image in spec.pending_images
            if str(image.get("researchLane") or "image") == lane
        )
        for lane in ("image", "homepage")
    }
    kept_by_lane["homepage"] += spec.kept_source_homepage_images
    fetch_issues, blocking_issues, typed_issues = _media_gate_issues(
        spec, kept_by_lane=kept_by_lane, kept_images=kept_images
    )

    preserved_dirs: set[Path] = set()
    if fetch_issues:
        preserved_dirs = set(spec.existing_image_source_dirs) - written_source_dirs
        written_source_dirs.update(preserved_dirs)
    pruned_units = _prune_stale_source_units(
        spec.object_dir,
        written_source_dirs,
        selected_lanes=None if spec.selected_lanes is None else set(spec.selected_lanes),
    )
    pruned_rejected = _prune_stale_rejected_source_units(
        spec.object_dir,
        set(spec.written_rejected_source_dirs),
        selected_lanes=None if spec.selected_lanes is None else set(spec.selected_lanes),
    )
    if preserved_dirs:
        print(
            f"[download] Preserved {len(preserved_dirs)} previous image source unit(s) "
            f"for failed repair of {spec.entity_id}", flush=True
        )
    if pruned_units:
        print(
            f"[download] Pruned {len(pruned_units)} stale source unit(s) for {spec.entity_id}: "
            + ", ".join(pruned_units), flush=True
        )
    if pruned_rejected:
        print(
            f"[download] Pruned {len(pruned_rejected)} stale rejected source unit(s) for {spec.entity_id}: "
            + ", ".join(pruned_rejected), flush=True
        )

    if (
        spec.image_lane_selected
        or spec.homepage_media_selected
        or bool(spec.provider_asset_counts)
    ):
        rights_issues = [
            *data_issues(
                DataIssueCode.MEDIA_RIGHTS_UNAVAILABLE,
                stage=DataIssueStage.IMAGE_RIGHTS,
                ref=spec.entity_id,
                lane=DataIssueLane.IMAGE,
                messages=spec.image_rights_issues,
                recovery=DataRecoveryAction.REPLACE_MEDIA,
            ),
        ]
        write_gate_report(
            execution_id=spec.execution_id,
            command="source",
            step="image_rights",
            ref=spec.entity_id,
            passed=not rights_issues,
            issues=rights_issues,
            evidence_summary={
                "plannedImages": len(spec.image_specs) + spec.planned_homepage_source_images,
                "blockedImages": len(rights_issues),
            },
            next_step="image_fetch",
        )
        write_gate_report(
            execution_id=spec.execution_id,
            command="source",
            step="image_fetch",
            ref=spec.entity_id,
            passed=not blocking_issues,
            issues=typed_issues,
            evidence_summary={
                "plannedImages": len(spec.image_specs) + spec.planned_homepage_source_images,
                "downloadedImages": kept_images,
                "minRequired": spec.required_images,
                "requiredByLane": {
                    "image": spec.required_image_work_images,
                    "homepage": spec.required_homepage_media,
                },
                "downloadedByLane": kept_by_lane,
                "rejectedForQuality": image_quality_issues,
                "rejectedByCategory": rejected_by_category,
                "nonBlockingImageIssues": fetch_issues if not blocking_issues else [],
                "sourceAssetCounts": [dict(row) for row in spec.provider_asset_counts],
            },
            next_step="quality_analysis",
        )
    for row in spec.provider_asset_counts:
        print(
            "[download] Source assets: "
            f"displayName={row.get('displayName') or '?'} "
            f"provider={row.get('provider') or 'unknown'} "
            f"assets={int(row.get('acceptedAssetCount') or 0)} "
            f"planned={int(row.get('plannedAssetCount') or 0)} "
            f"discovered={int(row.get('discoveredAssetCount') or 0)} "
            f"downloaded={int(row.get('downloadedAssetCount') or 0)} "
            f"accepted={int(row.get('acceptedAssetCount') or 0)} "
            f"rejected={int(row.get('rejectedAssetCount') or 0)}",
            flush=True,
        )
    print(
        f"[download] Entity done {spec.entity_index}/{spec.entity_count}: {spec.entity_id} "
        f"sources={len(spec.sources)} images={kept_images}", flush=True
    )
    _write_download_progress(
        spec.execution_id,
        status="running",
        entity_id=spec.entity_id,
        entity_index=spec.entity_index,
        entity_count=spec.entity_count,
        sources=len(spec.sources),
        images=kept_images,
        message="entity fetch done",
    )
    failed = (
        spec.image_lane_selected
        or spec.homepage_media_selected
    ) and bool(blocking_issues)
    return kept_images, failed
