"""Workflow service extracted from the retired monolithic runner."""
from __future__ import annotations
from content.execution.coverage import coverage_entity_type
from content.execution.support import Any, DataIssue, DataIssueCode, DataIssueStage, DataRecoveryAction, ExecutionContext, Mapping, Path, article_commercial_closure_enabled, data_issue, data_issues, execution_content_plan_packet_path, execution_root, image_count_is_hard_quota, minimum_publishable_images_per_target, read_json, relative_execution_ref, write_json

def _auto_content_plan(ctx: ExecutionContext, active_spec: Mapping[str, Any]) -> list[DataIssue]:
    """Build exact per-entity content plans from validated source units."""
    from content.execution.pipeline.content_plan_prep import _article_source_quality_sort_key, _assess_content_plan_publish_image, _clean_content_plan_outputs
    from content.post.base_draft import extract_source_title, load_base_draft_text
    from content.post.object_index import write_brief_object
    from core.quality_gates import derive_writing_intent
    from content.post.content_plan import (
        ARTICLE_MIN_BASE_DRAFT_CHARS,
        CONTENT_PLAN_SCHEMA,
        validate_content_plan,
    )
    from content.post.content_plan_state import load_content_plan_packet
    from content.execution.workspace import execution_content_plan_packet_path, relative_execution_ref
    from content.source.source_unit import resolve_entity_object_dir
    quotas = (active_spec.get("content") or {}).get("quotas") or {}
    commercial_closure = article_commercial_closure_enabled(active_spec)
    # 每个内容对象绑定单一 source unit；配额是对象数合同，不枚举全部来源。
    per_target_articles = int(quotas.get("entityArticlesPerTarget") or 0)
    per_target_images = int(quotas.get("imageWorksPerTarget") or 0)
    from content.execution.workspace import load_execution_manifest
    execution_content_type = str(
        load_execution_manifest(ctx.execution_id).get("contentType") or ""
    )
    active_content_types: set[str] = set()
    if per_target_articles > 0 or int(quotas.get("routeArticles") or 0) > 0:
        active_content_types.add("article")
    if per_target_images > 0:
        active_content_types.add("image")
    if int(quotas.get("entityHomepagesPerTarget") or 0) > 0:
        active_content_types.add("homepage")
    if active_content_types != {execution_content_type}:
        return [data_issue(
            DataIssueCode.CONTRACT_INVALID,
            stage=DataIssueStage.CONTENT_PLAN,
            ref=ctx.execution_id,
            recovery=DataRecoveryAction.STOP,
            message=(
                "one execution may build exactly its immutable contentType; "
                f"execution={execution_content_type!r} quotas={sorted(active_content_types)}; "
                "split carriers through recipe/release fanout"
            ),
        )]
    minimum_required_articles = (
        1
        if commercial_closure and per_target_articles > 0
        else per_target_articles
    )
    minimum_required_images = (
        per_target_images
        if image_count_is_hard_quota(active_spec)
        else minimum_publishable_images_per_target(active_spec)
    )
    article_lane_enabled = per_target_articles > 0
    image_lane_enabled = per_target_images > 0
    if not article_lane_enabled and not image_lane_enabled:
        return [data_issue(
            DataIssueCode.CONTRACT_INVALID,
            stage=DataIssueStage.CONTENT_PLAN,
            ref=ctx.execution_id,
            recovery=DataRecoveryAction.STOP,
            message="content quotas are empty; auto content_plan skipped",
        )]
    existing_packet = load_content_plan_packet(ctx.execution_id) or {}
    existing_source_site = (
        dict(existing_packet.get("sourceSite"))
        if isinstance(existing_packet.get("sourceSite"), Mapping)
        else None
    )
    _clean_content_plan_outputs(ctx)
    root = execution_root(ctx.execution_id)
    etype = coverage_entity_type(active_spec)
    targets = [
        str(target.get("name") or "").strip()
        for target in ((active_spec.get("scope") or {}).get("coverageTargets") or [])
        if str(target.get("name") or "").strip()
    ]
    task_region = str(((active_spec.get("scope") or {}).get("region") or "")).strip()
    workflow_policy = active_spec.get("workflowPolicy") if isinstance(active_spec.get("workflowPolicy"), Mapping) else {}
    daily_object_target = int(workflow_policy.get("targetObjectCount") or 0)
    if daily_object_target < 1:
        return [data_issue(
            DataIssueCode.CONTRACT_INVALID,
            stage=DataIssueStage.CONTENT_PLAN,
            ref=ctx.execution_id,
            recovery=DataRecoveryAction.STOP,
            message="workflowPolicy.targetObjectCount must be a positive frozen execution value",
        )]
    from content.execution.pipeline.content_plan_schedule import ContentPlanScheduler
    try:
        scheduler = ContentPlanScheduler.load(
            execution_id=ctx.execution_id,
            region=task_region,
            daily_object_target=daily_object_target,
        )
    except (OSError, TypeError, ValueError) as exc:
        return [data_issue(
            DataIssueCode.CONTRACT_INVALID,
            stage=DataIssueStage.CONTENT_PLAN,
            ref=ctx.execution_id,
            recovery=DataRecoveryAction.STOP,
            message=f"creator scheduling contract is invalid: {exc}",
        )]
    used_asset_refs: set[str] = set()
    used_asset_shas: set[str] = set()
    used_collection_ids: set[str] = set()
    used_article_source_refs: set[str] = set()
    items: list[dict[str, Any]] = []
    issues: list[DataIssue] = []
    source_diagnostics: dict[str, dict[str, Any]] = {}
    def _asset_rows(source_dir: Path) -> list[dict[str, Any]]:
        index_path = source_dir / "assets" / "index.json"
        if not index_path.is_file():
            return []
        try:
            rows = read_json(index_path).get("assets") or []
        except (OSError, ValueError, TypeError):
            rows = []
        return [row for row in rows if isinstance(row, dict)]
    def _asset_ref(source_dir: Path, row: Mapping[str, Any]) -> str:
        file_name = str(row.get("fileName") or "").strip()
        if not file_name:
            return ""
        return relative_execution_ref(source_dir / "assets" / file_name, ctx.execution_id)
    def _asset_sha(row: Mapping[str, Any]) -> str:
        return str(row.get("sha256") or "").removeprefix("sha256:").strip().lower()
    def _source_ref(source_dir: Path) -> str:
        return relative_execution_ref(source_dir / "source.md", ctx.execution_id)
    for target in targets:
        object_dir = resolve_entity_object_dir(ctx.execution_id, target, etype_hint=etype)
        from content.source.source_unit import iter_source_units
        source_units = iter_source_units(object_dir)
        if not source_units:
            reason = f"{target}: sources directory missing"
            source_diagnostics[target] = {
                "desiredArticleSources": per_target_articles,
                "minimumRequiredArticleSources": minimum_required_articles,
                "rawArticleBaseSources": 0,
                "qualifiedArticleBaseSources": 0,
                "pickedArticleBaseSources": 0,
                "desiredImageSources": per_target_images,
                "minimumRequiredImageSources": minimum_required_images,
                "rawImageAssets": 0,
                "qualifiedImageAssets": 0,
                "pickedImageSources": 0,
                "articleLaneEnabled": article_lane_enabled,
                "imageLaneEnabled": image_lane_enabled,
                "minimumQualityPassed": False,
                "articleQualityScore": 0.0,
                "articleLengthScore": 0.0,
                "imageCountScore": 0.0,
                "compositeScore": 0.0,
                "articleRejects": {"sources_directory_missing": 1} if article_lane_enabled else {},
                "articleRejectExamples": {"sources_directory_missing": [target]} if article_lane_enabled else {},
                "articleImageSoftWarnings": {},
                "articleImageSoftWarningExamples": {},
                "imageRejects": {"sources_directory_missing": 1} if image_lane_enabled else {},
                "imageRejectExamples": {"sources_directory_missing": [target]} if image_lane_enabled else {},
            }
            if commercial_closure:
                continue
            issues.append(data_issue(
                DataIssueCode.SOURCE_MISSING,
                stage=DataIssueStage.CONTENT_PLAN,
                ref=target,
                recovery=DataRecoveryAction.REPLACE_SOURCE,
                message=reason,
            ))
            continue
        article_candidates: list[dict[str, Any]] = []
        image_candidates: list[dict[str, Any]] = []
        article_raw_count = 0
        image_raw_count = 0
        image_rejects: dict[str, int] = defaultdict(int)
        image_reject_examples: dict[str, list[str]] = defaultdict(list)
        article_rejects: dict[str, int] = defaultdict(int)
        article_reject_examples: dict[str, list[str]] = defaultdict(list)
        article_image_soft_warnings: dict[str, int] = defaultdict(int)
        article_image_soft_warning_examples: dict[str, list[str]] = defaultdict(list)
        def _reject_article(reason: str, source_id: str, detail: str = "") -> None:
            article_rejects[reason] += 1
            examples = article_reject_examples[reason]
            if len(examples) < 5:
                examples.append(f"{source_id}{(': ' + detail) if detail else ''}")
        def _soft_warn_article_image(reason: str, source_id: str, detail: str = "") -> None:
            article_image_soft_warnings[reason] += 1
            examples = article_image_soft_warning_examples[reason]
            if len(examples) < 5:
                examples.append(f"{source_id}{(': ' + detail) if detail else ''}")
        def _reject_image(reason: str, source_id: str, detail: str = "") -> None:
            image_rejects[reason] += 1
            examples = image_reject_examples[reason]
            if len(examples) < 5:
                examples.append(f"{source_id}{(': ' + detail) if detail else ''}")
        for source_dir in source_units:
            meta_path = source_dir / "meta.json"
            if not meta_path.is_file() or not (source_dir / "source.md").is_file():
                continue
            try:
                meta = read_json(meta_path)
            except (OSError, ValueError, TypeError):
                meta = {}
            source_id = str(meta.get("sourceId") or source_dir.name).strip()
            lane = str(meta.get("researchLane") or "").strip()
            rows = _asset_rows(source_dir)
            if lane == "article":
                if str(meta.get("sourceRole") or "") != "base":
                    continue
                if "support" in source_id.lower() or "support" in source_dir.name.lower():
                    continue
                article_raw_count += 1
                if bool(meta.get("hasVideo")):
                    # P3 文章判据：含视频则放弃——不把视频内容强行图文化为攻略文章。
                    _reject_article("contains_video", source_id, "来源含内联视频，文章类放弃")
                    continue
                source_ref = _source_ref(source_dir)
                base_body = load_base_draft_text(ctx.execution_id, source_ref)
                from content.post.base_draft import base_draft_readiness
                readiness = base_draft_readiness(
                    base_body,
                    publish_media_mode=str(meta.get("publishMediaMode") or ""),
                )
                text_len = int(readiness["effectiveChars"])
                if not readiness["ready"]:
                    _reject_article(
                        "text_too_short",
                        source_id,
                        f"{text_len}<{ARTICLE_MIN_BASE_DRAFT_CHARS}; "
                        f"figures={readiness['inlineFigureCount']} captions={readiness['captionChars']}",
                    )
                    continue
                focus_score, focus_verdict = _classify_entity_focus(
                    base_body,
                    target,
                    title=str(meta.get("title") or ""),
                    sibling_names=targets,
                )
                from core.qunar_template import qunar_article_base_block_reason
                # 与 validate_content_plan 同口径：优先尊重 source unit meta
                # 中的实体锚点判定，避免 Qunar off_entity 游记进入 packet。
                qunar_focus_verdict = str(meta.get("entityFocusVerdict") or "").strip() or focus_verdict
                qunar_block = qunar_article_base_block_reason(meta, qunar_focus_verdict)
                if qunar_block:
                    _reject_article(qunar_block, source_id, "Qunar 模板底稿不可作为当前实体 article base")
                    continue
                # 底稿中心 1:1：实体退化为多标签，文章不再因"未整体指代单一实体"弃稿
                # （多目的地游记照样按单一底稿成稿，实体作为标签集合）；focus 仅留作诊断信号。
                draft_title = extract_source_title(ctx.execution_id, source_ref)
                if not draft_title:
                    # 标题取自底稿：文章源无法提取可用发布标题 → 上游诚实弃稿（不成稿）。
                    _reject_article("no_source_title", source_id, "底稿无法提取发布标题")
                    continue
                entity_tags = sorted(
                    {
                        *_coverage_targets_mentioned(base_body, str(meta.get("title") or ""), targets),
                        target,
                    }
                )
                if not rows:
                    _soft_warn_article_image("no_source_assets", source_id)
                article_candidates.append(
                    {
                        "sourceDir": source_dir,
                        "sourceRef": source_ref,
                        "sourceId": source_id,
                        "title": str(meta.get("title") or source_id),
                        "draftTitle": draft_title,
                        "writingIntent": derive_writing_intent(base_body),
                        "entityTags": entity_tags,
                        "sourceUseMode": str(meta.get("sourceUseMode") or "factual_reference_only"),
                        "sourceClass": str(meta.get("sourceClass") or meta.get("category") or ""),
                        "sourceQualityScore": float(
                            meta.get("sourceQualityScore")
                            or meta.get("qualityScore")
                            or meta.get("score")
                            or 0
                        ),
                        "textLen": text_len,
                        "entityFocusScore": focus_score,
                        "entityFocusVerdict": focus_verdict,
                        "sourceFreshnessTier": str(
                            meta.get("sourceFreshnessTier")
                            or ((meta.get("siteTemplate") or {}).get("freshnessTier") if isinstance(meta.get("siteTemplate"), Mapping) else "")
                            or ""
                        ),
                        "rows": rows,
                    }
                )
            elif lane == "image":
                for row in rows:
                    image_raw_count += 1
                    asset_ref = _asset_ref(source_dir, row)
                    collection_id = str(row.get("sourceCollectionId") or "").strip()
                    if not asset_ref:
                        _reject_image("missing_asset_ref", source_id)
                        continue
                    if not collection_id:
                        _reject_image("missing_source_collection_id", source_id, asset_ref)
                        continue
                    asset_path = root / asset_ref
                    if not asset_path.is_file():
                        _reject_image("asset_file_missing", source_id, asset_ref)
                        continue
                    verdict = _assess_content_plan_publish_image(asset_path, ctx)
                    if verdict.blocks_image_publish:
                        _reject_image(
                            "image_safety_blocked",
                            source_id,
                            f"{asset_ref}:{'/'.join(verdict.reasons) or verdict.status}",
                        )
                        continue
                    image_candidates.append(
                        {
                            "sourceDir": source_dir,
                            "sourceRef": _source_ref(source_dir),
                            "sourceId": source_id,
                            "assetRef": asset_ref,
                            "assetSha": _asset_sha(row),
                            "collectionId": collection_id,
                            "caption": str(row.get("caption") or "").strip(),
                            "title": str(meta.get("title") or "").strip(),
                        }
                    )
        article_candidates.sort(key=_article_source_quality_sort_key)
        image_candidates.sort(key=lambda row: (str(row["collectionId"]), str(row["assetRef"])))
        def _image_claims(candidate: Mapping[str, Any]) -> tuple[list[str], list[str], list[str]]:
            return (
                [str(candidate.get("assetRef") or "").strip()],
                [str(candidate.get("assetSha") or "").strip()],
                [str(candidate.get("collectionId") or "").strip()],
            )
        def _article_asset_claims(
            candidate: Mapping[str, Any],
        ) -> tuple[list[str], list[str], list[str], list[str]]:
            """Return one reserved source image for an article base draft.
            Article source images are part of the base draft, not decorative
            fallback material. Reserve a concrete source asset during planning
            so compose can only execute an already-admitted one-draft-one-image
            contract instead of discovering starvation at the end.
            """
            source_dir = candidate.get("sourceDir")
            if not isinstance(source_dir, Path):
                return [], [], [], []
            for row in candidate.get("rows") or []:
                if not isinstance(row, Mapping):
                    continue
                ref = _asset_ref(source_dir, row)
                sha = _asset_sha(row)
                collection_id = str(row.get("sourceCollectionId") or "").strip()
                if not ref:
                    continue
                asset_path = root / ref
                if not asset_path.is_file():
                    continue
                verdict = _assess_content_plan_publish_image(asset_path, ctx)
                if verdict.blocks_image_publish:
                    continue
                return (
                    [ref],
                    [sha] if sha else [],
                    [collection_id] if collection_id else [],
                    [ref],
                )
            return [], [], [], []
        def _claims_conflict(
            refs: list[str],
            shas: list[str],
            collections: list[str],
            *,
            claimed_refs: set[str],
            claimed_shas: set[str],
            claimed_collections: set[str],
        ) -> bool:
            return (
                any(ref in claimed_refs for ref in refs if ref)
                or any(sha in claimed_shas for sha in shas if sha)
                or any(cid in claimed_collections for cid in collections if cid)
            )
        def _claim(
            refs: list[str],
            shas: list[str],
            collections: list[str],
            *,
            claimed_refs: set[str],
            claimed_shas: set[str],
            claimed_collections: set[str],
        ) -> None:
            claimed_refs.update(ref for ref in refs if ref)
            claimed_shas.update(sha for sha in shas if sha)
            claimed_collections.update(cid for cid in collections if cid)
        protected_article_refs: set[str] = set()
        protected_article_shas: set[str] = set()
        protected_article_collections: set[str] = set()
        for candidate in article_candidates:
            refs, shas, collections, _asset_refs = _article_asset_claims(candidate)
            _claim(
                refs,
                shas,
                collections,
                claimed_refs=protected_article_refs,
                claimed_shas=protected_article_shas,
                claimed_collections=protected_article_collections,
            )
        picked_images: list[dict[str, Any]] = []
        for candidate in (image_candidates if image_lane_enabled else []):
            if per_target_images and len(picked_images) >= per_target_images:
                break
            refs, shas, collections = _image_claims(candidate)
            if _claims_conflict(
                refs,
                shas,
                collections,
                claimed_refs=protected_article_refs,
                claimed_shas=protected_article_shas,
                claimed_collections=protected_article_collections,
            ) or _claims_conflict(
                refs,
                shas,
                collections,
                claimed_refs=used_asset_refs,
                claimed_shas=used_asset_shas,
                claimed_collections=used_collection_ids,
            ):
                _reject_image(
                    "source_asset_reused",
                    str(candidate.get("sourceId") or candidate.get("sourceRef") or ""),
                    str(candidate.get("assetRef") or ""),
                )
                continue
            picked_images.append(candidate)
            _claim(
                refs,
                shas,
                collections,
                claimed_refs=used_asset_refs,
                claimed_shas=used_asset_shas,
                claimed_collections=used_collection_ids,
            )
        picked_articles: list[dict[str, Any]] = []
        for candidate in (article_candidates if article_lane_enabled else []):
            if per_target_articles and len(picked_articles) >= per_target_articles:
                break
            source_ref = str(candidate.get("sourceRef") or "").strip()
            if source_ref in used_article_source_refs:
                _reject_article("source_ref_reused", str(candidate["sourceId"]))
                continue
            refs, shas, collections, asset_refs = _article_asset_claims(candidate)
            if not asset_refs:
                _soft_warn_article_image("no_publishable_source_asset", str(candidate["sourceId"]))
            elif _claims_conflict(
                refs,
                shas,
                collections,
                claimed_refs=used_asset_refs,
                claimed_shas=used_asset_shas,
                claimed_collections=used_collection_ids,
            ):
                _soft_warn_article_image("source_asset_reused", str(candidate["sourceId"]))
                refs, shas, collections, asset_refs = [], [], [], []
            claimed_candidate = dict(candidate)
            claimed_candidate["assetRefs"] = asset_refs
            picked_articles.append(claimed_candidate)
            if source_ref:
                used_article_source_refs.add(source_ref)
            if asset_refs:
                _claim(
                    refs,
                    shas,
                    collections,
                    claimed_refs=used_asset_refs,
                    claimed_shas=used_asset_shas,
                    claimed_collections=used_collection_ids,
                )
        if article_lane_enabled and len(picked_articles) < per_target_articles:
            reason = (
                f"{target}: entityArticlesPerTarget quota {per_target_articles} "
                f"but only picked {len(picked_articles)} qualified article source(s)"
            )
            if commercial_closure:
                pass
            else:
                issues.append(data_issue(
                    DataIssueCode.SOURCE_RETAINED_SHORTFALL,
                    stage=DataIssueStage.CONTENT_PLAN,
                    ref=target,
                    recovery=DataRecoveryAction.STOP,
                    message=reason,
                    attributes={
                        "carrier": "article",
                        "required": per_target_articles,
                        "retained": len(picked_articles),
                    },
                ))
        if image_lane_enabled and len(picked_images) < per_target_images:
            reason = (
                f"{target}: imageWorksPerTarget quota {per_target_images} "
                f"but only picked {len(picked_images)} qualified image source(s)"
            )
            if commercial_closure:
                pass
            else:
                issues.append(data_issue(
                    DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL,
                    stage=DataIssueStage.CONTENT_PLAN,
                    ref=target,
                    recovery=DataRecoveryAction.STOP,
                    message=reason,
                    attributes={
                        "carrier": "image",
                        "required": per_target_images,
                        "retained": len(picked_images),
                    },
                ))
        def _normalized_quality_score(candidate: Mapping[str, Any]) -> float:
            try:
                raw = float(candidate.get("sourceQualityScore") or 0)
            except (TypeError, ValueError):
                raw = 0.0
            return max(0.0, min(raw / 10.0 if raw > 1 else raw, 1.0))
        def _article_evidence_requirements(_intent: str) -> dict[str, Any]:
            # 底稿中心单源文章以 baseDraftFidelity / factTraceability 守真；
            # 情绪钩子、喜欢/不喜欢和 writingIntent 只作软质量信号，不作 compose 硬门。
            return {"emotion": {"required": False}}
        def _article_length_score(candidate: Mapping[str, Any]) -> float:
            try:
                text_len = int(candidate.get("textLen") or 0)
            except (TypeError, ValueError):
                text_len = 0
            return max(0.0, min(text_len / ARTICLE_MIN_BASE_DRAFT_CHARS, 1.0))
        article_quality_score = round(
            sum(_normalized_quality_score(candidate) for candidate in picked_articles) / len(picked_articles),
            4,
        ) if picked_articles else 0.0
        article_length_score = round(
            sum(_article_length_score(candidate) for candidate in picked_articles) / len(picked_articles),
            4,
        ) if picked_articles else 0.0
        image_count_score = 1.0 if (picked_images or not image_lane_enabled) else 0.0
        # 底稿中心：目标"达标"= 启用的车道至少各产出一件作品；无 per-target 配额硬下限，
        # 仅当某目标在启用车道下连一件合格 source unit 都没有时记为未达标（用于诊断/排序）。
        minimum_quality_passed = (
            (minimum_required_articles <= 0 or bool(picked_articles))
            and (minimum_required_images <= 0 or bool(picked_images))
        )
        composite_score = round(
            70.0
            + 15.0 * article_quality_score
            + 5.0 * article_length_score
            + 10.0 * image_count_score,
            2,
        ) if minimum_quality_passed else 0.0
        source_diagnostics[target] = {
            "desiredArticleSources": per_target_articles,
            "minimumRequiredArticleSources": minimum_required_articles,
            "rawArticleBaseSources": article_raw_count,
            "qualifiedArticleBaseSources": len(article_candidates),
            "pickedArticleBaseSources": len(picked_articles),
            "desiredImageSources": per_target_images,
            "minimumRequiredImageSources": minimum_required_images,
            "rawImageAssets": image_raw_count,
            "qualifiedImageAssets": len(image_candidates),
            "pickedImageSources": len(picked_images),
            "articleLaneEnabled": article_lane_enabled,
            "imageLaneEnabled": image_lane_enabled,
            "minimumQualityPassed": minimum_quality_passed,
            "articleQualityScore": article_quality_score,
            "articleLengthScore": article_length_score,
            "imageCountScore": image_count_score,
            "compositeScore": composite_score,
            "articleRejects": dict(sorted(article_rejects.items())),
            "articleRejectExamples": {
                key: values for key, values in sorted(article_reject_examples.items())
            },
            "articleImageSoftWarnings": dict(sorted(article_image_soft_warnings.items())),
            "articleImageSoftWarningExamples": {
                key: values for key, values in sorted(article_image_soft_warning_examples.items())
            },
            "imageRejects": dict(sorted(image_rejects.items())),
            "imageRejectExamples": {
                key: values for key, values in sorted(image_reject_examples.items())
            },
        }
        for candidate in picked_articles:
            intent = str(candidate.get("writingIntent") or "")
            # 标题取自单一底稿（已剥平台痕迹），不再用 {实体}·{角度} 模板。
            title = str(candidate.get("draftTitle") or "").strip()
            source_id = str(candidate.get("sourceId") or "")
            ref = f"{target}__{source_id}".replace("/", "_")
            entity_ref = f"/entity/{etype}/{target}"
            entity_tags = list(candidate.get("entityTags") or [target])
            creator_assignment = scheduler.assign(carrier="article", target=target, intent=intent)
            publish_schedule = scheduler.schedule(creator_assignment)
            brief = {
                "titleHint": title,
                "carrier": "article",
                "entityRefs": [entity_ref],
                "entityTags": entity_tags,
                # mustIncludeFacts 是"正文必须包含且可追溯的目的地事实"，由 review 的
                # evidenceQuality/factTraceability 门逐条校验是否出现在正文。单一底稿 article
                # 没有独立抽取的事实清单——其"事实"就是底稿本身，由 baseDraftFidelity 门保真。
                # 历史上这里硬塞了两条**写作策略/指令**（单源轻改、配图同源一源一作品），
                # 它们是生产策略而非可叙述事实：agent 不可能把"我必须用同源图"写进游记正文并被
                # factTraceability 追溯，导致所有文章必败（不可满足的 mustIncludeFact）。这两条
                # 策略已由结构门（baseSourceRef 单源 + verify single-contract-source、
                # route_assets 同源选图 + source_quality RC4 红线 + baseDraftFidelity 门）强制，
                # 并在 prompt"底稿编辑硬合同"段向 agent 明确传达，无需再当作 mustIncludeFact。
                "mustIncludeFacts": [],
                "templateId": "travel.entity.guide",
                "writingIntent": intent,
                "evidenceRequirements": _article_evidence_requirements(intent),
                "baseSourceRef": candidate["sourceRef"],
                "assetRefs": list(candidate.get("assetRefs") or []),
                "publishSchedule": publish_schedule,
                **creator_assignment,
            }
            if not brief["assetRefs"]:
                brief["publishMediaMode"] = "text_only"
            write_brief_object(ctx.execution_id, ref, brief, content_type="article")
            items.append(
                {
                    "ref": ref,
                    "kind": "entity",
                    "carrier": "article",
                    "researchLane": "article",
                    "title": title,
                    "entityRefs": [entity_ref],
                    "entityTags": entity_tags,
                    "evidenceRefs": [candidate["sourceRef"]],
                    "rationale": f"底稿中心配额选源：单一 sourceRole=base 来源单元（正文≥{ARTICLE_MIN_BASE_DRAFT_CHARS}），标题取自底稿，实体作多标签",
                    "mustIncludeFacts": brief["mustIncludeFacts"],
                    "writingIntent": intent,
                    "evidenceRequirements": brief["evidenceRequirements"],
                    "baseSourceRef": candidate["sourceRef"],
                    "assetRefs": list(candidate.get("assetRefs") or []),
                    "sourceUseMode": candidate["sourceUseMode"],
                    "entityFocusScore": float(candidate.get("entityFocusScore") or 0.0),
                    "entityFocusVerdict": str(candidate.get("entityFocusVerdict") or _VERDICT_STRONG),
                    "publishSchedule": publish_schedule,
                    **creator_assignment,
                }
            )
            if not items[-1]["assetRefs"]:
                items[-1]["publishMediaMode"] = "text_only"
        if not picked_images:
            continue
        single_image = len(picked_images) == 1
        for index, candidate in enumerate(picked_images, start=1):
            # 单图作品保留 {target}_image，多图作品按序号去重，ref 始终唯一。
            ref = f"{target}_image" if single_image else f"{target}_image_{index}"
            title = str(candidate.get("title") or "").strip()[:80]
            caption = str(candidate.get("caption") or "").strip()[:300]
            entity_ref = f"/entity/{etype}/{target}"
            creator_assignment = scheduler.assign(carrier="image", target=target, intent="image")
            publish_schedule = scheduler.schedule(creator_assignment)
            brief = {
                "titleHint": title,
                "carrier": "image",
                "entityRefs": [entity_ref],
                "entityTags": [target],
                "mustIncludeFacts": [
                    f"{target} 开放许可图片作品",
                    "图片来自同一授权来源集合（单一 source unit），禁止跨作者/页面/底稿混图",
                ],
                "templateId": "travel.entity.gallery",
                "sourceCollectionId": candidate["collectionId"],
                "baseSourceRef": candidate["sourceRef"],
                "assetRefs": [candidate["assetRef"]],
                "caption": caption,
                "publishSchedule": publish_schedule,
                **creator_assignment,
            }
            write_brief_object(ctx.execution_id, ref, brief, content_type="image")
            items.append(
                {
                    "ref": ref,
                    "kind": "entity",
                    "carrier": "image",
                    "researchLane": "image",
                    "title": title,
                    "caption": caption,
                    "entityRefs": [entity_ref],
                    "entityTags": [target],
                    "evidenceRefs": [candidate["sourceRef"]],
                    "rationale": "底稿中心配额选源：image research lane 下单一 sourceCollectionId 的授权图片集合（一源一作品）",
                    "sourceCollectionId": candidate["collectionId"],
                    "baseSourceRef": candidate["sourceRef"],
                    "assetRefs": [candidate["assetRef"]],
                    "publishSchedule": publish_schedule,
                    **creator_assignment,
                }
            )
    write_json(
        root / "_shared" / "content_plan_source_diagnostics.json",
        {
            "schemaVersion": "quwoquan_data.content_plan_source_diagnostics",
            "executionId": ctx.execution_id,
            "targets": source_diagnostics,
        },
    )
    if issues:
        _clean_content_plan_outputs(ctx)
        return issues
    if not items:
        _clean_content_plan_outputs(ctx)
        return [data_issue(
            DataIssueCode.SOURCE_RETAINED_SHORTFALL,
            stage=DataIssueStage.CONTENT_PLAN,
            ref=ctx.execution_id,
            recovery=DataRecoveryAction.REPLACE_SOURCE,
            message="auto content_plan produced no items",
        )]
    packet = {
        "schemaVersion": CONTENT_PLAN_SCHEMA,
        "executionId": ctx.execution_id,
        "generatedBy": "deterministic_source_ready_planner",
        "items": items,
    }
    if existing_source_site:
        packet["sourceSite"] = existing_source_site
    write_json(execution_content_plan_packet_path(ctx.execution_id), packet)
    return data_issues(
        DataIssueCode.CONTRACT_INVALID,
        stage=DataIssueStage.CONTENT_PLAN,
        messages=validate_content_plan(ctx.execution_id, active_spec),
        recovery=DataRecoveryAction.REWIND_COMPOSE,
    )
