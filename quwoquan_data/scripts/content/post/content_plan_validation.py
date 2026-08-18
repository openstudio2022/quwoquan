"""Validate immutable content-plan packets against execution contracts."""
from __future__ import annotations
from pathlib import Path
from typing import Any, Mapping
from core.article_commercial_policy import article_commercial_closure_enabled
from content.post.article.base_draft import base_draft_readiness, load_base_draft_text
from core import ops_governance as og
from content.post.object_index import BRIEF_FILE, content_object_stage_dir, load_index
from governance.creators.assignment import creator_assignment_issues, creator_assignment_required
from core.image_rules import image_caption_quality_issue
from core.io import read_json
from core.image_safety import assess_image_publish_prefilter
from core.paths import STAGE_COMPOSE, execution_root
from core.quality_gates import WRITING_INTENTS, writing_intent_issues
from core.qunar_template import qunar_article_base_block_reason
from content.post.content_plan_state import load_content_plan_packet, packet_items as _items, reject_source_ids
from content.post.content_plan import (
    ARTICLE_BASE_SOURCE_CATEGORIES, ARTICLE_BASE_SOURCE_ROLES,
    ARTICLE_MIN_BASE_DRAFT_CHARS, ARTICLE_SUPPORTING_ONLY_CATEGORIES,
    CONTENT_PLAN_SCHEMA, _article_source_category, _source_asset_ref,
    _source_asset_rows, _source_meta, content_plan_quotas_required,
)

