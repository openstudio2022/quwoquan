"""Per-entity download fetch implementation."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.data_issue import (
    DataIssueCode, DataIssueError, DataIssueStage,
    DataIssueLane,
    DataRecoveryAction,
    data_issue,
)
from core.paths import execution_source_unit_dir
from core.article_commercial_policy import article_commercial_closure_enabled
from content.execution import store
from content.post.article.evidence_text import clean_source_markdown, score_source_markdown
from content.source.source_unit import (
    find_source_unit_raw_snapshot,
    write_source_unit,
)
from content.source.source_inputs import (
    manual_body_note,
    source_frontmatter,
)
from content.source.fetch_payload import fetch_source_payload
from content.source.handler_fetch_images import prepare_entity_images

from content.source.handler_plan import _write_download_progress
from content.source.handler_images import (
    _cached_source_quality_if_better,
    _find_source_unit_by_plan_key,
    _image_lane_source_unit_dirs,
    _move_rejected_source_unit,
)
from content.source.image_download import _download_source_unit_images
from content.source.handler_fetch_media import EntityMediaClosureInput, close_entity_media
from content.source.handler_fetch_setup import prepare_entity_fetch_plan
from content.source.inline_images import build_inline_image_candidates
from core.source_fidelity import assess_source_content_fidelity
from content.source.handler_fetch_contract import (
    canonicalize_source_url as _canonicalize_source_url,
    homepage_base_draft_admission,
    is_non_open_baike_source as _is_non_open_baike_source,
    publishable_homepage_source_image_count as _publishable_homepage_source_image_count,
    requires_factual_compression as _requires_factual_compression,
    require_source_candidate_admission,
    source_fetch_failure_issue as _source_fetch_failure_issue,
)
from content.homepage.quality_policy import (
    homepage_body_char_minimum,
    homepage_fact_count_minimum,
    homepage_fact_char_minimum,
)


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
    plan = prepare_entity_fetch_plan(
        execution_id=execution_id,
        entity_id=entity_id,
        entity_type=entity_type,
        domain=domain,
        etype=etype,
        selected_lanes=selected_lanes,
    )
    object_dir, target_ref, sources = plan.object_dir, plan.target_ref, plan.sources
    commercial_article_closure = article_commercial_closure_enabled(
        store.load_spec(execution_id)
    )
    existing_image_source_dirs = _image_lane_source_unit_dirs(object_dir)
    written_source_dirs: set[Path] = set()
    written_rejected_source_dirs: set[Path] = set()
    image_lane_selected = plan.image_lane_selected
    homepage_media_selected = plan.homepage_media_selected
    video_lane_selected = plan.video_lane_selected
    sourced_video_candidates = plan.sourced_video_candidates
    sourced_video_evidence = plan.sourced_video_evidence
    sourced_video_failure = plan.sourced_video_failure
    written_source_dirs.update(
        evidence_path.parent
        for evidence_path in sourced_video_evidence
    )
    # Page-owned homepage media are enumerated evidence, not a search pool:
    # process the complete list before applying the independent image-work
    # budget. A page image must end in download, explicit policy exclusion, or
    # a typed hard failure; it must never disappear because an unrelated image
    # work filled a quota first.
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
            message="direct video admission failed; retained frame sequence will be evaluated",
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
        video_lane_selected=video_lane_selected,
    )
    image_manifest = image_result.image_manifest
    image_rights_issues = image_result.rights_issues
    video_rights_issues = image_result.video_rights_issues
    image_quality_issues = image_result.quality_issues
    rejected_by_category = dict(image_result.rejected_by_category)
    pending_images = image_result.pending_images
    required_image_work_images = image_result.required_image_work_images
    planned_homepage_source_images = image_result.planned_homepage_source_images
    required_homepage_media = image_result.required_homepage_media
    required_video_frames = image_result.required_video_frames
    required_images = image_result.required_images
    if sourced_video_evidence:
        required_images = max(0, required_images - required_video_frames)
        required_video_frames = 0

    # 同实体源级去重：canonical URL 归一后重复的候选直接 Reject（跨源站消重）。
    seen_canonical_urls: set[str] = set()
    kept_source_homepage_images = 0

    for ordinal, source in enumerate(sources, start=1):
        try:
            require_source_candidate_admission(
                source,
                require_commercial_article_binding=commercial_article_closure,
            )
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
        # 统一结构化 IR（wiki wikitext / baike HTML 前端产物；None = 该源无结构前端）。
        source_layout: dict[str, Any] | None = None
        source_fetch_issue = None
        # RC3：本次抓取的同源内联 <img> 清单（与 source_md 的 source-inline 占位同序）。
        inline_images: list = []
        try:
            fetched = fetch_source_payload(
                source["url"],
                source=source,
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
            source_fetch_issue = _source_fetch_failure_issue(
                source,
                entity_id=entity_id,
                error=exc,
            )
            source_md = source_frontmatter(source, entity_id)
        note = manual_body_note(source)
        if note:
            source_md = source_md.rstrip() + f"\n\n{note}\n"
        clean_md = clean_source_markdown(source_md, raw_format=raw_format)
        if rendered_text:
            publishable_rendered_text = clean_source_markdown(
                rendered_text,
                raw_format=raw_format,
            )
            fidelity = assess_source_content_fidelity(
                publishable_rendered_text,
                clean_md,
            )
            if not fidelity.complete:
                raise DataIssueError(
                    (
                        data_issue(
                            DataIssueCode.SOURCE_CONTENT_INCOMPLETE,
                            stage=DataIssueStage.DOWNLOAD_FETCH,
                            ref=entity_id,
                            lane=DataIssueLane.HOMEPAGE,
                            recovery=DataRecoveryAction.REPLACE_SOURCE,
                            message="MediaWiki rendered prose was not preserved in source.clean.md",
                            attributes={
                                "sourceId": source["source_id"],
                                "authoritativeParagraphCount": fidelity.authoritative_paragraph_count,
                                "matchedParagraphCount": fidelity.matched_paragraph_count,
                                "missingPreview": fidelity.missing_paragraphs[0][:240],
                            },
                        ),
                    )
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

        # 同实体 canonical URL 消重：同一 URL 归一后第二次出现直接 Reject。
        canonical_url = _canonicalize_source_url(str(source.get("url") or ""))
        if canonical_url and canonical_url in seen_canonical_urls:
            quality_value = "Reject"
            quality_score = 0
            quality_reasons.append("duplicate_source_url")
        elif canonical_url:
            seen_canonical_urls.add(canonical_url)

        # Homepage fetch and source gates share one base-draft admission rule.
        # A frozen source must never pass planning then be rejected by a second,
        # divergent fact-count or title-matching implementation here.
        homepage_fact_count: int | None = None
        if (
            quality_value != "Reject"
            and str(source.get("researchLane") or "") == "homepage"
            and str(source.get("sourceRole") or "") != "support"
        ):
            resolved_title = str(fetch_runtime.get("resolvedTitle") or "").strip()
            homepage_admission = homepage_base_draft_admission(
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

        # factual_reference_only 来源（百度/搜狗/今日头条百科）事实化压缩：
        # >2000 字压至约 50%，1000-2000 轻度，<=1000 不压；
        # 结果进 source.clean.md，账目进 quality。
        compression_note: dict = {}
        if quality_value != "Reject" and _requires_factual_compression(source):
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
        cached_quality = _cached_source_quality_if_better(
            object_dir,
            ordinal=ordinal,
            source_id=source["source_id"],
            url=source["url"],
            candidate_quality=quality,
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
                # 缓存命中：复用既有已绑定的来源 source.md/资产，不再用本次 fetch 的
                # 内联清单二次注入（否则会重复下载并与已绑定占位错位）。
                inline_images = []
                clean_path = unit / "source.clean.md"
                clean_md = clean_path.read_text(encoding="utf-8") if clean_path.is_file() else ""
                page_path = find_source_unit_raw_snapshot(unit)
                html_bytes = page_path.read_bytes() if page_path else None
                # 复用既有原始快照格式，避免缓存恢复后又写错扩展名。
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
        # P3：检测来源页是否含内联视频（文章类据此弃稿，不把视频强行图文化）。
        from content.source.html_text import html_has_inline_video

        page_has_video = False
        if html_bytes:
            page_has_video = html_has_inline_video(html_bytes.decode("utf-8", errors="replace"))
        if not page_has_video and fetched_text:
            page_has_video = html_has_inline_video(fetched_text)
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
        source_drop_categories = source_image_funnel.get("dropReasonCounts")
        if isinstance(source_drop_categories, Mapping):
            category_map = {
                "fetch_failure": "fetch_or_non_image",
                "pixel_policy": "pixel_too_small",
                "decode_policy": "safety_or_watermark",
                "safety_policy": "safety_or_watermark",
                "rights_policy": "rights",
                "relevance_policy": "other",
                "invalid_payload": "other",
                "duplicate": "other",
            }
            for category, count in source_drop_categories.items():
                target_category = category_map.get(str(category), "other")
                rejected_by_category[target_category] += int(count or 0)
        source_for_unit = dict(source)
        for key in (
            "requestedTitle",
            "resolvedTitle",
            "redirectChain",
            "fetchFinalUrl",
        ):
            if key in fetch_runtime:
                source_for_unit[
                    "finalUrl" if key == "fetchFinalUrl" else key
                ] = fetch_runtime[key]
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
            kept_source_homepage_images += _publishable_homepage_source_image_count(
                source_images
            )
        written_source_dirs.add(unit_dir)
        quality_rows.append(
            {
                "sourceId": source["source_id"],
                "quality": quality.get("quality"),
                "score": quality.get("score"),
                "url": source["url"],
                "statusCode": quality.get("statusCode", status_code),
                "retainedFromCache": bool(quality.get("retainedFromCache")),
            }
        )
        fetched_sources.append(
            {
                "sourceId": source["source_id"],
                "url": source["url"],
                "quality": quality.get("quality"),
                "score": quality.get("score"),
                "entityId": entity_id,
                "retainedFromCache": bool(quality.get("retainedFromCache")),
            }
        )
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
        existing_image_source_dirs=frozenset(existing_image_source_dirs),
        written_source_dirs=frozenset(written_source_dirs),
        written_rejected_source_dirs=frozenset(written_rejected_source_dirs),
        selected_lanes=None if selected_lanes is None else frozenset(selected_lanes),
        image_rights_issues=tuple(image_rights_issues),
        video_rights_issues=tuple(video_rights_issues),
        image_quality_issues=tuple(image_quality_issues),
        rejected_by_category=rejected_by_category,
        image_lane_selected=image_lane_selected,
        homepage_media_selected=homepage_media_selected,
        video_lane_selected=video_lane_selected,
        required_image_work_images=required_image_work_images,
        required_homepage_media=required_homepage_media,
        required_video_frames=required_video_frames,
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
