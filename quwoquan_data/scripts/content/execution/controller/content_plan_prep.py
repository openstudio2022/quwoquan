"""Execution service extracted from the retired monolithic runner."""
from __future__ import annotations
from content.execution.coverage import coverage_entity_type, coverage_entity_type_for_entity
from content.execution.support import Any, ExecutionContext, Iterable, Mapping, Path, _active_spec, article_commercial_closure_enabled, defaultdict, execution_root, image_count_is_hard_quota, minimum_publishable_images_per_target, read_json, relative_execution_ref, shutil
from core.entity_focus import classify_entity_focus as _classify_entity_focus

def _clean_content_plan_outputs(ctx: ExecutionContext) -> None:
    root = execution_root(ctx.execution_id)
    for rel in ("posts/article", "posts/image", "posts/video"):
        path = root / rel
        if path.exists():
            shutil.rmtree(path)
    for rel in ("_shared/content_plan_packet.json", "_shared/content_object_index.json"):
        path = root / rel
        if path.exists():
            path.unlink()

def _entity_name_from_source_dir(source_dir: Path) -> str:
    """从来源单元 manifest 推导目标实体名。"""
    meta_path = source_dir / "meta.json"
    if meta_path.is_file():
        try:
            meta = read_json(meta_path)
        except (OSError, ValueError, TypeError):
            meta = {}
        relevance = meta.get("relevance") if isinstance(meta.get("relevance"), Mapping) else {}
        target_refs = [str(ref) for ref in (relevance.get("targetRefs") or []) if str(ref)]
        if target_refs:
            return target_refs[0].rstrip("/").rsplit("/", 1)[-1]
    parts = source_dir.parts
    for index, part in enumerate(parts):
        if part == "1.download" and index > 0:
            return parts[index - 1]
    return ""

def _article_source_quality_sort_key(row: Mapping[str, Any]) -> tuple[int, int, int, int, int, str]:
    """实体聚焦优先、再质量、再长度的 article 候选排序（无平台/来源类别偏置）。"""
    from content.post.content_plan import ARTICLE_MIN_BASE_DRAFT_CHARS
    from core.qunar_template import qunar_source_freshness_rank
    focus = float(row.get("entityFocusScore") or 0.0)
    focus_bucket = int(max(0.0, min(focus, 1.0)) * 20)  # 5% 一档，避免微小噪声扰动排序
    freshness_rank = qunar_source_freshness_rank(row)
    source_quality = int(float(row.get("sourceQualityScore") or row.get("qualityScore") or 0) * 1000)
    image_count = len(row.get("rows") or []) if isinstance(row.get("rows"), list) else 0
    text_len = int(row.get("textLen") or 0)
    length_score = min(max(text_len, 0), ARTICLE_MIN_BASE_DRAFT_CHARS)
    source_id = str(row.get("sourceId") or "")
    return (-focus_bucket, freshness_rank, -source_quality, -length_score, -image_count, source_id)

def _assess_content_plan_publish_image(asset_path: Path, ctx: ExecutionContext):
    """Use the same publish-safety decision before an image enters content_plan."""
    from core.image_safety import assess_image_cached, assess_image_publish_prefilter
    prefilter = assess_image_publish_prefilter(asset_path)
    if prefilter.blocks_image_publish:
        return prefilter
    cache_dir = execution_root(ctx.execution_id) / "_shared" / "image_safety_cache"
    return assess_image_cached(asset_path, cache_dir=cache_dir, require_ocr=True)