def validate_content_plan(execution_id: str, spec: Mapping[str, Any]) -> list[str]:
    """校验 content_plan 是否满足配额与证据链。"""
    issues: list[str] = []
    packet = load_content_plan_packet(execution_id)
    if packet is None:
        return ["content_plan_packet.json missing under execution _shared/"]

    items = _items(packet)
    if not items:
        if not content_plan_quotas_required(spec):
            return issues
        return ["content_plan_packet.items is empty"]
    if str(packet.get("schema") or "").strip() != CONTENT_PLAN_SCHEMA:
        issues.append(
            f"content_plan_packet.schema must be {CONTENT_PLAN_SCHEMA!r}, "
            f"got {packet.get('schema')!r}"
        )
    from content.execution.workspace import load_execution_manifest

    try:
        execution_content_type = str(
            load_execution_manifest(execution_id).get("contentType") or ""
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        return [f"canonical execution manifest unavailable: {exc}"]

    packet_content_types = {
        str(item.get("carrier") or item.get("contentType") or "article").strip()
        for item in items
        if isinstance(item, Mapping)
    }
    if packet_content_types != {execution_content_type}:
        issues.append(
            "content_plan_packet must contain exactly the immutable execution "
            f"contentType {execution_content_type!r}, got {sorted(packet_content_types)}"
        )

    content = spec.get("content") if isinstance(spec.get("content"), Mapping) else {}
    quotas = content.get("quotas") if isinstance(content.get("quotas"), Mapping) else {}
    acceptance = spec.get("acceptance") if isinstance(spec.get("acceptance"), Mapping) else {}
    separated_research = str(content.get("modalityContract") or "") == "separated_research"
    commercial_closure = article_commercial_closure_enabled(spec)
    want_entity = int(quotas.get("entityArticles") or 0)
    want_route = int(quotas.get("routeArticles") or 0)
    per_target_articles = int(quotas.get("entityArticlesPerTarget") or 0)
    per_target_images = int(quotas.get("imageWorksPerTarget") or 0)
    per_target_videos = int(quotas.get("videoWorksPerTarget") or 0)
    strict_rights_mode = bool(
        per_target_articles
        or per_target_images
        or per_target_videos
        or int(quotas.get("entityHomepagesPerTarget") or 0)
    )
    require_creator_assignment = creator_assignment_required(spec)
    targets = [
        str(target.get("name") or "").strip()
        for target in ((spec.get("scope") or {}).get("coverageTargets") or [])
        if isinstance(target, Mapping) and str(target.get("name") or "").strip()
    ]
    # 底稿中心：每个内容对象仍必须绑定单一 source unit；per-target 配额是放量对象数合同，
    # 不得在 separated_research 下退化为"枚举全部合格 source unit"的开关。
    if per_target_articles and not commercial_closure:
        want_entity = per_target_articles * len(targets)
    want_images = per_target_images * len(targets)
    want_videos = per_target_videos * len(targets)
    required_angles = [
        str(angle).strip()
        for angle in (acceptance.get("requiredAngles") or [])
        if str(angle).strip()
    ]
    required_article_intents = [angle for angle in required_angles if angle in WRITING_INTENTS]
    requires_image_angle = any(angle in {"image", "imagePost"} for angle in required_angles)
    unknown_angles = [
        angle
        for angle in required_angles
        if angle not in WRITING_INTENTS and angle not in {"image", "imagePost"}
    ]
    if unknown_angles:
        issues.append(f"acceptance.requiredAngles contains unknown angle(s): {unknown_angles}")
    if required_article_intents and per_target_articles and len(required_article_intents) > per_target_articles:
        issues.append(
            "acceptance.requiredAngles declares "
            f"{len(required_article_intents)} article intent(s) but "
            f"content.quotas.entityArticlesPerTarget={per_target_articles}"
        )
    if requires_image_angle and per_target_images < 1:
        issues.append(
            "acceptance.requiredAngles declares image but "
            "content.quotas.imageWorksPerTarget must be >= 1"
        )

    def _item_carrier(item: Mapping[str, Any]) -> str:
        return str(item.get("carrier") or item.get("contentType") or "article")

    if want_entity or want_route or want_images or want_videos:
        entity_article_n = sum(
            1 for i in items
            if str(i.get("kind") or "") == "entity" and _item_carrier(i) == "article"
        )
        image_n = sum(1 for i in items if _item_carrier(i) == "image")
        video_n = sum(1 for i in items if _item_carrier(i) == "video")
        route_n = sum(1 for i in items if str(i.get("kind") or "") == "route")
        if want_entity and entity_article_n != want_entity:
            issues.append(
                f"entityArticles quota {want_entity} "
                f"but packet has {entity_article_n}"
            )
        if want_images and image_n != want_images:
            issues.append(
                f"imageWorks quota {want_images} "
                f"but packet has {image_n}"
            )
        if want_videos and video_n != want_videos:
            issues.append(
                f"videoWorks quota {want_videos} but packet has {video_n}"
            )
        if want_route:
            if route_n != want_route:
                issues.append(
                    f"routeArticles quota {want_route} but packet has {route_n}"
                )

    root = execution_root(execution_id)
    index = load_index(execution_id)
    item_refs = {str(item.get("ref") or "").strip() for item in items if str(item.get("ref") or "").strip()}
    extra_index_refs = sorted(set(index) - item_refs)
    if extra_index_refs:
        issues.append(
            "content_object_index contains ref(s) outside content_plan_packet: "
            + ", ".join(extra_index_refs[:20])
            + (" ..." if len(extra_index_refs) > 20 else "")
        )
    expected_briefs: set[Path] = set()
    for ref in item_refs:
        if ref not in index:
            continue
        try:
            expected_briefs.add((content_object_stage_dir(execution_id, ref, STAGE_COMPOSE) / BRIEF_FILE).resolve())
        except (KeyError, OSError, ValueError):
            continue
    actual_briefs = {
        path.resolve()
        for path in (root / "posts").glob(f"*/*/*/*/{STAGE_COMPOSE}/{BRIEF_FILE}")
        if path.is_file()
    }
    extra_briefs = sorted(actual_briefs - expected_briefs)
    if extra_briefs:
        rels = [
            path.relative_to(root).as_posix() if path.is_relative_to(root) else path.as_posix()
            for path in extra_briefs[:20]
        ]
        issues.append(
            "posts contains brief(s) outside content_plan_packet/index: "
            + ", ".join(rels)
            + (" ..." if len(extra_briefs) > 20 else "")
        )
    rejected_sources = reject_source_ids(execution_id)
    seen_refs: set[str] = set()
    per_entity: dict[str, dict[str, list[Mapping[str, Any]]]] = {
        target: {"article": [], "image": [], "video": []} for target in targets
    }
    base_source_owners: dict[str, str] = {}
    source_asset_owners: dict[str, str] = {}
    source_asset_sha_owners: dict[str, str] = {}
    source_collection_owners: dict[str, str] = {}

    def _claim_asset(owner_ref: str, asset_ref: str) -> None:
        if not asset_ref:
            return
        previous = source_asset_owners.get(asset_ref)
        if previous and previous != owner_ref:
            issues.append(
                f"item[{owner_ref}]: sourceAssetRef {asset_ref!r} reused by {previous}; "
                "same execution requires one source image asset per work"
            )
        source_asset_owners.setdefault(asset_ref, owner_ref)

    def _claim_asset_sha(owner_ref: str, asset_sha: str) -> None:
        asset_sha = asset_sha.removeprefix("sha256:").strip().lower()
        if not asset_sha:
            return
        previous = source_asset_sha_owners.get(asset_sha)
        if previous and previous != owner_ref:
            issues.append(
                f"item[{owner_ref}]: image sha256 {asset_sha[:16]!r} reused by {previous}; "
                "same execution requires one physical source image per work"
            )
        source_asset_sha_owners.setdefault(asset_sha, owner_ref)

    def _claim_collection(owner_ref: str, collection_id: str) -> None:
        if not collection_id:
            return
        previous = source_collection_owners.get(collection_id)
        if previous and previous != owner_ref:
            issues.append(
                f"item[{owner_ref}]: sourceCollectionId {collection_id!r} reused by {previous}; "
                "same execution requires one image collection per work"
            )
        source_collection_owners.setdefault(collection_id, owner_ref)

    for idx, item in enumerate(items, start=1):
        ref = str(item.get("ref") or "").strip()
        kind = str(item.get("kind") or "").strip()
        title = str(item.get("title") or "").strip()
        if not ref:
            issues.append(f"item[{idx}]: missing ref")
            continue
        if ref in seen_refs:
            issues.append(f"item[{idx}]: duplicate ref {ref!r}")
        seen_refs.add(ref)
        if kind not in ("entity", "route"):
            issues.append(f"item[{ref}]: kind must be entity|route, got {kind!r}")
        carrier = _item_carrier(item)
        raw_carrier = str(item.get("carrier") or item.get("contentType") or "article")
        if require_creator_assignment and carrier in {"article", "image", "video"}:
            for creator_issue in creator_assignment_issues(
                item,
                carrier=carrier,
                prefix=f"item[{ref}].creatorAssignment",
            ):
                issues.append(creator_issue)
        image_work_mode = carrier == "image" and (raw_carrier == "image" or separated_research)
        if not image_work_mode and not title:
            issues.append(f"item[{ref}]: missing title")
        if image_work_mode:
            if len(title) > 80:
                issues.append(f"item[{ref}]: image title exceeds 80 characters")
            if len(str(item.get("caption") or "")) > 300:
                issues.append(f"item[{ref}]: image caption exceeds 300 characters")
            entity_tags = item.get("entityTags") if isinstance(item.get("entityTags"), list) else []
            image_entity = (
                str(item.get("targetEntity") or item.get("entityName") or "").strip()
                or (str(entity_tags[0]).strip() if entity_tags else "")
            )
            caption_issue = image_caption_quality_issue(
                str(item.get("caption") or title),
                entity_id=image_entity,
                asset_id=ref,
            )
            if caption_issue:
                issues.append(f"item[{ref}]: {caption_issue}")
            if str(item.get("researchLane") or "") != "image":
                issues.append(f"item[{ref}]: image work must use researchLane=image")
            collection_id = str(item.get("sourceCollectionId") or "").strip()
            if not collection_id:
                issues.append(f"item[{ref}]: image work missing sourceCollectionId")
            else:
                _claim_collection(ref, collection_id)
            asset_refs = item.get("assetRefs") or []
            if not isinstance(asset_refs, list) or not (1 <= len(asset_refs) <= 20):
                issues.append(f"item[{ref}]: image work assetRefs must contain 1..20 items")
            elif len({str(asset) for asset in asset_refs}) != len(asset_refs):
                issues.append(f"item[{ref}]: image work assetRefs contains duplicates")
            else:
                for asset_ref in asset_refs:
                    asset_path = root / str(asset_ref)
                    if not asset_path.is_file():
                        issues.append(f"item[{ref}]: image asset not found: {asset_ref}")
                        continue
                    index_path = asset_path.parent / "index.json"
                    if not index_path.is_file():
                        issues.append(f"item[{ref}]: image asset index missing: {index_path}")
                        continue
                    try:
                        entries = read_json(index_path).get("assets") or []
                    except (OSError, ValueError, TypeError):
                        entries = []
                    entry = next(
                        (
                            row for row in entries
                            if isinstance(row, Mapping)
                            and str(row.get("fileName") or "") == asset_path.name
                        ),
                        None,
                    )
                    if not entry:
                        issues.append(f"item[{ref}]: image asset absent from index: {asset_ref}")
                    elif str(entry.get("sourceCollectionId") or "") != collection_id:
                        issues.append(
                            f"item[{ref}]: asset {asset_ref} crosses sourceCollectionId"
                        )
                    verdict = assess_image_publish_prefilter(asset_path)
                    if verdict.blocks_image_publish:
                        reason = "/".join(verdict.reasons) or verdict.status
                        issues.append(
                            f"item[{ref}]: image asset blocked by image safety gate: "
                            f"{asset_ref}:{reason}"
                        )
                    source_meta_path = asset_path.parent.parent / "meta.json"
                    if not source_meta_path.is_file():
                        issues.append(f"item[{ref}]: image asset source meta missing: {asset_ref}")
                    else:
                        try:
                            source_meta = read_json(source_meta_path)
                        except (OSError, ValueError, TypeError):
                            source_meta = {}
                        # 底稿中心 1:1：图片实体退化为多标签，不再用 entity_focus 弃稿；
                        # 单源约束由 sourceCollectionId 一致性 + researchLane=image 把关。
                        if str(source_meta.get("researchLane") or "") != "image":
                            issues.append(
                                f"item[{ref}]: image asset must come from researchLane=image: "
                                f"{asset_ref}"
                            )
                    if entry:
                        _claim_asset_sha(ref, str(entry.get("sha256") or ""))
                    _claim_asset(ref, str(asset_ref))
        elif carrier == "video":
            from content.post.content_plan_video_validation import validate_video_plan_item
            issues.extend(
                validate_video_plan_item(
                    root=root,
                    item=item,
                    ref=ref,
                    claim_asset=_claim_asset,
                    claim_asset_sha=_claim_asset_sha,
                )
            )
        elif str(item.get("researchLane") or "article") != "article":
            issues.append(f"item[{ref}]: article must use researchLane=article")
        entity_refs = item.get("entityRefs") or []
        if not isinstance(entity_refs, list) or not entity_refs:
            issues.append(f"item[{ref}]: entityRefs required")
        elif kind == "route" and len(entity_refs) < 3:
            issues.append(f"item[{ref}]: route needs entityRefs>=3")
        if kind == "entity" and isinstance(entity_refs, list):
            matched_targets = [
                target
                for target in targets
                if any(str(entity_ref).rstrip("/").endswith("/" + target) for entity_ref in entity_refs)
            ]
            if len(matched_targets) != 1:
                issues.append(
                    f"item[{ref}]: entity item must map to exactly one coverage target, got {matched_targets}"
                )
            else:
                bucket = carrier
                per_entity[matched_targets[0]][bucket].append(item)
        evidence = item.get("evidenceRefs") or []
        if not isinstance(evidence, list) or not evidence:
            issues.append(f"item[{ref}]: evidenceRefs required")
        else:
            for ev in evidence:
                ev_path = root / str(ev)
                if not ev_path.is_file():
                    issues.append(f"item[{ref}]: evidence not found: {ev}")
        # 证据准入硬门：content_plan 不得引用 source_screen_gate=reject 的来源。
        cited = [str(e) for e in (evidence if isinstance(evidence, list) else [])]
        if item.get("baseSourceRef"):
            cited.append(str(item.get("baseSourceRef")))
        for sid in sorted(rejected_sources):
            for c in cited:
                if sid and sid in c:
                    issues.append(
                        f"item[{ref}]: cites rejected source {sid!r} "
                        f"(source_screen_gate=reject 必须 fallback download_fetch，不得进入 content_plan)"
                    )
                    break
        if not str(item.get("rationale") or "").strip():
            issues.append(f"item[{ref}]: missing rationale")
        base_source_ref = str(item.get("baseSourceRef") or "").strip()
        source_use_mode = str(item.get("sourceUseMode") or "").strip()
        if carrier == "article" and strict_rights_mode and source_use_mode not in (
            "licensed_adaptation",
            "factual_reference_only",
        ):
            issues.append(f"item[{ref}]: sourceUseMode required for scaled task")
        if carrier == "article" and strict_rights_mode and not base_source_ref:
            issues.append(f"item[{ref}]: article baseSourceRef required for scaled task")
        if carrier == "article" and base_source_ref:
            source_meta = _source_meta(root, base_source_ref)
            # 底稿中心 1:1：文章实体退化为多标签，不再用单实体聚焦门弃稿——多目的地游记照样按
            # 单一底稿成稿（entityRefs/entityTags 记录其覆盖的实体集合）。entity_focus 仅在
            # "实体->主页（百科源）"路径把关，不在 article/image 内容项重复设门。
            actual_mode = str(source_meta.get("sourceUseMode") or "").strip()
            if actual_mode == "blocked":
                issues.append(f"item[{ref}]: baseSourceRef points to blocked source")
            if source_use_mode and actual_mode and source_use_mode != actual_mode:
                issues.append(
                    f"item[{ref}]: sourceUseMode {source_use_mode!r} "
                    f"does not match source meta {actual_mode!r}"
                )
            research_lane = str(source_meta.get("researchLane") or "")
            if research_lane != "article":
                issues.append(
                    f"item[{ref}]: article baseSourceRef must come from article research, got {research_lane!r}"
                )
            source_role = str(source_meta.get("sourceRole") or "").strip()
            source_id = str(source_meta.get("sourceId") or "").strip()
            if strict_rights_mode and source_role not in ARTICLE_BASE_SOURCE_ROLES:
                issues.append(
                    f"item[{ref}]: article baseSourceRef must point to sourceRole=base, "
                    f"got {source_role or '<missing>'} ({source_id or base_source_ref})"
                )
            unit_name = (root / base_source_ref).parent.name
            if strict_rights_mode and source_role == "supporting":
                issues.append(
                    f"item[{ref}]: supporting source {source_id or unit_name!r} "
                    "cannot be used as article baseSourceRef"
                )
            category = _article_source_category(source_meta)
            if strict_rights_mode and category:
                category_norm = category.lower().replace("-", "_").replace(" ", "_")
                if category_norm in ARTICLE_SUPPORTING_ONLY_CATEGORIES:
                    issues.append(
                        f"item[{ref}]: article baseSourceRef category {category!r} "
                        "is supporting-only and cannot be used as article base"
                    )
                elif category_norm not in ARTICLE_BASE_SOURCE_CATEGORIES and "攻略" not in category and "游记" not in category:
                    issues.append(
                        f"item[{ref}]: article baseSourceRef category {category!r} "
                        "is not an approved article base category"
                    )
            qunar_block = qunar_article_base_block_reason(
                source_meta,
                str(source_meta.get("entityFocusVerdict") or ""),
            )
            if strict_rights_mode and qunar_block:
                issues.append(
                    f"item[{ref}]: Qunar source {source_id or unit_name!r} "
                    f"cannot be used as article baseSourceRef: {qunar_block}"
                )
            if strict_rights_mode:
                readiness = base_draft_readiness(
                    load_base_draft_text(execution_id, base_source_ref),
                    publish_media_mode=str(item.get("publishMediaMode") or source_meta.get("publishMediaMode") or ""),
                )
                if not readiness["ready"]:
                    issues.append(
                        f"item[{ref}]: baseSourceRef usable text too short "
                        f"({readiness['effectiveChars']} < {ARTICLE_MIN_BASE_DRAFT_CHARS}; "
                        f"figures={readiness['inlineFigureCount']} captions={readiness['captionChars']})"
                    )
            reuse_policy = str(item.get("baseSourceReusePolicy") or "").strip()
            if reuse_policy:
                # 底稿中心 1:1：一源只能一篇——彻底取消 baseSourceReusePolicy /
                # multi_intent_source_bundle 逃生口，任何复用声明都不允许。
                issues.append(
                    f"item[{ref}]: baseSourceReusePolicy is not allowed; "
                    "article baseSourceRef must be one-source-one-work"
                )
            previous = base_source_owners.get(base_source_ref)
            if previous and previous != ref:
                issues.append(
                    f"item[{ref}]: baseSourceRef reused by {previous}; main evidence must be one-source-one-work"
                )
            base_source_owners.setdefault(base_source_ref, ref)
            asset_rows = _source_asset_rows(root, base_source_ref)
            row_by_asset_ref = {
                _source_asset_ref(execution_id, root, base_source_ref, asset): asset
                for asset in asset_rows
            }
            declared_asset_refs = [
                str(asset_ref).strip()
                for asset_ref in (item.get("assetRefs") or [])
                if str(asset_ref).strip()
            ]
            if declared_asset_refs and len(set(declared_asset_refs)) != len(declared_asset_refs):
                issues.append(f"item[{ref}]: article assetRefs contains duplicates")
            for atomic_issue in og.source_unit_atomicity_issues(
                base_source_ref=base_source_ref,
                asset_refs=declared_asset_refs,
                supporting_refs=item.get("sourceUnitRefs") or [],
            ):
                issues.append(f"item[{ref}]: {atomic_issue}")
                og.append_conflict(
                    execution_id,
                    conflict_type="source_unit_atomicity",
                    subject=str(base_source_ref),
                    refs=[str(ref)],
                    reason=atomic_issue,
                )
            for asset_ref in declared_asset_refs:
                asset_path = root / asset_ref
                source_dir = (root / base_source_ref).parent
                if not asset_path.is_file():
                    issues.append(f"item[{ref}]: article asset not found: {asset_ref}")
                    continue
                try:
                    asset_path.relative_to(source_dir / "assets")
                except ValueError:
                    issues.append(
                        f"item[{ref}]: article assetRefs must belong to baseSourceRef assets: "
                        f"{asset_ref}"
                    )
                    continue
                asset = row_by_asset_ref.get(asset_ref)
                if not isinstance(asset, Mapping):
                    issues.append(f"item[{ref}]: article asset metadata missing: {asset_ref}")
                    continue
                missing_asset_fields = [
                    field
                    for field in ("license", "credit", "sourceUrl", "termsUrl", "usageScope")
                    if not str(asset.get(field) or "").strip()
                ]
                if missing_asset_fields:
                    issues.append(
                        f"item[{ref}]: baseSourceRef asset {asset.get('fileName') or '?'} "
                        f"missing rights fields {missing_asset_fields}"
                    )
                asset_row = row_by_asset_ref.get(asset_ref)
                if not asset_row:
                    issues.append(f"item[{ref}]: article asset absent from base source index: {asset_ref}")
                    continue
                verdict = assess_image_publish_prefilter(asset_path)
                if verdict.blocks_image_publish:
                    reason = "/".join(verdict.reasons) or verdict.status
                    issues.append(
                        f"item[{ref}]: article asset blocked by image safety gate: "
                        f"{asset_ref}:{reason}"
                    )
                _claim_asset(ref, asset_ref)
                _claim_asset_sha(ref, str(asset_row.get("sha256") or ""))
                _claim_collection(ref, str(asset_row.get("sourceCollectionId") or ""))
        if carrier == "article":
            for msg in writing_intent_issues(item.get("writingIntent")):
                issues.append(f"item[{ref}]: {msg}")
        if ref not in index:
            issues.append(f"item[{ref}]: not registered in content_object_index")
        else:
            brief_path = content_object_stage_dir(execution_id, ref, STAGE_COMPOSE) / BRIEF_FILE
            if not brief_path.is_file():
                issues.append(f"item[{ref}]: missing 3.compose/brief.json")

    from content.post.content_plan_quota_validation import validate_per_target_quotas
    issues.extend(validate_per_target_quotas(
        per_entity=per_entity,
        per_target_articles=per_target_articles,
        per_target_images=per_target_images,
        per_target_videos=per_target_videos,
        commercial_closure=commercial_closure,
        separated_research=separated_research,
        required_article_intents=required_article_intents,
    ))

    return issues
