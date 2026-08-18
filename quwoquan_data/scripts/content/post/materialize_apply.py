"""Materialize approved post objects from reviewed compose results."""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from core.article_package import (
    MARKDOWN_DIALECT,
    build_markdown_frontmatter,
    compute_asset_manifest_sha256,
    compute_document_sha256,
    copy_asset_files,
)
from core.control_types import ContentGenerator
from core.intersection_signal import build_intersection_hints
from core.io import write_json
from core.post_evidence_chain import build_finalization_report
from core.provenance import build_provenance

from content.execution.asset_registry import (
    allocate_post_asset_id,
    load_execution_asset_registry,
)
from content.execution.runtime_contract import stage_execution_context
from content.execution.runtime_state import load_execution_runtime_state
from content.post.article.draft_io import (
    read_draft_article,
    read_draft_meta,
    read_writing_pack,
)
from content.post.article.materialize_article import _resolve_materialized_article
from content.post.materialize_contract import (
    _ensure_published_manifest_mentions,
    _image_source_contract,
    _materialized_alignment_evidence,
    _materialized_asset_refs,
    _materialized_source_refs_snapshot,
    _normalized_runtime_entity_refs,
    _publication_story_spine,
    _relativize_ref,
    _resolve_entity_download_dir,
    _resolve_semantic_mentions,
)
from content.post.materialize_timestamps import materialized_manifest_times
from content.post.review_evidence import write_review_evidence
from content.post.source_attribution import source_unit_attribution