def _content_capacity_gate_for_entity(
    ctx: ExecutionContext,
    entity_id: str,
    *,
    active_spec: Mapping[str, Any] | None = None,
    entity_type: str = "",
) -> tuple[bool, list[str], dict[str, Any]]:
    """Preflight content-plan source capacity for one fetched entity.
    Download readiness is necessary but not sufficient for production: a target
    can have a valid homepage and an image collection while still lacking enough
    one-draft-one-use article sources after source-image exclusivity is applied.
    This gate mirrors the hard capacity portion of `_auto_content_plan` without
    writing briefs or content packets, so replacement candidates that would
    deterministically fail content_plan never become active.
    """
    from content.post.article.base_draft import base_draft_readiness, load_base_draft_text
    from content.post.article.base_draft_source import extract_source_title
    from content.execution.controller.content_plan_asset_semantics import (
        article_asset_semantic_issue,
    )
    from content.source.source_unit import iter_source_units, resolve_entity_object_dir
    spec = active_spec or _active_spec(ctx)
    quotas = (spec.get("content") or {}).get("quotas") or {}
    commercial_closure = article_commercial_closure_enabled(spec)
    # entityArticlesPerTarget 是放量对象数合同。前置容量门必须与最终
    # content_plan_packet 校验同口径，否则短缺目标会穿过 download_fetch，
    # 到 content_plan 才被误派给 Agent 反复重试。
    desired_articles = max(0, int(quotas.get("entityArticlesPerTarget") or 0))
    required_articles = (
        1
        if commercial_closure and desired_articles > 0
        else desired_articles
    )
    desired_images = max(0, int(quotas.get("imageWorksPerTarget") or 0))
    required_images = (
        desired_images
        if image_count_is_hard_quota(spec)
        else minimum_publishable_images_per_target(spec)
    )
    image_pick_limit = max(desired_images, required_images)
    etype = (
        coverage_entity_type_for_entity(dict(spec), entity_id)
        or str(entity_type or "").strip()
        or coverage_entity_type(dict(spec))
    )
    root = execution_root(ctx.execution_id)
    object_dir = resolve_entity_object_dir(ctx.execution_id, entity_id, etype_hint=etype)
    source_units = iter_source_units(object_dir)
    if not source_units:
        return False, [f"{entity_id}: sources directory missing"], {}
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
    def _first_publishable_asset(
        source_dir: Path,
        rows: Iterable[Mapping[str, Any]],
    ) -> tuple[str, str, str] | None:
        for row in rows:
            ref = _asset_ref(source_dir, row)
            if not ref:
                continue
            asset_path = root / ref
            if not asset_path.is_file():
                continue
            verdict = _assess_content_plan_publish_image(asset_path, ctx)
            if verdict.blocks_image_publish:
                continue
            return (
                ref,
                _asset_sha(row),
                str(row.get("sourceCollectionId") or "").strip(),
            )
        return None
    def _claims_conflict(ref: str, sha: str, collection_id: str) -> bool:
        return (
            bool(ref and ref in used_refs)
            or bool(sha and sha in used_shas)
            or bool(collection_id and collection_id in used_collections)
        )
    article_candidates: list[dict[str, Any]] = []
    article_source_closure: list[dict[str, str]] = []
    image_candidates: list[dict[str, Any]] = []
    article_raw_count = 0
    image_raw_count = 0
    article_rejects: dict[str, int] = defaultdict(int)
    article_image_soft_warnings: dict[str, int] = defaultdict(int)
    image_rejects: dict[str, int] = defaultdict(int)
    # 其它覆盖目标：用于多地点环线判定（底稿突出提及 >=2 个兄弟目标 → 单实体弃稿）。
    sibling_target_names = tuple(
        str(target.get("name") or "").strip()
        for target in ((spec.get("scope") or {}).get("coverageTargets") or [])
        if str(target.get("name") or "").strip()
    )
    entity_aliases = tuple(
        str(alias).strip()
        for target in ((spec.get("scope") or {}).get("coverageTargets") or [])
        if isinstance(target, Mapping)
        and str(target.get("name") or "").strip() == entity_id
        for alias in target.get("aliases") or []
        if str(alias).strip()
    )
    for source_dir in source_units:
        meta_path = source_dir / "meta.json"
        quality_path = source_dir / "source.quality.json"
        if not meta_path.is_file() or not (source_dir / "source.md").is_file():
            continue
        try:
            meta = read_json(meta_path)
        except (OSError, ValueError, TypeError):
            continue
        if not isinstance(meta, Mapping):
            continue
        source_id = str(meta.get("sourceId") or source_dir.name).strip()
        lane = str(meta.get("researchLane") or "").strip()
        rows = _asset_rows(source_dir)
        if lane == "article":
            if str(meta.get("sourceRole") or "") != "base":
                continue
            if "support" in source_id.lower() or "support" in source_dir.name.lower():
                continue
            article_raw_count += 1
            if not quality_path.is_file():
                article_rejects["quality_receipt_missing"] += 1
                continue
            try:
                quality = read_json(quality_path)
            except (OSError, ValueError, TypeError):
                article_rejects["quality_receipt_invalid"] += 1
                continue
            if not isinstance(quality, Mapping):
                article_rejects["quality_receipt_invalid"] += 1
                continue
            if str(quality.get("quality") or "") == "Reject":
                article_rejects["quality_rejected"] += 1
                continue
            if bool(quality.get("retainedFromCache")):
                article_rejects["retained_from_cache"] += 1
                continue
            if bool(meta.get("manualProbe")) or bool(quality.get("manualProbe")):
                article_rejects["manual_probe"] += 1
                continue
            if bool(meta.get("hasVideo")):
                # P3 文章判据：含视频则放弃——不把视频内容强行图文化为攻略文章。
                article_rejects["contains_video"] += 1
                continue
            source_ref = _source_ref(source_dir)
            base_body = load_base_draft_text(ctx.execution_id, source_ref)
            readiness = base_draft_readiness(
                base_body,
                publish_media_mode=str(meta.get("publishMediaMode") or ""),
            )
            text_len = int(readiness["effectiveChars"])
            if not readiness["ready"]:
                article_rejects["text_too_short"] += 1
                continue
            entity_name = _entity_name_from_source_dir(source_dir)
            focus_score, focus_verdict = _classify_entity_focus(
                base_body,
                entity_name,
                title=str(meta.get("title") or ""),
                sibling_names=sibling_target_names,
            )
            from core.qunar_template import qunar_article_base_block_reason
            # source unit meta 是最终 validator 的真相源；若下载/筛选阶段已判定
            # Qunar 游记 off_entity，这里不得因当前批次目标集合重算 focus 而放行。
            qunar_focus_verdict = str(meta.get("entityFocusVerdict") or "").strip() or focus_verdict
            qunar_block = qunar_article_base_block_reason(meta, qunar_focus_verdict)
            if qunar_block:
                article_rejects[qunar_block] += 1
                continue
            # 底稿中心 1:1：文章不再因"未整体指代单一实体"弃稿（多目的地游记照样成稿，实体作多标签）；
            # 唯一上游硬门是"底稿能否提取发布标题"——文章源无标题即诚实弃稿。
            if not extract_source_title(ctx.execution_id, source_ref):
                article_rejects["no_source_title"] += 1
                continue
            admitted_rows: list[dict[str, Any]] = []
            for row in rows:
                semantic_issue = article_asset_semantic_issue(
                    row,
                    entity_id=entity_id,
                    entity_aliases=entity_aliases,
                    article_text=base_body,
                )
                if semantic_issue:
                    article_image_soft_warnings["asset_semantic_mismatch"] += 1
                    continue
                admitted_rows.append(row)
            if len(admitted_rows) < 2:
                article_rejects["same_source_cover_body_missing"] += 1
                article_image_soft_warnings["no_publishable_source_asset"] += 1
                continue
            article_source_closure.append(
                {
                    "sourceId": source_id,
                    "provider": str(meta.get("platform") or "").strip(),
                "siteId": str(meta.get("articleSiteId") or "").strip(),
                "profileDigest": str(
                    meta.get("sourceDiscoveryProfileDigest") or ""
                ).strip(),
                    "sourceRef": source_ref,
                }
            )
            article_candidates.append(
                {
                    "sourceDir": source_dir,
                    "sourceRef": source_ref,
                    "sourceId": source_id,
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
                    "rows": admitted_rows,
                }
            )
        elif lane == "image":
            for row in rows:
                image_raw_count += 1
                ref = _asset_ref(source_dir, row)
                collection_id = str(row.get("sourceCollectionId") or "").strip()
                if not ref:
                    image_rejects["missing_asset_ref"] += 1
                    continue
                if not collection_id:
                    image_rejects["missing_source_collection_id"] += 1
                    continue
                asset_path = root / ref
                if not asset_path.is_file():
                    image_rejects["asset_file_missing"] += 1
                    continue
                verdict = _assess_content_plan_publish_image(asset_path, ctx)
                if verdict.blocks_image_publish:
                    image_rejects["image_safety_blocked"] += 1
                    continue
                image_candidates.append(
                    {
                        "sourceId": source_id,
                        "assetRef": ref,
                        "assetSha": _asset_sha(row),
                        "collectionId": collection_id,
                    }
                )
    article_candidates.sort(key=_article_source_quality_sort_key)
    image_candidates.sort(key=lambda row: (str(row["collectionId"]), str(row["assetRef"])))
    used_refs: set[str] = set()
    used_shas: set[str] = set()
    used_collections: set[str] = set()
    used_article_sources: set[str] = set()
    picked_articles = 0
    for candidate in article_candidates:
        source_ref = str(candidate.get("sourceRef") or "")
        if source_ref in used_article_sources:
            article_rejects["source_ref_reused"] += 1
            continue
        claim = _first_publishable_asset(candidate["sourceDir"], candidate.get("rows") or [])
        ref = sha = collection_id = ""
        if claim is None:
            article_image_soft_warnings["no_publishable_source_asset"] += 1
        else:
            ref, sha, collection_id = claim
            if _claims_conflict(ref, sha, collection_id):
                article_image_soft_warnings["source_asset_reused"] += 1
                ref = sha = collection_id = ""
        used_article_sources.add(source_ref)
        if ref:
            used_refs.add(ref)
            if sha:
                used_shas.add(sha)
            if collection_id:
                used_collections.add(collection_id)
        picked_articles += 1
        if picked_articles >= required_articles:
            break
    picked_images = 0
    if image_pick_limit:
        for candidate in image_candidates:
            ref = str(candidate.get("assetRef") or "")
            sha = str(candidate.get("assetSha") or "")
            collection_id = str(candidate.get("collectionId") or "")
            if _claims_conflict(ref, sha, collection_id):
                image_rejects["source_asset_reused"] += 1
                continue
            used_refs.add(ref)
            if sha:
                used_shas.add(sha)
            if collection_id:
                used_collections.add(collection_id)
            picked_images += 1
            if picked_images >= image_pick_limit:
                break
    diagnostics = {
        "entityType": etype,
        "desiredArticleSources": desired_articles,
        "minimumRequiredArticleSources": required_articles,
        "rawArticleBaseSources": article_raw_count,
        "qualifiedArticleBaseSources": len(article_candidates),
        "pickedArticleBaseSources": picked_articles,
        "articleSourceClosure": article_source_closure,
        "desiredImageSources": desired_images,
        "minimumRequiredImageSources": required_images,
        "rawImageAssets": image_raw_count,
        "qualifiedImageAssets": len(image_candidates),
        "pickedImageSources": picked_images,
        "minimumQualityPassed": (
            (required_articles <= 0 or picked_articles >= required_articles)
            and (required_images <= 0 or picked_images >= required_images)
        ),
        "articleRejects": dict(sorted(article_rejects.items())),
        "articleImageSoftWarnings": dict(sorted(article_image_soft_warnings.items())),
        "imageRejects": dict(sorted(image_rejects.items())),
    }
    issues: list[str] = []
    if required_articles and picked_articles < required_articles:
        reject_summary = ", ".join(
            f"{key}={value}" for key, value in sorted(article_rejects.items())
        ) or "none"
        issues.append(
            f"{entity_id}: content capacity article base source shortfall "
            f"{picked_articles}<{required_articles}; raw={article_raw_count}; "
            f"qualified={len(article_candidates)}; rejects={{ {reject_summary} }}"
        )
    if required_images and picked_images < required_images:
        issues.append(
            f"{entity_id}: content capacity image source shortfall "
            f"{picked_images}<{required_images}; raw={image_raw_count}; "
            f"qualified={len(image_candidates)}"
        )
    return (not issues), issues, diagnostics
