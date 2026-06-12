"""Materialize approved compose results into post packages."""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from pathlib import Path
import shutil
from typing import Any

from _common.article_package import (
    MARKDOWN_VERSION,
    build_gallery_markdown,
    compute_document_sha256,
    copy_asset_files,
)
from _common.batch_asset_registry import allocate_post_asset_id, load_batch_asset_registry
from _common.batch_manifest import load_batch_manifest
from _common.paths import DATA_ROOT, RUNTIME_ROOT, batch_root, relative_batch_ref
from _common.io import write_json
from _common.draft_io import read_draft_meta, read_writing_pack
from _common.provenance import build_provenance
from _common.intersection_signal import build_intersection_hints
from _common.entity_annotation import annotate_inline, normalize_link_ref


def _resolve_entity_download_dir(
    task_id: str,
    batch_id: str,
    entity_refs: list[str],
) -> Path | None:
    from _common.source_unit import find_entity_object_dirs, iter_source_units

    for ref in entity_refs:
        name = ref.strip("/").split("/")[-1]
        if not name:
            continue
        for obj in find_entity_object_dirs(task_id, batch_id, name):
            for unit in iter_source_units(obj):
                assets_dir = unit / "assets"
                if assets_dir.is_dir():
                    return assets_dir
    return None


def _relativize_ref(value: str, task_id: str, batch_id: str) -> str:
    """batch 内绝对路径 → 相对 batch 根；batch 外或已相对则原样返回（禁绝对路径进发布契约）。"""

    s = str(value or "")
    if not s:
        return s
    base = batch_root(task_id, batch_id).resolve()
    batch_prefix = f"batches/{batch_id}/"
    if s.startswith(batch_prefix):
        return s[len(batch_prefix) :]
    marker = f"/batches/{batch_id}/"
    normalized_full = s.replace("\\", "/")
    if marker in normalized_full:
        return normalized_full.split(marker, 1)[1]
    p = Path(s)
    if not p.is_absolute():
        runtime_candidates = []
        normalized = s.lstrip("./")
        if normalized.startswith("quwoquan_data/runtime/"):
            runtime_candidates.append(DATA_ROOT.parent / normalized)
        runtime_candidates.append(RUNTIME_ROOT / normalized)
        for candidate in runtime_candidates:
            try:
                candidate_resolved = candidate.resolve()
                candidate_resolved.relative_to(base)
            except (ValueError, OSError):
                continue
            return relative_batch_ref(candidate_resolved, task_id, batch_id)
        return s
    try:
        p.resolve().relative_to(base)
    except (ValueError, OSError):
        return s
    return relative_batch_ref(p, task_id, batch_id)


def _publication_condition_context(raw: object) -> object:
    """发布契约字段投影：保留 entityProfile，同时提供顶层 region/season 授权字段。"""
    if not isinstance(raw, dict):
        return raw
    context = dict(raw)
    top_regions = [str(v) for v in (context.get("regions") or []) if v]
    top_seasons = [str(v) for v in (context.get("seasons") or []) if v]
    if top_regions and not context.get("region"):
        context["region"] = top_regions[0]
    if top_seasons and not context.get("season"):
        context["season"] = top_seasons[0]
    profile = context.get("entityProfile")
    if isinstance(profile, dict):
        regions = [str(v) for v in (profile.get("regions") or []) if v]
        seasons = [str(v) for v in (profile.get("seasons") or []) if v]
        if regions and not context.get("region"):
            context["region"] = regions[0]
        if seasons and not context.get("season"):
            context["season"] = seasons[0]
    return context


def _annotate_manifest_entities(article_md: str, entity_refs: list[str]) -> str:
    """Materialized posts must keep article links and manifest.entityRefs closed."""
    dictionary: dict[str, str] = {}
    for raw_ref in entity_refs:
        ref = normalize_link_ref(str(raw_ref))
        name = ref.strip("/").split("/")[-1] if ref else ""
        if name:
            dictionary[name] = ref
    if not dictionary:
        return article_md
    annotated_article, _ = annotate_inline(article_md, dictionary)
    return annotated_article


def _publication_story_spine(compose_payload: dict) -> dict | list:
    """发布包只保留运行需要的叙事摘要，质量证据留在 provenance/review。"""
    raw = (
        compose_payload.get("storySpine")
        or compose_payload.get("progression")
        or compose_payload.get("sectionIntents")
        or []
    )
    if not isinstance(raw, dict):
        return raw
    return {
        key: raw[key]
        for key in (
            "primaryEntity",
            "routeEntities",
            "beats",
            "sourceNote",
            "relatedTopics",
            "mustIncludeFacts",
        )
        if key in raw
    }