def materialize_posts(
    execution_id: str,
    content_type: str,
    *,
    refs: list[str] | set[str] | tuple[str, ...] | None = None,
) -> list[Path]:
    """把 approved+agent 的 compose/review 成品落到**内容对象根**（§2.4）。

    成品（article.md/manifest.json/assets/ + _object.json）与过程
    阶段（2.quality/3.compose/4.draft/5.review）同处对象根 `posts/{type}/{angle}/{title}/{seq}/`；
    对象坐标（angle/title/seq）以 `_shared/content_object_index.json` 路由为唯一真相，不再自算序号。
    """
    from content.execution.stage_reports import (
        iter_stage_envelopes,
        read_stage_envelope,
    )
    from content.post import object_index as content_object

    materialized: list[Path] = []
    execution_state = load_execution_runtime_state(execution_id)

    allowed_refs = {str(ref) for ref in refs or []}
    review_envelopes = iter_stage_envelopes(execution_id, "post", "review")
    if not review_envelopes:
        return materialized

    for ref, review in review_envelopes:
        if allowed_refs and ref not in allowed_refs:
            continue
        payload = review.get("payload", review)
        if payload.get("decision") != "approved":
            continue

        coords = content_object.content_coords(execution_id, ref)
        if not coords or coords.get("contentType") != content_type:
            continue

        compose = read_stage_envelope(execution_id, "post", "compose", ref)
        if compose is None:
            continue

        compose_payload = compose.get("payload", compose)

        if content_type == "video":
            from content.post.video.materialize import materialize_video_post

            execution_sequence = (
                execution_state.execution_sequence if execution_state is not None else 0
            )
            if execution_sequence <= 0:
                raise RuntimeError(f"missing executionSequence for execution={execution_id}")
            post_dir = content_object.content_object_dir(execution_id, ref)
            try:
                materialize_video_post(
                    execution_id=execution_id,
                    ref=ref,
                    post_dir=post_dir,
                    compose_payload=compose_payload,
                    review_payload=payload,
                    execution_sequence=execution_sequence,
                )
            except ValueError as exc:
                # Object-level delivery shortfalls (e.g. sourced clip shorter than
                # policy minimum) must typed-discard the ref, not abort the batch.
                review_dir = post_dir / "5.review"
                review_dir.mkdir(parents=True, exist_ok=True)
                write_json(
                    review_dir / "materialize_failure.json",
                    {
                        "schema": "quwoquan_data.video_materialize_failure",
                        "ref": ref,
                        "code": "DATA.MEDIA.PUBLISHABLE_SHORTFALL",
                        "message": str(exc),
                    },
                )
                continue
            content_object.write_content_object_index(execution_id, ref)
            materialized.append(post_dir)
            continue

        is_image = content_type == "image"
        # 出处门：文章正文必须由 generator=agent 创作；图片作品不生成正文，
        # 只接受结构化 sourceCollection/assets/caption 证据包。
        generator = str(compose_payload.get("generator") or "")
        if (
            is_image
            and generator != ContentGenerator.IMAGE_EVIDENCE_PACK.value
        ) or (
            not is_image and generator != ContentGenerator.AGENT.value
        ):
            continue

        writing_pack = read_writing_pack(execution_id, ref) or {}
        allowed_contact_numbers = [
            str(value).strip()
            for value in writing_pack.get("allowedContactNumbers") or []
            if str(value).strip()
        ]
        raw_title = compose_payload.get("title")
        title = str(raw_title if raw_title is not None else ("" if is_image else ref))
        caption = str(compose_payload.get("caption") or compose_payload.get("summary") or "")
        if is_image and len(title) > 80:
            raise RuntimeError(f"{ref}: image title exceeds 80 characters")
        if is_image and len(caption) > 300:
            raise RuntimeError(f"{ref}: image caption exceeds 300 characters")
        template = compose_payload.get("template") or "journal"
        # 对象坐标（angle/title/seq）= 路由真相，与 promote/publish 发布面同名。
        angle = str(coords.get("angle") or "")
        publish_title = (
            str(compose_payload.get("publishTitle") or title or "")
            if is_image
            else str(coords.get("title") or compose_payload.get("publishTitle") or title)
        )
        seq = int(coords.get("seq") or 1)
        post_dir = content_object.content_object_dir(execution_id, ref)
        from core.paths import ensure_object_stages

        ensure_object_stages(post_dir)
        post_dir.mkdir(parents=True, exist_ok=True)
        assets_dir = post_dir / "assets"
        # 成品 assets 全量重建（仅清成品，过程阶段证据保留）。
        if assets_dir.exists():
            shutil.rmtree(assets_dir)
        entity_refs = compose_payload.get("entityRefs", [])
        normalized_entity_refs = (
            _normalized_runtime_entity_refs(entity_refs)
            if isinstance(entity_refs, list)
            else []
        )
        tag_refs = compose_payload.get("tagRefs", [])
        source_urls = compose_payload.get("sourceUrls", [])
        source_paths = compose_payload.get("sourcePaths", [])
        semantic_mentions = _ensure_published_manifest_mentions(
            _resolve_semantic_mentions(execution_id, ref, compose_payload),
            ref,
            entity_refs=entity_refs if isinstance(entity_refs, list) else [],
            tag_refs=tag_refs if isinstance(tag_refs, list) else [],
        )
        article_md = ""
        normalization_actions: list[str] = []
        if not is_image:
            article_md, normalization_actions = _resolve_materialized_article(
                execution_id,
                ref,
                compose_payload=compose_payload,
                entity_refs=entity_refs if isinstance(entity_refs, list) else [],
            )

        raw_assets = compose_payload.get("assets") or []
        if not raw_assets and compose_payload.get("coverAssetRef"):
            execution_sequence = (
                execution_state.execution_sequence if execution_state is not None else 0
            )
            if execution_sequence <= 0:
                raise RuntimeError(f"missing executionSequence for execution={execution_id}")
            asset_registry = load_execution_asset_registry(execution_id, execution_sequence)
            first_entity = ""
            if isinstance(entity_refs, list) and entity_refs:
                first_entity = str(entity_refs[0]).strip("/").split("/")[-1]
            cover_id = allocate_post_asset_id(
                entity_name=first_entity or ref,
                role="cover",
                ref=ref,
                execution_sequence=execution_sequence,
                registry=asset_registry,
                # 冷启动封面图注：文章标题优先（与下方 raw_assets caption 同源语义）。
                caption=str(title or ""),
                ordinal=1,
            )
            raw_assets = [
                {
                    "assetId": cover_id,
                    "fileName": f"{cover_id}.jpg",
                    # 冷启动封面 caption 以原文为基础：实体名 > 文章标题，禁止「封面」占位。
                    "caption": str(first_entity or title or "").strip(),
                    "kind": "image",
                    "scope": "cold_start",
                    "objectKey": compose_payload.get("coverObjectKey", ""),
                }
            ]

        if is_image and not 1 <= len(raw_assets) <= 20:
            raise RuntimeError(f"{ref}: image work requires 1..20 assets, got {len(raw_assets)}")
        image_source = (
            _image_source_contract(
                compose_payload,
                raw_assets,
                ref=ref,
                vertical=str(compose_payload.get("vertical") or ""),
            )
            if is_image
            else {}
        )

        download_images = _resolve_entity_download_dir(execution_id, entity_refs)
        assets = copy_asset_files(raw_assets, assets_dir, download_images)

        article_path = post_dir / "article.md"
        gallery_path = post_dir / "gallery.md"
        if gallery_path.exists():
            gallery_path.unlink()
        if is_image:
            if article_path.exists():
                article_path.unlink()
        else:
            had_frontmatter = article_md.lstrip().startswith("---")
            if article_md and "markdownDialect" not in article_md[:200]:
                if not article_md.lstrip().startswith("---"):
                    frontmatter = {
                        "title": title,
                        "template": template,
                        "markdownDialect": MARKDOWN_DIALECT,
                    }
                    if assets:
                        frontmatter["coverImage"] = f"asset://{assets[0]['assetId']}"
                    article_md = build_markdown_frontmatter(frontmatter) + article_md
            if not had_frontmatter and article_md.lstrip().startswith("---"):
                normalization_actions.append("frontmatter_injected")
            article_path.write_text(article_md, encoding="utf-8")

        render_profile = compose_payload.get("articleRenderProfile") or {
            "template": template,
            "fontPreset": "clean",
            "layoutPolicy": {
                "wrapDowngrade": "compactWidthToFullWidth",
                "galleryDowngrade": "singleColumn",
            },
        }
        creator_payload = compose_payload.get("creator") if isinstance(compose_payload.get("creator"), dict) else {}
        # 最小发布契约：只保留发布/渲染/出处必需字段。
        manifest = {
            "schema": "quwoquan_data.post_manifest",
            "topicId": ref,
            # Freeze pool identity before review. Delivery may reserve and
            # consume it later, but it may never allocate a new identity after
            # semantic approval.
            "contentId": "qwq_data_"
            + hashlib.sha256(f"{execution_id}|{ref}".encode()).hexdigest()[:24],
            "version": 1,
            "contentType": content_type,
            "contentIdentity": "work",
            "vertical": compose_payload.get("vertical"),
            "entityRefs": entity_refs,
            "normalizedEntityRefs": normalized_entity_refs,
            "tagRefs": tag_refs,
            "semanticMentions": semantic_mentions,
            "publishMediaMode": compose_payload.get("publishMediaMode"),
            "authorId": compose_payload.get("authorId") or creator_payload.get("authorId"),
            "creatorProfileId": compose_payload.get("creatorProfileId") or creator_payload.get("creatorProfileId"),
            "creatorArchetype": compose_payload.get("creatorArchetype") or creator_payload.get("creatorArchetype"),
            "creatorProfileDigest": compose_payload.get("creatorProfileDigest")
            or creator_payload.get("creatorProfileDigest"),
            "creatorProfileVersion": compose_payload.get("creatorProfileVersion")
            or creator_payload.get("creatorProfileVersion")
            or compose_payload.get("creatorProfileDigest")
            or creator_payload.get("creatorProfileDigest"),
            "creatorDisclosure": compose_payload.get("creatorDisclosure") or creator_payload.get("creatorDisclosure"),
            "experienceClaimMode": compose_payload.get("experienceClaimMode")
            or creator_payload.get("experienceClaimMode"),
            "authorQualitySignals": compose_payload.get("authorQualitySignals")
            or creator_payload.get("authorQualitySignals"),
            "sourceUrls": source_urls,
            "assets": [
                {
                    "assetId": a["assetId"],
                    "fileName": a.get("fileName", ""),
                    "caption": a.get("caption", ""),
                    "imageLayout": a.get("imageLayout", "fullWidth"),
                    "role": (
                        "cover"
                        if str(a.get("role") or "") == "cover"
                        else "detail"
                    ),
                    "sha256": a.get("sha256", ""),
                    # 资产证据链（相对 batch 根）：source 原图 + 原文，禁绝对路径。
                    "sourceAssetRef": _materialized_asset_refs(a, execution_id=execution_id)[1],
                    "sourceRef": _materialized_asset_refs(a, execution_id=execution_id)[0],
                    "alignmentEvidence": _materialized_alignment_evidence(a),
                    "sourceCollectionId": a.get("sourceCollectionId", ""),
                    "creator": a.get("creator", ""),
        "sourceAuthor": a.get("sourceAuthor", ""),
                    "collectionPageUrl": a.get("collectionPageUrl", ""),
                    "license": a.get("license", ""),
                    "termsUrl": a.get("termsUrl", ""),
                    "licenseSnapshot": a.get("licenseSnapshot", ""),
                    "authorizationProof": a.get("authorizationProof", ""),
                    "rightsAuditStatus": a.get("rightsAuditStatus", ""),
                    "rightsAuditIssues": a.get("rightsAuditIssues", []),
        "authorizationBasis": a.get("authorizationBasis", ""),
                    "usageScope": a.get("usageScope", ""),
        "pinUrl": a.get("pinUrl", ""),
        "discoveryUrl": a.get("discoveryUrl", ""),
        "originalAssetUrl": a.get("originalAssetUrl", ""),
        "repostAttribution": a.get("repostAttribution", ""),
        "watermarkScan": a.get("watermarkScan", ""),
        "ocrScan": a.get("ocrScan", ""),
        "collectedAt": a.get("collectedAt", ""),
                }
                for a in assets
            ],
            "template": template,
            "carrier": "image" if is_image else compose_payload.get("carrier", "article"),
            "generator": compose_payload.get(
                "generator", ContentGenerator.AGENT.value
            ),
            "generatorModel": compose_payload.get("generatorModel"),
            "citedSourceRefs": [
                _relativize_ref(r, execution_id)
                for r in (compose_payload.get("citedSourceRefs") or source_paths)
            ],
            "reviewDecision": "approved",
            "publishLayout": compose_payload.get("publishLayout", "travel"),
            "publishAngle": angle,
            **(
                {"writingIntent": compose_payload["writingIntent"]}
                if compose_payload.get("writingIntent")
                else {}
            ),
            **(
                {"articleCategory": compose_payload["articleCategory"]}
                if compose_payload.get("articleCategory")
                else {}
            ),
            "publishTitle": publish_title,
            "publishSeq": seq,
            # 叙事骨架：发布门 storySpine 真相源。优先 compose 显式 storySpine，
            # 回退到 progression（叙事主线）/ sectionIntents（章节意图），保证发布契约闭合。
            "storySpine": _publication_story_spine(compose_payload),
            # 溯源：内容来自哪个 execution，供 trace/hydrate 与推荐归因消费。
            "executionId": execution_id,
        }
        attribution = source_unit_attribution(
            execution_id,
            content_type,
            compose_payload=compose_payload,
            assets=assets,
        )
        if attribution is not None:
            manifest["sourceAttribution"] = attribution
        if is_image:
            manifest.update(
                {
                    "title": title,
                    "caption": caption,
                    **image_source,
                }
            )
        else:
            manifest.update(
                {
                    "markdownDialect": MARKDOWN_DIALECT,
                    "articleRenderProfile": render_profile,
                    "allowedContactNumbers": allowed_contact_numbers,
                }
            )
        created_at, updated_at = materialized_manifest_times(
            compose_payload,
            payload,
            execution_state,
        )
        manifest["createdAt"] = created_at
        manifest["updatedAt"] = updated_at
        for optional_creator_key in (
            "authorId",
            "creatorProfileId",
            "creatorArchetype",
            "creatorProfileDigest",
            "creatorProfileVersion",
            "creatorDisclosure",
            "experienceClaimMode",
            "authorQualitySignals",
        ):
            if manifest.get(optional_creator_key) in (None, "", {}):
                manifest.pop(optional_creator_key, None)
        from content.execution.planning.rewrite import apply_execution_rewrite_identity

        manifest = apply_execution_rewrite_identity(
            manifest,
            execution_id=execution_id,
            ref=ref,
        )
        # 「明」：预生成内容侧交集锚点（对齐 IntersectionReason 闭集口径），runtime 据此 + 用户补全文案。
        manifest["intersectionHints"] = build_intersection_hints(manifest)
        write_json(post_dir / "manifest.json", manifest)
        from verify.verify_content_quality import asset_closure_issues

        closure_issues = asset_closure_issues(post_dir, manifest)
        if closure_issues:
            raise RuntimeError("post asset closure failed:\n  - " + "\n  - ".join(closure_issues))

        # 结构化出处：只保留发布追责必需字段，取代分散的 post_trace.json。
        # 出处路径全部相对 batch 根（禁绝对路径进发布契约）。
        final_digest = (
            compute_asset_manifest_sha256(manifest["assets"])
            if is_image
            else compute_document_sha256(article_md)
        )
        provenance_compose = {
            **compose_payload,
            **image_source,
            "sourcePaths": [_relativize_ref(p, execution_id) for p in source_paths],
            "citedSourceRefs": manifest["citedSourceRefs"],
            (
                "assetManifestDigest" if is_image else "articleMarkdownDigest"
            ): final_digest,
        }
        draft_meta = read_draft_meta(execution_id, ref) or {}
        draft_meta = {
            **draft_meta,
            "citedSourcePaths": [
                _relativize_ref(p, execution_id)
                for p in (draft_meta.get("citedSourcePaths") or [])
            ],
        }
        provenance = build_provenance(
            ref,
            writing_pack=writing_pack,
            draft_meta=draft_meta,
            review_payload=payload,
            compose_payload=provenance_compose,
            manifest=manifest,
        )
        review_dir = post_dir / "5.review"
        review_dir.mkdir(parents=True, exist_ok=True)
        write_json(review_dir / "provenance.json", provenance)
        # 所有成品（含图片作品）都必须自持 `1.download/source_refs.json`，
        # 否则图片作品永远缺 1.download，阶段树不完整、无法回查来源。
        download_dir = post_dir / "1.download"
        download_dir.mkdir(parents=True, exist_ok=True)
        # 单底稿零参考：成品来源索引只认唯一底稿来源单元。
        # 文章用 writing_pack.baseSourceRef；图片作品的底稿来源单元 = 资产所属同一 source unit。
        if is_image:
            image_base_ref = next(
                (
                    str(asset.get("sourceRef") or "")
                    for asset in manifest["assets"]
                    if str(asset.get("sourceRef") or "")
                ),
                "",
            )
            source_refs_base = image_base_ref
        else:
            source_refs_base = str(writing_pack.get("baseSourceRef") or "")
        write_json(
            download_dir / "source_refs.json",
            _materialized_source_refs_snapshot(
                execution_id,
                base_source_ref=source_refs_base,
                is_image=is_image,
            ),
        )
        if not is_image:
            write_json(
                review_dir / "finalization_report.json",
                build_finalization_report(
                    ref,
                    draft_markdown=str(read_draft_article(execution_id, ref) or ""),
                    final_markdown=article_md,
                    normalization_actions=normalization_actions,
                    article_source="4.draft/draft.article.md",
                    compose_snapshot_markdown=compose_payload.get("articleMarkdown"),
                ),
            )
        else:
            write_json(
                review_dir / "finalization_report.json",
                build_finalization_report(
                    ref,
                    draft_markdown="",
                    final_markdown="",
                    normalization_actions=["asset_only_finalization"],
                    article_source="4.draft/draft_meta.json",
                ),
            )

        write_review_evidence(
            review_dir,
            execution=stage_execution_context(execution_id),
            object_ref=ref,
            review_payload=payload,
        )

        # 对象索引：publish 目标相对路径 + 成品相对路径 + 各阶段状态（§14.3）。
        content_object.write_content_object_index(execution_id, ref)

        materialized.append(post_dir)

    return materialized
