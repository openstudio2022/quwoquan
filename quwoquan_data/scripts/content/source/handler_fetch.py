"""Per-entity download fetch implementation."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from core.data_issue import (
    DataIssueCode,
    DataIssueError,
    DataIssueLane,
    DataIssueStage,
    DataRecoveryAction,
    data_issue,
)
from core.paths import execution_source_unit_dir

from content.source import handler_fetch_contract
from content.source.handler_fetch_images import prepare_entity_images
from content.source.handler_fetch_media import (
    EntityMediaClosureInput,
    close_entity_media,
)
from content.source.handler_fetch_metrics import (
    accepted_source_rows,
    apply_source_image_rejections,
    build_source_asset_count_row,
    page_has_inline_video,
    source_with_fetch_runtime,
)
from content.source.handler_fetch_setup import prepare_entity_fetch_plan
from content.source.handler_fetch_source_unit import adjudicate_source_candidate
from content.source.handler_images import (
    _image_lane_source_unit_dirs,
    _move_rejected_source_unit,
)
from content.source.handler_plan import _write_download_progress
from content.source.image_download import _download_source_unit_images
from content.source.inline_images import build_inline_image_candidates
from content.source.source_unit import write_source_unit


def _fetch_download_entity(
    *,
    execution_id: str,
    entity_type: str,
    vertical: str,
    domain: str,
    etype: str,
    entity_id: str,
    entity_index: int,
    entity_count: int,
    selected_lanes: set[str] | None = None,
    external_input_context: Any | None = None,
) -> dict[str, Any]:
    """Fetch and gate one entity in isolation for download_fetch concurrency."""
    fetched_sources: list[dict[str, Any]] = []
    quality_rows: list[dict[str, Any]] = []
    failed_image = False
    print(f"[download] Fetch entity {entity_index}/{entity_count}: {entity_id}", flush=True)
    _write_download_progress(
        execution_id,
        status="running",
        entity_id=entity_id,
        entity_index=entity_index,
        entity_count=entity_count,
        message="entity fetch started",
    )
    from content.source.research.scale_source_pool_runtime import (
        frozen_scale_source_pool_fetch_result,
    )

    frozen_result = frozen_scale_source_pool_fetch_result(
        execution_id,
        selected_lanes=selected_lanes,
        entity_id=entity_id,
        entity_type=entity_type,
        entity_index=entity_index,
    )
    if frozen_result is not None:
        return frozen_result
    plan = prepare_entity_fetch_plan(
        execution_id=execution_id,
        entity_id=entity_id,
        entity_type=entity_type,
        domain=domain,
        etype=etype,
        selected_lanes=selected_lanes,
        external_input_context=external_input_context,
    )
    object_dir, target_ref, sources = plan.object_dir, plan.target_ref, plan.sources
    existing_image_source_dirs = _image_lane_source_unit_dirs(object_dir)
    written_source_dirs: set[Path] = set()
    written_rejected_source_dirs: set[Path] = set()
    image_lane_selected = plan.image_lane_selected
    homepage_media_selected = plan.homepage_media_selected
    sourced_video_candidates = plan.sourced_video_candidates
    sourced_video_evidence = plan.sourced_video_evidence
    sourced_video_failure = plan.sourced_video_failure
    written_source_dirs.update(
        evidence_path.parent
        for evidence_path in sourced_video_evidence
    )
    image_specs = plan.image_specs
    _write_download_progress(
        execution_id,
        status="running",
        entity_id=entity_id,
        entity_index=entity_index,
        entity_count=entity_count,
        sources=0,
        images=0,
        message="entity source plan loaded",
        plannedSources=len(sources),
        plannedImages=len(image_specs),
        plannedVideos=len(sourced_video_candidates),
        admittedVideos=len(sourced_video_evidence),
    )
    if sourced_video_failure:
        _write_download_progress(
            execution_id,
            status="running",
            entity_id=entity_id,
            entity_index=entity_index,
            entity_count=entity_count,
            sources=0,
            images=0,
            message="direct video admission failed; target will be marked unavailable",
            lane="video",
            plannedVideos=len(sourced_video_candidates),
            admittedVideos=0,
            sourcedVideoFailure=sourced_video_failure[:800],
        )
    image_result = prepare_entity_images(
        execution_id=execution_id,
        entity_id=entity_id,
        entity_index=entity_index,
        entity_count=entity_count,
        vertical=vertical,
        object_dir=object_dir,
        sources=sources,
        image_specs=image_specs,
        image_lane_selected=image_lane_selected,
        homepage_media_selected=homepage_media_selected,
    )
    image_rights_issues = image_result.rights_issues
    image_quality_issues = image_result.quality_issues
    rejected_by_category = dict(image_result.rejected_by_category)
    pending_images = image_result.pending_images
    provider_asset_counts = image_result.provider_asset_counts
    professional_exclusions = image_result.professional_exclusions
    source_asset_counts = list(provider_asset_counts)
    required_image_work_images = image_result.required_image_work_images
    planned_homepage_source_images = image_result.planned_homepage_source_images
    required_homepage_media = image_result.required_homepage_media
    required_images = image_result.required_images

    seen_canonical_urls: set[str] = set()
    kept_source_homepage_images = 0

    for ordinal, source in enumerate(sources, start=1):
        try:
            handler_fetch_contract.require_source_candidate_admission(source)
        except ValueError as exc:
            raise DataIssueError(
                (
                    data_issue(
                        DataIssueCode.SOURCE_ENTITY_MISMATCH,
                        stage=DataIssueStage.DOWNLOAD_FETCH,
                        ref=entity_id,
                        lane=DataIssueLane(str(source.get("researchLane") or DataIssueLane.ALL.value)),
                        recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
                        message="source candidate failed its frozen match admission",
                        attributes={
                            "sourceId": str(source.get("source_id") or ""),
                            "reason": str(exc),
                        },
                    ),
                )
            ) from exc
        _write_download_progress(
            execution_id,
            status="running",
            entity_id=entity_id,
            entity_index=entity_index,
            entity_count=entity_count,
            sources=len(fetched_sources),
            images=len(pending_images),
            message="source fetch started",
            lane=str(source.get("researchLane") or ""),
            sourceId=str(source.get("source_id") or ""),
            sourceIndex=ordinal,
            sourceCount=len(sources),
        )
        candidate = adjudicate_source_candidate(
            source,
            execution_id=execution_id,
            entity_id=entity_id,
            object_dir=object_dir,
            ordinal=ordinal,
            seen_canonical_urls=seen_canonical_urls,
        )
        source_md = candidate.source_md
        clean_md = candidate.clean_md
        html_bytes = candidate.html_bytes
        raw_format = candidate.raw_format
        status_code = candidate.status_code
        fetched_text = candidate.fetched_text
        inline_images = candidate.inline_images
        source_layout = candidate.source_layout
        fetch_runtime = candidate.fetch_runtime
        quality = candidate.quality
        page_has_video = page_has_inline_video(html_bytes, fetched_text)
        source_images, source_image_issues, source_image_funnel = _download_source_unit_images(
            source,
            execution_id=execution_id,
            entity_id=entity_id,
            object_dir=object_dir,
            ordinal=ordinal,
            vertical=vertical,
            # 载体决定该资产的字节预算，载体来自来源单元自己声明的 research lane。
            research_lane=str(source.get("researchLane") or ""),
            extra_candidates=build_inline_image_candidates(inline_images, entity_id=entity_id),
        )
        if source_image_issues:
            image_quality_issues.extend(
                f"sourceImage:{source['source_id']}: {issue}"
                for issue in source_image_issues
            )
        apply_source_image_rejections(
            rejected_by_category,
            source_image_funnel.get("dropReasonCounts"),
        )
        source_for_unit = source_with_fetch_runtime(source, fetch_runtime)
        try:
            manifest = write_source_unit(
                object_dir,
                ordinal=ordinal,
                source_id=source["source_id"],
                source_md=source_md,
                clean_md=clean_md,
                html_bytes=html_bytes,
                quality=quality,
                platform=source.get("platform") or "web",
                source_category=source.get("category") or source.get("platform") or "web",
                source_kind=source.get("sourceKind") or "",
                extractor=source.get("extractor") or "",
                policy_revision=source.get("policyRevision") or "",
                source_use_mode=source.get("sourceUseMode") or "",
                publish_media_mode=source.get("publishMediaMode") or "",
                source_role=source.get("sourceRole") or "",
                image_evidence_mode=source.get("imageEvidenceMode") or "",
                research_lane=source.get("researchLane") or "",
                license_value=source.get("license") or "",
                url=source["url"],
                title=(
                    fetch_runtime.get("resolvedTitle")
                    or source.get("sourceTitle")
                    or source.get("title")
                    or source["source_id"]
                ),
                target_ref=target_ref,
                relevance=f"覆盖 {entity_id} 的基础事实/交通/季节等",
                has_video=page_has_video,
                images=source_images,
                asset_funnel=source_image_funnel,
                raw_format=raw_format,
                layout=source_layout,
                execution_id=execution_id,
                build_variants=False,
                source=source_for_unit,
            )
        except (ValueError, TypeError) as exc:
            # 隔离粒度：一条来源写不出合规单元只丢它自己。此前这里的异常向上冒到实体级
            # 处理器，峨眉山 12 条合法百科来源因为第 13 条不可归因被整体 exclude。
            unit_write_issue = handler_fetch_contract.source_unit_write_failure_issue(
                source,
                entity_id=entity_id,
                error=exc,
            )
            quality_rows.append(
                {
                    "sourceId": source["source_id"],
                    "quality": "Reject",
                    "score": 0,
                    "url": source["url"],
                    "statusCode": quality.get("statusCode", status_code),
                    "retainedFromCache": False,
                    "unitWriteIssue": unit_write_issue.as_dict(),
                }
            )
            print(
                f"[download] Source unit write failed, source dropped "
                f"{entity_id}/{source['source_id']}: {exc}",
                flush=True,
            )
            _write_download_progress(
                execution_id,
                status="running",
                entity_id=entity_id,
                entity_index=entity_index,
                entity_count=entity_count,
                sources=len(fetched_sources),
                images=len(pending_images),
                message="source unit write failed",
                lane=str(source.get("researchLane") or ""),
                sourceId=str(source.get("source_id") or ""),
                sourceIndex=ordinal,
                sourceCount=len(sources),
            )
            continue
        source_asset_counts.append(
            build_source_asset_count_row(
                manifest=manifest,
                source=source,
                quality=quality,
                source_image_funnel=source_image_funnel,
                source_images=source_images,
                vertical=vertical,
            )
        )
        unit_dir = execution_source_unit_dir(execution_id, str(manifest.get("sourceUnitId") or ""))
        if str(quality.get("quality") or "") == "Reject":
            rejected_dir = _move_rejected_source_unit(object_dir, unit_dir, quality=quality)
            written_rejected_source_dirs.add(rejected_dir)
            print(
                f"[download] Rejected source isolated {entity_id}/{source['source_id']}",
                flush=True,
            )
            _write_download_progress(
                execution_id,
                status="running",
                entity_id=entity_id,
                entity_index=entity_index,
                entity_count=entity_count,
                sources=len(fetched_sources),
                images=len(pending_images),
                message="source rejected",
                lane=str(source.get("researchLane") or ""),
                sourceId=str(source.get("source_id") or ""),
                sourceIndex=ordinal,
                sourceCount=len(sources),
            )
            continue
        if str(source.get("researchLane") or "") == "homepage":
            kept_source_homepage_images += handler_fetch_contract.publishable_homepage_source_image_count(
                source_images
            )
        written_source_dirs.add(unit_dir)
        quality_row, fetched_source = accepted_source_rows(
            source=source,
            quality=quality,
            entity_id=entity_id,
            status_code=status_code,
        )
        quality_rows.append(quality_row)
        fetched_sources.append(fetched_source)
        _write_download_progress(
            execution_id,
            status="running",
            entity_id=entity_id,
            entity_index=entity_index,
            entity_count=entity_count,
            sources=len(fetched_sources),
            images=len(pending_images),
            message="source fetch done",
            lane=str(source.get("researchLane") or ""),
            sourceId=str(source.get("source_id") or ""),
            sourceIndex=ordinal,
            sourceCount=len(sources),
        )
    kept_images, failed_image = close_entity_media(EntityMediaClosureInput(
        execution_id=execution_id,
        entity_id=entity_id,
        entity_index=entity_index,
        entity_count=entity_count,
        object_dir=object_dir,
        target_ref=target_ref,
        sources=tuple(sources),
        image_specs=tuple(image_specs),
        pending_images=tuple(pending_images),
        provider_asset_counts=tuple(source_asset_counts),
        professional_exclusions=tuple(professional_exclusions),
        existing_image_source_dirs=frozenset(existing_image_source_dirs),
        written_source_dirs=frozenset(written_source_dirs),
        written_rejected_source_dirs=frozenset(written_rejected_source_dirs),
        selected_lanes=None if selected_lanes is None else frozenset(selected_lanes),
        image_rights_issues=tuple(image_rights_issues),
        image_quality_issues=tuple(image_quality_issues),
        rejected_by_category=rejected_by_category,
        image_lane_selected=image_lane_selected,
        homepage_media_selected=homepage_media_selected,
        required_image_work_images=required_image_work_images,
        required_homepage_media=required_homepage_media,
        required_images=required_images,
        planned_homepage_source_images=planned_homepage_source_images,
        kept_source_homepage_images=kept_source_homepage_images,
    ))
    return {
        "entityId": entity_id,
        "entityIndex": entity_index,
        "sourceCount": len(sources),
        "imageCount": kept_images,
        "fetchedSources": fetched_sources,
        "qualityRows": quality_rows,
        "failedImage": failed_image,
        "sourcedVideoFailure": sourced_video_failure,
    }
__all__ = [name for name in globals() if not name.startswith("__")]