def _manifest_time_fact(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    text = str(value or "").strip()
    return text or None


def materialize_posts(task_id: str, batch_id: str, content_type: str) -> list[Path]:
    """把 approved+agent 的 compose/review 成品落到**内容对象根**（§2.4）。

    成品（article.md/manifest.json/assets/ + _object.json）与过程
    阶段（2.quality/3.compose/4.draft/5.review）同处对象根 `posts/{type}/{angle}/{title}/{seq}/`；
    对象坐标（angle/title/seq）以 `_shared/content_object_index.json` 路由为唯一真相，不再自算序号。
    """
    from _common import content_object
    from _common.stage_reports import iter_stage_envelopes, read_stage_envelope

    materialized: list[Path] = []

    review_envelopes = iter_stage_envelopes(task_id, batch_id, "produce", "review")
    if not review_envelopes:
        return materialized

    for ref, review in review_envelopes:
        payload = review.get("payload", review)
        if payload.get("decision") != "approved":
            continue

        coords = content_object.content_coords(task_id, batch_id, ref)
        if not coords or coords.get("contentType") != content_type:
            continue

        compose = read_stage_envelope(task_id, batch_id, "produce", "compose", ref)
        if compose is None:
            continue

        compose_payload = compose.get("payload", compose)

        # 出处门：只有 generator=agent 的正文允许进入交付面，脚本/占位一律拒绝落地。
        if str(compose_payload.get("generator") or "") != "agent":
            continue

        article_md = compose_payload.get("articleMarkdown", "")
        title = compose_payload.get("title") or ref
        template = compose_payload.get("template") or "journal"
        # 对象坐标（angle/title/seq）= 路由真相，与 promote/publish 发布面同名。
        angle = str(coords.get("angle") or "")
        publish_title = str(coords.get("title") or compose_payload.get("publishTitle") or title)
        seq = int(coords.get("seq") or 1)
        post_dir = content_object.content_object_dir(task_id, batch_id, ref)
        post_dir.mkdir(parents=True, exist_ok=True)
        assets_dir = post_dir / "assets"
        # 成品 assets 全量重建（仅清成品，过程阶段证据保留）。
        if assets_dir.exists():
            shutil.rmtree(assets_dir)
        entity_refs = compose_payload.get("entityRefs", [])
        tag_refs = compose_payload.get("tagRefs", [])
        source_urls = compose_payload.get("sourceUrls", [])
        source_paths = compose_payload.get("sourcePaths", [])
        if isinstance(entity_refs, list):
            article_md = _annotate_manifest_entities(article_md, entity_refs)

        raw_assets = compose_payload.get("assets") or []
        if not raw_assets and compose_payload.get("coverAssetRef"):
            manifest = load_batch_manifest(task_id, batch_id)
            global_batch_seq = int(manifest.get("globalBatchSeq") or 0)
            if global_batch_seq <= 0:
                raise RuntimeError(f"missing globalBatchSeq for task={task_id} batch={batch_id}")
            asset_registry = load_batch_asset_registry(task_id, batch_id, global_batch_seq)
            first_entity = ""
            if isinstance(entity_refs, list) and entity_refs:
                first_entity = str(entity_refs[0]).strip("/").split("/")[-1]
            cover_id = allocate_post_asset_id(
                entity_name=first_entity or ref,
                role="cover",
                ref=ref,
                global_batch_seq=global_batch_seq,
                registry=asset_registry,
            )
            raw_assets = [
                {
                    "assetId": cover_id,
                    "fileName": f"{cover_id}.jpg",
                    "caption": "封面",
                    "kind": "image",
                    "scope": "cold_start",
                    "objectKey": compose_payload.get("coverObjectKey", ""),
                }
            ]

        download_images = _resolve_entity_download_dir(task_id, batch_id, entity_refs)
        assets = copy_asset_files(raw_assets, assets_dir, download_images)

        gallery_path = post_dir / "gallery.md"
        if str(compose_payload.get("carrier") or "article") == "gallery" and assets:
            gallery_md = compose_payload.get("galleryMarkdown") or build_gallery_markdown(title, assets)
            gallery_path.write_text(gallery_md, encoding="utf-8")
        elif gallery_path.exists():
            gallery_path.unlink()

        if article_md and "articleMarkdownVersion" not in article_md[:200]:
            if not article_md.lstrip().startswith("---"):
                front = (
                    f"---\n"
                    f"title: {title}\n"
                    f"template: {template}\n"
                    f"articleMarkdownVersion: {MARKDOWN_VERSION}\n"
                )
                if assets:
                    front += f"coverImage: asset://{assets[0]['assetId']}\n"
                front += "---\n\n"
                article_md = front + article_md

        (post_dir / "article.md").write_text(article_md, encoding="utf-8")

        render_profile = compose_payload.get("articleRenderProfile") or {
            "template": template,
            "fontPreset": "clean",
            "layoutPolicy": {
                "wrapDowngrade": "compactWidthToFullWidth",
                "galleryDowngrade": "singleColumn",
            },
        }
        document_sha256 = compute_document_sha256(article_md)
        # 最小发布契约：只保留发布/渲染/出处必需字段。
        manifest = {
            "schemaVersion": "quwoquan_data.post_manifest",
            "topicId": ref,
            "contentType": content_type,
            "entityRefs": entity_refs,
            "tagRefs": tag_refs,
            "conditionContext": _publication_condition_context(compose_payload.get("conditionContext")),
            "sourceUrls": source_urls,
            "assets": [
                {
                    "assetId": a["assetId"],
                    "fileName": a.get("fileName", ""),
                    "caption": a.get("caption", ""),
                    "imageLayout": a.get("imageLayout", "fullWidth"),
                    "sha256": a.get("sha256", ""),
                    # 资产证据链（相对 batch 根）：source 原图 + 原文，禁绝对路径。
                    "sourceAssetRef": _relativize_ref(
                        a.get("sourceAssetRef") or a.get("sourcePath") or "", task_id, batch_id
                    ),
                    "sourceRef": _relativize_ref(a.get("sourceRef") or "", task_id, batch_id),
                }
                for a in assets
            ],
            "template": template,
            "carrier": compose_payload.get("carrier", "article"),
            "generator": compose_payload.get("generator", "agent"),
            "generatorModel": compose_payload.get("generatorModel"),
            "citedSourceRefs": [
                _relativize_ref(r, task_id, batch_id)
                for r in (compose_payload.get("citedSourceRefs") or source_paths)
            ],
            "reviewDecision": "approved",
            "articleMarkdownVersion": MARKDOWN_VERSION,
            "articleRenderProfile": render_profile,
            "publishLayout": compose_payload.get("publishLayout", "travel"),
            "publishAngle": angle,
            "publishTitle": publish_title,
            "publishSeq": seq,
            # 叙事骨架：发布门 storySpine 真相源。优先 compose 显式 storySpine，
            # 回退到 progression（叙事主线）/ sectionIntents（章节意图），保证发布契约闭合。
            "storySpine": _publication_story_spine(compose_payload),
            # 溯源：内容来自哪个任务/批次（task trace/hydrate、推荐归因消费）
            "sourceTaskId": task_id,
            "sourceBatchId": batch_id,
        }
        created_at = _manifest_time_fact(compose_payload, "createdAt")
        updated_at = _manifest_time_fact(compose_payload, "updatedAt")
        if created_at:
            manifest["createdAt"] = created_at
        if updated_at:
            manifest["updatedAt"] = updated_at
        # 「明」：预生成内容侧交集锚点（对齐 IntersectionReason 闭集口径），runtime 据此 + 用户补全文案。
        manifest["intersectionHints"] = build_intersection_hints(manifest)
        write_json(post_dir / "manifest.json", manifest)
        from verify.verify_content_quality import asset_closure_issues

        closure_issues = asset_closure_issues(post_dir, manifest)
        if closure_issues:
            raise RuntimeError("post asset closure failed:\n  - " + "\n  - ".join(closure_issues))

        # 结构化出处：只保留发布追责必需字段，取代分散的 produce_trace.json。
        # 出处路径全部相对 batch 根（禁绝对路径进发布契约）。
        provenance_compose = {
            **compose_payload,
            "sourcePaths": [_relativize_ref(p, task_id, batch_id) for p in source_paths],
            "citedSourceRefs": manifest["citedSourceRefs"],
            "articleMarkdownDigest": document_sha256,
        }
        draft_meta = read_draft_meta(task_id, batch_id, ref) or {}
        draft_meta = {
            **draft_meta,
            "citedSourcePaths": [
                _relativize_ref(p, task_id, batch_id)
                for p in (draft_meta.get("citedSourcePaths") or [])
            ],
        }
        provenance = build_provenance(
            ref,
            writing_pack=read_writing_pack(task_id, batch_id, ref),
            draft_meta=draft_meta,
            review_payload=payload,
            compose_payload=provenance_compose,
            manifest=manifest,
        )
        review_dir = post_dir / "5.review"
        review_dir.mkdir(parents=True, exist_ok=True)
        write_json(review_dir / "provenance.json", provenance)

        # 对象索引：publish 目标相对路径 + 成品相对路径 + 各阶段状态（§14.3）。
        content_object.write_content_object_index(task_id, batch_id, ref)

        materialized.append(post_dir)

    return materialized
