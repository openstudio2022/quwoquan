"""Per-entity download fetch implementation."""
from __future__ import annotations

from collections.abc import Mapping
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

from content.execution import store
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
from content.source.handler_images import (
    _cached_source_quality_if_better,
    _find_source_unit_by_plan_key,
    _image_lane_source_unit_dirs,
    _move_rejected_source_unit,
)
from content.source.handler_plan import _write_download_progress
from content.source.image_download import _download_source_unit_images
from content.source.inline_images import build_inline_image_candidates
from content.source.source_inputs import manual_body_note, source_frontmatter
from content.source.source_unit import find_source_unit_raw_snapshot, write_source_unit


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
        page_has_video = page_has_inline_video(html_bytes, fetched_text)
        source_images, source_image_issues, source_image_funnel = _download_source_unit_images(
            source,
            execution_id=execution_id,
            entity_id=entity_id,
            object_dir=object_dir,
            ordinal=ordinal,
            vertical=vertical,
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
